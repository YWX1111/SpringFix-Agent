"""Safe M5D artifact serialization and Markdown reporting."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from springfix_agent.repair.e2e_metrics import funnel_rows
from springfix_agent.repair.e2e_models import (
    DIAGNOSIS_CANDIDATE_DESCRIPTION_MAX_CHARS,
    DIAGNOSIS_CANDIDATE_MAX_COUNT,
    DIAGNOSIS_CANDIDATE_RECOMMENDED_FIX_MAX_CHARS,
    DIAGNOSIS_CANDIDATE_TITLE_MAX_CHARS,
    DIAGNOSIS_SUMMARY_MAX_CHARS,
    DiagnosisCandidateEvidence,
    DiagnosisEvidenceV1,
    DiagnosisTruncatedField,
    EndToEndCaseArtifact,
    EndToEndCaseResult,
    EndToEndRunResult,
)

_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{8,}")
_API_KEY_RE = re.compile(r"(?i)\bsk-[A-Za-z0-9_-]{16,}\b")
_SECRET_RE = re.compile(
    r"(?ix)\b(api[_ -]?key|token|secret|password|authorization|credential)\b"
    r"(\s*[:=]\s*)"
    r'(?:"[^"\r\n]*"|\'[^\'\r\n]*\'|[^\r\n,;]+)'
)
_URL_RE = re.compile(r"(?i)https?://[^\s\]\)}>]+")
_ABSOLUTE_PATH_RE = re.compile(
    r"(?i)(?:"
    r'["\'](?:[a-z]:[\\/]|\\\\|/(?:private/tmp|tmp|var|home|users?|root|workspaces?|opt|mnt)/)[^"\'\r\n]*["\']'
    r"|(?:[a-z]:[\\/]|\\\\|/(?:private/tmp|tmp|var|home|users?|root|workspaces?|opt|mnt)/)[^\r\n,;]+"
    r")"
)
_ENV_RE = re.compile(r"(?i)(?:^|[\\/])\.env(?:\.[^\s/\\,;]+)?")


def _safe_text(value: str) -> str:
    """Remove credentials, URLs, env paths, and machine-specific paths."""
    result = _BEARER_RE.sub("<redacted>", value)
    result = _API_KEY_RE.sub("<redacted>", result)
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


def _bounded_text(
    value: object,
    *,
    max_chars: int,
    field_name: DiagnosisTruncatedField,
    truncated_fields: list[DiagnosisTruncatedField],
) -> str:
    if not isinstance(value, str):
        return ""
    safe = _safe_text(value)
    if len(safe) > max_chars:
        truncated_fields.append(field_name)
        return safe[:max_chars]
    return safe


def capture_bounded_diagnosis_evidence(
    summary: str | None,
    candidates: Sequence[Mapping[str, object]],
) -> DiagnosisEvidenceV1:
    """Copy only public semantic result fields into a bounded artifact model."""
    truncated_fields: list[DiagnosisTruncatedField] = []
    bounded_summary = _bounded_text(
        summary,
        max_chars=DIAGNOSIS_SUMMARY_MAX_CHARS,
        field_name="summary",
        truncated_fields=truncated_fields,
    )
    if len(candidates) > DIAGNOSIS_CANDIDATE_MAX_COUNT:
        truncated_fields.append("candidates")

    bounded_candidates: list[DiagnosisCandidateEvidence] = []
    for index, candidate in enumerate(candidates[:DIAGNOSIS_CANDIDATE_MAX_COUNT]):
        title_field = cast(DiagnosisTruncatedField, f"candidates[{index}].title")
        description_field = cast(
            DiagnosisTruncatedField, f"candidates[{index}].description"
        )
        recommended_fix_field = cast(
            DiagnosisTruncatedField, f"candidates[{index}].recommended_fix"
        )
        bounded_candidates.append(
            DiagnosisCandidateEvidence(
                title=_bounded_text(
                    candidate.get("title"),
                    max_chars=DIAGNOSIS_CANDIDATE_TITLE_MAX_CHARS,
                    field_name=title_field,
                    truncated_fields=truncated_fields,
                ),
                description=_bounded_text(
                    candidate.get("description"),
                    max_chars=DIAGNOSIS_CANDIDATE_DESCRIPTION_MAX_CHARS,
                    field_name=description_field,
                    truncated_fields=truncated_fields,
                ),
                recommended_fix=_bounded_text(
                    candidate.get("recommended_fix"),
                    max_chars=DIAGNOSIS_CANDIDATE_RECOMMENDED_FIX_MAX_CHARS,
                    field_name=recommended_fix_field,
                    truncated_fields=truncated_fields,
                ),
            )
        )

    truncated = bool(truncated_fields)
    return DiagnosisEvidenceV1(
        summary=bounded_summary or None,
        candidates=tuple(bounded_candidates),
        truncated=truncated,
        truncated_fields=tuple(truncated_fields),
    )


def _case_artifact_payload(case: EndToEndCaseResult) -> dict[str, object]:
    payload: dict[str, object] = case.model_dump(mode="python")
    evidence = case.diagnosis_evidence
    if evidence is None:
        excluded = {
            "diagnosis_evidence",
            "diagnosis_evidence_schema_version",
            "root_cause_summary",
            "diagnosis_candidates",
        }
    else:
        payload["diagnosis_evidence_schema_version"] = evidence.schema_version
        if evidence.evaluation_ready and not evidence.truncated and not evidence.truncated_fields:
            payload["root_cause_summary"] = evidence.summary
            payload["diagnosis_candidates"] = evidence.candidates
            excluded = set()
        else:
            excluded = {"root_cause_summary", "diagnosis_candidates"}
    artifact = EndToEndCaseArtifact.model_validate(payload)
    return artifact.model_dump(mode="json", exclude=excluded)


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    safe = sanitize_artifact_value(payload)
    path.write_text(
        json.dumps(safe, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def render_end_to_end_report(result: EndToEndRunResult) -> str:
    """Render the funnel and per-case table from the same result models."""
    split = str(result.run_metadata.get("split", "legacy"))
    sample_size = result.aggregate.sample_size
    scope = (
        "the frozen unseen Holdout v1 benchmark"
        if split == "holdout"
        else "the current controlled Legacy benchmark"
    )
    lines = [
        f"# SpringFix {split.title()} End-to-End Repair Benchmark",
        "",
        f"- mode: `{result.mode}`",
        f"- run_id: `{result.run_id}`",
        f"- split: `{split}`",
        f"- sample_size: `{sample_size}`",
        "- M5D is a single-shot end-to-end benchmark; failed repairs are not retried.",
        f"- Results are limited to {scope} and are not a production accuracy rate.",
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
            f"- sample_size is {sample_size} and the bug categories are limited to the selected frozen split.",
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
            _case_artifact_payload(case),
        )
        if case.patch_diff:
            (case_dir / "patch.diff").write_text(_safe_text(case.patch_diff), encoding="utf-8")
    _write_json(
        output_dir / "summary.json",
        {
            "mode": result.mode,
            "run_id": result.run_id,
            "aggregate": result.aggregate.model_dump(mode="json"),
            "cases": [_case_artifact_payload(case) for case in result.cases],
        },
    )
    (output_dir / "report.md").write_text(render_end_to_end_report(result), encoding="utf-8")


__all__ = [
    "capture_bounded_diagnosis_evidence",
    "render_end_to_end_report",
    "sanitize_artifact_value",
    "write_end_to_end_artifacts",
]
