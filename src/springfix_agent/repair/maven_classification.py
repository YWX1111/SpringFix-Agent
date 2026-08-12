"""Deterministic classification of bounded Maven output."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from springfix_agent.repair.verification_models import MavenFailureClassification

_SOURCE_ERROR_RE = re.compile(
    r"(?m)(?:\[ERROR\]\s*)?(?P<path>(?:[A-Za-z]:[\\/]|/)[^\r\n\]]+?\.java|src[\\/][^\r\n\]]+?\.java):\[?\d+(?:,\d+)?\]?"
)
_SYMBOL_RE = re.compile(
    r"(?im)\bsymbol:\s*(?:class|interface|variable|method|constructor)\s+([A-Za-z_$][\w$]*)"
)


def _normalise_relative_path(value: str, workspace: Path | None) -> str | None:
    candidate = value.strip().replace("\\", "/")
    if candidate.startswith("<path>") or "<path>" in candidate:
        return None
    if workspace is not None:
        try:
            resolved = Path(candidate).resolve()
            relative = resolved.relative_to(workspace.resolve())
            return relative.as_posix()
        except (OSError, ValueError):
            pass
    marker = candidate.find("src/")
    if marker >= 0:
        return candidate[marker:]
    return candidate if not Path(candidate).is_absolute() else None


def _affected_file(output: str, workspace: Path | None) -> str | None:
    match = _SOURCE_ERROR_RE.search(output)
    if match is None:
        return None
    return _normalise_relative_path(match.group("path"), workspace)


def _first_error(output: str) -> str | None:
    patterns = (
        (r"cannot find symbol", "cannot find symbol"),
        (r"package\s+[^\r\n]+\s+does not exist", "package does not exist"),
        (r"incompatible types", "incompatible types"),
        (r"method\s+[^\r\n]+\s+cannot be applied", "method cannot be applied"),
        (r"constructor\s+[^\r\n]+\s+cannot be applied", "constructor cannot be applied"),
        (r"could not resolve dependencies", "Could not resolve dependencies"),
        (r"application failed to start", "APPLICATION FAILED TO START"),
        (r"nosuchbeandefinitionexception", "NoSuchBeanDefinitionException"),
        (r"nouniquebeandefinitionexception", "NoUniqueBeanDefinitionException"),
    )
    for pattern, result in patterns:
        if re.search(pattern, output, re.IGNORECASE):
            return result
    return None


def classify_maven_failure(
    *,
    stdout: str,
    stderr: str,
    executed: bool,
    timed_out: bool,
    exit_code: int | None,
    surefire_report_found: bool,
    target_test_found: bool,
    tests: int = 0,
    failures: int = 0,
    errors: int = 0,
    workspace: Path | None = None,
) -> MavenFailureClassification:
    """Classify Maven without an LLM or a complete-output artifact."""
    output = f"{stdout}\n{stderr}"
    lower = output.casefold()
    compiler_test = "maven-compiler-plugin" in lower and "testcompile" in lower
    compiler_main = "maven-compiler-plugin" in lower and ":compile" in lower and not compiler_test
    dependency = any(
        phrase in lower
        for phrase in (
            "could not resolve dependencies",
            "could not transfer artifact",
            "failed to read artifact descriptor",
            "non-resolvable parent pom",
        )
    )
    compile_error = any(
        phrase in lower
        for phrase in (
            "compilation error",
            "compilation failure",
            "cannot find symbol",
            "does not exist",
            "incompatible types",
        )
    )
    surefire_marker = "maven-surefire-plugin" in lower or "[info] running " in lower
    runtime_marker = any(
        phrase in lower
        for phrase in (
            "application failed to start",
            "nosuchbeandefinitionexception",
            "nouniquebeandefinitionexception",
        )
    )

    lifecycle: Literal[
        "dependency_resolution",
        "validate",
        "compile",
        "test_compile",
        "surefire",
        "test_runtime",
        "plugin",
        "unknown",
    ]
    category: Literal[
        "dependency_resolution_failure",
        "main_compile_failure",
        "test_compile_failure",
        "surefire_start_failure",
        "test_failure",
        "test_error",
        "plugin_failure",
        "timeout",
        "success",
        "unknown",
    ]
    if timed_out:
        lifecycle = "unknown"
        category = "timeout"
        first_error = "Maven verification timed out"
    elif not executed:
        lifecycle = "unknown"
        category = "unknown"
        first_error = None
    elif dependency:
        lifecycle = "dependency_resolution"
        category = "dependency_resolution_failure"
        first_error = _first_error(output)
    elif compiler_test or ("testcompile" in lower and compile_error):
        lifecycle = "test_compile"
        category = "test_compile_failure"
        first_error = _first_error(output)
    elif compiler_main or (compile_error and not surefire_marker and not runtime_marker):
        lifecycle = "compile"
        category = "main_compile_failure"
        first_error = _first_error(output)
    elif target_test_found and failures > 0:
        lifecycle = "test_runtime"
        category = "test_failure"
        first_error = _first_error(output)
    elif (target_test_found and errors > 0) or runtime_marker:
        lifecycle = "test_runtime"
        category = "test_error"
        first_error = _first_error(output)
    elif surefire_marker and not surefire_report_found:
        lifecycle = "surefire"
        category = "surefire_start_failure"
        first_error = _first_error(output)
    elif "failed to execute goal" in lower:
        lifecycle = "plugin"
        category = "plugin_failure"
        first_error = _first_error(output)
    elif exit_code == 0 and surefire_report_found and target_test_found:
        lifecycle = "test_runtime"
        category = "success"
        first_error = None
    else:
        lifecycle = "unknown"
        category = "unknown"
        first_error = _first_error(output)

    surefire_started: bool | None
    if surefire_report_found or surefire_marker:
        surefire_started = True
    elif category in {"dependency_resolution_failure", "main_compile_failure", "test_compile_failure"}:
        surefire_started = False
    else:
        surefire_started = None

    symbol_match = _SYMBOL_RE.search(output)
    return MavenFailureClassification(
        lifecycle_phase=lifecycle,
        failure_category=category,
        first_actionable_error=first_error,
        affected_file=_affected_file(output, workspace),
        affected_symbol=symbol_match.group(1) if symbol_match is not None else None,
        surefire_started=surefire_started,
    )


__all__ = ["classify_maven_failure"]
