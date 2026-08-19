"""M6B deterministic Maven failure classification fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from springfix_agent.repair.maven_classification import classify_maven_failure
from springfix_agent.repair.maven_verifier import MavenRepairVerifier
from springfix_agent.repair.verification_models import MavenTestResult

FIXTURES = Path(__file__).parents[2] / "fixtures" / "observability" / "maven"


@pytest.mark.parametrize(
    ("fixture", "category", "phase"),
    [
        ("dependency-resolution.txt", "dependency_resolution_failure", "dependency_resolution"),
        ("main-compile-cannot-find-symbol.txt", "main_compile_failure", "compile"),
        ("test-compile.txt", "test_compile_failure", "test_compile"),
        ("surefire-start-failure.txt", "surefire_start_failure", "surefire"),
        ("test-failure.txt", "test_failure", "test_runtime"),
        ("test-error.txt", "test_error", "test_runtime"),
        ("unknown.txt", "unknown", "unknown"),
        ("success.txt", "success", "test_runtime"),
    ],
)
def test_fixture_classification(fixture: str, category: str, phase: str) -> None:
    result = classify_maven_failure(
        stdout=(FIXTURES / fixture).read_text(encoding="utf-8"),
        stderr="",
        executed=True,
        timed_out=False,
        exit_code=0 if category == "success" else 1,
        surefire_report_found=category in {"test_failure", "test_error", "success"},
        target_test_found=category in {"test_failure", "test_error", "success"},
        tests=1,
        failures=1 if category == "test_failure" else 0,
        errors=1 if category == "test_error" else 0,
    )
    assert result.failure_category == category
    assert result.lifecycle_phase == phase


def test_main_compile_fixture_extracts_relative_file_and_symbol() -> None:
    result = classify_maven_failure(
        stdout=(FIXTURES / "main-compile-cannot-find-symbol.txt").read_text(encoding="utf-8"),
        stderr="",
        executed=True,
        timed_out=False,
        exit_code=1,
        surefire_report_found=False,
        target_test_found=False,
        workspace=None,
    )
    assert result.first_actionable_error == "cannot find symbol"
    # Without a repository root the classifier cannot prove that a path is a
    # real project file, so it intentionally withholds the field.
    assert result.affected_file is None
    assert result.affected_symbol == "Primary"
    assert "/workspace" not in result.model_dump_json()
    assert result.surefire_started is False


def test_timeout_is_explicit_and_surefire_state_is_unknown() -> None:
    result = classify_maven_failure(
        stdout=(FIXTURES / "timeout.txt").read_text(encoding="utf-8"),
        stderr="",
        executed=True,
        timed_out=True,
        exit_code=None,
        surefire_report_found=False,
        target_test_found=False,
    )
    assert result.failure_category == "timeout"
    assert result.surefire_started is None


def test_compile_failure_is_primary_over_missing_surefire(tmp_path: Path) -> None:
    source = tmp_path / "src" / "main" / "java" / "com" / "example" / "AuditClient.java"
    source.parent.mkdir(parents=True)
    source.write_text("class AuditClient {}\n", encoding="utf-8")
    output = (FIXTURES / "m7c-main-compile-missing-surefire.txt").read_text(
        encoding="utf-8"
    ).replace("<PROJECT_ROOT>", str(tmp_path))
    classification = classify_maven_failure(
        stdout=output,
        stderr="",
        executed=True,
        timed_out=False,
        exit_code=1,
        surefire_report_found=False,
        target_test_found=False,
        workspace=tmp_path,
    )
    result = MavenTestResult(
        executed=True,
        timed_out=False,
        exit_code=1,
        surefire_started=classification.surefire_started,
        maven_failure_classification=classification,
    )
    assert classification.failure_category == "main_compile_failure"
    assert classification.surefire_started is False
    assert classification.affected_file == "src/main/java/com/example/AuditClient.java"
    assert classification.affected_symbol == "AuditClient"
    assert classification.first_actionable_error == "duplicate class: AuditClient"
    assert "Method.java" not in classification.model_dump_json()
    assert MavenRepairVerifier._patched_failure_reason(result, reports_exist=False) == (
        "main_compile_failure"
    )


def test_framework_stack_frame_not_used_as_affected_file(tmp_path: Path) -> None:
    result = classify_maven_failure(
        stdout=(
            "[INFO] Running com.example.TargetTest\n"
            "at java.base/java.lang.reflect.Method.invoke(Method.java:568)\n"
            "at java.base/java.util.ArrayList.forEach(ArrayList.java:1511)\n"
            "at org.junit.jupiter.api.Assertions.assertEquals(Assertions.java:531)\n"
        ),
        stderr="",
        executed=True,
        timed_out=False,
        exit_code=1,
        surefire_report_found=True,
        target_test_found=True,
        tests=1,
        failures=1,
        workspace=tmp_path,
    )
    assert result.failure_category == "test_failure"
    assert result.affected_file is None


def test_compiler_path_is_repository_relative(tmp_path: Path) -> None:
    source = tmp_path / "src" / "main" / "java" / "com" / "example" / "AuditClient.java"
    source.parent.mkdir(parents=True)
    source.write_text("class AuditClient {}\n", encoding="utf-8")
    result = classify_maven_failure(
        stdout=f"[ERROR] {source}:[8,1] duplicate class: AuditClient\n",
        stderr="",
        executed=True,
        timed_out=False,
        exit_code=1,
        surefire_report_found=False,
        target_test_found=False,
        workspace=tmp_path,
    )
    assert result.affected_file == "src/main/java/com/example/AuditClient.java"
    assert not Path(result.affected_file).is_absolute()


def test_first_actionable_compile_error_extracted(tmp_path: Path) -> None:
    source = tmp_path / "src" / "main" / "java" / "com" / "example" / "AuditClient.java"
    source.parent.mkdir(parents=True)
    source.write_text("class AuditClient {}\n", encoding="utf-8")
    result = classify_maven_failure(
        stdout=(
            f"[ERROR] {source}:[4,1] duplicate class: AuditClient\n"
            "[ERROR] BUILD FAILURE\n"
            "[ERROR] Failed to execute goal ...\n"
            "[ERROR] -> [Help 1]\n"
        ),
        stderr="",
        executed=True,
        timed_out=False,
        exit_code=1,
        surefire_report_found=False,
        target_test_found=False,
        workspace=tmp_path,
    )
    assert result.first_actionable_error == "duplicate class: AuditClient"


def test_chinese_compiler_error_is_classified(tmp_path: Path) -> None:
    source = tmp_path / "src" / "main" / "java" / "com" / "example" / "AuditClient.java"
    source.parent.mkdir(parents=True)
    source.write_text("class AuditClient {}\n", encoding="utf-8")
    result = classify_maven_failure(
        stdout=f"[ERROR] {source}:[4,1] 找不到符号\n",
        stderr="",
        executed=True,
        timed_out=False,
        exit_code=1,
        surefire_report_found=False,
        target_test_found=False,
        workspace=tmp_path,
    )
    assert result.failure_category == "main_compile_failure"
    assert result.first_actionable_error == "找不到符号"


def test_test_failure_keeps_surefire_context() -> None:
    result = classify_maven_failure(
        stdout=(
            "[INFO] --- maven-surefire-plugin:test ---\n"
            "[INFO] Running com.example.TargetTest\n"
            "[ERROR] Tests run: 1, Failures: 1, Errors: 0, Skipped: 0\n"
        ),
        stderr="",
        executed=True,
        timed_out=False,
        exit_code=1,
        surefire_report_found=True,
        target_test_found=True,
        tests=1,
        failures=1,
        surefire_failure_text="expected: <1> but was: <0>",
    )
    assert result.failure_category == "test_failure"
    assert result.lifecycle_phase == "test_runtime"
    assert result.surefire_started is True
    assert result.first_actionable_error == "expected: <1> but was: <0>"


def test_success_classification_unchanged() -> None:
    result = classify_maven_failure(
        stdout="",
        stderr="",
        executed=True,
        timed_out=False,
        exit_code=0,
        surefire_report_found=True,
        target_test_found=True,
        tests=1,
    )
    assert result.failure_category == "success"
    assert result.lifecycle_phase == "test_runtime"


def test_timeout_primary_reason() -> None:
    classification = classify_maven_failure(
        stdout="",
        stderr="",
        executed=True,
        timed_out=True,
        exit_code=None,
        surefire_report_found=False,
        target_test_found=False,
    )
    result = MavenTestResult(
        executed=True,
        timed_out=True,
        maven_failure_classification=classification,
    )
    assert classification.failure_category == "timeout"
    assert MavenRepairVerifier._patched_failure_reason(result, reports_exist=False) == "timeout"


def test_process_failure_not_misclassified_as_surefire_missing() -> None:
    classification = classify_maven_failure(
        stdout="",
        stderr="",
        executed=False,
        timed_out=False,
        exit_code=None,
        surefire_report_found=False,
        target_test_found=False,
    )
    result = MavenTestResult(
        executed=False,
        timed_out=False,
        maven_failure_classification=classification,
    )
    assert classification.failure_category == "maven_execution_failure"
    assert classification.surefire_started is False
    assert MavenRepairVerifier._patched_failure_reason(result, reports_exist=False) == (
        "maven_execution_failure"
    )
