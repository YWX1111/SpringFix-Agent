"""Pydantic models for M5A patch proposals and audit results."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceSnippet(BaseModel):
    """A real source range that passed the deterministic evidence gate."""

    model_config = ConfigDict(extra="forbid")

    file: str = Field(min_length=1, max_length=240)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content: str = Field(min_length=1, max_length=8000)
    explanation: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def _ordered_range(self) -> EvidenceSnippet:
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        return self


class PatchEdit(BaseModel):
    """One proposed replacement; it is never applied by M5A."""

    model_config = ConfigDict(extra="forbid")

    file: str = Field(min_length=1, max_length=240)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    old_code: str = Field(min_length=1, max_length=12000)
    new_code: str = Field(min_length=1, max_length=12000)
    rationale: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def _ordered_range(self) -> PatchEdit:
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        return self


class PatchProposal(BaseModel):
    """Structured, review-only patch proposal."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["proposed", "insufficient_evidence", "unsafe_to_propose"]
    summary: str = Field(min_length=1, max_length=1200)
    root_cause_reference: str = Field(min_length=1, max_length=300)
    edits: list[PatchEdit] = Field(default_factory=list, max_length=20)
    verification_steps: list[str] = Field(default_factory=list, max_length=10)
    risks: list[str] = Field(default_factory=list, max_length=10)
    assumptions: list[str] = Field(default_factory=list, max_length=10)


class RejectedPatchEdit(BaseModel):
    """Internal audit record for an edit removed by deterministic validation."""

    model_config = ConfigDict(extra="forbid")

    edit_index: int = Field(ge=0)
    file: str | None = Field(default=None, max_length=240)
    line_range: tuple[int, int] | None = None
    reason: str = Field(min_length=1, max_length=200)
    affected_symbol: str | None = Field(default=None, max_length=120)


class JavaImportCheckResult(BaseModel):
    """Bounded result of the lightweight Java import consistency check."""

    model_config = ConfigDict(extra="forbid")

    introduced_symbols: list[str] = Field(default_factory=list, max_length=100)
    already_resolved_symbols: list[str] = Field(default_factory=list, max_length=100)
    unresolved_symbols: list[str] = Field(default_factory=list, max_length=100)
    status: Literal["pass", "fail", "unknown"]


class PatchValidationResult(BaseModel):
    """Validated proposal plus the internal rejected-edit audit."""

    model_config = ConfigDict(extra="forbid")

    proposal: PatchProposal
    rejected_edits: list[RejectedPatchEdit] = Field(default_factory=list)
    original_edit_count: int = Field(ge=0)
    accepted_edit_count: int = Field(ge=0)
    java_import_checks: list[JavaImportCheckResult] = Field(default_factory=list, max_length=50)

    @property
    def rejected_edit_count(self) -> int:
        """Return the public rejected-edit count."""
        return len(self.rejected_edits)

    @property
    def passed(self) -> bool:
        """Return whether the final proposal is safe to review as proposed."""
        return self.proposal.status == "proposed" and self.accepted_edit_count > 0


# A descriptive alias used by callers that call the input "validated code".
ValidatedEvidence = EvidenceSnippet
