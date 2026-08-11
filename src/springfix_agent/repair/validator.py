"""Deterministic M5A patch and evidence validation."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PureWindowsPath
from typing import Any

from springfix_agent.repair.models import (
    EvidenceSnippet,
    PatchEdit,
    PatchProposal,
    PatchValidationResult,
    RejectedPatchEdit,
)
from springfix_agent.tools._path_safety import PathSafetyError, resolve_relative_path

_ALLOWED_PREFIXES = ("src/main/java/", "src/main/resources/")
_FORBIDDEN_PARTS = frozenset({".git", "benchmark", "target", "artifacts"})
_DANGEROUS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "process_execution",
        re.compile(
            r"\bprocessbuilder\b|\bruntime\s*\.\s*(?:getruntime\s*\(\s*\)\s*\.\s*)?exec\b",
            re.I,
        ),
    ),
    ("process_exit", re.compile(r"\bsystem\s*\.\s*exit\b", re.I)),
    ("shell_command", re.compile(r"\b(?:bash|sh|powershell|pwsh|cmd)\b|(?:^|\s)(?:curl|wget)\b", re.I)),
    ("file_deletion", re.compile(r"\bfiles?\s*\.\s*(?:delete|deleteifexists)\b|\brm\s+-rf\b", re.I)),
    (
        "network_download",
        re.compile(r"\b(?:download|openstream|httpurlconnection|urlconnection)\b", re.I),
    ),
    ("credential_or_secret", re.compile(r"\b(?:credential|password|secret|api[_ -]?key)\b\s*[:=]", re.I)),
    ("hardcoded_bearer", re.compile(r"\bbearer\s+[A-Za-z0-9._-]{12,}", re.I)),
)


def _normalise_newlines(value: str) -> str:
    """Normalize line endings without stripping meaningful source text."""
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _normalise_path(value: object) -> str:
    """Use portable separators for all internal relative path comparisons."""
    return str(value or "").replace("\\", "/")


def _path_reason(file: object, repository_root: Path) -> tuple[str, str | None]:
    """Return a normalized path and a rejection reason, if any."""
    normalized = _normalise_path(file)
    if not normalized:
        return normalized, "path_not_allowed"
    pure = PureWindowsPath(normalized)
    if Path(normalized).is_absolute() or pure.is_absolute() or normalized.startswith("/"):
        return normalized, "path_not_allowed"
    parts = tuple(part for part in normalized.split("/") if part)
    if ".." in parts or any(part in _FORBIDDEN_PARTS for part in parts):
        return normalized, "path_not_allowed"
    if any(part == ".env" or part.startswith(".env.") for part in parts):
        return normalized, "path_not_allowed"
    lowered = normalized.casefold()
    if lowered.endswith(".md") or any(
        parts[index : index + 2] == ("src", "test")
        for index in range(max(0, len(parts) - 1))
    ):
        return normalized, "path_not_allowed"
    if not lowered.startswith(_ALLOWED_PREFIXES):
        return normalized, "path_not_allowed"
    try:
        candidate = resolve_relative_path(normalized, repository_root)
    except PathSafetyError:
        return normalized, "path_not_allowed"
    try:
        candidate.relative_to(repository_root.resolve())
    except ValueError:
        return normalized, "path_not_allowed"
    return normalized, None


def _line_range_from_item(item: object) -> tuple[str, int, int] | None:
    """Read a file and inclusive range from an evidence-like object."""
    if isinstance(item, EvidenceSnippet):
        return item.file, item.start_line, item.end_line
    if not isinstance(item, Mapping):
        return None
    file = item.get("file")
    start = item.get("start_line")
    end = item.get("end_line")
    if isinstance(start, int) and isinstance(end, int) and isinstance(file, str):
        return file, start, end
    line_range = item.get("line_range")
    if isinstance(line_range, (tuple, list)) and len(line_range) == 2:
        first, last = line_range
        if isinstance(file, str) and isinstance(first, int) and isinstance(last, int):
            return file, first, last
    return None


def _evidence_ranges(evidence: Iterable[object]) -> dict[str, list[tuple[int, int]]]:
    ranges: dict[str, list[tuple[int, int]]] = {}
    for item in evidence:
        parsed = _line_range_from_item(item)
        if parsed is None:
            continue
        file, start, end = parsed
        normalized = _normalise_path(file)
        if start >= 1 and end >= start:
            ranges.setdefault(normalized, []).append((start, end))
    return ranges


def _overlaps(start: int, end: int, other_start: int, other_end: int) -> bool:
    return start <= other_end and other_start <= end


def _read_code_range(path: Path, start_line: int, end_line: int) -> str:
    raw = path.read_bytes().decode("utf-8")
    lines = _normalise_newlines(raw).split("\n")
    return "\n".join(lines[start_line - 1 : end_line])


def _code_lines(path: Path) -> list[str]:
    raw = path.read_bytes().decode("utf-8")
    return _normalise_newlines(raw).split("\n")


def _code_equal(left: str, right: str) -> bool:
    """Compare normalized code while ignoring only a boundary newline."""
    left_normalized = _normalise_newlines(left)
    right_normalized = _normalise_newlines(right)
    return left_normalized == right_normalized or left_normalized.rstrip("\n") == right_normalized.rstrip("\n")


def _dangerous_reason(new_code: str) -> str | None:
    for _reason, pattern in _DANGEROUS_PATTERNS:
        if pattern.search(new_code):
            return "dangerous_new_code"
    return None


def collect_validated_evidence(
    repository_root: Path,
    root_cause_analysis: Mapping[str, object] | Any,
    retrieved_snippets: Sequence[Mapping[str, object] | EvidenceSnippet],
) -> list[EvidenceSnippet]:
    """Materialize only RCA references backed by snippets and real source.

    This is a repair-specific gate layered on top of the unchanged M4C
    RootCauseAnalyzer validator.  It never reads README, tests, Gold, or
    build output and returns no evidence for an unsupported reference.
    """
    if hasattr(root_cause_analysis, "model_dump"):
        raw_rca = root_cause_analysis.model_dump()
    elif isinstance(root_cause_analysis, Mapping):
        raw_rca = dict(root_cause_analysis)
    else:
        return []
    snippet_ranges = _evidence_ranges(retrieved_snippets)
    candidates = raw_rca.get("candidates")
    if not isinstance(candidates, list):
        return []
    result: list[EvidenceSnippet] = []
    seen: set[tuple[str, int, int]] = set()
    root = repository_root.resolve()
    for candidate in candidates[:3]:
        if not isinstance(candidate, Mapping):
            continue
        references = candidate.get("evidence")
        if not isinstance(references, list):
            continue
        for reference in references:
            if not isinstance(reference, Mapping):
                continue
            file = reference.get("file")
            start = reference.get("start_line")
            end = reference.get("end_line")
            if not isinstance(file, str) or not isinstance(start, int) or not isinstance(end, int):
                continue
            normalized, reason = _path_reason(file, root)
            if reason is not None or start < 1 or end < start:
                continue
            if not any(
                _overlaps(start, end, evidence_start, evidence_end)
                and start >= evidence_start
                and end <= evidence_end
                for evidence_start, evidence_end in snippet_ranges.get(normalized, [])
            ):
                continue
            key = (normalized, start, end)
            if key in seen:
                continue
            path = root / Path(normalized)
            if not path.is_file():
                continue
            try:
                content = _read_code_range(path, start, end)
            except (OSError, UnicodeError, IndexError):
                continue
            if not content:
                continue
            try:
                EvidenceSnippet(
                    file=normalized,
                    start_line=start,
                    end_line=end,
                    content=content,
                    explanation=str(reference.get("explanation", ""))[:500],
                )
            except ValueError:
                continue
            seen.add(key)
            result.append(
                EvidenceSnippet(
                    file=normalized,
                    start_line=start,
                    end_line=end,
                    content=content,
                    explanation=str(reference.get("explanation", ""))[:500],
                )
            )
    return result


def _reject(
    rejected: list[RejectedPatchEdit],
    index: int,
    edit: PatchEdit | None,
    reason: str,
) -> None:
    rejected.append(
        RejectedPatchEdit(
            edit_index=index,
            file=_normalise_path(edit.file) if edit is not None else None,
            line_range=(edit.start_line, edit.end_line) if edit is not None else None,
            reason=reason,
        )
    )


def validate_patch_proposal(
    proposal: PatchProposal,
    repository_root: Path,
    validated_evidence: Sequence[Mapping[str, object] | EvidenceSnippet],
) -> PatchValidationResult:
    """Validate every edit against the real file and validated evidence.

    Invalid edits are removed and retained in a bounded internal audit.  The
    function never writes a file and never interprets ``new_code`` as code.
    """
    root = repository_root.resolve()
    evidence_ranges = _evidence_ranges(validated_evidence)
    rejected: list[RejectedPatchEdit] = []
    candidates: list[tuple[int, PatchEdit, str]] = []
    dangerous_found = False

    for index, edit in enumerate(proposal.edits):
        normalized_file, path_reason = _path_reason(edit.file, root)
        if path_reason is not None:
            _reject(rejected, index, edit, path_reason)
            continue
        if proposal.status != "proposed":
            _reject(rejected, index, edit, "proposal_not_proposed")
            continue
        ranges = evidence_ranges.get(normalized_file, [])
        if not ranges:
            _reject(rejected, index, edit, "file_not_in_validated_evidence")
            continue
        if edit.start_line > edit.end_line or edit.start_line < 1:
            _reject(rejected, index, edit, "line_range_invalid")
            continue
        if not any(_overlaps(edit.start_line, edit.end_line, start, end) for start, end in ranges):
            _reject(rejected, index, edit, "line_range_outside_evidence")
            continue
        path = root / Path(normalized_file)
        if not path.is_file():
            _reject(rejected, index, edit, "file_not_found")
            continue
        try:
            lines = _code_lines(path)
            actual = _read_code_range(path, edit.start_line, edit.end_line)
        except (OSError, UnicodeError):
            _reject(rejected, index, edit, "file_not_found")
            continue
        if edit.end_line > len(lines):
            _reject(rejected, index, edit, "line_range_invalid")
            continue
        if not edit.old_code.strip():
            _reject(rejected, index, edit, "old_code_mismatch")
            continue
        if not _code_equal(actual, edit.old_code):
            _reject(rejected, index, edit, "old_code_mismatch")
            continue
        if not edit.new_code.strip() or _code_equal(edit.old_code, edit.new_code):
            _reject(rejected, index, edit, "empty_or_unchanged_edit")
            continue
        dangerous_reason = _dangerous_reason(edit.new_code)
        if dangerous_reason is not None:
            dangerous_found = True
            _reject(rejected, index, edit, dangerous_reason)
            continue
        candidates.append((index, edit, normalized_file))

    accepted: list[PatchEdit] = []
    accepted_ranges: list[tuple[str, int, int]] = []
    for index, edit, normalized_file in candidates:
        duplicate = any(
            normalized_file == file and edit.start_line == start and edit.end_line == end
            for file, start, end in accepted_ranges
        )
        if duplicate:
            _reject(rejected, index, edit, "duplicate_edit")
            continue
        conflict = any(
            normalized_file == file and _overlaps(edit.start_line, edit.end_line, start, end)
            for file, start, end in accepted_ranges
        )
        if conflict:
            _reject(rejected, index, edit, "conflicting_edit")
            continue
        accepted_ranges.append((normalized_file, edit.start_line, edit.end_line))
        accepted.append(edit.model_copy(update={"file": normalized_file}))

    if dangerous_found or proposal.status == "unsafe_to_propose":
        status = "unsafe_to_propose"
    elif accepted:
        status = "proposed"
    else:
        status = "insufficient_evidence"
    sanitized = proposal.model_copy(update={"status": status, "edits": accepted})
    return PatchValidationResult(
        proposal=sanitized,
        rejected_edits=rejected,
        original_edit_count=len(proposal.edits),
        accepted_edit_count=len(accepted),
    )


class PatchProposalValidator:
    """Stateful adapter for callers that validate many proposals per repo."""

    def __init__(
        self,
        repository_root: Path | None = None,
        validated_evidence: Sequence[Mapping[str, object] | EvidenceSnippet] = (),
    ) -> None:
        self._repository_root = repository_root
        self._validated_evidence = validated_evidence

    def validate(
        self,
        proposal: PatchProposal,
        repository_root: Path | None = None,
        validated_evidence: Sequence[Mapping[str, object] | EvidenceSnippet] | None = None,
    ) -> PatchValidationResult:
        """Validate using call-time context or the adapter's configured context."""
        root = repository_root if repository_root is not None else self._repository_root
        if root is None:
            raise ValueError("repository_root is required")
        evidence = (
            validated_evidence
            if validated_evidence is not None
            else self._validated_evidence
        )
        return validate_patch_proposal(proposal, root, evidence)


validate_proposal = validate_patch_proposal
