"""Serializable models for the M5D single-shot end-to-end benchmark."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from springfix_agent.repair.verification_models import MavenTestResult

StageStatus = Literal["not_run", "passed", "failed", "skipped"]
CaseOutcome = Literal[
    "complete_success",
    "repair_success_with_diagnostic_metric_miss",
    "diagnosis_failed",
    "proposal_failed",
    "application_failed",
    "verification_failed",
    "provider_failed",
    "infrastructure_failed",
]


class EndToEndCaseResult(BaseModel):
    """Redacted, per-case M5D result.

    Gold values are intentionally absent.  Gold-backed fields are populated by
    the deterministic evaluators after the Agent and Patch Proposal stages.
    """

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    model: str = Field(min_length=1)

    baseline_status: StageStatus = "not_run"
    diagnosis_status: StageStatus = "not_run"
    proposal_status: StageStatus = "not_run"
    application_status: StageStatus = "not_run"
    verification_status: StageStatus = "not_run"
    final_status: StageStatus = "failed"
    failed_stage: str | None = None
    failure_reason: str | None = None
    outcome: CaseOutcome = "infrastructure_failed"

    baseline_verified: bool = False
    diagnosis_completed: bool = False
    diagnosis_benchmark_pass: bool = False
    agent_diagnosis_status: str | None = None
    issue_category_match: bool = False
    diagnosis_status_match: bool = False
    root_cause_keyword_coverage: float = 0.0
    expected_file_hit: bool = False
    expected_file_recall: float = 0.0
    evidence_target_recall: float = 0.0
    model_evidence_count: int = 0
    validated_evidence_count: int = 0
    rejected_evidence_count: int = 0
    valid_evidence_rate: float | None = None
    hallucinated_evidence_reference_rate: float | None = None
    retrieval_expected_file_recall_at_1: bool = False
    retrieval_expected_file_recall_at_3: bool = False
    retrieval_expected_file_recall_at_5: bool = False

    proposal_generated: bool = False
    proposal_valid: bool = False
    proposal_result_status: str | None = None
    edit_count: int = 0
    validated_edit_count: int = 0
    rejected_edit_count: int = 0
    valid_edit_rate: float = 0.0
    evidence_supported_edit_rate: float = 0.0
    acceptable_change_concept_hit: bool = False
    forbidden_file_edits: bool = False

    patch_applied: bool = False
    all_edits_applied: bool = False
    requested_edit_count: int = 0
    applied_edit_count: int = 0
    rejected_application_edit_count: int = 0
    changed_files: list[str] = Field(default_factory=list)
    original_repository_unchanged: bool = False
    diff_generated: bool = False
    workspace_cleanup_success: bool = False

    maven_executed: bool = False
    maven_exit_code: int | None = None
    maven_timeout: bool = False
    surefire_report_found: bool = False
    target_test_found: bool = False
    tests: int = Field(default=0, ge=0)
    failures: int = Field(default=0, ge=0)
    errors: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    compile_success: bool | None = None
    test_integrity_preserved: bool = False
    pom_integrity_preserved: bool = False
    verification_failure_reason: str | None = None
    repair_success: bool = False
    end_to_end_repair_success: bool = False

    diagnostic_logical_llm_calls: int = 0
    patch_logical_llm_calls: int = 0
    total_logical_llm_calls: int = 0
    diagnostic_http_attempts: int = 0
    patch_http_attempts: int = 0
    total_http_attempts: int = 0
    diagnostic_input_tokens: int | None = None
    diagnostic_output_tokens: int | None = None
    patch_input_tokens: int | None = None
    patch_output_tokens: int | None = None
    total_input_tokens: int | None = None
    total_output_tokens: int | None = None
    total_tokens: int | None = None

    baseline_verification_ms: int = Field(default=0, ge=0)
    diagnosis_duration_ms: int = Field(default=0, ge=0)
    patch_proposal_duration_ms: int = Field(default=0, ge=0)
    patch_validation_ms: int = Field(default=0, ge=0)
    patch_application_ms: int = Field(default=0, ge=0)
    maven_verification_ms: int = Field(default=0, ge=0)
    total_pipeline_duration_ms: int = Field(default=0, ge=0)
    issue_parser_ms: int | None = None
    task_planner_ms: int | None = None
    retrieval_ms: int | None = None
    root_cause_analyzer_ms: int | None = None

    baseline_maven: MavenTestResult | None = None
    maven: MavenTestResult = Field(default_factory=lambda: MavenTestResult(executed=False, timed_out=False))
    patch_diff: str | None = Field(default=None, exclude=True)
    warnings: list[str] = Field(default_factory=list)


class EndToEndAggregateMetrics(BaseModel):
    """Aggregate M5D metrics for the cases in one Run."""

    model_config = ConfigDict(extra="forbid")

    sample_size: int = Field(ge=0)
    cases_total: int = Field(ge=0)
    cases_completed: int = Field(ge=0)
    baseline_verified_count: int = Field(ge=0)
    diagnosis_completed_count: int = Field(ge=0)
    diagnosis_pass_count: int = Field(ge=0)
    proposal_generated_count: int = Field(ge=0)
    proposal_valid_count: int = Field(ge=0)
    patch_applied_count: int = Field(ge=0)
    target_test_executed_count: int = Field(ge=0)
    repair_success_count: int = Field(ge=0)
    repair_success_rate: float = Field(ge=0.0, le=1.0)

    baseline_reproduction_rate: float = Field(ge=0.0, le=1.0)
    diagnosis_completion_rate: float = Field(ge=0.0, le=1.0)
    diagnosis_benchmark_pass_rate: float = Field(ge=0.0, le=1.0)
    proposal_generation_rate: float = Field(ge=0.0, le=1.0)
    proposal_validation_rate: float = Field(ge=0.0, le=1.0)
    patch_application_rate: float = Field(ge=0.0, le=1.0)
    target_test_execution_rate: float = Field(ge=0.0, le=1.0)

    mean_root_cause_keyword_coverage: float = Field(ge=0.0, le=1.0)
    mean_evidence_target_recall: float = Field(ge=0.0, le=1.0)
    total_model_evidence: int = Field(ge=0)
    total_validated_evidence: int = Field(ge=0)
    total_rejected_evidence: int = Field(ge=0)

    total_logical_llm_calls: int = Field(ge=0)
    total_http_attempts: int = Field(ge=0)
    total_input_tokens: int | None = None
    total_output_tokens: int | None = None
    total_tokens: int | None = None

    mean_pipeline_duration_ms: float = Field(ge=0.0)
    p50_pipeline_duration_ms: float = Field(ge=0.0)
    max_pipeline_duration_ms: int = Field(ge=0)


class EndToEndRunResult(BaseModel):
    """Complete redacted result returned by the M5D runner."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["mock", "live"]
    run_id: str = Field(min_length=1)
    run_metadata: dict[str, object]
    cases: list[EndToEndCaseResult]
    aggregate: EndToEndAggregateMetrics


__all__ = [
    "CaseOutcome",
    "EndToEndAggregateMetrics",
    "EndToEndCaseResult",
    "EndToEndRunResult",
    "StageStatus",
]
