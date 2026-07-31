"""Verify the sample Spring Boot Bug project reproduces the expected failure.

Gold standard: Surefire XML reports (target/surefire-reports/TEST-*.xml).
Console output is auxiliary diagnostic only.

Expected behaviour:
    - Maven exit code: non-zero
    - Surefire XML: tests=1, failures=1, errors=0, skipped=0
    - Test name: shouldRollbackOrderWhenInnerMethodThrows
    - Failure message contains transaction-related assertion keywords

Exit codes:
    0 - sample bug verified as expected
    1 - environment issue (no mvn/java, sample dir missing, no Java 17+)
    2 - Maven ran but results did not match the expected failure signature
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SAMPLE_DIR_NAME = "sample-springboot-bug-transaction-self-invocation"
EXPECTED_TEST_NAME = "shouldRollbackOrderWhenInnerMethodThrows"

# Minimum Java major version required by the sample project (pom.xml).
MIN_JAVA_VERSION = 17

# Stable keywords that must appear in the failure message/content.
FAILURE_KEYWORDS = (
    "expected",
    "rollback",
    "self-invocation",
)

# Java version extraction regex: "17.0.2", "21.0.1", "1.8.0_362"
_JAVA_VERSION_RE = re.compile(r'"(\d+)(?:\.(\d+))?')


def _parse_java_major_version(java_bin: Path) -> int | None:
    """Run ``java -version`` and return the major version, or None on error."""
    if not java_bin.exists():
        return None
    try:
        result = subprocess.run(
            [str(java_bin), "-version"],
            capture_output=True, text=True, timeout=10,
        )
        combined = (result.stdout or "") + (result.stderr or "")
        return _extract_major_version(combined)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _extract_major_version(version_output: str) -> int | None:
    """Parse major version from ``java -version`` output.

    Handles: "17.0.2", "21.0.1", legacy "1.8.0_362".
    Returns None if parsing fails.
    """
    m = _JAVA_VERSION_RE.search(version_output)
    if not m:
        return None
    major = int(m.group(1))
    if major == 1:
        # Legacy format: "1.8.0_362" → major = 8
        minor = m.group(2)
        return int(minor) if minor else None
    return major


def _java_bin_in(java_home: str | Path) -> Path:
    """Return the java binary path inside a JAVA_HOME directory."""
    return Path(java_home) / "bin" / ("java.exe" if sys.platform == "win32" else "java")


def _find_suitable_jdk(
    *,
    min_version: int = MIN_JAVA_VERSION,
    env: dict[str, str] | None = None,
) -> tuple[str | None, int | None]:
    """Find a JDK meeting minimum version requirement.

    Discovery order:
        1. Current process JAVA_HOME (if version sufficient)
        2. PATH java binary (if version sufficient)
        3. Platform-specific common JDK install directories
        4. None if nothing meets requirement

    Does NOT modify ``os.environ``. Uses ``env`` parameter for
    environment lookup (falls back to ``os.environ`` if None).

    Returns:
        (java_home_path, major_version) or (None, None)
    """
    lookup_env = env if env is not None else os.environ

    # 1. Current JAVA_HOME.
    current_home = lookup_env.get("JAVA_HOME", "")
    if current_home:
        java_bin = _java_bin_in(current_home)
        ver = _parse_java_major_version(java_bin)
        if ver is not None and ver >= min_version:
            return current_home, ver

    # 2. PATH java.
    path_java = shutil.which("java")
    if path_java:
        ver = _parse_java_major_version(Path(path_java))
        if ver is not None and ver >= min_version:
            # Try to derive JAVA_HOME from java binary.
            java_home = str(Path(path_java).resolve().parent.parent)
            return java_home, ver

    # 3. Platform-specific common install directories.
    search_dirs: list[Path] = []
    if sys.platform == "win32":
        search_dirs.extend([
            Path("C:/Program Files/Java"),
            Path("C:/Program Files/Eclipse Adoptium"),
            Path("C:/Program Files/Microsoft"),
            Path("C:/Program Files/AdoptOpenJDK"),
            Path("C:/Program Files/Zulu"),
        ])
    elif sys.platform == "darwin":
        # macOS: standard JDK install locations.
        search_dirs.extend([
            Path("/Library/Java/JavaVirtualMachines"),
        ])
    else:
        # Linux: setup-java and package managers use these.
        search_dirs.extend([
            Path("/usr/lib/jvm"),
            Path("/usr/local/lib/jvm"),
        ])

    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue
        # Sort reverse to prefer higher versions.
        for child in sorted(search_dir.iterdir(), reverse=True):
            if not child.is_dir():
                continue
            java_bin = _java_bin_in(child)
            ver = _parse_java_major_version(java_bin)
            if ver is not None and ver >= min_version:
                return str(child), ver

    return None, None


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
    """Verify a required binary is callable."""
    path = shutil.which(name)
    if path:
        return
    if sys.platform == "win32":
        for ext in (".cmd", ".bat", ".exe"):
            if shutil.which(name + ext):
                return
    print(f"[verify-sample-bug] required binary not found on PATH: {name}", file=sys.stderr)
    sys.exit(1)


def _find_surefire_xml(sample_dir: Path) -> list[Path]:
    """Find Surefire XML report files."""
    reports_dir = sample_dir / "target" / "surefire-reports"
    if not reports_dir.is_dir():
        return []
    return sorted(reports_dir.glob("TEST-*.xml"))


def _parse_surefire_xml(
    xml_files: list[Path],
) -> list[dict[str, object]]:
    """Parse Surefire XML reports and extract test suite information.

    Returns a list of dicts with keys:
        - suite_name: str
        - tests: int
        - failures: int
        - errors: int
        - skipped: int
        - testcases: list of dicts with name, classname, time, failure_message, failure_content
    """
    suites: list[dict[str, object]] = []
    for xml_path in xml_files:
        try:
            tree = ET.parse(xml_path)  # noqa: S314
            root = tree.getroot()
        except ET.ParseError:
            continue

        suite: dict[str, object] = {
            "suite_name": root.get("name", ""),
            "tests": int(root.get("tests", "0")),
            "failures": int(root.get("failures", "0")),
            "errors": int(root.get("errors", "0")),
            "skipped": int(root.get("skipped", "0")),
            "testcases": [],
        }

        for tc in root.findall("testcase"):
            tc_info: dict[str, object] = {
                "name": tc.get("name", ""),
                "classname": tc.get("classname", ""),
                "time": tc.get("time", "0"),
                "failure_message": None,
                "failure_content": None,
                "error_message": None,
            }
            failure_elem = tc.find("failure")
            if failure_elem is not None:
                tc_info["failure_message"] = failure_elem.get("message", "")
                tc_info["failure_content"] = failure_elem.text or ""
            error_elem = tc.find("error")
            if error_elem is not None:
                tc_info["error_message"] = error_elem.get("message", "")
            suite["testcases"].append(tc_info)  # type: ignore[union-attr]

        suites.append(suite)
    return suites


def _validate_surefire(
    suites: list[dict[str, object]],
) -> tuple[bool, list[str]]:
    """Validate Surefire results against expected bug signature.

    Returns (passed, diagnostics) where diagnostics describes each check.
    """
    checks: list[tuple[str, bool]] = []

    if not suites:
        return False, ["no Surefire XML reports found"]

    # Find the target test suite.
    target_suite = None
    for s in suites:
        for tc in s["testcases"]:  # type: ignore[union-attr]
            if tc["name"] == EXPECTED_TEST_NAME:
                target_suite = s
                break
        if target_suite is not None:
            break

    if target_suite is None:
        return False, [
            f"target test {EXPECTED_TEST_NAME} not found in any Surefire report"
        ]

    checks.append(("tests = 1", int(target_suite["tests"]) == 1))  # type: ignore[arg-type]
    checks.append(("failures = 1", int(target_suite["failures"]) == 1))  # type: ignore[arg-type]
    checks.append(("errors = 0", int(target_suite["errors"]) == 0))  # type: ignore[arg-type]
    checks.append(("skipped = 0", int(target_suite["skipped"]) == 0))  # type: ignore[arg-type]

    # Find the target testcase.
    target_tc = None
    for tc in target_suite["testcases"]:  # type: ignore[union-attr]
        if tc["name"] == EXPECTED_TEST_NAME:
            target_tc = tc
            break

    if target_tc is None:
        checks.append((f"testcase {EXPECTED_TEST_NAME} exists", False))
    else:
        checks.append((f"testcase {EXPECTED_TEST_NAME} exists", True))
        checks.append(("failure element present", target_tc["failure_message"] is not None))

        # Check failure content contains expected keywords.
        failure_text = (
            str(target_tc.get("failure_message") or "")
            + " "
            + str(target_tc.get("failure_content") or "")
        ).lower()
        for kw in FAILURE_KEYWORDS:
            checks.append((f"failure contains '{kw}'", kw in failure_text))

    diagnostics: list[str] = []
    all_ok = True
    for label, ok in checks:
        diagnostics.append(f"  [{'PASS' if ok else 'FAIL'}] {label}")
        if not ok:
            all_ok = False

    return all_ok, diagnostics


def main() -> int:
    _require_binary("mvn")
    _require_binary("java")

    try:
        sample_dir = _find_sample_dir()
    except FileNotFoundError as e:
        print(f"[verify-sample-bug] {e}", file=sys.stderr)
        return 1

    # Find suitable JDK (does not modify os.environ).
    java_home, java_ver = _find_suitable_jdk(min_version=MIN_JAVA_VERSION)
    if java_home is None:
        print(
            f"[verify-sample-bug] FAIL: Java {MIN_JAVA_VERSION}+ not found. "
            f"The sample project requires Java {MIN_JAVA_VERSION} "
            f"(pom.xml <java.version>{MIN_JAVA_VERSION}</java.version>). "
            f"Current JAVA_HOME: {os.environ.get('JAVA_HOME', '(not set)')}",
            file=sys.stderr,
        )
        return 1

    # Build subprocess environment (does NOT modify os.environ).
    env = {**os.environ, "JAVA_HOME": java_home, "MAVEN_OPTS": "-Dfile.encoding=UTF-8"}
    print(f"[verify-sample-bug] using Java {java_ver} from: {java_home}")
    print(f"[verify-sample-bug] running 'mvn test' in: {sample_dir}")

    result = subprocess.run(
        "mvn test",
        shell=True,
        cwd=sample_dir,
        capture_output=True,
        text=True,
        env=env,
        timeout=600,
    )

    # Phase 1: Check Maven exit code.
    if result.returncode == 0:
        print(
            "[verify-sample-bug] FAIL: mvn test exited with 0; the @Transactional "
            "self-invocation bug may have been fixed. Expected non-zero exit code.",
            file=sys.stderr,
        )
        return 2

    print(f"[verify-sample-bug] Maven exit code: {result.returncode} (non-zero, as expected)")

    # Phase 2: Parse Surefire XML (gold standard).
    xml_files = _find_surefire_xml(sample_dir)
    if not xml_files:
        print(
            "[verify-sample-bug] FAIL: Maven failed but no Surefire XML reports found. "
            "This indicates a build or environment error, not the expected test failure.",
            file=sys.stderr,
        )
        # Print console excerpt for diagnosis.
        combined = (result.stdout or "") + "\n" + (result.stderr or "")
        excerpt = "\n".join(combined.splitlines()[-20:])
        print(f"\n[verify-sample-bug] Console excerpt (last 20 lines):\n{excerpt}", file=sys.stderr)
        return 2

    print(f"[verify-sample-bug] Found {len(xml_files)} Surefire XML report(s)")

    suites = _parse_surefire_xml(xml_files)
    if not suites:
        print(
            "[verify-sample-bug] FAIL: Surefire XML files found but could not be parsed.",
            file=sys.stderr,
        )
        return 2

    # Phase 3: Validate against expected signature.
    passed, diagnostics = _validate_surefire(suites)

    print()
    print("[verify-sample-bug] Surefire validation:")
    for d in diagnostics:
        print(d)
    print()

    if passed:
        print("[verify-sample-bug] sample bug verified as expected.")
        return 0

    print(
        "[verify-sample-bug] FAIL: Maven failed and surefire XML exists, but results "
        "did not match the expected @Transactional self-invocation signature.",
        file=sys.stderr,
    )

    # Print suite summary for diagnosis.
    for s in suites:
        print(
            f"  suite: {s['suite_name']} "
            f"tests={s['tests']} failures={s['failures']} "
            f"errors={s['errors']} skipped={s['skipped']}",
            file=sys.stderr,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
