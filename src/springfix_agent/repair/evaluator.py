"""Deterministic Repair Proposal benchmark evaluator."""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from springfix_agent.repair.models import PatchValidationResult
from springfix_agent.repair.observability import ProposalGenerationAudit


def _normalise(value: str) -> str:
    return value.replace("\\", "/").strip().casefold()


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


class RepairGold(BaseModel):
    """Gold concepts used only after proposal generation."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    acceptable_files: list[str] = Field(min_length=1)
    acceptable_change_concepts: list[str] = Field(min_length=1)
    forbidden_files: list[str] = Field(default_factory=list)

    @field_validator("acceptable_files", "forbidden_files", mode="before")
    @classmethod
    def _normalize_paths(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            raise ValueError("file lists must be lists")
        return [str(item).replace("\\", "/").strip() for item in value if str(item).strip()]


class RepairCaseMetrics(BaseModel):
    """Per-case deterministic Patch Proposal metrics."""

    model_config = ConfigDict(extra="forbid")

    proposal_generated: bool
    proposal_status: Literal["proposed", "insufficient_evidence", "unsafe_to_propose"]
    proposal_validation_passed: bool
    edit_count: int = Field(ge=0)
    validated_edit_count: int = Field(ge=0)
    rejected_edit_count: int = Field(ge=0)
    valid_edit_rate: float
    allowed_file_rate: float
    evidence_supported_edit_rate: float
    old_code_match_rate: float
    acceptable_change_concept_hit: bool
    forbidden_file_edits: bool
    diagnostic_llm_calls: int = Field(ge=0)
    patch_llm_calls: int = Field(ge=0)
    logical_llm_calls: int = Field(ge=0)
    http_attempts: int = Field(ge=0)
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int = Field(ge=0)


class RepairCaseResult(BaseModel):
    """Redacted per-case result; it contains no Gold payload."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    model: str
    proposal_status: Literal["proposed", "insufficient_evidence", "unsafe_to_propose"]
    proposal_generation_audit: ProposalGenerationAudit | None = None
    import_check_status: Literal["not_run", "pass", "fail", "unknown"] = "not_run"
    introduced_symbols: list[str] = Field(default_factory=list)
    unresolved_symbols: list[str] = Field(default_factory=list)
    summary: str
    edits: list[dict[str, object]] = Field(default_factory=list)
    verification_steps: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    rejected_edit_reasons: dict[str, int] = Field(default_factory=dict)
    metrics: RepairCaseMetrics


class RepairAggregateMetrics(BaseModel):
    """Aggregate Patch Proposal metrics for one sample."""

    model_config = ConfigDict(extra="forbid")

    sample_size: int
    proposal_generation_rate: float
    proposal_validation_rate: float
    mean_valid_edit_rate: float
    evidence_supported_edit_rate: float
    acceptable_change_concept_hit_rate: float
    unsafe_proposal_rate: float
    total_edits: int
    total_validated_edits: int
    total_rejected_edits: int
    total_diagnostic_llm_calls: int
    total_patch_llm_calls: int
    total_logical_llm_calls: int
    total_http_attempts: int
    total_input_tokens: int | None
    total_output_tokens: int | None
    mean_duration_ms: float


class RepairBenchmarkRunResult(BaseModel):
    """In-memory M5A run result."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["mock", "live"]
    run_metadata: dict[str, object]
    cases: list[RepairCaseResult]
    aggregate: RepairAggregateMetrics


def _concept_hit(gold: RepairGold, proposal_text: str) -> bool:
    text = proposal_text.casefold()
    aliases: list[str] = []
    for concept in gold.acceptable_change_concepts:
        normalized = concept.casefold()
        aliases.append(normalized)
        if "qualifier" in normalized:
            aliases.append("@qualifier")
        if "primary" in normalized:
            aliases.append("@primary")
        if "springfix.email" in normalized or "springfix.mail" in normalized:
            aliases.extend(["springfix.email", "springfix.mail"])
        if "prefix" in normalized or "hierarchy" in normalized:
            aliases.extend(["prefix", "hierarchy"])
        if "proxy" in normalized or "transaction" in normalized:
            aliases.extend(["proxy", "transactional"])
    return any(alias and alias in text for alias in aliases)


def _forbidden_file(file: str, forbidden_files: Iterable[str]) -> bool:
    normalized = _normalise(file)
    return any(
        normalized == _normalise(forbidden)
        or normalized.startswith(_normalise(forbidden).rstrip("/") + "/")
        or _normalise(forbidden) in {"src/test", "target", "benchmark"}
        and _normalise(forbidden) in normalized
        for forbidden in forbidden_files
    )


def evaluate_repair_proposal(
    gold: RepairGold,
    validation: PatchValidationResult,
    *,
    model: str,
    diagnostic_llm_calls: int,
    patch_llm_calls: int,
    http_attempts: int,
    input_tokens: int | None,
    output_tokens: int | None,
    duration_ms: int,
    proposal_generation_audit: ProposalGenerationAudit | None = None,
) -> RepairCaseResult:
    """Evaluate concept/path/safety metrics without a model judge."""
    proposal = validation.proposal
    edits = proposal.edits
    acceptable = {_normalise(file) for file in gold.acceptable_files}
    allowed_count = sum(1 for edit in edits if _normalise(edit.file) in acceptable)
    forbidden = any(
        _forbidden_file(edit.file, gold.forbidden_files) for edit in edits
    ) or any(
        _forbidden_file(rejected.file or "", gold.forbidden_files)
        for rejected in validation.rejected_edits
    )
    text_parts = [proposal.summary, proposal.root_cause_reference]
    for edit in edits:
        text_parts.extend([edit.rationale, edit.new_code])
    original_edit_count = validation.original_edit_count
    valid_rate = _ratio(validation.accepted_edit_count, original_edit_count)
    result_metrics = RepairCaseMetrics(
        proposal_generated=proposal.status == "proposed",
        proposal_status=proposal.status,
        proposal_validation_passed=validation.passed and not forbidden,
        edit_count=original_edit_count,
        validated_edit_count=validation.accepted_edit_count,
        rejected_edit_count=validation.rejected_edit_count,
        valid_edit_rate=valid_rate,
        allowed_file_rate=_ratio(allowed_count, validation.accepted_edit_count),
        evidence_supported_edit_rate=valid_rate,
        old_code_match_rate=valid_rate,
        acceptable_change_concept_hit=_concept_hit(gold, "\n".join(text_parts)),
        forbidden_file_edits=forbidden,
        diagnostic_llm_calls=diagnostic_llm_calls,
        patch_llm_calls=patch_llm_calls,
        logical_llm_calls=diagnostic_llm_calls + patch_llm_calls,
        http_attempts=http_attempts,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration_ms=max(0, duration_ms),
    )
    reasons: dict[str, int] = {}
    for rejected in validation.rejected_edits:
        reasons[rejected.reason] = reasons.get(rejected.reason, 0) + 1
    return RepairCaseResult(
        case_id=gold.case_id,
        model=model,
        proposal_status=proposal.status,
        summary=proposal.summary[:1200],
        edits=[edit.model_dump() for edit in edits],
        verification_steps=proposal.verification_steps,
        risks=proposal.risks,
        assumptions=proposal.assumptions,
        rejected_edit_reasons=reasons,
        proposal_generation_audit=proposal_generation_audit,
        import_check_status=(
            "fail"
            if any(check.status == "fail" for check in validation.java_import_checks)
            else "unknown"
            if any(check.status == "unknown" for check in validation.java_import_checks)
            else "pass"
            if validation.java_import_checks
            else "not_run"
        ),
        introduced_symbols=sorted(
            {
                symbol
                for check in validation.java_import_checks
                for symbol in check.introduced_symbols
            }
        ),
        unresolved_symbols=sorted(
            {
                symbol
                for check in validation.java_import_checks
                for symbol in check.unresolved_symbols
            }
        ),
        metrics=result_metrics,
    )


def aggregate_repair_metrics(cases: Sequence[RepairCaseResult]) -> RepairAggregateMetrics:
    """Aggregate metrics using all executed cases as denominators."""
    size = len(cases)
    metrics = [case.metrics for case in cases]
    input_values = [item.input_tokens for item in metrics if item.input_tokens is not None]
    output_values = [item.output_tokens for item in metrics if item.output_tokens is not None]
    return RepairAggregateMetrics(
        sample_size=size,
        proposal_generation_rate=_ratio(sum(item.proposal_generated for item in metrics), size),
        proposal_validation_rate=_ratio(
            sum(item.proposal_validation_passed for item in metrics), size
        ),
        mean_valid_edit_rate=round(statistics.mean(item.valid_edit_rate for item in metrics), 4)
        if metrics
        else 0.0,
        evidence_supported_edit_rate=_ratio(
            sum(item.validated_edit_count for item in metrics),
            sum(item.edit_count for item in metrics),
        ),
        acceptable_change_concept_hit_rate=_ratio(
            sum(item.acceptable_change_concept_hit for item in metrics), size
        ),
        unsafe_proposal_rate=_ratio(
            sum(item.proposal_status == "unsafe_to_propose" for item in metrics), size
        ),
        total_edits=sum(item.edit_count for item in metrics),
        total_validated_edits=sum(item.validated_edit_count for item in metrics),
        total_rejected_edits=sum(item.rejected_edit_count for item in metrics),
        total_diagnostic_llm_calls=sum(item.diagnostic_llm_calls for item in metrics),
        total_patch_llm_calls=sum(item.patch_llm_calls for item in metrics),
        total_logical_llm_calls=sum(item.logical_llm_calls for item in metrics),
        total_http_attempts=sum(item.http_attempts for item in metrics),
        total_input_tokens=sum(input_values) if input_values and len(input_values) == size else None,
        total_output_tokens=sum(output_values) if output_values and len(output_values) == size else None,
        mean_duration_ms=round(statistics.mean(item.duration_ms for item in metrics), 3)
        if metrics
        else 0.0,
    )
