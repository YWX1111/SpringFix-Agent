"""Structured results for the isolated M5C repair verification stage."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VerificationStatus = Literal["success", "timeout", "failed", "not_executed"]


class MavenFailureClassification(BaseModel):
    """Deterministic, redacted classification of one Maven invocation."""

    model_config = ConfigDict(extra="forbid")

    lifecycle_phase: Literal[
        "dependency_resolution",
        "validate",
        "compile",
        "test_compile",
        "surefire",
        "test_runtime",
        "plugin",
        "unknown",
    ]
    failure_category: Literal[
        "dependency_resolution_failure",
        "main_compile_failure",
        "test_compile_failure",
        "surefire_start_failure",
        "test_failure",
        "test_error",
        "plugin_failure",
        "timeout",
        "success",
        "unknown",
    ]
    first_actionable_error: str | None = Field(default=None, max_length=200)
    affected_file: str | None = Field(default=None, max_length=240)
    affected_symbol: str | None = Field(default=None, max_length=200)
    surefire_started: bool | None = None


class MavenTestResult(BaseModel):
    """Bounded result of one fixed Maven invocation."""

    model_config = ConfigDict(extra="forbid")

    executed: bool
    timed_out: bool
    exit_code: int | None = None
    tests: int = Field(default=0, ge=0)
    failures: int = Field(default=0, ge=0)
    errors: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    target_test_found: bool = False
    surefire_report_found: bool = False
    surefire_started: bool | None = None
    maven_failure_classification: MavenFailureClassification | None = None
    duration_ms: int = Field(default=0, ge=0)
    stdout_tail: str = Field(default="", max_length=4096)
    stderr_tail: str = Field(default="", max_length=4096)


class BaselineVerificationResult(BaseModel):
    """Verification-only summary for the original, intentionally broken sample."""

    model_config = ConfigDict(extra="forbid")

    verified: bool
    maven_result: MavenTestResult
    failure_reason: str | None = None


class RepairVerificationResult(BaseModel):
    """Full redacted result for one M5C case."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    baseline_verified: bool
    proposal_valid: bool
    patch_applied: bool
    all_edits_applied: bool = False
    original_repository_unchanged: bool
    test_integrity_verified: bool = False
    pom_integrity_verified: bool = False
    source_integrity_verified: bool = False
    maven_result: MavenTestResult
    repair_success: bool
    failure_reason: str | None = None
    verification_status: VerificationStatus
    workspace_cleanup_success: bool
    verification_duration_ms: int = Field(default=0, ge=0)


class RepairCaseMetrics(BaseModel):
    """Stable per-case M5C metrics used for aggregate reporting."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    baseline_verified: bool
    proposal_valid: bool
    patch_applied: bool
    all_edits_applied: bool
    original_repository_unchanged: bool
    maven_executed: bool
    maven_exit_code: int | None
    maven_timed_out: bool
    target_test_found: bool
    tests: int = Field(ge=0)
    failures: int = Field(ge=0)
    errors: int = Field(ge=0)
    skipped: int = Field(ge=0)
    repair_success: bool
    failure_reason: str | None = None
    verification_status: VerificationStatus
    verification_duration_ms: int = Field(ge=0)
    workspace_cleanup_success: bool


class RepairAggregateMetrics(BaseModel):
    """Aggregate metrics for the controlled benchmark sample."""

    model_config = ConfigDict(extra="forbid")

    sample_size: int = Field(ge=0)
    baseline_reproduction_rate: float = Field(ge=0.0, le=1.0)
    patch_application_rate: float = Field(ge=0.0, le=1.0)
    maven_execution_rate: float = Field(ge=0.0, le=1.0)
    target_test_execution_rate: float = Field(ge=0.0, le=1.0)
    repair_success_rate: float = Field(ge=0.0, le=1.0)
    workspace_integrity_rate: float = Field(ge=0.0, le=1.0)
    workspace_cleanup_rate: float = Field(ge=0.0, le=1.0)
    mean_verification_duration_ms: float = Field(ge=0.0)
    p50_verification_duration_ms: float = Field(ge=0.0)
    max_verification_duration_ms: int = Field(ge=0)


class RepairVerificationRunResult(BaseModel):
    """Redacted M5C run result."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["mock"]
    cases: list[RepairCaseMetrics]
    aggregate: RepairAggregateMetrics


__all__ = [
    "BaselineVerificationResult",
    "MavenFailureClassification",
    "MavenTestResult",
    "RepairAggregateMetrics",
    "RepairCaseMetrics",
    "RepairVerificationResult",
    "RepairVerificationRunResult",
    "VerificationStatus",
]
