"""Path safety: canonicalize and validate repository boundaries.

This module is the single source of truth for sandbox enforcement.
All tools must resolve user-supplied relative paths through this module
before reading any file. The API layer also uses this module to validate
``repository_path`` against ``allow_root`` at submission time.
"""

from __future__ import annotations

from pathlib import Path


class PathSafetyError(ValueError):
    """Raised when a path escapes the repository sandbox or violates a constraint."""


def canonicalize_repository(repository_path: Path, allow_root: Path) -> Path:
    """Resolve ``repository_path`` and verify it lies inside ``allow_root``.

    Returns the canonicalized absolute path of the repository.

    Raises:
        PathSafetyError: if the path does not exist, is not a directory,
            resolves outside ``allow_root``, or is a symlink that escapes.
    """
    allow_resolved = allow_root.resolve()
    repo_resolved = repository_path.resolve()

    try:
        repo_resolved.relative_to(allow_resolved)
    except ValueError as e:
        msg = (
            f"repository_path {repository_path} resolves to {repo_resolved}, "
            f"which is outside allow_root {allow_resolved}"
        )
        raise PathSafetyError(msg) from e

    if not repo_resolved.exists():
        raise PathSafetyError(f"repository_path does not exist: {repository_path}")
    if not repo_resolved.is_dir():
        raise PathSafetyError(f"repository_path is not a directory: {repository_path}")

    return repo_resolved


def resolve_relative_path(relative_path: str, repository_path: Path) -> Path:
    """Resolve a relative path against ``repository_path`` and verify sandbox.

    Rejects:
        - Absolute paths
        - Paths containing ``..`` that escape the repository after
          canonicalization
        - Symlinks whose canonicalized target lies outside the repository

    Returns the canonicalized absolute path. Does NOT check existence;
    callers that need an existing file must check separately.
    """
    p = Path(relative_path)
    if p.is_absolute():
        raise PathSafetyError(f"absolute paths are not allowed: {relative_path}")

    repo_resolved = repository_path.resolve()
    candidate = (repo_resolved / relative_path).resolve()

    try:
        candidate.relative_to(repo_resolved)
    except ValueError as e:
        msg = (
            f"path {relative_path!r} resolves to {candidate}, "
            f"which escapes repository {repo_resolved}"
        )
        raise PathSafetyError(msg) from e

    return candidate


def is_within(child: Path, parent: Path) -> bool:
    """Return True if ``child`` is ``parent`` or inside ``parent`` after canonicalization."""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False
