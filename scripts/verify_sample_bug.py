"""Verify the sample Spring Boot Bug project reproduces the expected failure.

Expected behaviour:
    mvn test must fail with:
        Tests run: 1, Failures: 1, Errors: 0, Skipped: 0
        shouldRollbackOrderWhenInnerMethodThrows
        expected: <0> but was: <1>

Exit codes:
    0 - sample bug verified as expected
    1 - environment issue (no mvn/java, sample dir missing)
    2 - mvn ran but output did not match the expected failure signature
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SAMPLE_DIR_NAME = "sample-springboot-bug-transaction-self-invocation"

# Expected output fragments (any of these must be present to prove the bug)
EXPECTED_TEST_NAME = "shouldRollbackOrderWhenInnerMethodThrows"
EXPECTED_COUNT_PATTERN = re.compile(r"Tests run:\s*1,\s*Failures:\s*1,\s*Errors:\s*0")
EXPECTED_ASSERTION_PATTERN = re.compile(r"expected:\s*<0>\s*but\s*was:\s*<1>")
EXPECTED_FAILURE_LINE = re.compile(
    r"(?:FAILURES?|ERRORS?):\s*" + re.escape(EXPECTED_TEST_NAME)
)


def _find_sample_dir() -> Path:
    """Locate the sample bug directory relative to this script or CWD."""
    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir.parent / "samples" / SAMPLE_DIR_NAME,
        Path.cwd() / "samples" / SAMPLE_DIR_NAME,
        Path.cwd() / SAMPLE_DIR_NAME,
    ]
    for c in candidates:
        if c.is_dir() and (c / "pom.xml").exists():
            return c
    raise FileNotFoundError(
        f"could not locate sample project {SAMPLE_DIR_NAME}; expected under "
        f"one of: {[str(p) for p in candidates]}"
    )


def _require_binary(name: str) -> None:
    """Verify a required binary is callable. Tolerates Windows .cmd wrappers."""
    path = shutil.which(name)
    if path:
        return
    if sys.platform == "win32":
        for ext in (".cmd", ".bat", ".exe"):
            if shutil.which(name + ext):
                return
    print(f"[verify-sample-bug] required binary not found on PATH: {name}", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    _require_binary("mvn")
    _require_binary("java")

    try:
        sample_dir = _find_sample_dir()
    except FileNotFoundError as e:
        print(f"[verify-sample-bug] {e}", file=sys.stderr)
        return 1

    print(f"[verify-sample-bug] running 'mvn test' in: {sample_dir}")

    # shell=True: on Windows this delegates to cmd.exe which resolves
    # mvn.cmd wrappers; on POSIX it delegates to /bin/sh which finds mvn.
    # Arguments are hard-coded so there is no shell-injection surface.
    result = subprocess.run(
        "mvn test",
        shell=True,
        cwd=sample_dir,
        capture_output=True,
        text=True,
        env={**os.environ, "MAVEN_OPTS": "-Dfile.encoding=UTF-8"},
        timeout=600,
    )

    combined = (result.stdout or "") + "\n" + (result.stderr or "")

    checks: list[tuple[str, bool]] = [
        ("test name shouldRollbackOrderWhenInnerMethodThrows", EXPECTED_TEST_NAME in combined),
        ("Tests run: 1, Failures: 1, Errors: 0", bool(EXPECTED_COUNT_PATTERN.search(combined))),
        ("assertion expected:<0> but was:<1>", bool(EXPECTED_ASSERTION_PATTERN.search(combined))),
    ]

    print()
    print("[verify-sample-bug] check results:")
    for label, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    print()

    if result.returncode == 0:
        print(
            "[verify-sample-bug] FAIL: mvn test exited with 0; the @Transactional "
            "self-invocation bug may have been fixed. Expected non-zero exit code.",
            file=sys.stderr,
        )
        return 2

    if all(ok for _, ok in checks):
        print("[verify-sample-bug] sample bug verified as expected.")
        return 0

    print(
        "[verify-sample-bug] FAIL: mvn test failed but output did not match "
        "the expected @Transactional self-invocation signature. "
        "Possible causes: compilation error, dependency failure, test name changed, "
        "assertion changed, or the bug was accidentally fixed.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
