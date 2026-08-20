"""Bounded E2E diagnosis evidence persistence and replay tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from springfix_agent.benchmark.diagnosis_v2 import (
    load_diagnosis_v2_specs,
    replay_frozen_e2e_summary,
)
from springfix_agent.repair.e2e_artifacts import (
    capture_bounded_diagnosis_evidence,
    sanitize_artifact_value,
    write_end_to_end_artifacts,
)
from springfix_agent.repair.e2e_metrics import aggregate_end_to_end_metrics
from springfix_agent.repair.e2e_models import (
    DIAGNOSIS_CANDIDATE_DESCRIPTION_MAX_CHARS,
    DIAGNOSIS_CANDIDATE_MAX_COUNT,
    DIAGNOSIS_CANDIDATE_RECOMMENDED_FIX_MAX_CHARS,
    DIAGNOSIS_CANDIDATE_TITLE_MAX_CHARS,
    DIAGNOSIS_EVIDENCE_SCHEMA_VERSION,
    DIAGNOSIS_SUMMARY_MAX_CHARS,
    DiagnosisEvidenceV1,
    EndToEndCaseArtifact,
    EndToEndCaseResult,
    EndToEndRunResult,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
V2_METADATA = PROJECT_ROOT / "benchmark" / "dev_semantic_diagnosis_v2.jsonl"
CASE_ID = "dev-s2-code-property-override"


def _write_summary(tmp_path: Path, evidence: DiagnosisEvidenceV1) -> dict[str, object]:
    case = EndToEndCaseResult(
        case_id=CASE_ID,
        model="test-model",
        diagnosis_completed=True,
        diagnosis_status_match=True,
        issue_category_match=True,
        expected_file_hit=True,
        evidence_target_recall=1.0,
        rejected_evidence_count=0,
        diagnosis_evidence=evidence,
    )
    result = EndToEndRunResult(
        mode="mock",
        run_id="bounded-evidence-test",
        run_metadata={"split": "dev_semantic_v1"},
        cases=[case],
        aggregate=aggregate_end_to_end_metrics([case]),
    )
    write_end_to_end_artifacts(result, tmp_path)
    payload = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _case_record(summary: dict[str, object]) -> dict[str, object]:
    cases = summary["cases"]
    assert isinstance(cases, list)
    case = cases[0]
    assert isinstance(case, dict)
    return case


def test_bounded_evidence_is_versioned_persisted_and_consumed_by_frozen_v2(
    tmp_path: Path,
) -> None:
    summary_text = (
        "The system property overrides application.yml for the notification channel."
    )
    candidates = [
        {
            "title": "Code property override",
            "description": "Application code replaces the configured channel.",
            "recommended_fix": "Remove the system property override.",
        }
    ]
    evidence = capture_bounded_diagnosis_evidence(summary_text, candidates)
    summary = _write_summary(tmp_path, evidence)
    record = _case_record(summary)
    per_case_record = json.loads(
        (tmp_path / "cases" / CASE_ID / "result.json").read_text(encoding="utf-8")
    )

    assert record["diagnosis_evidence_schema_version"] == DIAGNOSIS_EVIDENCE_SCHEMA_VERSION
    assert per_case_record["root_cause_summary"] == record["root_cause_summary"]
    assert per_case_record["diagnosis_candidates"] == record["diagnosis_candidates"]
    EndToEndCaseArtifact.model_validate(record)
    nested = record["diagnosis_evidence"]
    assert isinstance(nested, dict)
    assert nested == {
        "bounded": True,
        "candidates": candidates,
        "evaluation_ready": True,
        "sanitized": True,
        "schema_version": DIAGNOSIS_EVIDENCE_SCHEMA_VERSION,
        "summary": summary_text,
        "truncated": False,
        "truncated_fields": [],
    }
    assert record["root_cause_summary"] == summary_text
    assert record["diagnosis_candidates"] == candidates

    spec = next(spec for spec in load_diagnosis_v2_specs(V2_METADATA) if spec.case_id == CASE_ID)
    replay = replay_frozen_e2e_summary(summary, [spec])
    aggregate = replay["diagnosis_v2"]["aggregate"]
    assert aggregate["cases_evaluated"] == 1
    assert aggregate["cases_passed"] == 1
    assert aggregate["cases_insufficient_artifact"] == 0


def test_truncation_is_bounded_flagged_and_fail_closed_for_v2(tmp_path: Path) -> None:
    candidates = [
        {
            "title": "t" * (DIAGNOSIS_CANDIDATE_TITLE_MAX_CHARS + 1),
            "description": "d" * (DIAGNOSIS_CANDIDATE_DESCRIPTION_MAX_CHARS + 1),
            "recommended_fix": (
                "f" * (DIAGNOSIS_CANDIDATE_RECOMMENDED_FIX_MAX_CHARS + 1)
            ),
        }
        for _ in range(DIAGNOSIS_CANDIDATE_MAX_COUNT + 1)
    ]
    evidence = capture_bounded_diagnosis_evidence(
        "s" * (DIAGNOSIS_SUMMARY_MAX_CHARS + 1),
        candidates,
    )

    assert evidence.truncated is True
    assert evidence.evaluation_ready is False
    assert len(evidence.summary or "") == DIAGNOSIS_SUMMARY_MAX_CHARS
    assert len(evidence.candidates) == DIAGNOSIS_CANDIDATE_MAX_COUNT
    assert len(evidence.candidates[0].title) == DIAGNOSIS_CANDIDATE_TITLE_MAX_CHARS
    assert len(evidence.candidates[0].description) == DIAGNOSIS_CANDIDATE_DESCRIPTION_MAX_CHARS
    assert (
        len(evidence.candidates[0].recommended_fix)
        == DIAGNOSIS_CANDIDATE_RECOMMENDED_FIX_MAX_CHARS
    )
    assert "summary" in evidence.truncated_fields
    assert "candidates" in evidence.truncated_fields

    summary = _write_summary(tmp_path, evidence)
    record = _case_record(summary)
    assert "root_cause_summary" not in record
    assert "diagnosis_candidates" not in record
    EndToEndCaseArtifact.model_validate(record)
    spec = next(spec for spec in load_diagnosis_v2_specs(V2_METADATA) if spec.case_id == CASE_ID)
    replay = replay_frozen_e2e_summary(summary, [spec])
    result = replay["diagnosis_v2"]["cases"][0]
    assert result["evaluation_status"] == "insufficient_artifact"
    assert result["semantic_pass"] is None


def test_missing_semantic_text_remains_insufficient_artifact(tmp_path: Path) -> None:
    evidence = capture_bounded_diagnosis_evidence(None, [])
    assert evidence.evaluation_ready is False
    summary = _write_summary(tmp_path, evidence)
    spec = next(spec for spec in load_diagnosis_v2_specs(V2_METADATA) if spec.case_id == CASE_ID)
    replay = replay_frozen_e2e_summary(summary, [spec])
    aggregate = replay["diagnosis_v2"]["aggregate"]
    assert aggregate["cases_evaluated"] == 0
    assert aggregate["cases_insufficient_artifact"] == 1


def test_truncated_fields_cannot_be_overridden_into_an_evaluable_projection(
    tmp_path: Path,
) -> None:
    evidence = DiagnosisEvidenceV1(
        summary="apparently complete",
        truncated=False,
        truncated_fields=["summary"],
        evaluation_ready=True,
    )
    assert evidence.truncated is True
    assert evidence.evaluation_ready is False
    record = _case_record(_write_summary(tmp_path, evidence))
    assert "root_cause_summary" not in record
    assert "diagnosis_candidates" not in record


def test_evidence_is_immutable_and_truncated_field_names_are_bounded() -> None:
    evidence = capture_bounded_diagnosis_evidence(
        "summary",
        [{"title": "title", "description": "description", "recommended_fix": "fix"}],
    )
    assert evidence.evaluation_ready is True
    with pytest.raises(ValidationError):
        evidence.truncated = True  # type: ignore[misc]
    with pytest.raises(ValidationError):
        evidence.summary = "x" * (DIAGNOSIS_SUMMARY_MAX_CHARS + 1)  # type: ignore[misc]
    with pytest.raises(ValidationError):
        DiagnosisEvidenceV1(truncated_fields=("unbounded-secret",))  # type: ignore[arg-type]


def test_capture_whitelists_public_text_and_sanitizes_secrets_and_paths() -> None:
    candidates: list[dict[str, object]] = [
        {
            "title": "Bearer abcdefghijklmnop",
            "description": r"credential=hunter2 at D:\Users\Administrator\Temp\agent-output.txt",
            "recommended_fix": "Use sk-abcdefghijklmnopqrstuvwx via https://secret.example/v1",
            "reasoning": "COT_CANARY",
            "thinking": "THINKING_CANARY",
            "analysis": "ANALYSIS_CANARY",
            "internal_reasoning": "INTERNAL_CANARY",
            "prompt": "PROMPT_CANARY",
            "raw_provider_response": "RAW_PROVIDER_CANARY",
            "tool_transcript": "TOOL_TRANSCRIPT_CANARY",
            "source_file": "SOURCE_FILE_CANARY",
            "maven_output": "MAVEN_OUTPUT_CANARY",
            "repair_log": "REPAIR_LOG_CANARY",
            "holdout_gold": "HOLDOUT_GOLD_CANARY",
        }
    ]
    evidence = capture_bounded_diagnosis_evidence("api_key=topsecret", candidates)
    payload = evidence.model_dump(mode="json")
    text = json.dumps(payload, ensure_ascii=False)

    assert "topsecret" not in text
    assert "abcdefghijklmnop" not in text
    assert "hunter2" not in text
    assert "sk-abcdefghijklmnopqrstuvwx" not in text
    assert "secret.example" not in text
    assert "D:\\\\Users" not in text
    for canary in (
        "COT_CANARY",
        "THINKING_CANARY",
        "ANALYSIS_CANARY",
        "INTERNAL_CANARY",
        "PROMPT_CANARY",
        "RAW_PROVIDER_CANARY",
        "TOOL_TRANSCRIPT_CANARY",
        "SOURCE_FILE_CANARY",
        "MAVEN_OUTPUT_CANARY",
        "REPAIR_LOG_CANARY",
        "HOLDOUT_GOLD_CANARY",
    ):
        assert canary not in text
    assert set(payload["candidates"][0]) == {"title", "description", "recommended_fix"}
    assert "<redacted>" in text


@pytest.mark.parametrize(
    "secret_text",
    [
        "Authorization: Basic dXNlcjpwYXNz",
        'api_key = "secret value"',
        "credential='credential value'",
    ],
)
def test_capture_redacts_quoted_and_spaced_credentials(secret_text: str) -> None:
    evidence = capture_bounded_diagnosis_evidence(
        secret_text,
        [{"title": "safe", "description": "safe", "recommended_fix": "safe"}],
    )
    text = evidence.model_dump_json()
    assert "dXNlcjpwYXNz" not in text
    assert "secret value" not in text
    assert "credential value" not in text


@pytest.mark.parametrize(
    "machine_path",
    [
        r"D:\Users\Administrator\Temp\artifact.json",
        r"D:\Users\Jane Doe\TOP_SECRET_PATH\artifact.json",
        r"\\build-server\share\agent\artifact.json",
        r"\\build-server\share\Jane Doe\TOP_SECRET_PATH\artifact.json",
        "/private/tmp/agent/artifact.json",
        "/workspace/Jane Doe/TOP_SECRET_PATH/artifact.json",
        "/workspace/repository/artifact.json",
        "/root/.cache/agent/artifact.json",
        "/opt/agent/artifact.json",
        "/mnt/c/repository/artifact.json",
    ],
)
def test_capture_redacts_common_machine_absolute_paths(machine_path: str) -> None:
    evidence = capture_bounded_diagnosis_evidence(
        "summary",
        [
            {
                "title": "path",
                "description": machine_path,
                "recommended_fix": "Use a repository-relative reference.",
            }
        ],
    )
    text = evidence.model_dump_json()
    assert machine_path not in text
    assert "<path>" in text


def test_artifact_sanitizer_is_idempotent_after_bounding() -> None:
    evidence = capture_bounded_diagnosis_evidence(
        "api_key=topsecret",
        [
            {
                "title": "Bearer abcdefghijklmnop",
                "description": "/workspace/private/result.json",
                "recommended_fix": "See https://secret.example/v1",
            }
        ],
    )
    once = sanitize_artifact_value(evidence.model_dump(mode="json"))
    twice = sanitize_artifact_value(once)
    assert twice == once
