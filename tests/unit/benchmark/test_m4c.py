"""M4C sanitizer, deterministic metrics and runner regression tests."""

from __future__ import annotations

import json
from pathlib import Path

from springfix_agent.benchmark.loader import load_cases
from springfix_agent.benchmark.repository_view import create_repository_view
from springfix_agent.benchmark.runner import BenchmarkRunner

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_repository_view_excludes_answer_bearing_content(tmp_path: Path) -> None:
    source = tmp_path / "sample"
    (source / "src" / "main").mkdir(parents=True)
    (source / "src" / "test").mkdir(parents=True)
    (source / "target").mkdir()
    (source / ".git").mkdir()
    (source / "benchmark").mkdir()
    (source / "artifacts").mkdir()
    (source / "Main.java").write_text("class Main {}", encoding="utf-8")
    (source / "README.md").write_text("gold answer", encoding="utf-8")
    (source / "src" / "main" / "App.java").write_text("class App {}", encoding="utf-8")
    (source / "src" / "test" / "AppTest.java").write_text("class AppTest {}", encoding="utf-8")
    (source / "target" / "App.class").write_bytes(b"class")

    with create_repository_view(source) as view:
        assert view.path is not None
        names = {path.relative_to(view.path).as_posix() for path in view.path.rglob("*")}
        assert "README.md" not in names
        assert "src/test/AppTest.java" not in names
        assert "src/main/App.java" in names
        assert all(not name.startswith("target/") for name in names)
        assert all(not name.startswith(".git/") for name in names)
    assert view.path is None


def test_repository_view_include_tests_is_explicit(tmp_path: Path) -> None:
    source = tmp_path / "sample"
    test_file = source / "src" / "test" / "AppTest.java"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("class AppTest {}", encoding="utf-8")
    with create_repository_view(source, include_tests=True) as view:
        assert view.path is not None
        assert (view.path / "src" / "test" / "AppTest.java").exists()


def test_mock_benchmark_runs_three_cases_and_writes_redacted_artifacts(tmp_path: Path) -> None:
    result = BenchmarkRunner(
        project_root=PROJECT_ROOT,
        manifest_path=PROJECT_ROOT / "benchmark" / "agent_cases.jsonl",
        output_dir=tmp_path / "artifacts",
        mode="mock",
    ).run()
    assert result.aggregate.sample_size == 3
    assert result.aggregate.cases_passed == 3
    assert result.aggregate.total_logical_llm_calls == 9
    assert result.aggregate.total_http_attempts == 9
    assert result.aggregate.total_input_tokens is None
    assert (tmp_path / "artifacts" / "mock" / "report.md").exists()
    case_json = (tmp_path / "artifacts" / "mock" / "cases" / "transaction-self-invocation.json").read_text(
        encoding="utf-8"
    )
    assert "repository_path" not in case_json
    assert "expected_files" not in case_json
    assert "raw response" not in case_json.lower()


def test_manifest_agent_projection_has_only_three_fields() -> None:
    case = load_cases(PROJECT_ROOT / "benchmark" / "agent_cases.jsonl")[0]
    assert set(case.agent_input()) == {"repository", "issue_description", "error_log"}
    assert "expected_root_cause_keywords" not in json.dumps(case.agent_input())
