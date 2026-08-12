"""Metrics and sanitized artifacts for the M5C verification runner."""

from __future__ import annotations

import json
import statistics
from collections.abc import Mapping, Sequence
from pathlib import Path

from springfix_agent.repair.verification_models import (
    RepairAggregateMetrics,
    RepairCaseMetrics,
    RepairVerificationRunResult,
)


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def aggregate_repair_metrics(cases: Sequence[RepairCaseMetrics]) -> RepairAggregateMetrics:
    """Aggregate M5C metrics using the executed cases as denominators."""
    size = len(cases)
    durations = [case.verification_duration_ms for case in cases]
    return RepairAggregateMetrics(
        sample_size=size,
        baseline_reproduction_rate=_ratio(sum(case.baseline_verified for case in cases), size),
        patch_application_rate=_ratio(sum(case.patch_applied for case in cases), size),
        maven_execution_rate=_ratio(sum(case.maven_executed for case in cases), size),
        target_test_execution_rate=_ratio(sum(case.target_test_found for case in cases), size),
        repair_success_rate=_ratio(sum(case.repair_success for case in cases), size),
        workspace_integrity_rate=_ratio(
            sum(case.original_repository_unchanged for case in cases), size
        ),
        workspace_cleanup_rate=_ratio(
            sum(case.workspace_cleanup_success for case in cases), size
        ),
        mean_verification_duration_ms=round(statistics.mean(durations), 3) if durations else 0.0,
        p50_verification_duration_ms=round(statistics.median(durations), 3) if durations else 0.0,
        max_verification_duration_ms=max(durations, default=0),
    )


def _safe_json(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_repair_verification_report(result: RepairVerificationRunResult) -> str:
    """Render a report with deterministic public fields only."""
    lines = [
        "# SpringFix M5C Repair Verification",
        "",
        f"- mode: `{result.mode}`",
        f"- sample_size: `{result.aggregate.sample_size}`",
        "- Repair Success Rate is measured only on the current 3-case controlled benchmark.",
        "- M5C restricts command type, cwd, environment, timeout, and artifact handling.",
        "- M5C does not provide OS/container/network sandbox isolation.",
        "",
        "## Cases",
        "",
        "| Case | Baseline | Patch | Maven | Target | Tests | F | E | S | Repair | Reason | Duration (ms) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|",
    ]
    for case in result.cases:
        lines.append(
            f"| `{case.case_id}` | {str(case.baseline_verified).lower()} | "
            f"{str(case.patch_applied).lower()} | {str(case.maven_executed).lower()} | "
            f"{str(case.target_test_found).lower()} | {case.tests} | {case.failures} | "
            f"{case.errors} | {case.skipped} | {str(case.repair_success).lower()} | "
            f"`{case.failure_reason or 'none'}` | {case.verification_duration_ms} |"
        )
    lines.extend(
        [
            "",
            "## Aggregate Metrics",
            "",
            "```json",
            json.dumps(result.aggregate.model_dump(), ensure_ascii=False, indent=2, sort_keys=True),
            "```",
            "",
            "## Repair Success Definition",
            "",
            "Baseline bug reproduced, validated patch applied, original/test/pom integrity "
            "preserved, target test executed, Maven exit code 0, and no failures/errors/skips.",
            "",
        ]
    )
    return "\n".join(lines)


def write_repair_verification_artifacts(
    result: RepairVerificationRunResult,
    details: Mapping[str, Mapping[str, object]],
    output_dir: Path,
) -> None:
    """Write bounded per-case and aggregate artifacts without temp paths or Gold."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for case in result.cases:
        case_dir = output_dir / case.case_id
        case_dir.mkdir(exist_ok=True)
        payload = {
            "case_id": case.case_id,
            "metrics": case.model_dump(),
            **dict(details.get(case.case_id, {})),
        }
        (case_dir / "verification.json").write_text(_safe_json(payload), encoding="utf-8")
        summary_lines = [
            f"case_id={case.case_id}",
            f"baseline_verified={str(case.baseline_verified).lower()}",
            f"proposal_valid={str(case.proposal_valid).lower()}",
            f"patch_applied={str(case.patch_applied).lower()}",
            f"all_edits_applied={str(case.all_edits_applied).lower()}",
            f"original_repository_unchanged={str(case.original_repository_unchanged).lower()}",
            f"maven_executed={str(case.maven_executed).lower()}",
            f"maven_exit_code={case.maven_exit_code}",
            f"target_test_found={str(case.target_test_found).lower()}",
            f"tests={case.tests}",
            f"failures={case.failures}",
            f"errors={case.errors}",
            f"skipped={case.skipped}",
            f"repair_success={str(case.repair_success).lower()}",
            f"failure_reason={case.failure_reason or 'none'}",
            f"verification_status={case.verification_status}",
            f"verification_duration_ms={case.verification_duration_ms}",
            f"workspace_cleanup_success={str(case.workspace_cleanup_success).lower()}",
        ]
        (case_dir / "summary.txt").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    summary = {
        "mode": result.mode,
        "aggregate": result.aggregate.model_dump(),
        "cases": [case.model_dump() for case in result.cases],
    }
    (output_dir / "summary.json").write_text(_safe_json(summary), encoding="utf-8")
    (output_dir / "report.md").write_text(
        render_repair_verification_report(result),
        encoding="utf-8",
    )


__all__ = [
    "aggregate_repair_metrics",
    "render_repair_verification_report",
    "write_repair_verification_artifacts",
]
