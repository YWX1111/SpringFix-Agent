"""Diagnosis V2 semantic validity, discrimination, and replay tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from springfix_agent.benchmark.diagnosis_v2 import (
    DIAGNOSIS_V2_SCHEMA_VERSION,
    DiagnosisV2Input,
    DiagnosisV2ManifestError,
    DiagnosisV2Result,
    evaluate_diagnosis_v2,
    load_diagnosis_v2_specs,
    replay_frozen_e2e_summary,
)
from springfix_agent.benchmark.evaluator import evaluate_case
from springfix_agent.benchmark.loader import load_cases

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEV_CASES = PROJECT_ROOT / "benchmark" / "dev_semantic_cases.jsonl"
V2_METADATA = PROJECT_ROOT / "benchmark" / "dev_semantic_diagnosis_v2.jsonl"


def _s2_spec():
    return load_diagnosis_v2_specs(V2_METADATA)[1]


def _semantic_input(
    text: str,
    *,
    expected_file_hit: bool = True,
    evidence_target_hit_count: int = 1,
) -> DiagnosisV2Input:
    return DiagnosisV2Input(
        case_id="dev-s2-code-property-override",
        agent_completed=True,
        diagnosis_status_match=True,
        issue_category_match=True,
        expected_file_hit=expected_file_hit,
        evidence_target_hit_count=evidence_target_hit_count,
        invalid_rejected_evidence_count=0,
        root_cause_summary=text,
    )


def _evaluate(text: str, **kwargs: object) -> DiagnosisV2Result:
    return evaluate_diagnosis_v2(_semantic_input(text, **kwargs), _s2_spec())


@pytest.mark.parametrize(
    ("case_id", "diagnosis"),
    [
        (
            "dev-s1-profile-config-source",
            "The active dev profile should provide the shipping endpoint. "
            "application-dev.yml declares staging through on-profile.",
        ),
        (
            "dev-s2-code-property-override",
            "The system property overrides application.yml for the notification channel.",
        ),
        (
            "dev-s3-storage-validation",
            "Storage properties bind max entries. The zero max entries violates the "
            "minimum value validation.",
        ),
        (
            "dev-s4-conditional-notification",
            "alerts.provider selects an email provider and NotificationSender is missing. "
            "The email provider does not satisfy the ConditionalOnProperty webhook condition.",
        ),
        (
            "dev-s5-cache-binding-key",
            "cache.region-ttl leaves an empty map. region-ttl does not bind to ttlByRegion.",
        ),
        (
            "dev-s6-local-precedence-conflict",
            "The active local profile loads application-local.yml. application-local.yml "
            "overrides application.yml. The retry-limit 0 violates the minimum value "
            "validation constraint.",
        ),
    ],
)
def test_each_dev_contract_has_a_strong_positive_control(
    case_id: str, diagnosis: str
) -> None:
    specs = {spec.case_id: spec for spec in load_diagnosis_v2_specs(V2_METADATA)}
    value = DiagnosisV2Input(
        case_id=case_id,
        agent_completed=True,
        diagnosis_status_match=True,
        issue_category_match=True,
        expected_file_hit=True,
        evidence_target_hit_count=1,
        invalid_rejected_evidence_count=0,
        root_cause_summary=diagnosis,
    )
    result = evaluate_diagnosis_v2(value, specs[case_id])
    assert result.semantic_pass is True, result.failure_reasons


def test_exact_strong_semantic_diagnosis_passes() -> None:
    result = _evaluate(
        "The System.setProperty call creates a system property for the notification channel. "
        "The system property overrides application.yml."
    )
    assert result.evaluation_status == "evaluated"
    assert result.semantic_pass is True
    assert result.semantic_score == 1.0


def test_semantic_paraphrase_passes_without_exact_gold_phrase() -> None:
    result = _evaluate(
        "The channel property comes from a code-supplied property. "
        "Application configuration has lower precedence than the code-supplied property."
    )
    assert result.semantic_pass is True
    assert all(result.required_concept_hits.values())
    assert all(result.required_relation_hits.values())


def test_incomplete_vague_diagnosis_fails() -> None:
    result = _evaluate("Spring configuration has a wrong value and should be changed.")
    assert result.semantic_pass is False
    assert any(reason.startswith("missing_concept:") for reason in result.failure_reasons)
    assert any(reason.startswith("missing_relation:") for reason in result.failure_reasons)


def test_wrong_source_fails() -> None:
    result = _evaluate(
        "An environment variable overrides application.yml for the notification channel."
    )
    assert result.semantic_pass is False
    assert result.required_concept_hits["higher_precedence_source"] is False


def test_reversed_precedence_and_keyword_stuffing_fail() -> None:
    result = _evaluate(
        "System property, System.setProperty, higher precedence, application.yml, "
        "notification channel. Application configuration overrides the system property."
    )
    assert result.semantic_pass is False
    assert result.required_relation_hits["code_source_overrides_configuration"] is False
    assert result.contradiction_hits == ["configuration_overrides_code_source"]


def test_contradictory_diagnosis_fails_even_with_correct_relation() -> None:
    result = _evaluate(
        "The system property overrides application.yml for the notification channel. "
        "Application configuration also overrides the system property."
    )
    assert result.required_relation_hits["code_source_overrides_configuration"] is True
    assert result.contradiction_hits == ["configuration_overrides_code_source"]
    assert result.semantic_pass is False


def test_correct_semantics_require_expected_source_evidence() -> None:
    text = (
        "The system property overrides application configuration for the notification channel."
    )
    result = _evaluate(text, expected_file_hit=False, evidence_target_hit_count=0)
    assert result.semantic_pass is False
    assert result.structural_conditions["expected_source_file_hit"] is False
    assert result.structural_conditions["evidence_target_hit"] is False


def test_v1_keyword_contract_remains_backward_compatible() -> None:
    case = load_cases(DEV_CASES)[1]
    evidence_file = case.evidence_targets[0].file
    state: dict[str, object] = {
        "status": "completed",
        "issue_analysis": {"issue_category": "configuration"},
        "root_cause_analysis": {
            "diagnosis_status": "complete",
            "summary": (
                "System.setProperty creates a higher precedence property source for the "
                "notification channel in application code."
            ),
            "candidates": [
                {
                    "title": "Override",
                    "description": "The configured channel is replaced.",
                    "recommended_fix": "Remove the override.",
                    "verification_steps": [],
                    "evidence": [
                        {
                            "file": evidence_file,
                            "start_line": 7,
                            "end_line": 13,
                            "explanation": "The code supplies the property.",
                        }
                    ],
                }
            ],
            "rejected_evidence": [],
        },
        "retrieved_snippets": [{"file": evidence_file}],
    }
    result = evaluate_case(case, state, [], total_duration_ms=1, model="test")
    assert result.metrics.root_cause_keyword_coverage == 1.0
    assert result.metrics.case_pass is True
    assert "semantic_pass" not in result.metrics.model_dump()


def test_v2_schema_version_is_strict(tmp_path: Path) -> None:
    payload = json.loads(V2_METADATA.read_text(encoding="utf-8").splitlines()[0])
    payload["schema_version"] = "diagnosis-semantic-v3.0"
    path = tmp_path / "invalid.jsonl"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DiagnosisV2ManifestError, match="schema_version"):
        load_diagnosis_v2_specs(path)


def test_v2_metadata_is_not_in_agent_projection() -> None:
    case = load_cases(DEV_CASES)[0]
    spec = load_diagnosis_v2_specs(V2_METADATA)[0]
    assert spec.schema_version == DIAGNOSIS_V2_SCHEMA_VERSION
    assert set(case.agent_input()) == {"repository", "issue_description", "error_log"}
    assert "required_concepts" not in json.dumps(case.agent_input())
    assert "required_relations" not in json.dumps(case.agent_input())


def test_frozen_replay_marks_missing_semantic_text_as_insufficient_artifact() -> None:
    summary: dict[str, object] = {
        "run_id": "frozen-run",
        "aggregate": {"repair_success_count": 1, "sample_size": 1},
        "cases": [
            {
                "case_id": "dev-s2-code-property-override",
                "diagnosis_completed": True,
                "diagnosis_status_match": True,
                "issue_category_match": True,
                "expected_file_hit": True,
                "evidence_target_recall": 1.0,
                "rejected_evidence_count": 0,
                "root_cause_keyword_coverage": 0.4,
                "diagnosis_benchmark_pass": False,
            }
        ],
    }
    replay = replay_frozen_e2e_summary(summary, [_s2_spec()])
    assert replay["agent_rerun"] is False
    assert replay["new_llm_calls"] == 0
    assert replay["diagnosis_v1"]["passed"] == 0
    aggregate = replay["diagnosis_v2"]["aggregate"]
    assert aggregate["cases_evaluated"] == 0
    assert aggregate["cases_insufficient_artifact"] == 1
    case = replay["diagnosis_v2"]["cases"][0]
    assert case["evaluation_status"] == "insufficient_artifact"
    assert case["semantic_pass"] is None
