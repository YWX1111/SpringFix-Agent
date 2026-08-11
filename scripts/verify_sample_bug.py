"""Backward-compatible verifier for the original transaction Sample.

The reusable Maven/Surefire implementation lives in
``scripts/benchmark_verification.py``.  This wrapper keeps the original
command and the original unit-test helper names stable.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import benchmark_verification as _benchmark  # noqa: E402
from benchmark_verification import (  # noqa: E402
    MavenExpectation,
    _parse_java_major_version,
    find_maven_binary,
    validate_surefire,
    verify_sample,
)

_extract_major_version = _benchmark.extract_major_version
_parse_surefire_xml = _benchmark.parse_surefire_xml
_find_surefire_xml = _benchmark.find_surefire_xml

SAMPLE_DIR_NAME = "sample-springboot-bug-transaction-self-invocation"
EXPECTED_TEST_NAME = "shouldRollbackOrderWhenInnerMethodThrows"
MIN_JAVA_VERSION = 17
FAILURE_KEYWORDS = ("expected", "rollback", "self-invocation")

_EXPECTATION = MavenExpectation(
    test_name=EXPECTED_TEST_NAME,
    tests=1,
    failures=1,
    errors=0,
    skipped=0,
    required_failure_terms=FAILURE_KEYWORDS,
)


def _java_bin_in(java_home: str | Path) -> Path:
    """Return the Java binary path used by the compatibility JDK seam."""
    return Path(java_home) / "bin" / ("java.exe" if sys.platform == "win32" else "java")


def _find_suitable_jdk(
    *,
    min_version: int = MIN_JAVA_VERSION,
    env: dict[str, str] | None = None,
) -> tuple[str | None, int | None]:
    """Find a suitable JDK while preserving the historical patchable seam."""
    lookup_env = env if env is not None else os.environ
    current_home = lookup_env.get("JAVA_HOME", "")
    if current_home:
        version = _parse_java_major_version(_java_bin_in(current_home))
        if version is not None and version >= min_version:
            return current_home, version

    path_java = shutil.which("java")
    if path_java:
        version = _parse_java_major_version(Path(path_java))
        if version is not None and version >= min_version:
            return str(Path(path_java).resolve().parent.parent), version

    if sys.platform == "win32":
        search_dirs = (
            Path("C:/Program Files/Java"),
            Path("C:/Program Files/Eclipse Adoptium"),
            Path("C:/Program Files/Microsoft"),
            Path("C:/Program Files/AdoptOpenJDK"),
            Path("C:/Program Files/Zulu"),
        )
    elif sys.platform == "darwin":
        search_dirs = (Path("/Library/Java/JavaVirtualMachines"),)
    else:
        search_dirs = (Path("/usr/lib/jvm"), Path("/usr/local/lib/jvm"))

    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue
        for child in sorted(search_dir.iterdir(), reverse=True):
            if not child.is_dir():
                continue
            version = _parse_java_major_version(_java_bin_in(child))
            if version is not None and version >= min_version:
                return str(child), version
    return None, None


def _find_sample_dir() -> Path:
    """Locate the transaction Sample relative to this script or CWD."""
    project_root = SCRIPT_DIR.parent
    candidates = (
        project_root / "samples" / SAMPLE_DIR_NAME,
        Path.cwd() / "samples" / SAMPLE_DIR_NAME,
        Path.cwd() / SAMPLE_DIR_NAME,
    )
    for candidate in candidates:
        if candidate.is_dir() and (candidate / "pom.xml").is_file():
            return candidate
    raise FileNotFoundError(f"could not locate sample project {SAMPLE_DIR_NAME}")


def _require_binary(name: str) -> None:
    """Keep the original helper's exit behaviour for callers."""
    found = find_maven_binary() if name == "mvn" else shutil.which(name)
    if found:
        return
    print(f"[verify-sample-bug] required binary not found on PATH: {name}", file=sys.stderr)
    raise SystemExit(1)


def _validate_surefire(
    suites: list[dict[str, object]],
) -> tuple[bool, list[str]]:
    """Validate the original sample using the reusable generic validator."""
    return validate_surefire(suites, _EXPECTATION)  # type: ignore[arg-type]


def main() -> int:
    """Run the original transaction verification command."""
    _require_binary("mvn")
    _require_binary("java")
    try:
        sample_dir = _find_sample_dir()
    except FileNotFoundError as exc:
        print(f"[verify-sample-bug] {exc}", file=sys.stderr)
        return 1

    # The generic runner performs JDK discovery and does not mutate os.environ.
    result = verify_sample(sample_dir, _EXPECTATION, min_java_version=MIN_JAVA_VERSION)
    for line in result.diagnostics:
        print(f"[verify-sample-bug] {line}")
    print()
    if result.passed:
        print("[verify-sample-bug] sample bug verified as expected.")
        return 0
    print("[verify-sample-bug] FAIL: sample did not match the expected failure.", file=sys.stderr)
    if not result.suites and result.stderr:
        excerpt = "\n".join(result.stderr.splitlines()[-20:])
        print(f"\n[verify-sample-bug] Console excerpt:\n{excerpt}", file=sys.stderr)
    return 1 if result.environment_issue else 2


if __name__ == "__main__":
    raise SystemExit(main())
