"""Deterministic Gold-vs-Agent evaluation for M4C.

This module is the only place where Gold fields are consumed.  The runner
passes the final Agent state and trace records here only after the temporary
repository has been removed from the Agent's reach.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import PureWindowsPath
from typing import Literal

from springfix_agent.benchmark.models import BenchmarkCase, EvidenceTarget
from springfix_agent.benchmark.result_models import (
    AggregateMetrics,
    CaseMetrics,
    CaseResult,
    EvidenceRecord,
    LatencyMetrics,
    TokenUsage,
)
from springfix_agent.storage.models import Trace

_INVALID_EVIDENCE_REASONS = frozenset(
    {
        "file_not_in_retrieved_snippets",
        "line_range_outside_snippet",
        "start_line_greater_than_end_line",
    }
)

_CATEGORY_ALIASES: dict[str, str] = {
    "bean_resolution": "dependency_injection",
    "bean_resolution_ambiguity": "dependency_injection",
    "dependency_injection": "dependency_injection",
    "dependency_injection_ambiguity": "dependency_injection",
    "transaction_management": "transaction",
    "transactions": "transaction",
    "configuration_properties": "configuration",
    "config": "configuration",
}
_ABSOLUTE_PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/]|(?<!\w)/)[^\s,;)}\]]+")


def _redact_path_text(value: object) -> str:
    """Remove absolute local paths before any result is serialized."""
    text = str(value or "")
    return _ABSOLUTE_PATH_RE.sub("<absolute-path-redacted>", text)


def _safe_evidence_file(value: object) -> str:
    """Keep relative evidence paths and redact absolute references."""
    text = str(value or "").replace("\\", "/")
    if text.startswith("/") or PureWindowsPath(text).is_absolute():
        return "<absolute-path-redacted>"
    return text


def normalize_category(value: object) -> str:
    """Normalize case, whitespace and the small stable category alias set."""
    text = str(value or "").strip().casefold()
    text = text.replace("-", "_").replace(" ", "_")
    return _CATEGORY_ALIASES.get(text, text)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _optional_sum(values: Iterable[int | None]) -> int | None:
    known = [value for value in values if isinstance(value, int)]
    return sum(known) if known else None


def _trace_payloads(traces: Sequence[Trace], kind: str) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for trace in traces:
        if trace.kind != kind:
            continue
        payloads.append(dict(trace.payload))
    return payloads


def _payload_int(payload: Mapping[str, object], key: str) -> int | None:
    value = payload.get(key)
    return value if isinstance(value, int) else None


def _phase_duration(node_timings: Sequence[Mapping[str, object]], node: str) -> int | None:
    values = [
        _payload_int(timing, "duration_ms")
        for timing in node_timings
        if timing.get("node") == node
    ]
    known = [value for value in values if value is not None]
    return sum(known) if known else None


def _text_for_keywords(rca: Mapping[str, object]) -> str:
    """Build the bounded public RCA text used for keyword coverage."""
    parts: list[str] = [str(rca.get("summary", ""))]
    candidates = rca.get("candidates")
    if isinstance(candidates, list):
        for candidate in candidates[:3]:
            if not isinstance(candidate, Mapping):
                continue
            for key in ("title", "description", "recommended_fix"):
                parts.append(str(candidate.get(key, "")))
            steps = candidate.get("verification_steps")
            if isinstance(steps, list):
                parts.extend(str(step) for step in steps[:5])
    return "\n".join(parts).casefold()


def _keyword_coverage(case: BenchmarkCase, rca: Mapping[str, object]) -> tuple[int, int, float]:
    """Return total, matched and coverage, supporting explicit alias groups."""
    groups = case.keyword_groups
    if groups is None:
        groups = [[keyword] for keyword in case.expected_root_cause_keywords]
    text = _text_for_keywords(rca)
    matched = sum(
        1 for group in groups if any(alias.casefold() in text for alias in group)
    )
    return len(groups), matched, _ratio(matched, len(groups)) if groups else 1.0


def _validated_evidence(rca: Mapping[str, object]) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    candidates = rca.get("candidates")
    if not isinstance(candidates, list):
        return records
    for candidate in candidates[:3]:
        if not isinstance(candidate, Mapping):
            continue
        evidence = candidate.get("evidence")
        if not isinstance(evidence, list):
            continue
        for ref in evidence:
            if not isinstance(ref, Mapping):
                continue
            file = _safe_evidence_file(ref.get("file", ""))
            start = ref.get("start_line")
            end = ref.get("end_line")
            if not file or not isinstance(start, int) or not isinstance(end, int):
                continue
            records.append(
                EvidenceRecord(
                    file=file,
                    start_line=start,
                    end_line=end,
                    explanation=_redact_path_text(ref.get("explanation", "")),
                )
            )
    return records


def _rejected_evidence(rca: Mapping[str, object]) -> list[dict[str, object]]:
    raw = rca.get("rejected_evidence")
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def _target_status(target: EvidenceTarget, evidence: Sequence[EvidenceRecord]) -> str:
    same_file = [item for item in evidence if item.file == target.file]
    if any(
        item.start_line >= target.start_line and item.end_line <= target.end_line
        for item in same_file
    ):
        return "exact_containment"
    if any(
        item.start_line <= target.end_line and target.start_line <= item.end_line
        for item in same_file
    ):
        return "overlap_only"
    return "miss"


def _retrieval_metrics(
    snippets: object, expected_files: Sequence[str]
) -> tuple[bool, bool, bool, int | None]:
    files: list[str] = []
    if isinstance(snippets, list):
        for snippet in snippets:
            if not isinstance(snippet, Mapping):
                continue
            raw_file = snippet.get("file")
            if isinstance(raw_file, str):
                files.append(raw_file.replace("\\", "/"))
    expected = set(expected_files)
    def hit(k: int) -> bool:
        return bool(expected.intersection(files[:k]))

    ranks = [index for index, file in enumerate(files, start=1) if file in expected]
    return hit(1), hit(3), hit(5), min(ranks) if ranks else None


def _candidate_summaries(rca: Mapping[str, object]) -> list[dict[str, object]]:
    """Keep useful model output while avoiding duplicate evidence and Gold data."""
    candidates = rca.get("candidates")
    if not isinstance(candidates, list):
        return []
    result: list[dict[str, object]] = []
    for candidate in candidates[:3]:
        if not isinstance(candidate, Mapping):
            continue
        result.append(
            {
                "title": _redact_path_text(candidate.get("title", "")),
                "description": _redact_path_text(candidate.get("description", "")),
                "confidence": str(candidate.get("confidence", "")),
                "recommended_fix": _redact_path_text(candidate.get("recommended_fix", "")),
            }
        )
    return result


def evaluate_case(
    case: BenchmarkCase,
    state: Mapping[str, object],
    traces: Sequence[Trace],
    *,
    total_duration_ms: int,
    model: str,
    timed_out: bool = False,
) -> CaseResult:
    """Evaluate one final Agent state using only deterministic rules."""
    status = str(state.get("status", "failed"))
    agent_completed = status == "completed" and not timed_out
    execution_status: Literal["agent_completed", "agent_failed", "timeout"] = "timeout" if timed_out else (
        "agent_completed" if agent_completed else "agent_failed"
    )
    issue_analysis = state.get("issue_analysis")
    issue = issue_analysis if isinstance(issue_analysis, Mapping) else {}
    rca_raw = state.get("root_cause_analysis")
    rca = rca_raw if isinstance(rca_raw, Mapping) else {}
    actual_category = str(issue.get("issue_category", "")) or None
    actual_diagnosis = str(rca.get("diagnosis_status", "")) or None
    structural_valid = bool(
        agent_completed
        and isinstance(issue_analysis, Mapping)
        and isinstance(rca_raw, Mapping)
        and actual_diagnosis in {"complete", "partial", "insufficient_evidence"}
    )

    evidence = _validated_evidence(rca)
    rejected = _rejected_evidence(rca)
    invalid_rejected = [
        item
        for item in rejected
        if str(item.get("rejection_reason", "")) in _INVALID_EVIDENCE_REASONS
    ]
    rejection_reasons = Counter(
        str(item.get("rejection_reason", "unknown")) for item in invalid_rejected
    )
    model_evidence_count = len(evidence) + len(invalid_rejected)
    total_keywords, matched_keywords, coverage = _keyword_coverage(case, rca)
    expected_file_set = set(case.expected_files)
    evidence_files = {record.file for record in evidence}
    expected_file_count = len(expected_file_set.intersection(evidence_files))
    target_statuses = [_target_status(target, evidence) for target in case.evidence_targets]
    target_counts = Counter(target_statuses)
    target_hits = sum(status != "miss" for status in target_statuses)
    retrieval_at_1, retrieval_at_3, retrieval_at_5, first_rank = _retrieval_metrics(
        state.get("retrieved_snippets"), case.expected_files
    )

    llm_payloads = _trace_payloads(traces, "llm_call")
    node_payloads = _trace_payloads(traces, "node_timing")
    input_tokens = _optional_sum(
        _payload_int(payload, "input_tokens") for payload in llm_payloads
    )
    output_tokens = _optional_sum(
        _payload_int(payload, "output_tokens") for payload in llm_payloads
    )
    total_tokens = input_tokens + output_tokens if input_tokens is not None and output_tokens is not None else None

    diagnosis_match = agent_completed and actual_diagnosis == case.expected_diagnosis_status
    category_match = agent_completed and normalize_category(actual_category) == normalize_category(
        case.expected_issue_category
    )
    valid_rate = _ratio(len(evidence), model_evidence_count) if model_evidence_count else None
    hallucinated_rate = (
        _ratio(len(invalid_rejected), model_evidence_count) if model_evidence_count else None
    )
    case_pass = (
        agent_completed
        and diagnosis_match
        and coverage >= 0.66
        and bool(expected_file_count)
        and target_hits > 0
        and not invalid_rejected
    )
    metrics = CaseMetrics(
        agent_completed=agent_completed,
        agent_failed=not agent_completed and not timed_out,
        timeout=timed_out,
        structurally_valid=structural_valid,
        diagnosis_status_match=diagnosis_match,
        issue_category_match=category_match,
        root_cause_keywords_total=total_keywords,
        root_cause_keywords_matched=matched_keywords,
        root_cause_keyword_coverage=coverage,
        expected_file_hit=bool(expected_file_count),
        expected_file_recall=_ratio(expected_file_count, len(expected_file_set)),
        evidence_target_hit_count=target_hits,
        evidence_target_total=len(target_statuses),
        evidence_target_recall=_ratio(target_hits, len(target_statuses)),
        model_evidence_count=model_evidence_count,
        validated_evidence_count=len(evidence),
        rejected_evidence_count=len(invalid_rejected),
        valid_evidence_rate=valid_rate,
        hallucinated_evidence_count=len(invalid_rejected),
        hallucinated_evidence_rate=hallucinated_rate,
        expected_file_retrieved_at_1=retrieval_at_1,
        expected_file_retrieved_at_3=retrieval_at_3,
        expected_file_retrieved_at_5=retrieval_at_5,
        first_expected_file_rank=first_rank,
        logical_llm_calls=len(llm_payloads),
        http_attempts=sum(
            1
            if payload.get("provider") == "mock"
            else max(1, _payload_int(payload, "attempt") or 1)
            for payload in llm_payloads
        ),
        case_pass=case_pass,
    )
    latency = LatencyMetrics(
        total_duration_ms=max(0, total_duration_ms),
        issue_parser_ms=_phase_duration(node_payloads, "issue_parser"),
        task_planner_ms=_phase_duration(node_payloads, "task_planner"),
        retrieval_ms=_phase_duration(node_payloads, "retrieve_code"),
        root_cause_analyzer_ms=_phase_duration(node_payloads, "root_cause_analyzer"),
        report_build_ms=_phase_duration(node_payloads, "build_diagnostic_report"),
    )
    raw_warnings = state.get("warnings")
    warnings = (
        [str(item) for item in raw_warnings if isinstance(item, str)]
        if isinstance(raw_warnings, list)
        else []
    )
    return CaseResult(
        case_id=case.case_id,
        model=model,
        execution_status=execution_status,
        issue_category=actual_category,
        diagnosis_status=actual_diagnosis,
        root_cause_summary=_redact_path_text(rca.get("summary", "")) or None,
        candidates=_candidate_summaries(rca),
        evidence=evidence,
        evidence_target_match_counts={
            "exact_containment": target_counts.get("exact_containment", 0),
            "overlap_only": target_counts.get("overlap_only", 0),
            "miss": target_counts.get("miss", 0),
        },
        tokens=TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        ),
        latency=latency,
        metrics=metrics,
        warnings=[_redact_path_text(item) for item in warnings],
        rejected_evidence_reasons=dict(rejection_reasons),
    )


def aggregate_metrics(cases: Sequence[CaseResult]) -> AggregateMetrics:
    """Aggregate all executed cases; failed cases remain in every denominator."""
    total = len(cases)
    completed = sum(case.metrics.agent_completed for case in cases)
    passed = sum(case.metrics.case_pass for case in cases)
    durations = [case.latency.total_duration_ms for case in cases]
    model_evidence = sum(case.metrics.model_evidence_count for case in cases)
    validated = sum(case.metrics.validated_evidence_count for case in cases)
    rejected = sum(case.metrics.rejected_evidence_count for case in cases)
    input_tokens = _optional_sum(case.tokens.input_tokens for case in cases)
    output_tokens = _optional_sum(case.tokens.output_tokens for case in cases)
    return AggregateMetrics(
        sample_size=total,
        cases_total=total,
        cases_completed=completed,
        cases_structurally_valid=sum(case.metrics.structurally_valid for case in cases),
        cases_passed=passed,
        case_pass_rate=_ratio(passed, total),
        issue_category_match_rate=_ratio(
            sum(case.metrics.issue_category_match for case in cases), total
        ),
        diagnosis_status_match_rate=_ratio(
            sum(case.metrics.diagnosis_status_match for case in cases), total
        ),
        mean_root_cause_keyword_coverage=round(
            statistics.mean(case.metrics.root_cause_keyword_coverage for case in cases), 4
        )
        if cases
        else 0.0,
        expected_file_hit_rate=_ratio(
            sum(case.metrics.expected_file_hit for case in cases), total
        ),
        mean_evidence_target_recall=round(
            statistics.mean(case.metrics.evidence_target_recall for case in cases), 4
        )
        if cases
        else 0.0,
        total_model_evidence=model_evidence,
        total_validated_evidence=validated,
        total_rejected_evidence=rejected,
        valid_evidence_rate=_ratio(validated, model_evidence) if model_evidence else None,
        hallucinated_evidence_reference_rate=_ratio(rejected, model_evidence)
        if model_evidence
        else None,
        retrieval_expected_file_recall_at_1=_ratio(
            sum(case.metrics.expected_file_retrieved_at_1 for case in cases), total
        ),
        retrieval_expected_file_recall_at_3=_ratio(
            sum(case.metrics.expected_file_retrieved_at_3 for case in cases), total
        ),
        retrieval_expected_file_recall_at_5=_ratio(
            sum(case.metrics.expected_file_retrieved_at_5 for case in cases), total
        ),
        total_logical_llm_calls=sum(case.metrics.logical_llm_calls for case in cases),
        total_http_attempts=sum(case.metrics.http_attempts for case in cases),
        total_input_tokens=input_tokens,
        total_output_tokens=output_tokens,
        mean_case_duration_ms=round(statistics.mean(durations), 3) if durations else 0.0,
        p50_case_duration_ms=round(statistics.median(durations), 3) if durations else 0.0,
        max_case_duration_ms=max(durations, default=0),
    )


evaluate = evaluate_case
