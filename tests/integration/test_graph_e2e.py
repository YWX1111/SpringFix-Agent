"""End-to-end Graph tests for M2 (7-node graph)."""

from __future__ import annotations

from pathlib import Path

from springfix_agent.service.task_service import TaskService

_NO_SCHEDULER = lambda tid: None  # noqa: E731


def test_seven_nodes_in_order(task_service: TaskService, sample_repo_path: str) -> None:
    """All seven M2 nodes execute in declaration order."""
    task = task_service.submit_task(
        repository_path=sample_repo_path,
        issue_description="calling createOrder throws but data not rolled back",
        error_log=None,
        scheduler=_NO_SCHEDULER,
    )
    task_service.run_task_sync(task.task_id)
    traces = task_service.get_traces(task.task_id)
    node_timings = [t for t in traces if t.kind == "node_timing"]
    assert [t.payload["node"] for t in node_timings] == [
        "validate_input",
        "issue_parser",
        "task_planner",
        "explore_repository",
        "retrieve_code",
        "root_cause_analyzer",
        "build_diagnostic_report",
    ]


def test_invalid_input_does_not_access_repository(
    task_service: TaskService, allow_root: Path
) -> None:
    """Invalid input sets failed status; no tool calls touch the repo."""
    repo = task_service._repo  # type: ignore[attr-defined]
    task = repo.create_task(
        repository_path="/etc/passwd",
        issue_description="calling createOrder throws but data not rolled back",
        error_log=None,
    )
    task_service.run_task_sync(task.task_id)
    fetched = task_service.get_task(task.task_id)
    assert fetched is not None
    assert fetched.status == "failed"
    tool_calls = [t for t in repo.get_traces(task.task_id) if t.kind == "tool_call"]
    assert tool_calls == []
    report = task_service.get_report(task.task_id)
    assert report is not None


def test_diagnostic_report_generated(task_service: TaskService, sample_repo_path: str) -> None:
    """A diagnostic report is generated after graph completes."""
    task = task_service.submit_task(
        repository_path=sample_repo_path,
        issue_description="calling createOrder throws but data not rolled back",
        error_log=None,
        scheduler=_NO_SCHEDULER,
    )
    task_service.run_task_sync(task.task_id)
    report = task_service.get_report(task.task_id)
    assert report is not None
    assert report.json_report["task_id"] == task.task_id
    assert len(report.markdown_report) > 0
    # M2 report always carries diagnosis_status
    assert "diagnosis_status" in report.json_report


def test_report_does_not_overclaim(
    task_service: TaskService, sample_repo_path: str
) -> None:
    """Report explicitly disclaims when status is not complete."""
    task = task_service.submit_task(
        repository_path=sample_repo_path,
        issue_description="calling createOrder throws but data not rolled back",
        error_log=None,
        scheduler=_NO_SCHEDULER,
    )
    task_service.run_task_sync(task.task_id)
    report = task_service.get_report(task.task_id)
    assert report is not None
    md = report.markdown_report
    # M2 report must always carry a diagnosis_status disambiguator
    assert "diagnosis_status" in md
    assert "已确定根因" not in md


def test_run_task_sync_completes(task_service: TaskService, sample_repo_path: str) -> None:
    """run_task_sync transitions a successful task to completed."""
    task = task_service.submit_task(
        repository_path=sample_repo_path,
        issue_description="calling createOrder throws but data not rolled back",
        error_log=None,
        scheduler=_NO_SCHEDULER,
    )
    task_service.run_task_sync(task.task_id)
    fetched = task_service.get_task(task.task_id)
    assert fetched is not None
    assert fetched.status == "completed"
    assert fetched.finished_at is not None


def test_run_task_sync_fails_on_invalid_path(
    task_service: TaskService, sample_repo_path: str
) -> None:
    """run_task_sync transitions a failed task to failed."""
    repo = task_service._repo  # type: ignore[attr-defined]
    bogus = str(Path(sample_repo_path) / "does" / "not" / "exist")
    task = repo.create_task(
        repository_path=bogus,
        issue_description="calling createOrder throws but data not rolled back",
        error_log=None,
    )
    task_service.run_task_sync(task.task_id)
    fetched = task_service.get_task(task.task_id)
    assert fetched is not None
    assert fetched.status == "failed"
    assert fetched.finished_at is not None


def test_graph_with_error_log_extracts_stack_symbols(
    task_service: TaskService, sample_repo_path: str
) -> None:
    """Symbols from a Java stack frame flow into explore_repository."""
    error_log = (
        "java.lang.RuntimeException: simulated failure\n"
        "\tat com.example.OrderService.createOrderInTransaction(OrderService.java:14)\n"
        "\tat com.example.OrderService.createOrder(OrderService.java:9)\n"
    )
    task = task_service.submit_task(
        repository_path=sample_repo_path,
        issue_description="calling createOrder throws but data not rolled back",
        error_log=error_log,
        scheduler=_NO_SCHEDULER,
    )
    task_service.run_task_sync(task.task_id)
    traces = task_service.get_traces(task.task_id)
    tool_calls = [t for t in traces if t.kind == "tool_call"]
    tool_names = [tc.payload.get("tool_name") for tc in tool_calls]
    assert "find_java_symbol" in tool_names
    fetched = task_service.get_task(task.task_id)
    assert fetched is not None
    assert fetched.status == "completed"
