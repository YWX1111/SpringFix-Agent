"""M5D aggregate metrics and funnel calculations."""

from __future__ import annotations

import statistics
from collections.abc import Sequence

from springfix_agent.repair.e2e_models import EndToEndAggregateMetrics, EndToEndCaseResult


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _optional_total(values: Sequence[int | None]) -> int | None:
    """Sum provider usage only when every executed case reported it."""
    if not values or any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def aggregate_end_to_end_metrics(
    cases: Sequence[EndToEndCaseResult],
) -> EndToEndAggregateMetrics:
    """Aggregate every stage with the full executed sample as denominator."""
    items = list(cases)
    total = len(items)
    durations = [case.total_pipeline_duration_ms for case in items]
    return EndToEndAggregateMetrics(
        sample_size=total,
        cases_total=total,
        cases_completed=sum(case.final_status in {"passed", "failed"} for case in items),
        baseline_verified_count=sum(case.baseline_verified for case in items),
        diagnosis_completed_count=sum(case.diagnosis_completed for case in items),
        diagnosis_pass_count=sum(case.diagnosis_benchmark_pass for case in items),
        proposal_generated_count=sum(case.proposal_generated for case in items),
        proposal_valid_count=sum(case.proposal_valid for case in items),
        patch_applied_count=sum(case.patch_applied for case in items),
        target_test_executed_count=sum(case.target_test_found for case in items),
        repair_success_count=sum(case.end_to_end_repair_success for case in items),
        repair_success_rate=_ratio(
            sum(case.end_to_end_repair_success for case in items), total
        ),
        baseline_reproduction_rate=_ratio(sum(case.baseline_verified for case in items), total),
        diagnosis_completion_rate=_ratio(sum(case.diagnosis_completed for case in items), total),
        diagnosis_benchmark_pass_rate=_ratio(
            sum(case.diagnosis_benchmark_pass for case in items), total
        ),
        proposal_generation_rate=_ratio(sum(case.proposal_generated for case in items), total),
        proposal_validation_rate=_ratio(sum(case.proposal_valid for case in items), total),
        patch_application_rate=_ratio(sum(case.patch_applied for case in items), total),
        target_test_execution_rate=_ratio(sum(case.target_test_found for case in items), total),
        mean_root_cause_keyword_coverage=round(
            statistics.mean(case.root_cause_keyword_coverage for case in items), 4
        )
        if items
        else 0.0,
        mean_evidence_target_recall=round(
            statistics.mean(case.evidence_target_recall for case in items), 4
        )
        if items
        else 0.0,
        total_model_evidence=sum(case.model_evidence_count for case in items),
        total_validated_evidence=sum(case.validated_evidence_count for case in items),
        total_rejected_evidence=sum(case.rejected_evidence_count for case in items),
        total_logical_llm_calls=sum(case.total_logical_llm_calls for case in items),
        total_http_attempts=sum(case.total_http_attempts for case in items),
        total_input_tokens=_optional_total([case.total_input_tokens for case in items]),
        total_output_tokens=_optional_total([case.total_output_tokens for case in items]),
        total_tokens=_optional_total([case.total_tokens for case in items]),
        mean_pipeline_duration_ms=round(statistics.mean(durations), 3) if durations else 0.0,
        p50_pipeline_duration_ms=round(statistics.median(durations), 3) if durations else 0.0,
        max_pipeline_duration_ms=max(durations, default=0),
    )


def funnel_rows(result: object) -> list[tuple[str, int, int]]:
    """Return the fixed M5D funnel in report order."""
    aggregate = result.aggregate  # type: ignore[attr-defined]
    return [
        ("Baseline Reproduced", aggregate.baseline_verified_count, aggregate.cases_total),
        ("Diagnosis Completed", aggregate.diagnosis_completed_count, aggregate.cases_total),
        ("Diagnosis Benchmark Passed", aggregate.diagnosis_pass_count, aggregate.cases_total),
        ("Proposal Generated", aggregate.proposal_generated_count, aggregate.cases_total),
        ("Proposal Validated", aggregate.proposal_valid_count, aggregate.cases_total),
        ("Patch Applied", aggregate.patch_applied_count, aggregate.cases_total),
        ("Target Test Executed", aggregate.target_test_executed_count, aggregate.cases_total),
        ("Repair Successful", aggregate.repair_success_count, aggregate.cases_total),
    ]


__all__ = ["aggregate_end_to_end_metrics", "funnel_rows"]
