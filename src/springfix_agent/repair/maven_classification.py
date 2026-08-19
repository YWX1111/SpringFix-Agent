"""Deterministic classification of bounded Maven output."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from springfix_agent.repair.verification_models import MavenFailureClassification

_SOURCE_ERROR_RE = re.compile(
    r"(?m)^\s*(?:\[ERROR\]\s*)?"
    r"(?P<path>(?:[A-Za-z]:[\\/]|/|src[\\/])[^\r\n\]]+?\.java)"
    r":\[?\d+(?:,\d+)?\]?"
)
_SYMBOL_RE = re.compile(
    r"(?im)\bsymbol:\s*(?:class|interface|variable|method|constructor)\s+([A-Za-z_$][\w$]*)"
)
_DUPLICATE_CLASS_RE = re.compile(
    r"(?im)\bduplicate\s+class:\s*([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)"
)
_CHINESE_DUPLICATE_CLASS_RE = re.compile(
    r"(?m)重复的类[：:]\s*([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)"
)
_STACK_FRAME_RE = re.compile(
    r"(?:(?:at)\s+)?"
    r"(?:(?:[A-Za-z_$][\w$]*)/)?"
    r"(?P<class>[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+)"
    r"\.(?P<method>[A-Za-z_$][\w$<>]*)"
    r"\((?P<file>[A-Za-z_$][\w$.-]*\.java):\d+\)"
)
_FRAMEWORK_PREFIXES = (
    "java.",
    "javax.",
    "jdk.",
    "sun.",
    "com.sun.",
    "org.junit.",
    "org.apache.maven.",
    "org.springframework.",
    "org.gradle.",
    "org.mockito.",
)


def _repository_relative_path(value: str, workspace: Path | None) -> str | None:
    """Return an existing repository-relative file, never an absolute path."""
    if workspace is None:
        return None
    candidate = value.strip().strip("()[]{}")
    if not candidate or "<path>" in candidate:
        return None
    candidate = candidate.replace("\\", "/")
    root = workspace.resolve()
    path = Path(candidate)
    if not path.is_absolute():
        path = root / path
    try:
        resolved = path.resolve()
        relative = resolved.relative_to(root)
    except (OSError, ValueError):
        return None
    if not resolved.is_file() or not relative.parts:
        return None
    return relative.as_posix()


def _normalise_relative_path(value: str, workspace: Path | None) -> str | None:
    return _repository_relative_path(value, workspace)


def _source_error_paths(output: str) -> list[str]:
    return [match.group("path") for match in _SOURCE_ERROR_RE.finditer(output)]


def _is_framework_class(class_name: str) -> bool:
    return class_name.casefold().startswith(_FRAMEWORK_PREFIXES)


def _stack_source_path(class_name: str, workspace: Path) -> str | None:
    source_class = class_name.split("$", 1)[0]
    relative_class = Path(*source_class.split("."))
    for source_root in (workspace / "src" / "test" / "java", workspace / "src" / "main" / "java"):
        candidate = source_root / relative_class.with_suffix(".java")
        if candidate.is_file():
            return candidate.as_posix()
    return None


def _stack_file_candidates(output: str, workspace: Path | None) -> list[str]:
    if workspace is None:
        return []
    test_files: list[str] = []
    application_files: list[str] = []
    for match in _STACK_FRAME_RE.finditer(output):
        class_name = match.group("class")
        if _is_framework_class(class_name):
            continue
        source_path = _stack_source_path(class_name, workspace)
        if source_path is None:
            continue
        relative = _repository_relative_path(source_path, workspace)
        if relative is None:
            continue
        if relative.startswith("src/test/"):
            test_files.append(relative)
        else:
            application_files.append(relative)
    return test_files + application_files


def _affected_file(output: str, workspace: Path | None) -> str | None:
    # Compiler paths are authoritative.  A stack frame is only considered
    # after a repository-backed path check and framework filtering.
    for path in _source_error_paths(output):
        relative = _normalise_relative_path(path, workspace)
        if relative is not None:
            return relative
    stack_files = _stack_file_candidates(output, workspace)
    return stack_files[0] if stack_files else None


def _bounded_line(value: str) -> str:
    line = re.sub(r"^\s*(?:\[ERROR\]|\[WARNING\])\s*", "", value.strip())
    line = re.sub(r"\s+", " ", line)
    return line[:200]


def _first_error(output: str) -> str | None:
    events: list[tuple[int, str]] = []
    patterns = (
        (r"cannot find symbol", "cannot find symbol"),
        (r"package\s+[^\r\n]+\s+does not exist", "package does not exist"),
        (r"incompatible types", "incompatible types"),
        (r"method\s+[^\r\n]+\s+cannot be applied", "method cannot be applied"),
        (r"constructor\s+[^\r\n]+\s+cannot be applied", "constructor cannot be applied"),
        (r"method does not override or implement a method from a supertype", "method does not override or implement a method from a supertype"),
        (r"duplicate\s+class:\s*([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)", None),
        (r"重复的类[：:]\s*([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)", None),
        (r"could not resolve dependencies", "Could not resolve dependencies"),
        (r"application failed to start", "APPLICATION FAILED TO START"),
        (r"nosuchbeandefinitionexception", "NoSuchBeanDefinitionException"),
        (r"nouniquebeandefinitionexception", "NoUniqueBeanDefinitionException"),
        (r"expected:\s*<[^\r\n]+?\s+but was:\s*<[^\r\n>]+>", None),
        (r"找不到符号|程序包[^\r\n]+不存在|不兼容的类型|方法[^\r\n]+无法应用", None),
    )
    for pattern, result in patterns:
        for match in re.finditer(pattern, output, re.IGNORECASE):
            rendered = _bounded_line(match.group(0)) if result is None else result
            events.append((match.start(), rendered))
    return min(events, key=lambda event: event[0])[1] if events else None


def _affected_symbol(output: str) -> str | None:
    events: list[tuple[int, str]] = []
    for match in _SYMBOL_RE.finditer(output):
        events.append((match.start(), match.group(1)))
    for pattern in (_DUPLICATE_CLASS_RE, _CHINESE_DUPLICATE_CLASS_RE):
        for match in pattern.finditer(output):
            events.append((match.start(), match.group(1).rsplit(".", 1)[-1]))
    return min(events, key=lambda event: event[0])[1] if events else None


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
    skipped: int = 0,
    surefire_failure_text: str = "",
    workspace: Path | None = None,
) -> MavenFailureClassification:
    """Classify Maven without an LLM or a complete-output artifact."""
    output = f"{stdout}\n{stderr}"
    diagnostic_output = f"{output}\n{surefire_failure_text}"
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
    source_error_paths = _source_error_paths(output)
    compile_error = any(
        phrase in lower
        for phrase in (
            "compilation error",
            "compilation failure",
            "cannot find symbol",
            "does not exist",
            "incompatible types",
            "找不到符号",
            "不存在",
            "不兼容的类型",
            "无法应用",
        )
    )
    surefire_marker = "maven-surefire-plugin" in lower or "[info] running " in lower
    surefire_execution_marker = bool(
        re.search(r"(?im)^\s*\[info\]\s+running\s+|^\s*\[info\]\s+tests\s+run:", output)
    )
    test_source_error = any("src/test/" in path.replace("\\", "/") for path in source_error_paths)
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
        "maven_execution_failure",
        "timeout",
        "success",
        "unknown",
    ]
    first_error: str | None
    if timed_out:
        lifecycle = "unknown"
        category = "timeout"
        first_error = "Maven verification timed out"
    elif not executed:
        lifecycle = "unknown"
        category = "maven_execution_failure"
        first_error = "Maven process could not be started"
    elif dependency:
        lifecycle = "dependency_resolution"
        category = "dependency_resolution_failure"
        first_error = _first_error(output)
    elif compiler_test or test_source_error or ("testcompile" in lower and compile_error):
        lifecycle = "test_compile"
        category = "test_compile_failure"
        first_error = _first_error(diagnostic_output)
    elif compiler_main or source_error_paths or (compile_error and not target_test_found):
        lifecycle = "compile"
        category = "main_compile_failure"
        first_error = _first_error(diagnostic_output)
    elif target_test_found and failures > 0:
        lifecycle = "test_runtime"
        category = "test_failure"
        first_error = _first_error(diagnostic_output)
    elif (target_test_found and errors > 0) or runtime_marker:
        lifecycle = "test_runtime"
        category = "test_error"
        first_error = _first_error(diagnostic_output)
    elif surefire_marker and not surefire_report_found:
        lifecycle = "surefire"
        category = "surefire_start_failure"
        first_error = _first_error(diagnostic_output)
    elif "failed to execute goal" in lower:
        lifecycle = "plugin"
        category = "plugin_failure"
        first_error = _first_error(diagnostic_output)
    elif (
        exit_code == 0
        and surefire_report_found
        and target_test_found
        and tests > 0
        and failures == 0
        and errors == 0
        and skipped == 0
    ):
        lifecycle = "test_runtime"
        category = "success"
        first_error = None
    else:
        lifecycle = "unknown"
        category = "unknown"
        first_error = _first_error(diagnostic_output)

    surefire_started: bool | None
    if surefire_report_found or surefire_execution_marker:
        surefire_started = True
    elif category in {
        "dependency_resolution_failure",
        "main_compile_failure",
        "test_compile_failure",
        "maven_execution_failure",
    }:
        surefire_started = False
    else:
        surefire_started = None

    return MavenFailureClassification(
        lifecycle_phase=lifecycle,
        failure_category=category,
        first_actionable_error=first_error,
        affected_file=_affected_file(diagnostic_output, workspace),
        affected_symbol=_affected_symbol(diagnostic_output),
        surefire_started=surefire_started,
    )


__all__ = ["classify_maven_failure"]
