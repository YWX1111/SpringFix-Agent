"""Path safety tests (1-6 from M1 acceptance list)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from springfix_agent.tools._path_safety import (
    PathSafetyError,
    canonicalize_repository,
    resolve_relative_path,
)


def test_canonicalize_repository_accepts_valid(allow_root: Path, sample_repo: Path) -> None:
    """Case 1: a valid repo inside allow_root canonicalizes successfully."""
    result = canonicalize_repository(sample_repo, allow_root)
    assert result == sample_repo.resolve()
    assert result.is_dir()


def test_canonicalize_repository_rejects_missing(allow_root: Path) -> None:
    """Case 2: a non-existent path is rejected."""
    missing = allow_root / "does-not-exist"
    with pytest.raises(PathSafetyError, match="does not exist"):
        canonicalize_repository(missing, allow_root)


def test_canonicalize_repository_rejects_file(allow_root: Path) -> None:
    """Case 3: a file (not a directory) is rejected."""
    file_path = allow_root / "not-a-dir.txt"
    file_path.write_text("hello", encoding="utf-8")
    with pytest.raises(PathSafetyError, match="not a directory"):
        canonicalize_repository(file_path, allow_root)


def test_canonicalize_repository_rejects_outside_allow_root(allow_root: Path, tmp_path: Path) -> None:
    """Case 4: a path outside allow_root is rejected."""
    outside = tmp_path / "outside-repo"
    outside.mkdir()
    with pytest.raises(PathSafetyError, match="outside allow_root"):
        canonicalize_repository(outside, allow_root)


def test_resolve_relative_path_rejects_dotdot_escape(sample_repo: Path) -> None:
    """Case 5: ../ path that escapes repository is rejected."""
    with pytest.raises(PathSafetyError, match="escapes repository"):
        resolve_relative_path("../../etc/passwd", sample_repo)


def test_resolve_relative_path_rejects_absolute(sample_repo: Path) -> None:
    """Absolute paths are rejected outright (or detected as escaping on Windows)."""
    with pytest.raises(PathSafetyError, match=r"(absolute paths|escapes repository)"):
        resolve_relative_path("/etc/passwd", sample_repo)


def test_resolve_relative_path_accepts_inside(sample_repo: Path) -> None:
    """A legitimate relative path inside the repo resolves successfully."""
    resolved = resolve_relative_path("pom.xml", sample_repo)
    assert resolved == (sample_repo / "pom.xml").resolve()


def test_resolve_relative_path_rejects_symlink_escape(sample_repo: Path, tmp_path: Path) -> None:
    """Case 6: symlink whose target escapes repository is rejected."""
    if os.name == "nt" and not getattr(os, "symlink", None):
        pytest.skip("symlinks not supported on this Windows build")
    if sys.platform == "win32":
        try:
            import ctypes  # noqa: PLC0415

            if not ctypes.windll.kernel32.IsUserAnAdmin():  # type: ignore[attr-defined]
                pytest.skip("symlink test requires admin privileges on Windows")
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"cannot determine admin status: {exc}")

    outside_target = tmp_path / "outside-target.txt"
    outside_target.write_text("secret", encoding="utf-8")
    link_path = sample_repo / "escape-link.txt"
    try:
        os.symlink(outside_target, link_path)
    except OSError as exc:
        pytest.skip(f"symlink creation failed: {exc}")

    with pytest.raises(PathSafetyError, match="escapes repository"):
        resolve_relative_path("escape-link.txt", sample_repo)
