"""Safe M5D artifact serialization and Markdown reporting."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from springfix_agent.repair.e2e_metrics import funnel_rows
from springfix_agent.repair.e2e_models import EndToEndRunResult

_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{8,}")
_SECRET_RE = re.compile(
    r"(?i)(api[_ -]?key|token|secret|password|authorization)(\s*[:=]\s*)[^\s,;]+"
)
_URL_RE = re.compile(r"(?i)https?://[^\s\]\)}>]+")
_ABSOLUTE_PATH_RE = re.compile(
    r"(?i)(?:[a-z]:[\\/]|/(?:tmp|var|home|users?)/)[^\s\r\n,;]+"
)
_ENV_RE = re.compile(r"(?i)(?:^|[\\/])\.env(?:\.[^\s/\\,;]+)?")


def _safe_text(value: str) -> str:
    """Remove credentials, URLs, env paths, and machine-specific paths."""
    result = _BEARER_RE.sub("<redacted>", value)
    result = _SECRET_RE.sub(r"\1=<redacted>", result)
    result = _URL_RE.sub("<url>", result)
    result = _ENV_RE.sub("/<redacted-env>", result)
    return _ABSOLUTE_PATH_RE.sub("<path>", result)


def sanitize_artifact_value(value: Any) -> Any:
    """Recursively sanitize a JSON-compatible artifact payload."""
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, Mapping):
        return {str(key): sanitize_artifact_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [sanitize_artifact_value(item) for item in value]
    return value


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    safe = sanitize_artifact_value(payload)
    path.write_text(
        json.dumps(safe, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def render_end_to_end_report(result: EndToEndRunResult) -> str:
    """Render the funnel and per-case table from the same result models."""
    lines = [
        "# SpringFix M5D End-to-End Repair Benchmark",
        "",
        f"- mode: `{result.mode}`",
        f"- run_id: `{result.run_id}`",
        f"- sample_size: `{result.aggregate.sample_size}`",
        "- M5D is a single-shot end-to-end benchmark; failed repairs are not retried.",
        "- Results are limited to the current controlled three-case sample and are not a production accuracy rate.",
        "",
        "## End-to-End Funnel",
        "",
        "| Stage | Passed | Total |",
        "|---|---:|---:|",
    ]
    for label, passed, total in funnel_rows(result):
        lines.append(f"| {label} | {passed}/{total} | {total} |")
    lines.extend(
        [
            "",
            "## Cases",
            "",
            "| Case | Diagnosis | Proposal | Apply | Test | Repair | Failed stage |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for case in result.cases:
        lines.append(
            f"| `{case.case_id}` | {case.diagnosis_status.upper()} | "
            f"{case.proposal_status.upper()} | {case.application_status.upper()} | "
            f"{str(case.target_test_found).upper()} | {str(case.repair_success).upper()} | "
            f"`{case.failed_stage or 'none'}` |"
        )
    lines.extend(
        [
            "",
            "## Run Metadata",
            "",
            "```json",
            json.dumps(
                sanitize_artifact_value(result.run_metadata),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            "```",
            "",
            "## Aggregate Metrics",
            "",
            "```json",
            json.dumps(
                sanitize_artifact_value(result.aggregate.model_dump(mode="json")),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            "```",
            "",
            "## Limitations",
            "",
            "- sample_size is three and the bug categories are limited to the controlled benchmark cases.",
            "- Live results depend on the selected model version and frozen provider configuration.",
            "- The benchmark has no statistical significance claim and no iterative repair loop.",
            "- Maven verification is restricted by command shape, cwd, environment, and timeout, but is not an OS/container/network sandbox.",
            "- Maven may access normal dependency repositories required by the sample projects.",
            "- `compile_success` is true only when Surefire confirms the target test executed; otherwise it remains null unless a verifier provides a definitive compilation classification.",
            "",
        ]
    )
    return "\n".join(lines)


def write_end_to_end_artifacts(result: EndToEndRunResult, output_dir: Path) -> None:
    """Write redacted, sorted artifacts for one M5D Run."""
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "run_metadata.json", result.run_metadata)
    for case in result.cases:
        case_dir = output_dir / "cases" / case.case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            case_dir / "result.json",
            {"case_id": case.case_id, **case.model_dump(mode="json")},
        )
        if case.patch_diff:
            (case_dir / "patch.diff").write_text(_safe_text(case.patch_diff), encoding="utf-8")
    _write_json(
        output_dir / "summary.json",
        {
            "mode": result.mode,
            "run_id": result.run_id,
            "aggregate": result.aggregate.model_dump(mode="json"),
            "cases": [case.model_dump(mode="json") for case in result.cases],
        },
    )
    (output_dir / "report.md").write_text(render_end_to_end_report(result), encoding="utf-8")


__all__ = [
    "render_end_to_end_report",
    "sanitize_artifact_value",
    "write_end_to_end_artifacts",
]
