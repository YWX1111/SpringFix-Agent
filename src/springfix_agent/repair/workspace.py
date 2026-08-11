"""Short-lived isolated repository copies for deterministic patch application.

The source repository is never used as the write target.  This module also
provides the source manifest used to prove that the source tree did not
change while an application was running.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from types import TracebackType

_EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git",
        "target",
        "build",
        "node_modules",
        "artifacts",
        "benchmark",
        "__pycache__",
    }
)
_EXCLUDED_SUFFIXES = frozenset({".class", ".jar", ".log"})


def _is_excluded(relative_path: Path) -> bool:
    """Return whether a relative path is outside the M5B copy boundary."""
    parts = tuple(part.casefold() for part in relative_path.parts)
    if any(part in _EXCLUDED_DIRECTORIES for part in parts):
        return True
    name = relative_path.name.casefold()
    if name == ".env" or name.startswith(".env."):
        return True
    if relative_path.suffix.casefold() in _EXCLUDED_SUFFIXES:
        return True
    return name.endswith(".md")


def _iter_copyable_files(root: Path) -> list[tuple[Path, Path]]:
    """Return sorted ``(absolute_path, repository_relative_path)`` files."""
    result: list[tuple[Path, Path]] = []
    for current, dir_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        relative_dir = current_path.relative_to(root)
        if relative_dir != Path(".") and _is_excluded(relative_dir):
            dir_names[:] = []
            continue

        kept_dirs: list[str] = []
        for dirname in sorted(dir_names):
            candidate = current_path / dirname
            relative = candidate.relative_to(root)
            if candidate.is_symlink() or _is_excluded(relative):
                continue
            kept_dirs.append(dirname)
        dir_names[:] = kept_dirs

        for filename in sorted(file_names):
            candidate = current_path / filename
            relative = candidate.relative_to(root)
            if candidate.is_symlink() or _is_excluded(relative) or not candidate.is_file():
                continue
            result.append((candidate, relative))
    return result


def compute_sha256_manifest(repository_root: Path) -> dict[str, str]:
    """Hash every file that is inside the M5B copy boundary.

    Paths are repository-relative POSIX strings so manifests are stable across
    Windows and POSIX hosts.  Excluded content is deliberately not part of the
    integrity contract because it is never copied into the patch workspace.
    """
    root = repository_root.resolve()
    if not root.is_dir():
        raise ValueError(f"repository root is not a directory: {root}")
    manifest: dict[str, str] = {}
    for path, relative in _iter_copyable_files(root):
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        manifest[relative.as_posix()] = digest.hexdigest()
    return dict(sorted(manifest.items()))


class IsolatedPatchWorkspace:
    """Context manager that copies a repository into a disposable workspace."""

    def __init__(self, repository_root: Path) -> None:
        self.source = repository_root.resolve()
        self.path: Path | None = None
        self._temp_dir: Path | None = None
        self.original_before_hashes: dict[str, str] = {}
        self.cleanup_succeeded: bool | None = None

    def __enter__(self) -> IsolatedPatchWorkspace:
        if not self.source.is_dir():
            raise ValueError(f"repository root is not a directory: {self.source}")
        self.original_before_hashes = compute_sha256_manifest(self.source)
        temp_dir = Path(tempfile.mkdtemp(prefix="springfix-patch-"))
        destination = temp_dir / "repository"
        destination.mkdir()
        self._temp_dir = temp_dir
        try:
            self._copy_tree(destination)
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            self._temp_dir = None
            raise
        self.path = destination.resolve()
        self.cleanup_succeeded = None
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Clean up the temporary copy even when application fails."""
        del exc_type, exc_value, traceback
        success = True
        if self._temp_dir is not None and self._temp_dir.exists():
            try:
                shutil.rmtree(self._temp_dir)
            except OSError:
                success = False
        self.cleanup_succeeded = success
        self.path = None
        self._temp_dir = None

    def verify_source_unchanged(self) -> bool:
        """Compare the source manifest captured before copying with the current one."""
        try:
            return self.original_before_hashes == compute_sha256_manifest(self.source)
        except (OSError, ValueError):
            return False

    def _copy_tree(self, destination: Path) -> None:
        """Copy only regular files inside the allowlisted workspace boundary."""
        for source_path, relative in _iter_copyable_files(self.source):
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target)


def create_isolated_patch_workspace(repository_root: Path) -> IsolatedPatchWorkspace:
    """Return a disposable M5B patch workspace context manager."""
    return IsolatedPatchWorkspace(repository_root)


__all__ = [
    "IsolatedPatchWorkspace",
    "compute_sha256_manifest",
    "create_isolated_patch_workspace",
]
