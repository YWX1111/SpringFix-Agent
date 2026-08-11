"""Serializable, redacted models for M4C benchmark output."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TokenUsage(BaseModel):
    """Provider-reported token usage; missing provider fields stay ``null``."""

    model_config = ConfigDict(extra="forbid")

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class LatencyMetrics(BaseModel):
    """End-to-end and graph phase latency in milliseconds."""

    model_config = ConfigDict(extra="forbid")

    total_duration_ms: int
    issue_parser_ms: int | None = None
    task_planner_ms: int | None = None
    retrieval_ms: int | None = None
    root_cause_analyzer_ms: int | None = None
    report_build_ms: int | None = None


class EvidenceRecord(BaseModel):
    """A model evidence reference that survived deterministic validation."""

    model_config = ConfigDict(extra="forbid")

    file: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    explanation: str = ""


class EvidenceTargetResult(BaseModel):
    """Comparison of one gold target with validated model evidence."""

    model_config = ConfigDict(extra="forbid")

    file: str
    start_line: int
    end_line: int
    status: Literal["exact_containment", "overlap_only", "miss"]


class CaseMetrics(BaseModel):
    """All deterministic metrics for one case."""

    model_config = ConfigDict(extra="forbid")

    agent_completed: bool
    agent_failed: bool
    timeout: bool
    structurally_valid: bool
    diagnosis_status_match: bool
    issue_category_match: bool
    root_cause_keywords_total: int
    root_cause_keywords_matched: int
    root_cause_keyword_coverage: float
    expected_file_hit: bool
    expected_file_recall: float
    evidence_target_hit_count: int
    evidence_target_total: int
    evidence_target_recall: float
    model_evidence_count: int
    validated_evidence_count: int
    rejected_evidence_count: int
    valid_evidence_rate: float | None
    hallucinated_evidence_count: int
    hallucinated_evidence_rate: float | None
    expected_file_retrieved_at_1: bool
    expected_file_retrieved_at_3: bool
    expected_file_retrieved_at_5: bool
    first_expected_file_rank: int | None
    logical_llm_calls: int
    http_attempts: int
    case_pass: bool


class CaseResult(BaseModel):
    """Redacted per-case result. It deliberately contains no Gold fields."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    model: str
    execution_status: Literal["agent_completed", "agent_failed", "timeout"]
    issue_category: str | None = None
    diagnosis_status: str | None = None
    root_cause_summary: str | None = None
    candidates: list[dict[str, object]] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    evidence_target_match_counts: dict[str, int] = Field(default_factory=dict)
    tokens: TokenUsage = Field(default_factory=TokenUsage)
    latency: LatencyMetrics
    metrics: CaseMetrics
    warnings: list[str] = Field(default_factory=list)
    rejected_evidence_reasons: dict[str, int] = Field(default_factory=dict)


class AggregateMetrics(BaseModel):
    """Aggregate metrics for exactly the cases executed in one run."""

    model_config = ConfigDict(extra="forbid")

    sample_size: int
    cases_total: int
    cases_completed: int
    cases_structurally_valid: int
    cases_passed: int
    case_pass_rate: float
    issue_category_match_rate: float
    diagnosis_status_match_rate: float
    mean_root_cause_keyword_coverage: float
    expected_file_hit_rate: float
    mean_evidence_target_recall: float
    total_model_evidence: int
    total_validated_evidence: int
    total_rejected_evidence: int
    valid_evidence_rate: float | None
    hallucinated_evidence_reference_rate: float | None
    retrieval_expected_file_recall_at_1: float
    retrieval_expected_file_recall_at_3: float
    retrieval_expected_file_recall_at_5: float
    total_logical_llm_calls: int
    total_http_attempts: int
    total_input_tokens: int | None
    total_output_tokens: int | None
    mean_case_duration_ms: float
    p50_case_duration_ms: float
    max_case_duration_ms: int


class BenchmarkRunResult(BaseModel):
    """In-memory result returned by the runner before artifact serialization."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["mock", "live"]
    include_tests: bool
    run_metadata: dict[str, object]
    cases: list[CaseResult]
    aggregate: AggregateMetrics
