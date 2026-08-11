"""Create a short-lived, agent-safe view of a benchmark repository.

Benchmark samples contain documentation, build output and tests that can leak
the answer or change the cost of a run.  The Agent receives only the copied
tree produced here; the original sample is never passed to the graph.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from types import TracebackType

DEFAULT_EXCLUDED_DIRECTORIES = frozenset({".git", "target", "benchmark", "artifacts"})
DEFAULT_EXCLUDED_FILES = frozenset({"README.md"})


def _is_test_directory(relative_path: Path) -> bool:
    """Return whether a path is inside the conventional ``src/test`` tree."""
    parts = tuple(part.lower() for part in relative_path.parts)
    return len(parts) >= 2 and parts[-2:] == ("src", "test")


def _excluded(relative_path: Path, *, include_tests: bool) -> bool:
    """Return whether a relative path must not be copied to the agent view."""
    parts = tuple(part.lower() for part in relative_path.parts)
    if any(part in DEFAULT_EXCLUDED_DIRECTORIES for part in parts):
        return True
    if not include_tests and any(
        parts[index : index + 2] == ("src", "test") for index in range(max(0, len(parts) - 1))
    ):
        return True
    name = relative_path.name
    if name.lower() in {item.lower() for item in DEFAULT_EXCLUDED_FILES}:
        return True
    if relative_path.suffix.lower() == ".md":
        return True
    return name.lower() == ".env" or name.lower().startswith(".env.")


class RepositoryView:
    """Context manager holding a sanitized temporary repository copy."""

    def __init__(self, source: Path, *, include_tests: bool = False) -> None:
        self.source = source.resolve()
        self.include_tests = include_tests
        self.path: Path | None = None
        self._temp_dir: Path | None = None

    def __enter__(self) -> RepositoryView:
        if not self.source.is_dir():
            raise ValueError(f"benchmark repository is not a directory: {self.source}")
        temp_root = Path(tempfile.mkdtemp(prefix="springfix-benchmark-"))
        self._temp_dir = temp_root
        destination = temp_root / "repository"
        destination.mkdir()
        try:
            self._copy_tree(destination)
        except Exception:
            shutil.rmtree(temp_root, ignore_errors=True)
            self._temp_dir = None
            raise
        self.path = destination.resolve()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Remove the temporary view even when graph execution fails."""
        if self._temp_dir is not None and self._temp_dir.exists():
            shutil.rmtree(self._temp_dir)
        self.path = None
        self._temp_dir = None

    def _copy_tree(self, destination: Path) -> None:
        """Copy regular files while pruning answer-bearing or unsafe content."""
        source_root = self.source
        for current, dir_names, file_names in os.walk(source_root, followlinks=False):
            current_path = Path(current)
            relative_dir = current_path.relative_to(source_root)
            if relative_dir != Path(".") and _excluded(
                relative_dir, include_tests=self.include_tests
            ):
                dir_names[:] = []
                continue

            kept_dirs: list[str] = []
            for dirname in dir_names:
                candidate = current_path / dirname
                relative = candidate.relative_to(source_root)
                if candidate.is_symlink() or _excluded(relative, include_tests=self.include_tests):
                    continue
                kept_dirs.append(dirname)
                (destination / relative).mkdir(parents=True, exist_ok=True)
            dir_names[:] = kept_dirs

            output_dir = destination / relative_dir
            output_dir.mkdir(parents=True, exist_ok=True)
            for filename in file_names:
                candidate = current_path / filename
                relative = candidate.relative_to(source_root)
                if candidate.is_symlink() or _excluded(relative, include_tests=self.include_tests):
                    continue
                if not candidate.is_file():
                    continue
                shutil.copy2(candidate, destination / relative)


def create_repository_view(source: Path, *, include_tests: bool = False) -> RepositoryView:
    """Return a context manager for one sanitized benchmark repository."""
    return RepositoryView(source, include_tests=include_tests)


RepositorySanitizer = RepositoryView
sanitize_repository = create_repository_view
