"""Reusable Maven/Surefire verification for the M4B sample projects.

This module contains no agent or LLM code.  It executes a real Maven test,
requires a non-zero exit caused by a JUnit assertion, and validates the exact
Surefire testcase counters and failure terms declared by the manifest.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

MIN_JAVA_VERSION = 17
_JAVA_VERSION_RE = re.compile(r'"(\d+)(?:\.(\d+))?')


class TestCaseRecord(TypedDict):
    name: str
    classname: str
    time: str
    failure_message: str | None
    failure_content: str | None
    error_message: str | None


class SuiteRecord(TypedDict):
    suite_name: str
    tests: int
    failures: int
    errors: int
    skipped: int
    testcases: list[TestCaseRecord]


@dataclass(frozen=True)
class MavenExpectation:
    """Surefire expectations for one benchmark testcase."""

    test_name: str
    tests: int
    failures: int
    errors: int
    skipped: int
    required_failure_terms: tuple[str, ...] = ()


@dataclass
class MavenVerificationResult:
    """Full result of one Maven benchmark verification."""

    passed: bool
    environment_issue: bool
    returncode: int | None
    diagnostics: list[str]
    suites: list[SuiteRecord]
    stdout: str = ""
    stderr: str = ""


def extract_major_version(version_output: str) -> int | None:
    """Parse modern and legacy Java version strings."""
    match = _JAVA_VERSION_RE.search(version_output)
    if not match:
        return None
    major = int(match.group(1))
    if major == 1:
        minor = match.group(2)
        return int(minor) if minor else None
    return major


def parse_java_major_version(java_bin: Path) -> int | None:
    """Run ``java -version`` without modifying the parent environment."""
    if not java_bin.exists():
        return None
    try:
        result = subprocess.run(
            [str(java_bin), "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    combined = (result.stdout or "") + (result.stderr or "")
    return extract_major_version(combined)


def _java_bin_in(java_home: str | Path) -> Path:
    """Return the platform-specific Java binary under a JDK home."""
    return Path(java_home) / "bin" / ("java.exe" if sys.platform == "win32" else "java")


def find_suitable_jdk(
    *,
    min_version: int = MIN_JAVA_VERSION,
    env: dict[str, str] | None = None,
) -> tuple[str | None, int | None]:
    """Find a JDK meeting ``min_version`` without changing ``os.environ``."""
    lookup_env = env if env is not None else os.environ

    current_home = lookup_env.get("JAVA_HOME", "")
    if current_home:
        version = parse_java_major_version(_java_bin_in(current_home))
        if version is not None and version >= min_version:
            return current_home, version

    path_java = shutil.which("java", path=lookup_env.get("PATH"))
    if path_java:
        version = parse_java_major_version(Path(path_java))
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
            version = parse_java_major_version(_java_bin_in(child))
            if version is not None and version >= min_version:
                return str(child), version
    return None, None


def find_maven_binary() -> str | None:
    """Find a Maven launcher on PATH, including Windows launcher suffixes."""
    for name in ("mvn", "mvn.cmd", "mvn.bat", "mvn.exe"):
        path = shutil.which(name)
        if path:
            return path
    return None


def parse_surefire_xml(xml_files: list[Path]) -> list[SuiteRecord]:
    """Parse Surefire XML files into small, serializable suite records."""
    suites: list[SuiteRecord] = []
    for xml_path in xml_files:
        try:
            root = ET.parse(xml_path).getroot()  # noqa: S314
        except (ET.ParseError, OSError, ValueError):
            continue
        testcases: list[TestCaseRecord] = []
        for testcase in root.findall(".//testcase"):
            failure = testcase.find("failure")
            error = testcase.find("error")
            testcases.append(
                {
                    "name": testcase.get("name", ""),
                    "classname": testcase.get("classname", ""),
                    "time": testcase.get("time", "0"),
                    "failure_message": (
                        failure.get("message", "") if failure is not None else None
                    ),
                    "failure_content": failure.text if failure is not None else None,
                    "error_message": error.get("message", "") if error is not None else None,
                }
            )
        try:
            suite: SuiteRecord = {
                "suite_name": root.get("name", ""),
                "tests": int(root.get("tests", "0")),
                "failures": int(root.get("failures", "0")),
                "errors": int(root.get("errors", "0")),
                "skipped": int(root.get("skipped", "0")),
                "testcases": testcases,
            }
        except (TypeError, ValueError):
            continue
        suites.append(suite)
    return suites


def find_surefire_xml(sample_dir: Path) -> list[Path]:
    """Find all standard Surefire XML reports for a sample."""
    reports_dir = sample_dir / "target" / "surefire-reports"
    if not reports_dir.is_dir():
        return []
    return sorted(reports_dir.glob("TEST-*.xml"))


def validate_surefire(
    suites: list[SuiteRecord], expectation: MavenExpectation,
) -> tuple[bool, list[str]]:
    """Validate exact counters and assertion-failure content for a testcase."""
    if not suites:
        return False, ["no Surefire XML reports found"]

    target_suite: SuiteRecord | None = None
    target_test: TestCaseRecord | None = None
    for suite in suites:
        for testcase in suite["testcases"]:
            if testcase["name"] == expectation.test_name:
                target_suite = suite
                target_test = testcase
                break
        if target_suite is not None:
            break

    if target_suite is None or target_test is None:
        return False, [f"target test {expectation.test_name} not found in any Surefire report"]

    checks: list[tuple[str, bool]] = [
        (f"tests = {expectation.tests}", target_suite["tests"] == expectation.tests),
        (f"failures = {expectation.failures}", target_suite["failures"] == expectation.failures),
        (f"errors = {expectation.errors}", target_suite["errors"] == expectation.errors),
        (f"skipped = {expectation.skipped}", target_suite["skipped"] == expectation.skipped),
        (f"testcase {expectation.test_name} exists", True),
        (
            "failure element present",
            (target_test["failure_message"] is not None) == (expectation.failures > 0),
        ),
    ]
    failure_text = (
        str(target_test["failure_message"] or "")
        + " "
        + str(target_test["failure_content"] or "")
    ).lower()
    for term in expectation.required_failure_terms:
        checks.append((f"failure contains '{term}'", term.lower() in failure_text))

    diagnostics = [f"  [{'PASS' if ok else 'FAIL'}] {label}" for label, ok in checks]
    return all(ok for _, ok in checks), diagnostics


def verify_sample(
    sample_dir: Path,
    expectation: MavenExpectation,
    *,
    min_java_version: int = MIN_JAVA_VERSION,
    timeout_seconds: int = 600,
) -> MavenVerificationResult:
    """Run Maven and verify one sample against a precise expectation."""
    maven = find_maven_binary()
    if maven is None:
        return MavenVerificationResult(
            passed=False,
            environment_issue=True,
            returncode=None,
            diagnostics=["required binary not found on PATH: mvn"],
            suites=[],
        )
    java_home, java_version = find_suitable_jdk(min_version=min_java_version)
    if java_home is None or java_version is None:
        return MavenVerificationResult(
            passed=False,
            environment_issue=True,
            returncode=None,
            diagnostics=[f"Java {min_java_version}+ not found"],
            suites=[],
        )
    if not sample_dir.is_dir() or not (sample_dir / "pom.xml").is_file():
        return MavenVerificationResult(
            passed=False,
            environment_issue=True,
            returncode=None,
            diagnostics=[f"sample directory or pom.xml missing: {sample_dir}"],
            suites=[],
        )

    environment = os.environ.copy()
    environment["JAVA_HOME"] = java_home
    environment["MAVEN_OPTS"] = (
        environment.get("MAVEN_OPTS", "") + " -Dfile.encoding=UTF-8"
    ).strip()
    try:
        completed = subprocess.run(
            [maven, "test"],
            cwd=sample_dir,
            capture_output=True,
            text=True,
            env=environment,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return MavenVerificationResult(
            passed=False,
            environment_issue=False,
            returncode=None,
            diagnostics=[f"Maven execution failed: {type(exc).__name__}: {exc}"],
            suites=[],
        )

    suites = parse_surefire_xml(find_surefire_xml(sample_dir))
    diagnostics: list[str] = [
        f"using Java {java_version} from: {java_home}",
        f"Maven exit code: {completed.returncode}",
    ]
    if completed.returncode == 0:
        diagnostics.append("mvn test exited with 0; expected a deliberate failing test")
        return MavenVerificationResult(
            passed=False,
            environment_issue=False,
            returncode=completed.returncode,
            diagnostics=diagnostics,
            suites=suites,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )
    if not suites:
        diagnostics.append(
            "Maven failed but no Surefire XML reports were found; this is not a target assertion failure"
        )
        return MavenVerificationResult(
            passed=False,
            environment_issue=False,
            returncode=completed.returncode,
            diagnostics=diagnostics,
            suites=[],
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )

    passed, validation_diagnostics = validate_surefire(suites, expectation)
    diagnostics.extend(validation_diagnostics)
    return MavenVerificationResult(
        passed=passed,
        environment_issue=False,
        returncode=completed.returncode,
        diagnostics=diagnostics,
        suites=suites,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


# Private aliases keep the original transaction verifier's test seam stable.
_extract_major_version = extract_major_version
_parse_java_major_version = parse_java_major_version
_find_suitable_jdk = find_suitable_jdk
_parse_surefire_xml = parse_surefire_xml
_find_surefire_xml = find_surefire_xml
