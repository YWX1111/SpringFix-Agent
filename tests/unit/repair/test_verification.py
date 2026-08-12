"""M5C command, environment, timeout, Surefire, and artifact safety tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from springfix_agent.repair import maven_verifier
from springfix_agent.repair.maven_verifier import MavenRepairVerifier
from springfix_agent.repair.verification_models import MavenTestResult


@dataclass(frozen=True)
class _Expectation:
    test_name: str = "testTarget"
    tests: int = 1
    failures: int = 1
    errors: int = 0
    skipped: int = 0
    required_failure_terms: list[str] | None = None

    def __post_init__(self) -> None:
        if self.required_failure_terms is None:
            object.__setattr__(self, "required_failure_terms", [])


def _test_source(root: Path, method: str = "testTarget") -> Path:
    source = root / "src" / "test" / "java" / "com" / "example" / "TargetTest.java"
    source.parent.mkdir(parents=True)
    source.write_text(
        "package com.example;\n"
        "class TargetTest {\n"
        f"    void {method}() {{}}\n"
        "}\n",
        encoding="utf-8",
    )
    return source


def _write_report(
    root: Path,
    *,
    test_name: str = "testTarget",
    tests: int = 1,
    failures: int = 0,
    errors: int = 0,
    skipped: int = 0,
    failure_text: str = "",
) -> None:
    reports = root / "target" / "surefire-reports"
    reports.mkdir(parents=True, exist_ok=True)
    failure = f'<failure message="{failure_text}">{failure_text}</failure>' if failures else ""
    skipped_node = "<skipped/>" if skipped else ""
    (reports / "TEST-com.example.TargetTest.xml").write_text(
        f'<testsuite name="com.example.TargetTest" tests="{tests}" '
        f'failures="{failures}" errors="{errors}" skipped="{skipped}">'
        f'<testcase name="{test_name}" classname="com.example.TargetTest">'
        f"{failure}{skipped_node}</testcase></testsuite>",
        encoding="utf-8",
    )


def test_restricted_environment_removes_credentials() -> None:
    env = {
        "PATH": "path",
        "JAVA_HOME": "java",
        "HOME": "home",
        "TEMP": "temp",
        "LLM_API_KEY": "one",
        "OPENAI_API_KEY": "two",
        "DASHSCOPE_API_KEY": "three",
        "AUTHORIZATION": "Bearer secret",
        "CUSTOM_TOKEN": "four",
        "CUSTOM_SECRET": "five",
    }
    restricted = maven_verifier.build_restricted_maven_environment(
        source_env=env,
        java_home="java-17",
    )
    assert restricted["JAVA_HOME"] == "java-17"
    assert restricted["MAVEN_OPTS"] == "-Dfile.encoding=UTF-8"
    assert not any("KEY" in key or "TOKEN" in key or "SECRET" in key for key in restricted)
    assert "AUTHORIZATION" not in restricted


def test_process_uses_shell_false(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: dict[str, object] = {}

    class FakeProcess:
        returncode = 0

        def communicate(self, timeout: int | None = None) -> tuple[str, str]:
            calls["timeout"] = timeout
            return "out", "err"

        def poll(self) -> int:
            return 0

        def kill(self) -> None:
            calls["killed"] = True

        def wait(self) -> int:
            return 0

    def fake_popen(*args: object, **kwargs: object) -> FakeProcess:
        calls["args"] = args
        calls.update(kwargs)
        return FakeProcess()

    monkeypatch.setattr(maven_verifier.subprocess, "Popen", fake_popen)
    result = maven_verifier._execute_maven(
        ["mvn", "-q", "-Dtest=TargetTest#testTarget", "test"],
        cwd=tmp_path,
        env={"PATH": "path"},
        timeout_seconds=5,
    )
    assert calls["shell"] is False
    assert calls["args"] == (["mvn", "-q", "-Dtest=TargetTest#testTarget", "test"],)
    assert result.executed is True
    assert result.timed_out is False


def test_timeout_is_classified_and_process_is_killed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class FakeProcess:
        returncode = -9

        def __init__(self) -> None:
            self.calls = 0
            self.killed = False

        def communicate(self, timeout: int | None = None) -> tuple[str, str]:
            del timeout
            self.calls += 1
            if self.calls == 1:
                raise maven_verifier.subprocess.TimeoutExpired(["mvn"], 1)
            return "", ""

        def poll(self) -> int | None:
            return None if not self.killed else 0

        def kill(self) -> None:
            self.killed = True

        def wait(self) -> int:
            return 0

    process = FakeProcess()
    monkeypatch.setattr(maven_verifier.subprocess, "Popen", lambda *args, **kwargs: process)
    result = maven_verifier._execute_maven(
        ["mvn", "test"], cwd=tmp_path, env={}, timeout_seconds=1
    )
    assert result.timed_out is True
    assert process.killed is True


def test_patched_verification_uses_exact_target_and_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _test_source(tmp_path)
    captured: dict[str, object] = {}

    def fake_execute(args: list[str], *, cwd: Path, env: dict[str, str], timeout_seconds: int) -> object:
        captured.update({"args": args, "cwd": cwd, "env": env, "timeout": timeout_seconds})
        _write_report(cwd, tests=1, failures=0)
        return maven_verifier._ProcessResult(True, False, 0, "", "", 17)

    monkeypatch.setattr(maven_verifier, "find_maven_binary", lambda _env: "mvn")
    monkeypatch.setattr(maven_verifier, "find_suitable_jdk", lambda **kwargs: ("java-17", 17))
    monkeypatch.setattr(maven_verifier, "_execute_maven", fake_execute)
    outcome = MavenRepairVerifier(
        environment={"PATH": "path", "OPENAI_API_KEY": "secret"},
        timeout_seconds=9,
    ).verify_patched_workspace(tmp_path, _Expectation(failures=0))
    assert outcome.failure_reason is None
    assert outcome.result.target_test_found is True
    assert captured["cwd"] == tmp_path
    assert captured["args"] == ["mvn", "-q", "-Dtest=com.example.TargetTest#testTarget", "test"]
    assert "OPENAI_API_KEY" not in captured["env"]
    assert captured["timeout"] == 9


def test_baseline_requires_expected_failure_and_terms(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _test_source(tmp_path)

    def fake_execute(args: list[str], *, cwd: Path, env: dict[str, str], timeout_seconds: int) -> object:
        del args, env, timeout_seconds
        _write_report(
            cwd,
            tests=1,
            failures=1,
            failure_text="expected rollback self-invocation",
        )
        return maven_verifier._ProcessResult(True, False, 1, "", "", 10)

    monkeypatch.setattr(maven_verifier, "find_maven_binary", lambda _env: "mvn")
    monkeypatch.setattr(maven_verifier, "find_suitable_jdk", lambda **kwargs: ("java-17", 17))
    monkeypatch.setattr(maven_verifier, "_execute_maven", fake_execute)
    result = MavenRepairVerifier(environment={"PATH": "path"}).verify_baseline(
        tmp_path,
        _Expectation(required_failure_terms=["rollback", "self-invocation"]),
    )
    assert result.verified is True


def test_multiple_xml_selection_ignores_wrong_test() -> None:
    suites = [
        maven_verifier.SurefireSuite(
            "wrong",
            7,
            0,
            0,
            0,
            (maven_verifier.SurefireTestCase("other", "Wrong", None, None, None, False),),
        ),
        maven_verifier.SurefireSuite(
            "target",
            1,
            0,
            0,
            0,
            (maven_verifier.SurefireTestCase("testTarget", "Target", None, None, None, False),),
        ),
    ]
    found, tests, failures, errors, skipped, _ = maven_verifier._target_summary(
        suites, "testTarget"
    )
    assert (found, tests, failures, errors, skipped) == (True, 1, 0, 0, 0)


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (MavenTestResult(executed=True, timed_out=True), "maven_timeout"),
        (
            MavenTestResult(executed=True, timed_out=False, exit_code=0, target_test_found=True),
            "tests_zero",
        ),
        (
            MavenTestResult(executed=True, timed_out=False, exit_code=1, target_test_found=True, tests=1, failures=1),
            "test_failure_remaining",
        ),
        (
            MavenTestResult(executed=True, timed_out=False, exit_code=1, target_test_found=True, tests=1, errors=1),
            "test_error_remaining",
        ),
        (
            MavenTestResult(executed=True, timed_out=False, exit_code=0, target_test_found=True, tests=1, skipped=1),
            "test_skipped",
        ),
    ],
)
def test_patched_failure_reasons_are_deterministic(
    result: MavenTestResult,
    expected: str,
) -> None:
    assert MavenRepairVerifier._patched_failure_reason(result) == expected


def test_sanitized_tail_removes_secrets_and_absolute_paths() -> None:
    tail = maven_verifier.tail_output(
        "Authorization: Bearer abcdefghijklmnop\n"
        "OPENAI_API_KEY=super-secret\n"
        "at C:\\Users\\Administrator\\temp\\TEST.xml\n"
    )
    assert "super-secret" not in tail
    assert "abcdefghijklmnop" not in tail
    assert "C:\\Users" not in tail
    assert "<redacted>" in tail
    assert "<path>" in tail
