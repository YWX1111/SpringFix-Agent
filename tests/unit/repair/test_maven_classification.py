"""M6B deterministic Maven failure classification fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from springfix_agent.repair.maven_classification import classify_maven_failure

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
    assert result.affected_file == "src/main/java/com/example/StripePaymentGateway.java"
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
