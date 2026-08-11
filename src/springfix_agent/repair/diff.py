"""Deterministic unified diff generation for applied patch edits."""

from __future__ import annotations

import difflib
import hashlib
from collections.abc import Mapping
from pathlib import PurePosixPath


def _validate_relative_file(file: str) -> str:
    """Normalize and validate a repository-relative diff path."""
    normalized = file.replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts:
        raise ValueError("diff paths must be repository-relative")
    return normalized


def _normalise_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def generate_unified_diff(
    original_files: Mapping[str, str],
    patched_files: Mapping[str, str],
) -> str:
    """Generate a stable ``a/``/``b/`` unified diff for changed files only."""
    original = {_validate_relative_file(key): value for key, value in original_files.items()}
    patched = {_validate_relative_file(key): value for key, value in patched_files.items()}
    changed = sorted(set(original) | set(patched))
    output: list[str] = []
    for file in changed:
        before = _normalise_newlines(original.get(file, "")).splitlines()
        after = _normalise_newlines(patched.get(file, "")).splitlines()
        if before == after and file in original and file in patched:
            continue
        output.extend(
            difflib.unified_diff(
                before,
                after,
                fromfile=f"a/{file}",
                tofile=f"b/{file}",
                lineterm="",
            )
        )
    return "\n".join(output) + ("\n" if output else "")


def sha256_text(value: str) -> str:
    """Return the SHA-256 digest used by application audit records."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = ["generate_unified_diff", "sha256_text"]
