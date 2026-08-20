"""Diagnosis V2.2 evaluator correction and bounded adversarial controls."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from springfix_agent.benchmark.diagnosis_v2 import load_diagnosis_v2_specs
from springfix_agent.benchmark.diagnosis_v22 import (
    DIAGNOSIS_V22_SCHEMA_VERSION,
    DiagnosisV22Input,
    DiagnosisV22ManifestError,
    _concept_group_hit,
    _forbidden_group_hit,
    _normalize,
    _relation_group_hit,
    evaluate_diagnosis_v22,
    load_diagnosis_v22_regressions,
    load_diagnosis_v22_specs,
    load_frozen_summary,
    replay_frozen_e2e_summary_v22,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
V22_METADATA = PROJECT_ROOT / "benchmark" / "dev_semantic_diagnosis_v2_2.jsonl"
V22_REGRESSIONS = PROJECT_ROOT / "benchmark" / "dev_semantic_diagnosis_v2_2_regressions.jsonl"
V22_MANIFEST = PROJECT_ROOT / "benchmark" / "dev_semantic_diagnosis_v2_2_manifest.json"
V20_METADATA = PROJECT_ROOT / "benchmark" / "dev_semantic_diagnosis_v2.jsonl"
CALIBRATION_SUMMARY = PROJECT_ROOT / "artifacts" / "benchmark-development" / "m7e2c2a-bounded-diagnosis-evidence" / "live" / "20260820T040110Z-20b0fcf2" / "summary.json"
FRESH_SUMMARY = PROJECT_ROOT / "artifacts" / "benchmark-development" / "m7e2c2c2-v21-fresh-validation" / "live" / "20260820T060935Z-fb5af9c3" / "summary.json"


def _input(case_id: str, text: str, *, candidates: list[dict[str, object]] | None = None) -> DiagnosisV22Input:
    return DiagnosisV22Input(
        case_id=case_id,
        agent_completed=True,
        diagnosis_status_match=True,
        issue_category_match=True,
        expected_file_hit=True,
        evidence_target_hit_count=1,
        invalid_rejected_evidence_count=0,
        root_cause_summary=text,
        candidates=candidates or [],
    )


def _specs() -> dict[str, object]:
    return {spec.case_id: spec for spec in load_diagnosis_v22_specs(V22_METADATA)}


def test_v22_metadata_is_independent_and_bounded() -> None:
    specs = load_diagnosis_v22_specs(V22_METADATA)
    regressions = load_diagnosis_v22_regressions(V22_REGRESSIONS)
    assert all(spec.schema_version == DIAGNOSIS_V22_SCHEMA_VERSION for spec in specs)
    assert len(specs) == 6
    assert len(regressions) == 15
    assert sum(item.expected_v2_2["matched"] is True for item in regressions) == 14
    assert regressions[-1].expected_v2_2["matched"] is False
    assert all(len(item.bounded_input["text"]) <= 400 for item in regressions)


def test_v22_manifest_hashes_match_new_files_and_freezes() -> None:
    manifest = json.loads(V22_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == DIAGNOSIS_V22_SCHEMA_VERSION
    assert manifest["v2_0_evaluator_sha256"] == "ba7306d02182c81a50b1ab3ec9ce8b59de572987edad8ccd2fcf34ded8d5a060"
    assert manifest["v2_1_evaluator_sha256"] == "33e9fa4262ed14e4ef5e58bc4259b619839740e55234828b232a6e2bc3621403"
    assert manifest["v2_2_evaluator_sha256"] == hashlib.sha256((PROJECT_ROOT / "src/springfix_agent/benchmark/diagnosis_v22.py").read_bytes()).hexdigest()
    assert manifest["v2_2_metadata_sha256"] == hashlib.sha256(V22_METADATA.read_bytes()).hexdigest()
    assert manifest["v2_2_regression_corpus_sha256"] == hashlib.sha256(V22_REGRESSIONS.read_bytes()).hexdigest()


def test_v22_schema_rejects_v21_metadata(tmp_path: Path) -> None:
    payload = json.loads(V22_METADATA.read_text(encoding="utf-8").splitlines()[0])
    payload["schema_version"] = "diagnosis-semantic-v2.1"
    path = tmp_path / "invalid.jsonl"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DiagnosisV22ManifestError, match="schema_version"):
        load_diagnosis_v22_specs(path)


def test_v22_normalization_is_finite() -> None:
    assert _normalize("WebhookNotificationSender requires webhook") == "webhook notification sender require webhook"
    assert _normalize("application-dev.yml doesn't match staging") == "application dev yml do not match staging"
    assert _normalize("StorageProperties") == "storage property"


@pytest.mark.parametrize(
    ("case_id", "text"),
    [
        ("dev-s1-profile-config-source", "The endpoint is ignored because application-dev.yml restricts its activation to the staging profile via spring.config.activate.on-profile. When the dev profile is active, the file is skipped and the default endpoint is used."),
        ("dev-s2-code-property-override", "The Application class sets a system property. System properties take precedence over application.yml and override the configured notification channel."),
        ("dev-s3-storage-validation", "StorageProperties binds max-entries set to 0, which violates the @Min(1) validation constraint."),
        ("dev-s4-conditional-notification", "The configured email provider leaves the WebhookNotificationSender conditionally disabled; the sender requires webhook and the NotificationSender bean is missing."),
        ("dev-s5-cache-binding-key", "cache.region-ttl does not match the CacheProperties map because the key leaves the map with its empty default."),
        ("dev-s6-local-precedence-conflict", "The active local profile loads application-local.yml, which overrides application.yml with warehouse.retry-limit 0; warehouse.retry-limit 0 violates the validation constraint."),
    ],
)
def test_confirmed_calibration_paraphrases_pass_v22(case_id: str, text: str) -> None:
    result = evaluate_diagnosis_v22(_input(case_id, text), _specs()[case_id])
    assert result.semantic_pass is True, result.failure_reasons


def test_fresh_s1_s4_s5_corrections_pass_v22() -> None:
    specs = _specs()
    cases = {
        "dev-s1-profile-config-source": "The development endpoint is ignored because application-dev.yml incorrectly restricts its activation to the staging profile via spring.config.activate.on-profile. When the dev profile is active, this file is skipped.",
        "dev-s4-conditional-notification": "NotificationService requires a NotificationSender bean, but the WebhookNotificationSender is conditionally disabled. The configured email provider is incompatible because the sender requires webhook.",
        "dev-s5-cache-binding-key": "The configuration property cache.region-ttl does not match the field ttlByRegion in CacheProperties, leaving the map with its empty default.",
    }
    for case_id, text in cases.items():
        result = evaluate_diagnosis_v22(_input(case_id, text), specs[case_id])
        assert result.semantic_pass is True, (case_id, result.failure_reasons)


@pytest.mark.parametrize(
    ("case_id", "text"),
    [
        ("dev-s1-profile-config-source", "application-dev.yml targets dev while the dev profile is active; the staging profile is not involved."),
        ("dev-s1-profile-config-source", "The staging profile is active, so the base configuration is skipped instead of the profile file."),
        ("dev-s4-conditional-notification", "The configured webhook provider satisfies the WebhookNotificationSender requirement."),
        ("dev-s4-conditional-notification", "The sender requires email and the configured provider is email."),
        ("dev-s4-conditional-notification", "The sender condition expects webhook while provider=webhook; the condition is satisfied."),
        ("dev-s5-cache-binding-key", "The incorrect key matches ttlByRegion and binds successfully."),
        ("dev-s5-cache-binding-key", "If region-ttl matched ttlByRegion, the map would populate."),
        ("dev-s5-cache-binding-key", "The correct key should match ttlByRegion; after changing to ttl-by-region, it matches."),
        ("dev-s1-profile-config-source", "application-dev.yml and the staging profile are mentioned, but the dev profile is active and no profile gate connects them."),
        ("dev-s4-conditional-notification", "The webhook provider is configured, but the sender requires email; this is not a webhook condition mismatch."),
        ("dev-s5-cache-binding-key", "region-ttl does not not match ttlByRegion and the map remains empty."),
        ("dev-s5-cache-binding-key", "ttl-by-region matches ttlByRegion, while region-ttl remains unbound and the map is empty."),
    ],
)
def test_v22_adversarial_negatives_are_rejected(case_id: str, text: str) -> None:
    result = evaluate_diagnosis_v22(_input(case_id, text), _specs()[case_id])
    assert result.semantic_pass is False


def test_all_fifteen_confirmed_regressions_have_expected_bounded_match() -> None:
    specs = _specs()
    for regression in load_diagnosis_v22_regressions(V22_REGRESSIONS):
        spec = specs[regression.case_id]
        text = regression.bounded_input["text"]
        if regression.semantic_component_id == "incorrect_key_binds_successfully":
            hit = _forbidden_group_hit(
                [part for part in [" ".join(_normalize(text).split())] if part],
                next(group for group in spec.forbidden_relations if group.name == regression.semantic_component_id),
                _normalize(text),
            )
        else:
            concept = next((group for group in spec.required_concepts if group.name == regression.semantic_component_id), None)
            if concept is not None:
                hit = _concept_group_hit(_normalize(text), concept)
            else:
                relation = next(group for group in spec.required_relations if group.name == regression.semantic_component_id)
                hit = _relation_group_hit([_normalize(text)], relation, _normalize(text))
        assert hit is regression.expected_v2_2["matched"], regression.regression_id


def test_s5_negated_required_relation_does_not_hit_forbidden_positive() -> None:
    spec = _specs()["dev-s5-cache-binding-key"]
    result = evaluate_diagnosis_v22(
        _input("dev-s5-cache-binding-key", "cache.region-ttl does not match ttlByRegion, so the map has an empty default."),
        spec,
    )
    assert result.required_relation_hits["configuration_key_binding_mismatch"] is True
    assert result.contradiction_hits == []
    assert result.semantic_pass is True


def test_s5_positive_current_state_still_hits_forbidden_relation() -> None:
    spec = _specs()["dev-s5-cache-binding-key"]
    forbidden = spec.forbidden_relations[0]
    assert _forbidden_group_hit(["region ttl match ttl by region"], forbidden, "region ttl match ttl by region")


def test_recommended_fix_is_excluded_only_from_contradiction_context() -> None:
    spec = _specs()["dev-s5-cache-binding-key"]
    result = evaluate_diagnosis_v22(
        _input(
            "dev-s5-cache-binding-key",
            "cache.region-ttl does not match ttlByRegion and the map retains its empty default.",
            candidates=[{"title": "Key mismatch", "description": "The incorrect key is not binding.", "recommended_fix": "Rename the key so it matches ttlByRegion."}],
        ),
        spec,
    )
    assert result.semantic_pass is True
    assert result.contradiction_hits == []


def test_v22_missing_text_is_insufficient_artifact() -> None:
    spec = _specs()["dev-s2-code-property-override"]
    result = evaluate_diagnosis_v22(
        DiagnosisV22Input(
            case_id=spec.case_id,
            agent_completed=True,
            diagnosis_status_match=True,
            issue_category_match=True,
            expected_file_hit=True,
            evidence_target_hit_count=1,
            invalid_rejected_evidence_count=0,
        ),
        spec,
    )
    assert result.evaluation_status == "insufficient_artifact"
    assert result.semantic_pass is None


def test_frozen_replays_preserve_v20_v21_and_score_v22() -> None:
    replay_cal = replay_frozen_e2e_summary_v22(
        load_frozen_summary(CALIBRATION_SUMMARY),
        load_diagnosis_v22_specs(V22_METADATA),
        load_diagnosis_v2_specs(V20_METADATA),
    )
    replay_fresh = replay_frozen_e2e_summary_v22(
        load_frozen_summary(FRESH_SUMMARY),
        load_diagnosis_v22_specs(V22_METADATA),
        load_diagnosis_v2_specs(V20_METADATA),
    )
    for replay in (replay_cal, replay_fresh):
        assert replay["agent_rerun"] is False
        assert replay["new_llm_calls"] == 0
        assert replay["diagnosis_v2_0"]["aggregate"]["cases_evaluated"] == 6
        assert replay["diagnosis_v2_1"]["aggregate"]["cases_evaluated"] == 6
        assert replay["diagnosis_v2_2"]["aggregate"]["cases_evaluated"] == 6
        assert replay["diagnosis_v2_2"]["aggregate"]["cases_insufficient_artifact"] == 0
    assert replay_cal["diagnosis_v2_2"]["aggregate"]["cases_passed"] == 6
    assert replay_fresh["diagnosis_v2_2"]["aggregate"]["cases_passed"] == 6
