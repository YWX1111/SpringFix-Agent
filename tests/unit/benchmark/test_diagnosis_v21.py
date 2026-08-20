"""Diagnosis V2.1 fairness calibration and adversarial controls."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from springfix_agent.benchmark.diagnosis_v2 import load_diagnosis_v2_specs, load_frozen_summary
from springfix_agent.benchmark.diagnosis_v21 import (
    DIAGNOSIS_V21_SCHEMA_VERSION,
    DiagnosisV21Input,
    DiagnosisV21ManifestError,
    _concept_group_hit,
    _normalize,
    _relation_group_hit,
    evaluate_diagnosis_v21,
    load_diagnosis_v21_regressions,
    load_diagnosis_v21_specs,
    replay_frozen_e2e_summary_v21,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
V21_METADATA = PROJECT_ROOT / "benchmark" / "dev_semantic_diagnosis_v2_1.jsonl"
V21_REGRESSIONS = PROJECT_ROOT / "benchmark" / "dev_semantic_diagnosis_v2_1_regressions.jsonl"
V20_METADATA = PROJECT_ROOT / "benchmark" / "dev_semantic_diagnosis_v2.jsonl"
FROZEN_SUMMARY = (
    PROJECT_ROOT
    / "artifacts"
    / "benchmark-development"
    / "m7e2c2a-bounded-diagnosis-evidence"
    / "live"
    / "20260820T040110Z-20b0fcf2"
    / "summary.json"
)


def _input(case_id: str, text: str) -> DiagnosisV21Input:
    return DiagnosisV21Input(
        case_id=case_id,
        agent_completed=True,
        diagnosis_status_match=True,
        issue_category_match=True,
        expected_file_hit=True,
        evidence_target_hit_count=1,
        invalid_rejected_evidence_count=0,
        root_cause_summary=text,
    )


def test_v21_metadata_and_regression_corpus_are_independent_and_bounded() -> None:
    specs = load_diagnosis_v21_specs(V21_METADATA)
    regressions = load_diagnosis_v21_regressions(V21_REGRESSIONS)
    assert all(spec.schema_version == DIAGNOSIS_V21_SCHEMA_VERSION for spec in specs)
    assert len(specs) == 6
    assert len(regressions) == 11
    assert all(regression.expected_v2_0["matched"] is False for regression in regressions)
    assert all(regression.expected_v2_1["matched"] is True for regression in regressions)
    assert all(len(item.bounded_input["text"]) <= 400 for item in regressions)


def test_v21_schema_rejects_v20_metadata(tmp_path: Path) -> None:
    payload = json.loads(V21_METADATA.read_text(encoding="utf-8").splitlines()[0])
    payload["schema_version"] = "diagnosis-semantic-v2.0"
    path = tmp_path / "invalid.jsonl"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DiagnosisV21ManifestError, match="schema_version"):
        load_diagnosis_v21_specs(path)


def test_bounded_normalization_handles_punctuation_camelcase_plural_and_inflection() -> None:
    assert _normalize("`dev` profile") == "dev profile"
    assert _normalize("StorageProperties") == "storage property"
    assert _normalize("system properties") == "system property"
    assert _normalize("application-local.yml overriding application.yml") == (
        "application local yml override application yml"
    )


@pytest.mark.parametrize(
    ("case_id", "text"),
    [
        (
            "dev-s1-profile-config-source",
            "The application falls back because `application-dev.yml` incorrectly "
            "specifies `on-profile: staging`. When the `dev` profile is active, "
            "the properties are ignored and the fallback shipping endpoint is used.",
        ),
        (
            "dev-s2-code-property-override",
            "The Application class sets a system property. System properties take "
            "precedence over application.yml and override the configured notification channel.",
        ),
        (
            "dev-s3-storage-validation",
            "StorageProperties binds max-entries set to 0, which "
            "violates the @Min(1) validation constraint.",
        ),
        (
            "dev-s4-conditional-notification",
            "The configured email provider has only a WebhookNotificationSender, "
            "which is conditionally registered only when the provider is webhook; "
            "NotificationSender is missing.",
        ),
        (
            "dev-s5-cache-binding-key",
            "cache.region-ttl is not binding to the CacheProperties map because the key is "
            "mismatched; the map retains its empty default.",
        ),
        (
            "dev-s6-local-precedence-conflict",
            "The active local profile loads application-local.yml, which is overriding "
            "application.yml with a warehouse.retry-limit value of 0; value 0 fails validation.",
        ),
    ],
)
def test_frozen_live_paraphrases_pass_v21(case_id: str, text: str) -> None:
    specs = {spec.case_id: spec for spec in load_diagnosis_v21_specs(V21_METADATA)}
    result = evaluate_diagnosis_v21(_input(case_id, text), specs[case_id])
    assert result.semantic_pass is True, result.failure_reasons


def test_each_confirmed_component_regression_is_recognized() -> None:
    specs = {spec.case_id: spec for spec in load_diagnosis_v21_specs(V21_METADATA)}
    regressions = load_diagnosis_v21_regressions(V21_REGRESSIONS)
    for regression in regressions:
        spec = specs[regression.case_id]
        text = _normalize(regression.bounded_input["text"])
        component_id = regression.semantic_component_id
        concept = next(
            (group for group in spec.required_concepts if group.name == component_id), None
        )
        if concept is not None:
            assert _concept_group_hit(text, concept), regression.regression_id
            continue
        relation = next(group for group in spec.required_relations if group.name == component_id)
        clauses = [_normalize(item) for item in text.split(".") if _normalize(item)]
        assert _relation_group_hit(clauses, relation), regression.regression_id


@pytest.mark.parametrize(
    ("case_id", "text"),
    [
        (
            "dev-s2-code-property-override",
            "Application configurations override system properties for the notification channel.",
        ),
        (
            "dev-s6-local-precedence-conflict",
            "application.yml is overriding application-local.yml for the retry setting.",
        ),
        (
            "dev-s3-storage-validation",
            "OtherProperties has max-entries set to 0 and violates the minimum validation constraint.",
        ),
        (
            "dev-s3-storage-validation",
            "max-entries is set to 1, unrelated value 0 violates the validation constraint.",
        ),
        (
            "dev-s3-storage-validation",
            "max-entries is set to 1. An unrelated value 0 violates the validation constraint.",
        ),
        (
            "dev-s6-local-precedence-conflict",
            "application-local.yml and application.yml both define the retry setting.",
        ),
        (
            "dev-s3-storage-validation",
            "max-entries is set to 1 and satisfies the validation constraint.",
        ),
        (
            "dev-s5-cache-binding-key",
            "region-ttl binds to the CacheProperties map successfully.",
        ),
        (
            "dev-s2-code-property-override",
            "The system property overrides application.yml. Application configuration also "
            "overrides the system property.",
        ),
        (
            "dev-s2-code-property-override",
            "system property, application.yml, overrides, channel; application configuration, "
            "system properties.",
        ),
        (
            "dev-s2-code-property-override",
            "system properties, application configurations, notification channels.",
        ),
        (
            "dev-s2-code-property-override",
            "An environment variable overrides application.yml for the notification channel.",
        ),
    ],
)
def test_adversarial_negative_controls_remain_rejected(case_id: str, text: str) -> None:
    specs = {spec.case_id: spec for spec in load_diagnosis_v21_specs(V21_METADATA)}
    result = evaluate_diagnosis_v21(_input(case_id, text), specs[case_id])
    assert result.semantic_pass is False


def test_frozen_replay_reports_v20_and_v21_independently() -> None:
    replay = replay_frozen_e2e_summary_v21(
        load_frozen_summary(FROZEN_SUMMARY),
        load_diagnosis_v21_specs(V21_METADATA),
        load_diagnosis_v2_specs(V20_METADATA),
    )
    assert replay["agent_rerun"] is False
    assert replay["new_llm_calls"] == 0
    assert replay["diagnosis_v1"]["passed"] == 0
    assert replay["diagnosis_v2_0"]["aggregate"]["cases_passed"] == 0
    assert replay["diagnosis_v2_0"]["aggregate"]["cases_evaluated"] == 6
    assert replay["diagnosis_v2_1"]["aggregate"]["cases_passed"] == 6
    assert replay["diagnosis_v2_1"]["aggregate"]["cases_evaluated"] == 6
    assert replay["diagnosis_v2_1"]["aggregate"]["cases_insufficient_artifact"] == 0


def test_v21_missing_text_is_insufficient_artifact() -> None:
    spec = next(
        spec
        for spec in load_diagnosis_v21_specs(V21_METADATA)
        if spec.case_id == "dev-s2-code-property-override"
    )
    result = evaluate_diagnosis_v21(
        DiagnosisV21Input(
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
