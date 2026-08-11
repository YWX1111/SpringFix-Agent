"""Metric aggregation and redacted Markdown rendering for M4C."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from springfix_agent.benchmark.evaluator import aggregate_metrics
from springfix_agent.benchmark.result_models import (
    AggregateMetrics,
    BenchmarkRunResult,
    CaseResult,
)


def compute_aggregate_metrics(cases: list[CaseResult]) -> AggregateMetrics:
    """Return aggregate metrics using the evaluator's fixed denominators."""
    return aggregate_metrics(cases)


def render_report(result: BenchmarkRunResult) -> str:
    """Render the artifact report from the same models used for ``summary.json``."""
    aggregate = result.aggregate.model_dump(mode="json")
    lines = [
        "# SpringFix Agent Evaluation",
        "",
        "## Evaluation Scope",
        "",
        f"- mode: `{result.mode}`",
        f"- sample size = {result.aggregate.sample_size}",
        f"- include_tests: `{str(result.include_tests).lower()}`",
        "- This is a project-level benchmark, not a production accuracy rate.",
        "- It does not represent all Spring bugs or statistical significance.",
        "",
        "## Environment",
        "",
        "```json",
        json.dumps(result.run_metadata, ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Benchmark Cases",
        "",
        "| Case | Execution | Category | Diagnosis | Case pass | Duration (ms) | LLM calls | HTTP attempts |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for case in result.cases:
        metrics = case.metrics
        lines.append(
            f"| `{case.case_id}` | `{case.execution_status}` | "
            f"{str(metrics.issue_category_match).lower()} | "
            f"{str(metrics.diagnosis_status_match).lower()} | "
            f"{str(metrics.case_pass).lower()} | {case.latency.total_duration_ms} | "
            f"{metrics.logical_llm_calls} | {metrics.http_attempts} |"
        )
    lines.extend(
        [
            "",
            "## Case Results",
            "",
            "```json",
            json.dumps(
                [case.model_dump(mode="json") for case in result.cases],
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            "```",
            "",
            "## Aggregate Metrics",
            "",
            "```json",
            json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True),
            "```",
            "",
            "## Gold Isolation",
            "",
            "- Gold fields are consumed only by the deterministic evaluator after execution.",
            "- The Agent view excludes README/Markdown, target, .git, benchmark, artifacts, and (by default) src/test.",
            "- No prompt, raw model response, API key, Manifest, or absolute sample path is saved.",
            "",
            "## Limitations",
            "",
            "- `case_pass` is this project's workflow acceptance rule, not an industry-standard accuracy measure.",
            "- Mock results validate Runner/Evaluator/Artifact behavior and do not represent model capability.",
            "- Live results depend on the selected model, provider configuration, and current model version.",
            "- Token values are null when the provider did not return usage; no cost estimate is produced.",
            "",
        ]
    )
    return "\n".join(lines)


def write_run_artifacts(result: BenchmarkRunResult, output_dir: Path) -> None:
    """Write only redacted, reproducible artifacts for one run."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "run_metadata.json").write_text(
        json.dumps(result.run_metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    cases_dir = output_dir / "cases"
    cases_dir.mkdir(exist_ok=True)
    for case in result.cases:
        (cases_dir / f"{case.case_id}.json").write_text(
            json.dumps(case.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
    (output_dir / "summary.json").write_text(
        json.dumps(
            {
                "mode": result.mode,
                "include_tests": result.include_tests,
                "aggregate": result.aggregate.model_dump(mode="json"),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(render_report(result), encoding="utf-8")


def result_summary(result: BenchmarkRunResult) -> dict[str, Any]:
    """Return a compact object useful to callers that do not need artifacts."""
    return {
        "mode": result.mode,
        "sample_size": result.aggregate.sample_size,
        "cases_passed": result.aggregate.cases_passed,
        "case_pass_rate": result.aggregate.case_pass_rate,
    }
