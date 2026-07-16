"""TaskRepository tests (cases 28-32)."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from springfix_agent.observability.in_memory_tracer import InMemoryTracer
from springfix_agent.service.task_service import TaskService, TaskValidationError
from springfix_agent.storage.in_memory import InMemoryTaskRepository
from springfix_agent.storage.models import Trace
from springfix_agent.tools._invoker import invoke_tool
from springfix_agent.tools.base import Tool, ToolContext
from springfix_agent.tools.read_file import ReadFileTool


def _no_scheduler(_task_id: str) -> None:
    """No-op scheduler: tests run tasks via run_task_sync."""
    return None


def test_task_crud(task_service: TaskService, sample_repo_path: str) -> None:
    """Case 28: Task CRUD works through the repository."""
    task = task_service.submit_task(
        repository_path=sample_repo_path,
        issue_description="calling createOrder throws but data not rolled back",
        error_log=None,
        scheduler=_no_scheduler,
    )
    fetched = task_service.get_task(task.task_id)
    assert fetched is not None
    assert fetched.task_id == task.task_id
    assert fetched.status == "pending"
    assert task_service.get_report(task.task_id) is None
    assert task_service.get_traces(task.task_id) == []


def test_task_id_not_found(task_service: TaskService) -> None:
    """Case 29: querying a non-existent task_id returns None / empty."""
    assert task_service.get_task("nonexistent-uuid") is None
    assert task_service.get_report("nonexistent-uuid") is None
    assert task_service.get_traces("nonexistent-uuid") == []


def test_trace_ordering(task_service: TaskService, sample_repo_path: str) -> None:
    """Case 30: traces are returned in execution (recorded_at) order."""
    task = task_service.submit_task(
        repository_path=sample_repo_path,
        issue_description="calling createOrder throws but data not rolled back",
        error_log=None,
        scheduler=_no_scheduler,
    )
    task_service.run_task_sync(task.task_id)
    traces = task_service.get_traces(task.task_id)
    timestamps = [t.recorded_at for t in traces]
    assert timestamps == sorted(timestamps)
    node_timings = [t for t in traces if t.kind == "node_timing"]
    assert len(node_timings) == 4
    assert [t.payload["node"] for t in node_timings] == [
        "validate_input",
        "explore_repository",
        "retrieve_code",
        "build_basic_report",
    ]


def test_tool_failure_still_leaves_trace(
    task_service: TaskService, sample_repo_path: str, allow_root: Path
) -> None:
    """Case 31: a failing tool call still produces a trace record."""
    repo = task_service._repo  # type: ignore[attr-defined]
    task = repo.create_task(
        repository_path=sample_repo_path,
        issue_description="test issue description",
        error_log=None,
    )
    tracer = InMemoryTracer(repo)
    ctx = ToolContext(
        task_id=task.task_id,
        repository_path=Path(sample_repo_path),
        allow_root=allow_root,
    )
    result = invoke_tool(
        ReadFileTool(),
        {"relative_path": "nonexistent.java"},
        ctx,
        "test_node",
        tracer,
    )
    assert result["status"] == "error"
    traces = repo.get_traces(task.task_id)
    tool_calls = [t for t in traces if t.kind == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0].payload["status"] == "error"


def test_concurrent_read_write(task_service: TaskService, sample_repo_path: str) -> None:
    """Case 32: concurrent creates and reads do not crash."""
    task_ids: list[str] = []

    def create_one() -> None:
        task = task_service.submit_task(
            repository_path=sample_repo_path,
            issue_description="concurrent test issue description",
            error_log=None,
            scheduler=_no_scheduler,
        )
        task_ids.append(task.task_id)

    threads = [threading.Thread(target=create_one) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(task_ids) == 5
    for tid in task_ids:
        assert task_service.get_task(tid) is not None


def test_repository_trace_save_round_trip(allow_root: Path) -> None:
    """Direct repository save/get_trace round trip with a Trace object."""
    repo = InMemoryTaskRepository()
    task = repo.create_task(
        repository_path=str(allow_root),
        issue_description="test issue description",
        error_log=None,
    )
    trace = Trace(
        task_id=task.task_id,
        kind="tool_call",
        payload={"tool_name": "list_project_tree", "status": "success"},
    )
    repo.save_trace(task.task_id, trace)
    fetched = repo.get_traces(task.task_id)
    assert len(fetched) == 1
    assert fetched[0].payload["tool_name"] == "list_project_tree"


def test_invalid_submit_raises(task_service: TaskService) -> None:
    """submit_task rejects invalid inputs with TaskValidationError."""
    with pytest.raises(TaskValidationError):
        task_service.submit_task(
            repository_path="/etc/passwd",
            issue_description="calling createOrder throws but data not rolled back",
            error_log=None,
            scheduler=_no_scheduler,
        )
    with pytest.raises(TaskValidationError):
        task_service.submit_task(
            repository_path=".",
            issue_description="short",
            error_log=None,
            scheduler=_no_scheduler,
        )
    # Unused import guard to satisfy Tool re-export linter expectations.
    _ = Tool
