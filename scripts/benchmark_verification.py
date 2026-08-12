"""Reusable Maven/Surefire verification for the M4B sample projects.

This module contains no agent or LLM code.  It executes a real Maven test,
requires a non-zero exit caused by a JUnit assertion, and validates the exact
Surefire testcase counters and failure terms declared by the manifest.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from springfix_agent.repair.maven_verifier import (
    build_restricted_maven_environment,
)
from springfix_agent.repair.maven_verifier import (
    extract_major_version as _extract_major_version_impl,
)
from springfix_agent.repair.maven_verifier import (
    find_maven_binary as _find_maven_binary_impl,
)
from springfix_agent.repair.maven_verifier import (
    find_suitable_jdk as _find_suitable_jdk_impl,
)
from springfix_agent.repair.maven_verifier import (
    find_surefire_xml as _find_surefire_xml_impl,
)
from springfix_agent.repair.maven_verifier import (
    parse_java_major_version as _parse_java_major_version_impl,
)
from springfix_agent.repair.maven_verifier import (
    parse_surefire_xml as _parse_surefire_xml_impl,
)

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
    return _extract_major_version_impl(version_output)


def parse_java_major_version(java_bin: Path) -> int | None:
    """Run ``java -version`` without modifying the parent environment."""
    return _parse_java_major_version_impl(java_bin)


def _java_bin_in(java_home: str | Path) -> Path:
    """Return the platform-specific Java binary under a JDK home."""
    return Path(java_home) / "bin" / ("java.exe" if sys.platform == "win32" else "java")


def find_suitable_jdk(
    *,
    min_version: int = MIN_JAVA_VERSION,
    env: dict[str, str] | None = None,
) -> tuple[str | None, int | None]:
    """Find a JDK meeting ``min_version`` without changing ``os.environ``."""
    return _find_suitable_jdk_impl(min_version=min_version, env=env)


def find_maven_binary() -> str | None:
    """Find a Maven launcher on PATH, including Windows launcher suffixes."""
    return _find_maven_binary_impl()


def parse_surefire_xml(xml_files: list[Path]) -> list[SuiteRecord]:
    """Parse Surefire XML files into small, serializable suite records."""
    return [
        {
            "suite_name": suite.suite_name,
            "tests": suite.tests,
            "failures": suite.failures,
            "errors": suite.errors,
            "skipped": suite.skipped,
            "testcases": [
                {
                    "name": testcase.name,
                    "classname": testcase.classname,
                    "time": "0",
                    "failure_message": testcase.failure_message,
                    "failure_content": testcase.failure_content,
                    "error_message": testcase.error_message,
                }
                for testcase in suite.testcases
            ],
        }
        for suite in _parse_surefire_xml_impl(xml_files)
    ]


def find_surefire_xml(sample_dir: Path) -> list[Path]:
    """Find all standard Surefire XML reports for a sample."""
    return _find_surefire_xml_impl(sample_dir)


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

    environment = build_restricted_maven_environment(java_home=java_home)
    try:
        completed = subprocess.run(
            [maven, "test"],
            cwd=sample_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            shell=False,
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
