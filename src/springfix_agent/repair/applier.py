"""Deterministic, all-or-nothing application of validated patch proposals."""

from __future__ import annotations

import os
import re
import tempfile
from collections import defaultdict
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from springfix_agent.repair.application_models import (
    AppliedEdit,
    PatchApplicationResult,
    RejectedApplicationEdit,
)
from springfix_agent.repair.diff import generate_unified_diff, sha256_text
from springfix_agent.repair.models import PatchEdit, PatchValidationResult
from springfix_agent.repair.workspace import IsolatedPatchWorkspace

_ALLOWED_PREFIXES = ("src/main/java/", "src/main/resources/")
_FORBIDDEN_PARTS = frozenset(
    {
        ".git",
        "target",
        "build",
        "node_modules",
        "artifacts",
        "benchmark",
        "__pycache__",
        "src/test",
    }
)
_SENSITIVE_DIFF_PATTERN = re.compile(
    r"(?i)(?:\.env(?:\.|$)|benchmark|readme|api[_ -]?key|authorization\s*:\s*bearer|"
    r"[a-z]:[\\/]|\\\\[a-z]|/(?:tmp|var|home|users?)/|\bsk-[a-z0-9]{16,}\b)"
)


def _normalise_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _code_equal(left: str, right: str) -> bool:
    """Compare code exactly after newline normalization and one boundary newline."""
    left_normalized = _normalise_newlines(left)
    right_normalized = _normalise_newlines(right)
    if left_normalized == right_normalized:
        return True
    return (
        left_normalized.removesuffix("\n") == right_normalized
        or left_normalized == right_normalized.removesuffix("\n")
    )


def _normalise_path(value: str) -> str:
    return value.replace("\\", "/")


def _allowed_path(file: str, root: Path) -> tuple[str, Path | None]:
    """Validate a patch path and return its normalized workspace target."""
    normalized = _normalise_path(file)
    pure = PureWindowsPath(normalized)
    if (
        not normalized
        or Path(normalized).is_absolute()
        or pure.is_absolute()
        or normalized.startswith("/")
    ):
        return normalized, None
    parts = tuple(part for part in normalized.split("/") if part)
    lowered_parts = tuple(part.casefold() for part in parts)
    if ".." in parts or any(part in _FORBIDDEN_PARTS for part in lowered_parts):
        return normalized, None
    if any(part == ".env" or part.startswith(".env.") for part in lowered_parts):
        return normalized, None
    if normalized.casefold().endswith(".md") or not normalized.casefold().startswith(
        _ALLOWED_PREFIXES
    ):
        return normalized, None
    candidate = (root / Path(normalized)).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return normalized, None
    return normalized, candidate


def _logical_lines(text: str) -> tuple[list[str], bool]:
    """Return logical lines and whether the original text ended in a newline."""
    normalized = _normalise_newlines(text)
    trailing_newline = normalized.endswith("\n")
    body = normalized[:-1] if trailing_newline else normalized
    if not body and not trailing_newline:
        return [], False
    return body.split("\n"), trailing_newline


def _render_lines(lines: list[str], *, trailing_newline: bool, newline: str) -> str:
    normalized = "\n".join(lines)
    if trailing_newline:
        normalized += "\n"
    return normalized.replace("\n", newline)


def _replacement_lines(code: str) -> list[str]:
    normalized = _normalise_newlines(code)
    if normalized.endswith("\n"):
        normalized = normalized[:-1]
    return normalized.split("\n") if normalized else [""]


def _detect_newline(text: str) -> str:
    if "\r\n" in text:
        return "\r\n"
    if "\r" in text:
        return "\r"
    return "\n"


@dataclass(frozen=True)
class _TextSnapshot:
    file: str
    path: Path
    raw: bytes
    text: str
    lines: list[str]
    trailing_newline: bool
    newline: str
    bom: bool

    @classmethod
    def read(cls, file: str, path: Path) -> _TextSnapshot:
        raw = path.read_bytes()
        bom = raw.startswith(b"\xef\xbb\xbf")
        payload = raw[3:] if bom else raw
        text = payload.decode("utf-8")
        lines, trailing_newline = _logical_lines(text)
        return cls(
            file=file,
            path=path,
            raw=raw,
            text=text,
            lines=lines,
            trailing_newline=trailing_newline,
            newline=_detect_newline(text),
            bom=bom,
        )

    def render(self, lines: list[str]) -> tuple[str, bytes]:
        text = _render_lines(lines, trailing_newline=self.trailing_newline, newline=self.newline)
        encoded = text.encode("utf-8")
        if self.bom:
            encoded = b"\xef\xbb\xbf" + encoded
        return text, encoded


def _atomic_write(path: Path, payload: bytes) -> None:
    """Write a sibling temp file, flush it, then replace the target."""
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
        )
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            with suppress(FileNotFoundError):
                temporary.unlink()


def _rejected(
    index: int,
    edit: PatchEdit | None,
    reason: str,
) -> RejectedApplicationEdit:
    return RejectedApplicationEdit(
        edit_index=index,
        file=_normalise_path(edit.file) if edit is not None else None,
        reason=reason,
    )


class PatchApplier:
    """Apply a fully validated proposal only inside an isolated workspace."""

    def apply(
        self,
        validation: PatchValidationResult,
        workspace: IsolatedPatchWorkspace,
    ) -> PatchApplicationResult:
        """Preflight every edit, then apply all edits in one deterministic pass."""
        root = workspace.path
        if root is None:
            raise ValueError("workspace must be active before patch application")
        proposal = validation.proposal
        edits = proposal.edits
        if not validation.passed:
            reason = "proposal_not_validated"
            rejected = [_rejected(index, edit, reason) for index, edit in enumerate(edits)]
            return self._result(
                validation,
                status="rejected",
                applied_edits=[],
                rejected_edits=rejected,
                changed_files=[],
                unified_diff="",
                workspace=workspace,
                application_error=reason,
            )

        snapshots: dict[str, _TextSnapshot] = {}
        failures: dict[int, str] = {}
        normalized_edits: list[tuple[int, PatchEdit, str]] = []
        for index, edit in enumerate(edits):
            normalized, target = _allowed_path(edit.file, root)
            if target is None:
                failures[index] = "path_not_allowed"
                continue
            if target.is_symlink():
                failures[index] = "path_not_allowed"
                continue
            if not target.exists():
                failures[index] = "new_file_not_supported"
                continue
            if not target.is_file():
                failures[index] = "file_not_found"
                continue
            try:
                snapshot = snapshots.get(normalized)
                if snapshot is None:
                    snapshot = _TextSnapshot.read(normalized, target)
                    snapshots[normalized] = snapshot
            except UnicodeDecodeError:
                failures[index] = "unsupported_encoding"
                continue
            except OSError:
                failures[index] = "file_not_found"
                continue
            if edit.start_line < 1 or edit.end_line < edit.start_line:
                failures[index] = "invalid_range"
                continue
            if edit.end_line > len(snapshot.lines):
                failures[index] = "invalid_range"
                continue
            actual = "\n".join(snapshot.lines[edit.start_line - 1 : edit.end_line])
            if not _code_equal(actual, edit.old_code):
                failures[index] = "stale_patch"
                continue
            if not edit.new_code.strip() or _code_equal(edit.old_code, edit.new_code):
                failures[index] = "empty_or_unchanged_edit"
                continue
            normalized_edits.append((index, edit.model_copy(update={"file": normalized}), normalized))

        by_file: dict[str, list[tuple[int, PatchEdit]]] = defaultdict(list)
        for index, edit, normalized in normalized_edits:
            by_file[normalized].append((index, edit))
        for file_edits in by_file.values():
            for position, (index, edit) in enumerate(file_edits):
                for other_index, other in file_edits[position + 1 :]:
                    overlaps = edit.start_line <= other.end_line and other.start_line <= edit.end_line
                    if not overlaps:
                        continue
                    same_edit = (
                        edit.start_line == other.start_line
                        and edit.end_line == other.end_line
                        and _code_equal(edit.old_code, other.old_code)
                        and _code_equal(edit.new_code, other.new_code)
                    )
                    failures.setdefault(other_index, "duplicate_edit" if same_edit else "conflicting_edit")
                    if not same_edit:
                        failures.setdefault(index, "conflicting_edit")

        if failures:
            rejected = [
                _rejected(index, edit, failures.get(index, "preflight_aborted"))
                for index, edit in enumerate(edits)
            ]
            return self._result(
                validation,
                status="rejected",
                applied_edits=[],
                rejected_edits=rejected,
                changed_files=[],
                unified_diff="",
                workspace=workspace,
                application_error="preflight_failed",
            )

        planned: dict[str, tuple[_TextSnapshot, list[str], bytes, str]] = {}
        applied_audit: list[AppliedEdit] = []
        for file, file_edits in by_file.items():
            snapshot = snapshots[file]
            lines = list(snapshot.lines)
            for index, edit in sorted(file_edits, key=lambda item: item[1].start_line, reverse=True):
                lines[edit.start_line - 1 : edit.end_line] = _replacement_lines(edit.new_code)
                applied_audit.append(
                    AppliedEdit(
                        edit_index=index,
                        file=file,
                        original_start_line=edit.start_line,
                        original_end_line=edit.end_line,
                        old_code_sha256=sha256_text(_normalise_newlines(edit.old_code)),
                        new_code_sha256=sha256_text(_normalise_newlines(edit.new_code)),
                    )
                )
            text, payload = snapshot.render(lines)
            planned[file] = (snapshot, lines, payload, text)
        applied_audit.sort(key=lambda item: item.edit_index)

        original_texts = {
            file: snapshot.text for file, (snapshot, _lines, _payload, _text) in planned.items()
        }
        patched_texts = {
            file: text for file, (_snapshot, _lines, _payload, text) in planned.items()
        }
        unified_diff = generate_unified_diff(original_texts, patched_texts)
        changed_files = sorted(
            file for file in patched_texts if original_texts[file] != patched_texts[file]
        )
        if _SENSITIVE_DIFF_PATTERN.search(unified_diff):
            return self._result(
                validation,
                status="rejected",
                applied_edits=[],
                rejected_edits=[
                    _rejected(index, edit, "unsafe_diff") for index, edit in enumerate(edits)
                ],
                changed_files=[],
                unified_diff="",
                workspace=workspace,
                application_error="unsafe_diff",
            )

        written: list[tuple[Path, bytes]] = []
        try:
            for file in sorted(planned):
                snapshot, _lines, payload, _text = planned[file]
                _atomic_write(snapshot.path, payload)
                written.append((snapshot.path, snapshot.raw))
        except (OSError, ValueError) as exc:
            for path, original in reversed(written):
                with suppress(OSError):
                    _atomic_write(path, original)
            rejected = [_rejected(index, edit, "application_error") for index, edit in enumerate(edits)]
            return self._result(
                validation,
                status="rejected",
                applied_edits=[],
                rejected_edits=rejected,
                changed_files=[],
                unified_diff="",
                workspace=workspace,
                application_error=f"atomic_write_failed: {type(exc).__name__}",
            )

        return self._result(
            validation,
            status="applied",
            applied_edits=applied_audit,
            rejected_edits=[],
            changed_files=changed_files,
            unified_diff=unified_diff,
            workspace=workspace,
            application_error=None,
        )

    def _result(
        self,
        validation: PatchValidationResult,
        *,
        status: str,
        applied_edits: list[AppliedEdit],
        rejected_edits: list[RejectedApplicationEdit],
        changed_files: list[str],
        unified_diff: str,
        workspace: IsolatedPatchWorkspace,
        application_error: str | None,
    ) -> PatchApplicationResult:
        """Build a result without exposing the temporary workspace path."""
        unchanged = workspace.verify_source_unchanged()
        final_status = status if unchanged else "rejected"
        error = application_error
        if not unchanged:
            error = "original_repository_modified"
        return PatchApplicationResult(
            status=final_status,  # type: ignore[arg-type]
            proposal_status=validation.proposal.status,
            edits_requested=len(validation.proposal.edits),
            edits_applied=len(applied_edits) if unchanged else 0,
            edits_rejected=len(rejected_edits) if unchanged else len(validation.proposal.edits),
            changed_files=changed_files if unchanged else [],
            applied_edits=applied_edits if unchanged else [],
            rejected_edits=rejected_edits,
            unified_diff=unified_diff if unchanged else "",
            original_repository_unchanged=unchanged,
            workspace_integrity="verified" if unchanged else "failed",
            application_error=error,
        )


__all__ = ["PatchApplier"]
