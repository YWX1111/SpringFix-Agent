"""Structured Pydantic schemas for every LLM output.

These models are the only valid way to consume an LLM response. Node
code must call ``LLMClient.invoke_structured(..., response_model=...)``
and work with the typed model instance — never raw dicts.

Constraints:

    - IssueAnalysis.extracted_symbols ≤ 10.
    - IssueAnalysis.search_terms ≤ 15.
    - InvestigationPlan.steps ∈ [3, 6].
    - InvestigationStep IDs are 1-based, strictly increasing.
    - RootCauseAnalysis.candidates ∈ [0, 3].
    - EvidenceReference.file must correspond to a snippet file.
    - EvidenceReference.[start_line, end_line] must fall within the
      snippet's line_range.
    - diagnosis_status ∈ {complete, partial, insufficient_evidence}.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator


class IssueAnalysis(BaseModel):
    """Output of the IssueParser node."""

    issue_category: Literal[
        "transaction",
        "dependency_injection",
        "startup",
        "configuration",
        "database",
        "cache",
        "concurrency",
        "network",
        "unknown",
    ] = Field(
        description="Coarse problem category inferred from the description and log.",
    )
    summary: str = Field(min_length=1, max_length=400)
    symptoms: list[str] = Field(default_factory=list)
    exception_types: list[str] = Field(default_factory=list)
    extracted_symbols: list[str] = Field(default_factory=list)
    search_terms: list[str] = Field(default_factory=list)
    spring_concepts: list[str] = Field(default_factory=list)

    @field_validator("symptoms", "exception_types", mode="before")
    @classmethod
    def _limit_str(cls, v: object) -> list[str]:
        if not isinstance(v, list):
            return []
        out: list[str] = []
        for item in v:
            if isinstance(item, str):
                trimmed = item.strip()[:200]
                if trimmed:
                    out.append(trimmed)
            if len(out) >= 10:
                break
        return out

    @field_validator("extracted_symbols", mode="before")
    @classmethod
    def _trim_extracted(cls, v: object) -> list[str]:
        if not isinstance(v, list):
            return []
        out: list[str] = []
        for item in v:
            if isinstance(item, str):
                trimmed = item.strip()[:64]
                if trimmed:
                    out.append(trimmed)
            if len(out) >= 10:
                break
        return out

    @field_validator("search_terms", mode="before")
    @classmethod
    def _trim_search(cls, v: object) -> list[str]:
        if not isinstance(v, list):
            return []
        out: list[str] = []
        for item in v:
            if isinstance(item, str):
                trimmed = item.strip()[:64]
                if trimmed:
                    out.append(trimmed)
            if len(out) >= 15:
                break
        return out

    @field_validator("spring_concepts", mode="before")
    @classmethod
    def _trim_concepts(cls, v: object) -> list[str]:
        if not isinstance(v, list):
            return []
        out: list[str] = []
        for item in v:
            if isinstance(item, str):
                trimmed = item.strip()[:64]
                if trimmed:
                    out.append(trimmed)
            if len(out) >= 10:
                break
        return out


class InvestigationStep(BaseModel):
    """One step inside an InvestigationPlan."""

    step_id: int = Field(ge=1, description="1-based step id, strictly increasing.")
    objective: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=200)
    search_terms: list[str] = Field(default_factory=list)
    target_symbols: list[str] = Field(default_factory=list)
    expected_evidence: list[str] = Field(default_factory=list)

    @field_validator("search_terms", mode="before")
    @classmethod
    def _trim_search(cls, v: object) -> list[str]:
        if not isinstance(v, list):
            return []
        out: list[str] = []
        for item in v:
            if isinstance(item, str):
                trimmed = item.strip()[:64]
                if trimmed:
                    out.append(trimmed)
            if len(out) >= 8:
                break
        return out

    @field_validator("target_symbols", "expected_evidence", mode="before")
    @classmethod
    def _trim_symbols(cls, v: object) -> list[str]:
        if not isinstance(v, list):
            return []
        out: list[str] = []
        for item in v:
            if isinstance(item, str):
                trimmed = item.strip()[:64]
                if trimmed:
                    out.append(trimmed)
            if len(out) >= 6:
                break
        return out

    @field_validator("objective", "rationale")
    @classmethod
    def _no_shell(cls, v: str) -> str:
        forbidden_tokens = ("mvn ", "mvn\t", "bash ", "sh ", "sudo ", "rm -rf", "curl ")
        lowered = v.lower()
        if any(tok in lowered for tok in forbidden_tokens):
            raise ValueError("step must not ask to run shell commands")
        return v


class InvestigationPlan(BaseModel):
    """Output of the TaskPlanner node."""

    steps: list[InvestigationStep] = Field(min_length=3, max_length=6)

    @field_validator("steps")
    @classmethod
    def _strict_ids(cls, v: list[InvestigationStep]) -> list[InvestigationStep]:
        if not v:
            return v
        ids = [s.step_id for s in v]
        if ids != list(range(1, len(v) + 1)):
            raise ValueError("step_id must be 1-based and strictly increasing")
        return v


class EvidenceReference(BaseModel):
    """A single pointer to a retrieved snippet."""

    file: str = Field(min_length=1, max_length=200)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    explanation: str = Field(min_length=1, max_length=400)

    @field_validator("end_line")
    @classmethod
    def _end_ge_start(cls, v: int, info: ValidationInfo) -> int:
        start = info.data.get("start_line")
        if isinstance(start, int) and v < start:
            raise ValueError("end_line must be >= start_line")
        return v


class RootCauseCandidate(BaseModel):
    """A single root-cause hypothesis with evidence references."""

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=600)
    confidence: Literal["low", "medium", "high"]
    evidence: list[EvidenceReference] = Field(min_length=1)
    recommended_fix: str = Field(min_length=1, max_length=600)
    verification_steps: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("recommended_fix")
    @classmethod
    def _no_shell_in_fix(cls, v: str) -> str:
        forbidden = ("mvn ", "mvn\t", "bash ", "sh ", "sudo ", "rm -rf")
        lowered = v.lower()
        if any(tok in lowered for tok in forbidden):
            raise ValueError("recommended_fix must not run shell commands")
        return v

    @field_validator("verification_steps", mode="before")
    @classmethod
    def _no_shell_in_verify(cls, v: object) -> list[str]:
        if not isinstance(v, list):
            return []
        forbidden = ("mvn ", "mvn\t", "bash ", "sh ", "sudo ", "rm -rf", "curl ")
        out: list[str] = []
        for item in v:
            if isinstance(item, str):
                trimmed = item.strip()
                if not trimmed:
                    continue
                if any(tok in trimmed.lower() for tok in forbidden):
                    raise ValueError("verification_steps must not execute shell commands")
                out.append(trimmed[:200])
            if len(out) >= 5:
                break
        return out


class RootCauseAnalysis(BaseModel):
    """Output of the RootCauseAnalyzer node."""

    diagnosis_status: Literal["complete", "partial", "insufficient_evidence"]
    summary: str = Field(min_length=1, max_length=400)
    candidates: list[RootCauseCandidate] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    rejected_evidence: list[dict[str, object]] = Field(
        default_factory=list,
        description="Audit trail of evidence references rejected by the secondary "
        "business validator. Each record carries candidate_index, "
        "evidence_index, rejection_reason, referenced_file and "
        "referenced_line_range. Never contains full code bodies.",
    )

    model_config = {"extra": "ignore"}

    @model_validator(mode="after")
    def _enforce_status_consistency(self) -> RootCauseAnalysis:
        if self.diagnosis_status == "insufficient_evidence" and self.candidates:
            self.candidates = []
        return self

    @field_validator("candidates", mode="before")
    @classmethod
    def _trim_candidates(cls, v: object) -> list[RootCauseCandidate]:
        if not isinstance(v, list):
            return []
        return v[:3]

    @field_validator("missing_information", mode="before")
    @classmethod
    def _trim_missing(cls, v: object) -> list[str]:
        if not isinstance(v, list):
            return []
        out: list[str] = []
        for item in v:
            if isinstance(item, str):
                trimmed = item.strip()[:200]
                if trimmed:
                    out.append(trimmed)
            if len(out) >= 8:
                break
        return out
