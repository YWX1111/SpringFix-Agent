"""Structured M5B patch application and benchmark result models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AppliedEdit(BaseModel):
    """Audit information for one edit written to the temporary copy."""

    model_config = ConfigDict(extra="forbid")

    edit_index: int = Field(ge=0)
    file: str = Field(min_length=1, max_length=240)
    original_start_line: int = Field(ge=1)
    original_end_line: int = Field(ge=1)
    old_code_sha256: str = Field(min_length=64, max_length=64)
    new_code_sha256: str = Field(min_length=64, max_length=64)


class RejectedApplicationEdit(BaseModel):
    """Audit information for an edit rejected during M5B preflight/apply."""

    model_config = ConfigDict(extra="forbid")

    edit_index: int = Field(ge=0)
    file: str | None = Field(default=None, max_length=240)
    reason: str = Field(min_length=1, max_length=200)


class PatchApplicationResult(BaseModel):
    """Result of applying a validated proposal to one isolated copy."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["applied", "partially_applied", "rejected"]
    proposal_status: str = Field(min_length=1)
    edits_requested: int = Field(ge=0)
    edits_applied: int = Field(ge=0)
    edits_rejected: int = Field(ge=0)
    changed_files: list[str] = Field(default_factory=list)
    applied_edits: list[AppliedEdit] = Field(default_factory=list)
    rejected_edits: list[RejectedApplicationEdit] = Field(default_factory=list)
    unified_diff: str = ""
    original_repository_unchanged: bool
    workspace_cleaned: bool | None = None
    workspace_integrity: Literal["verified", "failed"] = "verified"
    application_error: str | None = None


class PatchApplicationCaseMetrics(BaseModel):
    """Redacted per-case M5B metrics."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    proposal_valid: bool
    proposal_status: str
    application_status: Literal["applied", "partially_applied", "rejected"]
    requested_edit_count: int = Field(ge=0)
    applied_edit_count: int = Field(ge=0)
    rejected_edit_count: int = Field(ge=0)
    all_edits_applied: bool
    original_repository_unchanged: bool
    changed_file_count: int = Field(ge=0)
    expected_changed_file_hit: bool | None
    diff_generated: bool
    diff_non_empty: bool
    workspace_cleanup_success: bool
    application_duration_ms: int = Field(ge=0)


class PatchApplicationAggregateMetrics(BaseModel):
    """Aggregate M5B metrics; this is Patch Application, not Repair Success."""

    model_config = ConfigDict(extra="forbid")

    sample_size: int = Field(ge=0)
    proposal_validation_rate: float
    application_success_rate: float
    all_edits_applied_rate: float
    original_repository_integrity_rate: float
    diff_generation_rate: float
    workspace_cleanup_rate: float


class PatchApplicationRunResult(BaseModel):
    """Redacted M5B run result used by the CLI and artifact writer."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["mock"]
    cases: list[PatchApplicationCaseMetrics]
    aggregate: PatchApplicationAggregateMetrics


__all__ = [
    "AppliedEdit",
    "PatchApplicationAggregateMetrics",
    "PatchApplicationCaseMetrics",
    "PatchApplicationResult",
    "PatchApplicationRunResult",
    "RejectedApplicationEdit",
]
