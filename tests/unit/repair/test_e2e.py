"""M5D orchestration, funnel, short-circuit, and artifact safety tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from springfix_agent.llm.mock import MockLLMClient
from springfix_agent.repair.e2e_artifacts import sanitize_artifact_value
from springfix_agent.repair.e2e_metrics import aggregate_end_to_end_metrics
from springfix_agent.repair.e2e_models import EndToEndCaseResult
from springfix_agent.repair.e2e_runner import EndToEndRepairBenchmarkRunner
from springfix_agent.repair.maven_verifier import MavenVerificationOutcome
from springfix_agent.repair.verification_models import (
    BaselineVerificationResult,
    MavenTestResult,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class _FakeVerifier:
    """Keep orchestration tests deterministic without a second Maven run."""

    def __init__(self, *, baseline_verified: bool = True) -> None:
        self.baseline_verified = baseline_verified

    def verify_baseline(self, _repository: Path, _expectation: object) -> BaselineVerificationResult:
        return BaselineVerificationResult(
            verified=self.baseline_verified,
            maven_result=MavenTestResult(
                executed=True,
                timed_out=False,
                exit_code=1,
                failures=1,
                tests=1,
                target_test_found=True,
                surefire_report_found=True,
            ),
            failure_reason=None if self.baseline_verified else "baseline_bug_not_reproduced",
        )

    def verify_patched_workspace(
        self, _workspace: Path, _expectation: object
    ) -> MavenVerificationOutcome:
        return MavenVerificationOutcome(
            result=MavenTestResult(
                executed=True,
                timed_out=False,
                exit_code=0,
                tests=1,
                target_test_found=True,
                surefire_report_found=True,
            ),
            failure_reason=None,
        )


def _runner(tmp_path: Path, *, verifier: object, llm: MockLLMClient | None = None) -> EndToEndRepairBenchmarkRunner:
    return EndToEndRepairBenchmarkRunner(
        project_root=PROJECT_ROOT,
        manifest_path=PROJECT_ROOT / "benchmark" / "agent_cases.jsonl",
        repair_gold_path=PROJECT_ROOT / "benchmark" / "repair_gold.jsonl",
        output_dir=tmp_path / "artifacts",
        mode="mock",
        case_id="transaction-self-invocation",
        llm=llm,
        verifier=verifier,  # type: ignore[arg-type]
    )


def test_m5d_mock_orchestration_uses_existing_stages(tmp_path: Path) -> None:
    result = _runner(tmp_path, verifier=_FakeVerifier()).run()
    case = result.cases[0]
    assert result.aggregate.sample_size == 1
    assert case.diagnosis_completed is True
    assert case.proposal_generated is True
    assert case.proposal_valid is True
    assert case.patch_applied is True
    assert case.target_test_found is True
    assert case.repair_success is True
    assert case.total_logical_llm_calls == 4
    assert case.diagnostic_logical_llm_calls == 3
    assert case.patch_logical_llm_calls == 1
    assert case.patch_proposal_duration_ms >= 0
    assert case.patch_application_ms >= 0
    assert case.verification_status == "passed"
    assert case.diagnosis_evidence is not None
    assert case.diagnosis_evidence.evaluation_ready is True
    assert case.diagnosis_evidence.truncated is False


def test_diagnosis_capture_failure_does_not_change_repair_pipeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_capture(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("synthetic artifact failure")

    monkeypatch.setattr(
        "springfix_agent.repair.e2e_runner.capture_bounded_diagnosis_evidence",
        fail_capture,
    )
    result = _runner(tmp_path, verifier=_FakeVerifier()).run()
    case = result.cases[0]
    assert case.repair_success is True
    assert case.proposal_generated is True
    assert case.patch_applied is True
    assert case.target_test_found is True
    assert case.diagnosis_evidence is None
    assert case.warnings == ["diagnosis_evidence_capture_failed"]


def test_baseline_failure_short_circuits_before_agent(tmp_path: Path) -> None:
    result = _runner(tmp_path, verifier=_FakeVerifier(baseline_verified=False)).run()
    case = result.cases[0]
    assert case.failed_stage == "baseline"
    assert case.failure_reason == "baseline_bug_not_reproduced"
    assert case.diagnosis_status == "not_run"
    assert case.proposal_status == "not_run"
    assert case.patch_applied is False
    assert case.total_logical_llm_calls == 0


def test_provider_failure_short_circuits_proposal(tmp_path: Path) -> None:
    llm = MockLLMClient()
    llm.use_profile("timeout")
    result = _runner(tmp_path, verifier=_FakeVerifier(), llm=llm).run()
    case = result.cases[0]
    assert case.failed_stage == "diagnosis"
    assert case.failure_reason == "provider_failure"
    assert case.outcome == "provider_failed"
    assert case.proposal_status == "not_run"
    assert case.patch_logical_llm_calls == 0
    assert case.diagnostic_logical_llm_calls == 3


def test_failed_cases_remain_in_funnel_denominators() -> None:
    cases = [
        EndToEndCaseResult(case_id="ok", model="m", final_status="passed", repair_success=True, end_to_end_repair_success=True, total_pipeline_duration_ms=10),
        EndToEndCaseResult(case_id="failed", model="m", final_status="failed", failed_stage="diagnosis", failure_reason="provider_failure", total_pipeline_duration_ms=20),
    ]
    aggregate = aggregate_end_to_end_metrics(cases)
    assert aggregate.sample_size == 2
    assert aggregate.repair_success_count == 1
    assert aggregate.repair_success_rate == 0.5
    assert aggregate.diagnosis_completion_rate == 0.0
    assert aggregate.mean_pipeline_duration_ms == 15


def test_artifact_sanitizer_removes_secret_url_env_and_absolute_path() -> None:
    value = sanitize_artifact_value({
        "api_key_configured": True,
        "Authorization": "Bearer abcdefghijklmnop",
        "base": "https://secret.example.test/v1",
        "path": r"D:\Users\Administrator\repo\.env",
        "raw": "raw response and prompt",
    })
    text = json.dumps(value, ensure_ascii=False)
    assert "abcdefghijklmnop" not in text
    assert "https://secret.example.test" not in text
    assert "D:\\Users" not in text
    assert ".env" not in text
    assert value["api_key_configured"] is True


def test_case_artifact_excludes_patch_diff_from_json_model() -> None:
    case = EndToEndCaseResult(
        case_id="sample",
        model="mock-fixed",
        patch_diff="--- a/src/main/App.java\n+++ b/src/main/App.java\n",
    )
    assert "patch_diff" not in case.model_dump(mode="json")
