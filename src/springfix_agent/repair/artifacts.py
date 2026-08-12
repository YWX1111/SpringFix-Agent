"""Redacted JSON and Markdown artifacts for Patch Proposal runs."""

from __future__ import annotations

import json
from pathlib import Path

from springfix_agent.repair.application_models import (
    PatchApplicationResult,
    PatchApplicationRunResult,
)
from springfix_agent.repair.diff import sha256_text
from springfix_agent.repair.evaluator import RepairBenchmarkRunResult


def render_repair_report(result: RepairBenchmarkRunResult) -> str:
    """Render a report using only public proposal and metric fields."""
    lines = [
        "# SpringFix Patch Proposal Evaluation",
        "",
        f"- mode: `{result.mode}`",
        f"- sample_size: `{result.aggregate.sample_size}`",
        "- This measures Patch Proposal Validation Rate, not Repair Success.",
        "- M5A proposes changes only; it never applies a patch or runs Maven.",
        "",
        "## Cases",
        "",
        "| Case | Status | Edits | Validated | Rejected | Concept | Duration (ms) |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for case in result.cases:
        metrics = case.metrics
        lines.append(
            f"| `{case.case_id}` | `{case.proposal_status}` | {metrics.edit_count} | "
            f"{metrics.validated_edit_count} | {metrics.rejected_edit_count} | "
            f"{str(metrics.acceptable_change_concept_hit).lower()} | {metrics.duration_ms} |"
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
            "## Scope",
            "",
            "- Diagnostic LLM calls and Patch LLM calls are recorded separately.",
            "- Gold, full prompts, raw responses, API keys, and absolute repository paths are not saved.",
            "- M5B isolated application and M5C Maven verification are separate stages.",
            "",
        ]
    )
    return "\n".join(lines)


def write_repair_artifacts(result: RepairBenchmarkRunResult, output_dir: Path) -> None:
    """Write a run summary and one proposal artifact per case."""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "run_metadata.json").write_text(
        json.dumps(result.run_metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for case in result.cases:
        case_dir = output_dir / case.case_id
        case_dir.mkdir(exist_ok=True)
        payload = {
            "case_id": case.case_id,
            "model": case.model,
            "proposal_status": case.proposal_status,
            "proposal_generation_audit": (
                case.proposal_generation_audit.model_dump()
                if case.proposal_generation_audit is not None
                else None
            ),
            "summary": case.summary,
            "edits": case.edits,
            "verification_steps": case.verification_steps,
            "risks": case.risks,
            "assumptions": case.assumptions,
            "rejected_edit_count": case.metrics.rejected_edit_count,
            "rejected_edit_reasons": case.rejected_edit_reasons,
            "diagnostic_llm_calls": case.metrics.diagnostic_llm_calls,
            "patch_llm_calls": case.metrics.patch_llm_calls,
            "logical_llm_calls": case.metrics.logical_llm_calls,
            "http_attempts": case.metrics.http_attempts,
            "input_tokens": case.metrics.input_tokens,
            "output_tokens": case.metrics.output_tokens,
            "duration_ms": case.metrics.duration_ms,
        }
        (case_dir / "proposal.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        md_lines = [
            "# Patch Proposal",
            "",
            f"- case_id: `{case.case_id}`",
            f"- model: `{case.model}`",
            f"- status: **{case.proposal_status}**",
            f"- rejected_edit_count: `{case.metrics.rejected_edit_count}`",
            "",
            "## Summary",
            "",
            case.summary,
            "",
            "## Edits",
            "",
        ]
        if not case.edits:
            md_lines.append("No edit proposed.")
        for index, edit in enumerate(case.edits, start=1):
            md_lines.extend(
                [
                    f"### Edit {index}: `{edit['file']}` lines {edit['start_line']}-{edit['end_line']}",
                    "",
                    f"Rationale: {edit['rationale']}",
                    "",
                    "```text",
                    str(edit["old_code"]),
                    "```",
                    "becomes",
                    "```text",
                    str(edit["new_code"]),
                    "```",
                    "",
                ]
            )
        (case_dir / "proposal.md").write_text("\n".join(md_lines), encoding="utf-8")
    (output_dir / "summary.json").write_text(
        json.dumps(
            {"mode": result.mode, "aggregate": result.aggregate.model_dump()},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(render_repair_report(result), encoding="utf-8")


def write_patch_application_artifacts(
    result: PatchApplicationRunResult,
    applications: dict[str, PatchApplicationResult],
    output_dir: Path,
) -> None:
    """Write M5B application records without temporary paths or raw prompts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for case in result.cases:
        application = applications[case.case_id]
        case_dir = output_dir / case.case_id
        case_dir.mkdir(exist_ok=True)
        payload = application.model_dump()
        payload.pop("unified_diff", None)
        payload.update(
            {
                "case_id": case.case_id,
                "diff_sha256": sha256_text(application.unified_diff),
                "metrics": case.model_dump(),
            }
        )
        (case_dir / "application.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (case_dir / "patch.diff").write_text(application.unified_diff, encoding="utf-8")

    summary = {
        "mode": result.mode,
        "aggregate": result.aggregate.model_dump(),
        "cases": [case.model_dump() for case in result.cases],
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
