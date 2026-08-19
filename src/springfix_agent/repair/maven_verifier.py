"""Restricted Maven and Surefire verification for M5C.

The verifier owns the command shape, working-directory checks, subprocess
environment, timeout, and report selection.  Callers provide only a trusted
benchmark expectation; they cannot provide a shell command or arbitrary
subprocess arguments.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from springfix_agent.repair.maven_classification import classify_maven_failure
from springfix_agent.repair.verification_models import (
    BaselineVerificationResult,
    MavenTestResult,
)

MIN_JAVA_VERSION = 17
DEFAULT_MAVEN_TIMEOUT_SECONDS = 120
MAX_OUTPUT_TAIL_CHARS = 4096
MAX_OUTPUT_TAIL_LINES = 100
_JAVA_VERSION_RE = re.compile(r'"(\d+)(?:\.(\d+))?')
_SECRET_KEY_RE = re.compile(r"(?:API[_-]?KEY|TOKEN|SECRET|AUTHORIZATION|BEARER|PASSWORD)", re.I)
_SECRET_VALUE_RE = re.compile(
    r"(?i)(api[_ -]?key|token|secret|password|authorization)(\s*[:=]\s*)[^\s,;]+"
)
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{8,}")
_ABSOLUTE_PATH_RE = re.compile(r"(?i)(?:[a-z]:[\\/]|/(?:tmp|var|home|users?)/)[^\s\r\n,;]+")
_JAVA_METHOD_RE = re.compile(r"\b(?:default\s+)?[\w<>\[\], ?]+\s+(\w+)\s*\(")
_JAVA_CLASS_RE = re.compile(r"\bclass\s+(\w+)")
_JAVA_PACKAGE_RE = re.compile(r"\bpackage\s+([\w.]+)\s*;")

_ALLOWED_ENV_KEYS = frozenset(
    {
        "PATH",
        "JAVA_HOME",
        "HOME",
        "USERPROFILE",
        "TEMP",
        "TMP",
        "SYSTEMROOT",
        "MAVEN_HOME",
        "M2_HOME",
        "PATHEXT",
    }
)


class MavenExpectation(Protocol):
    """Trusted manifest fields required by the verifier."""

    test_name: str
    tests: int
    failures: int
    errors: int
    skipped: int
    required_failure_terms: list[str]


@dataclass(frozen=True)
class SurefireTestCase:
    """Small parsed representation of one Surefire testcase."""

    name: str
    classname: str
    failure_message: str | None
    failure_content: str | None
    error_message: str | None
    skipped: bool


@dataclass(frozen=True)
class SurefireSuite:
    """Small parsed representation of one Surefire suite."""

    suite_name: str
    tests: int
    failures: int
    errors: int
    skipped: int
    testcases: tuple[SurefireTestCase, ...]


@dataclass(frozen=True)
class MavenVerificationOutcome:
    """Maven result plus a deterministic failure classification."""

    result: MavenTestResult
    failure_reason: str | None


@dataclass(frozen=True)
class _ProcessResult:
    executed: bool
    timed_out: bool
    returncode: int | None
    stdout: str
    stderr: str
    duration_ms: int


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


def _java_bin_in(java_home: str | Path) -> Path:
    """Return the platform-specific Java binary under a JDK home."""
    return Path(java_home) / "bin" / ("java.exe" if sys.platform == "win32" else "java")


def _lookup_env_value(source_env: dict[str, str], key: str) -> str | None:
    """Read an environment key case-insensitively for Windows compatibility."""
    wanted = key.casefold()
    for actual, value in source_env.items():
        if actual.casefold() == wanted:
            return value
    return None


def _is_secret_key(key: str) -> bool:
    """Return whether a key is credential-like and must not cross the boundary."""
    return bool(_SECRET_KEY_RE.search(key)) or key.upper().endswith(
        ("_API_KEY", "_TOKEN", "_SECRET")
    )


def build_restricted_maven_environment(
    *,
    source_env: dict[str, str] | None = None,
    java_home: str | None = None,
) -> dict[str, str]:
    """Build a minimal subprocess environment without LLM credentials."""
    source = dict(source_env if source_env is not None else os.environ)
    result: dict[str, str] = {}
    for key in sorted(_ALLOWED_ENV_KEYS):
        value = _lookup_env_value(source, key)
        if value is not None and not _is_secret_key(key):
            result[key] = value
    if java_home is not None:
        result["JAVA_HOME"] = java_home
    # Maven needs a stable encoding, but it does not need the caller's Maven
    # options, extension classpath, proxy, or repository injection settings.
    result["MAVEN_OPTS"] = "-Dfile.encoding=UTF-8"
    return result


def parse_java_major_version(java_bin: Path, *, env: dict[str, str] | None = None) -> int | None:
    """Run ``java -version`` with the same restricted environment policy."""
    if not java_bin.is_file():
        return None
    try:
        result = subprocess.run(
            [str(java_bin), "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=build_restricted_maven_environment(source_env=env),
            shell=False,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    combined = (result.stdout or "") + (result.stderr or "")
    return extract_major_version(combined)


def find_suitable_jdk(
    *,
    min_version: int = MIN_JAVA_VERSION,
    env: dict[str, str] | None = None,
) -> tuple[str | None, int | None]:
    """Find a JDK meeting ``min_version`` without modifying the parent environment."""
    lookup_env = env if env is not None else dict(os.environ)
    current_home = _lookup_env_value(lookup_env, "JAVA_HOME") or ""
    if current_home:
        version = parse_java_major_version(
            _java_bin_in(current_home),
            env=lookup_env,
        )
        if version is not None and version >= min_version:
            return current_home, version

    path_value = _lookup_env_value(lookup_env, "PATH")
    path_java = shutil.which("java", path=path_value)
    if path_java:
        version = parse_java_major_version(Path(path_java), env=lookup_env)
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
            version = parse_java_major_version(_java_bin_in(child), env=lookup_env)
            if version is not None and version >= min_version:
                return str(child), version
    return None, None


def find_maven_binary(env: dict[str, str] | None = None) -> str | None:
    """Find a Maven launcher on PATH, including Windows launcher suffixes."""
    lookup_env = env if env is not None else dict(os.environ)
    path_value = _lookup_env_value(lookup_env, "PATH")
    for name in ("mvn", "mvn.cmd", "mvn.bat", "mvn.exe"):
        path = shutil.which(name, path=path_value)
        if path:
            return path
    return None


def read_maven_timeout_seconds(env: dict[str, str] | None = None) -> int:
    """Read a positive bounded timeout from the caller environment."""
    lookup_env = env if env is not None else dict(os.environ)
    raw = _lookup_env_value(lookup_env, "REPAIR_MAVEN_TIMEOUT_SECONDS")
    if raw is None:
        return DEFAULT_MAVEN_TIMEOUT_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAVEN_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_MAVEN_TIMEOUT_SECONDS


def sanitize_output(value: str) -> str:
    """Redact common credential-shaped values before retaining output."""
    redacted = _BEARER_RE.sub("Bearer <redacted>", value)
    redacted = _SECRET_VALUE_RE.sub(r"\1\2<redacted>", redacted)
    return _ABSOLUTE_PATH_RE.sub("<path>", redacted)


def tail_output(value: str) -> str:
    """Keep at most 100 final lines and 4 KiB of sanitized process output."""
    sanitized = sanitize_output(value)
    lines = sanitized.splitlines()
    return "\n".join(lines[-MAX_OUTPUT_TAIL_LINES:])[-MAX_OUTPUT_TAIL_CHARS:]


def parse_surefire_xml(xml_files: list[Path]) -> list[SurefireSuite]:
    """Parse standard Surefire XML while ignoring malformed unrelated files."""
    suites: list[SurefireSuite] = []
    for xml_path in xml_files:
        try:
            root = ET.parse(xml_path).getroot()  # noqa: S314 - local Maven report XML
        except (ET.ParseError, OSError, ValueError):
            continue
        testcases: list[SurefireTestCase] = []
        for testcase in root.findall(".//testcase"):
            failure = testcase.find("failure")
            error = testcase.find("error")
            skipped = testcase.find("skipped") is not None
            testcases.append(
                SurefireTestCase(
                    name=testcase.get("name", ""),
                    classname=testcase.get("classname", ""),
                    failure_message=failure.get("message", "") if failure is not None else None,
                    failure_content=failure.text if failure is not None else None,
                    error_message=error.get("message", "") if error is not None else None,
                    skipped=skipped,
                )
            )
        try:
            suites.append(
                SurefireSuite(
                    suite_name=root.get("name", ""),
                    tests=int(root.get("tests", "0")),
                    failures=int(root.get("failures", "0")),
                    errors=int(root.get("errors", "0")),
                    skipped=int(root.get("skipped", "0")),
                    testcases=tuple(testcases),
                )
            )
        except (TypeError, ValueError):
            continue
    return suites


def find_surefire_xml(workspace: Path) -> list[Path]:
    """Return sorted report files from the workspace only."""
    reports_dir = workspace / "target" / "surefire-reports"
    if not reports_dir.is_dir():
        return []
    return sorted(reports_dir.glob("TEST-*.xml"))


def _target_summary(
    suites: list[SurefireSuite],
    test_name: str,
) -> tuple[bool, int, int, int, int, str]:
    """Aggregate only suites that contain the exact trusted target testcase."""
    method_name = test_name.rsplit("#", 1)[-1]
    matching = [
        suite for suite in suites if any(item.name == method_name for item in suite.testcases)
    ]
    if not matching:
        return False, 0, 0, 0, 0, ""
    target_cases = [
        item
        for suite in matching
        for item in suite.testcases
        if item.name == method_name
    ]
    failure_text = " ".join(
        f"{item.failure_message or ''} {item.failure_content or ''}" for item in target_cases
    )
    return (
        True,
        sum(suite.tests for suite in matching),
        sum(suite.failures for suite in matching),
        sum(suite.errors for suite in matching),
        sum(suite.skipped for suite in matching),
        failure_text,
    )


def _target_failure_element_exists(suites: list[SurefireSuite], test_name: str) -> bool:
    """Return whether the exact target testcase contains a Surefire failure node."""
    method_name = _target_method_name(test_name)
    return any(
        item.name == method_name and item.failure_message is not None
        for suite in suites
        for item in suite.testcases
    )


def _target_method_name(test_name: str) -> str:
    return test_name.rsplit("#", 1)[-1]


def _find_target_test_selector(workspace: Path, test_name: str) -> str | None:
    """Build a Surefire class#method selector from the trusted manifest method."""
    if "#" in test_name:
        class_name, method_name = test_name.split("#", 1)
        if class_name and method_name and re.fullmatch(r"[\w.$]+", class_name):
            return test_name
        return None
    candidates: list[str] = []
    test_root = workspace / "src" / "test" / "java"
    if not test_root.is_dir():
        return None
    for source in sorted(test_root.rglob("*.java")):
        try:
            text = source.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        if not re.search(rf"\b{re.escape(test_name)}\s*\(", text):
            continue
        class_match = _JAVA_CLASS_RE.search(text)
        if class_match is None:
            continue
        package_match = _JAVA_PACKAGE_RE.search(text)
        class_name = class_match.group(1)
        qualified = f"{package_match.group(1)}.{class_name}" if package_match else class_name
        method_match = _JAVA_METHOD_RE.search(
            text[text.find(test_name) - 80 : text.find(test_name) + len(test_name) + 2]
        )
        if method_match is not None and method_match.group(1) != test_name:
            continue
        candidates.append(f"{qualified}#{_target_method_name(test_name)}")
    return candidates[0] if len(candidates) == 1 else None


def _clear_surefire_reports(workspace: Path) -> None:
    """Remove only the temporary workspace's old Surefire reports."""
    root = workspace.resolve()
    reports = (root / "target" / "surefire-reports").resolve()
    try:
        reports.relative_to(root)
    except ValueError as exc:
        raise ValueError("Surefire report path escaped workspace") from exc
    if reports.is_dir():
        shutil.rmtree(reports)


def _execute_maven(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: int,
) -> _ProcessResult:
    """Execute a fixed argument vector without a shell and enforce timeout."""
    started = time.monotonic()
    process: subprocess.Popen[str] | None = None
    try:
        creationflags = 0
        if sys.platform == "win32":
            creationflags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        process = subprocess.Popen(
            args,
            cwd=str(cwd),
            env=env,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=sys.platform != "win32",
            creationflags=creationflags,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            stdout, stderr = process.communicate()
            return _ProcessResult(
                executed=True,
                timed_out=True,
                returncode=process.returncode,
                stdout=str(stdout or exc.stdout or ""),
                stderr=str(stderr or exc.stderr or ""),
                duration_ms=max(0, int((time.monotonic() - started) * 1000)),
            )
        return _ProcessResult(
            executed=True,
            timed_out=False,
            returncode=process.returncode,
            stdout=stdout or "",
            stderr=stderr or "",
            duration_ms=max(0, int((time.monotonic() - started) * 1000)),
        )
    except OSError:
        return _ProcessResult(
            executed=False,
            timed_out=False,
            returncode=None,
            stdout="",
            stderr="",
            duration_ms=max(0, int((time.monotonic() - started) * 1000)),
        )
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()


class MavenRepairVerifier:
    """Verify an original bug and one patched target test deterministically."""

    def __init__(
        self,
        *,
        timeout_seconds: int | None = None,
        environment: dict[str, str] | None = None,
        min_java_version: int = MIN_JAVA_VERSION,
    ) -> None:
        self._environment = dict(environment if environment is not None else os.environ)
        self._timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None and timeout_seconds > 0
            else read_maven_timeout_seconds(self._environment)
        )
        self._min_java_version = min_java_version

    def verify_baseline(
        self,
        repository: Path,
        expectation: MavenExpectation,
    ) -> BaselineVerificationResult:
        """Run the fixed full sample test and require the manifest's bug shape."""
        maven = find_maven_binary(self._environment)
        if maven is None:
            return BaselineVerificationResult(
                verified=False,
                maven_result=MavenTestResult(executed=False, timed_out=False),
                failure_reason="maven_not_found",
            )
        java_home, java_version = find_suitable_jdk(
            min_version=self._min_java_version,
            env=self._environment,
        )
        del java_version
        if java_home is None:
            return BaselineVerificationResult(
                verified=False,
                maven_result=MavenTestResult(executed=False, timed_out=False),
                failure_reason="java_not_compatible",
            )
        _clear_surefire_reports(repository)
        process = _execute_maven(
            [maven, "test"],
            cwd=repository,
            env=build_restricted_maven_environment(
                source_env=self._environment,
                java_home=java_home,
            ),
            timeout_seconds=self._timeout_seconds,
        )
        result = self._result_from_process(repository, expectation, process)
        suites = parse_surefire_xml(find_surefire_xml(repository)) if process.executed else []
        _, _, _, _, _, failure_text = _target_summary(
            suites,
            expectation.test_name,
        )
        reason = self._baseline_failure_reason(
            result,
            expectation,
            failure_text,
            failure_present=_target_failure_element_exists(suites, expectation.test_name),
        )
        return BaselineVerificationResult(
            verified=reason is None,
            maven_result=result,
            failure_reason=reason,
        )

    def verify_patched_workspace(
        self,
        workspace: Path,
        expectation: MavenExpectation,
    ) -> MavenVerificationOutcome:
        """Run only the trusted target test in an active temporary workspace."""
        maven = find_maven_binary(self._environment)
        if maven is None:
            return MavenVerificationOutcome(
                result=MavenTestResult(executed=False, timed_out=False),
                failure_reason="maven_not_found",
            )
        java_home, java_version = find_suitable_jdk(
            min_version=self._min_java_version,
            env=self._environment,
        )
        del java_version
        if java_home is None:
            return MavenVerificationOutcome(
                result=MavenTestResult(executed=False, timed_out=False),
                failure_reason="java_not_compatible",
            )
        selector = _find_target_test_selector(workspace, expectation.test_name)
        if selector is None:
            return MavenVerificationOutcome(
                result=MavenTestResult(executed=False, timed_out=False),
                failure_reason="target_test_not_executed",
            )
        _clear_surefire_reports(workspace)
        process = _execute_maven(
            [maven, "-q", f"-Dtest={selector}", "test"],
            cwd=workspace,
            env=build_restricted_maven_environment(
                source_env=self._environment,
                java_home=java_home,
            ),
            timeout_seconds=self._timeout_seconds,
        )
        result = self._result_from_process(workspace, expectation, process)
        reports_exist = bool(find_surefire_xml(workspace)) if process.executed else False
        return MavenVerificationOutcome(
            result=result,
            failure_reason=self._patched_failure_reason(result, reports_exist=reports_exist),
        )

    def _result_from_process(
        self,
        workspace: Path,
        expectation: MavenExpectation,
        process: _ProcessResult,
    ) -> MavenTestResult:
        report_files = find_surefire_xml(workspace) if process.executed else []
        suites = parse_surefire_xml(report_files)
        found, tests, failures, errors, skipped, _failure_text = _target_summary(
            suites,
            expectation.test_name,
        )
        classification = classify_maven_failure(
            stdout=process.stdout,
            stderr=process.stderr,
            executed=process.executed,
            timed_out=process.timed_out,
            exit_code=process.returncode,
            surefire_report_found=bool(report_files),
            target_test_found=found,
            tests=tests,
            failures=failures,
            errors=errors,
            skipped=skipped,
            surefire_failure_text=_failure_text,
            workspace=workspace,
        )
        return MavenTestResult(
            executed=process.executed,
            timed_out=process.timed_out,
            exit_code=process.returncode,
            tests=tests,
            failures=failures,
            errors=errors,
            skipped=skipped,
            target_test_found=found,
            surefire_report_found=bool(report_files),
            surefire_started=classification.surefire_started,
            duration_ms=process.duration_ms,
            stdout_tail=tail_output(process.stdout),
            stderr_tail=tail_output(process.stderr),
            maven_failure_classification=classification,
        )

    @staticmethod
    def _baseline_failure_reason(
        result: MavenTestResult,
        expectation: MavenExpectation,
        failure_text: str,
        failure_present: bool,
    ) -> str | None:
        if result.timed_out:
            return "maven_timeout"
        if not result.executed:
            return "maven_not_found"
        classification = result.maven_failure_classification
        if classification is not None and classification.failure_category in {
            "main_compile_failure",
            "test_compile_failure",
            "timeout",
            "maven_execution_failure",
        }:
            return classification.failure_category
        if result.exit_code == 0:
            return "baseline_bug_not_reproduced"
        if not result.target_test_found:
            return "target_test_not_executed"
        if (
            result.tests != expectation.tests
            or result.failures != expectation.failures
            or result.errors != expectation.errors
            or result.skipped != expectation.skipped
        ):
            return "baseline_bug_not_reproduced"
        if expectation.failures > 0 and not failure_present:
            return "baseline_bug_not_reproduced"
        if any(term.casefold() not in failure_text.casefold() for term in expectation.required_failure_terms):
            return "baseline_bug_not_reproduced"
        return None

    @staticmethod
    def _patched_failure_reason(
        result: MavenTestResult,
        *,
        reports_exist: bool = True,
    ) -> str | None:
        classification = result.maven_failure_classification
        if classification is not None and classification.failure_category != "success":
            return classification.failure_category
        if result.timed_out:
            return "maven_timeout"
        if not result.executed:
            return "maven_not_found"
        if not result.target_test_found:
            return "surefire_report_missing" if not reports_exist else "target_test_not_executed"
        if result.tests == 0:
            return "tests_zero"
        if result.skipped > 0:
            return "test_skipped"
        if result.failures > 0:
            return "test_failure_remaining"
        if result.errors > 0:
            return "test_error_remaining"
        if result.exit_code != 0:
            return "maven_nonzero_exit"
        return None


__all__ = [
    "DEFAULT_MAVEN_TIMEOUT_SECONDS",
    "MAX_OUTPUT_TAIL_CHARS",
    "MAX_OUTPUT_TAIL_LINES",
    "MavenExpectation",
    "MIN_JAVA_VERSION",
    "MavenRepairVerifier",
    "MavenVerificationOutcome",
    "SurefireSuite",
    "SurefireTestCase",
    "build_restricted_maven_environment",
    "extract_major_version",
    "find_maven_binary",
    "find_suitable_jdk",
    "find_surefire_xml",
    "parse_java_major_version",
    "parse_surefire_xml",
    "read_maven_timeout_seconds",
    "sanitize_output",
    "tail_output",
]
