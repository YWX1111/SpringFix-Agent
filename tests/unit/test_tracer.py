"""InMemoryTracer tests."""

from __future__ import annotations

from pathlib import Path

from springfix_agent.observability.in_memory_tracer import InMemoryTracer
from springfix_agent.observability.tracer import NodeTiming
from springfix_agent.storage.in_memory import InMemoryTaskRepository
from springfix_agent.tools.base import ToolCall


def test_tracer_never_raises_on_missing_task(allow_root: Path) -> None:
    """Tracer swallows errors when task_id doesn't exist in repository."""
    repo = InMemoryTaskRepository()
    tracer = InMemoryTracer(repo)

    call = ToolCall(
        node="test",
        tool_name="test_tool",
        params={},
        duration_ms=1,
        status="success",
        result_summary="ok",
        error=None,
    )
    # Should not raise
    tracer.record_tool_call("nonexistent-task-id", call)

    timing = NodeTiming(
        node="test",
        start="2026-07-15T00:00:00+00:00",
        end="2026-07-15T00:00:01+00:00",
        duration_ms=1000,
    )
    # Should not raise
    tracer.record_node_timing("nonexistent-task-id", timing)


def test_tracer_persists_to_repository(allow_root: Path) -> None:
    """Tracer writes ToolCall and NodeTiming as Trace records."""
    repo = InMemoryTaskRepository()
    tracer = InMemoryTracer(repo)
    task = repo.create_task(
        repository_path=str(allow_root),
        issue_description="test issue description",
        error_log=None,
    )

    call = ToolCall(
        node="explore_repository",
        tool_name="list_project_tree",
        params={"max_depth": 3},
        duration_ms=42,
        status="success",
        result_summary="tree_lines=20, file_count=10",
        error=None,
    )
    tracer.record_tool_call(task.task_id, call)

    timing = NodeTiming(
        node="validate_input",
        start="2026-07-15T10:00:00+00:00",
        end="2026-07-15T10:00:01+00:00",
        duration_ms=1000,
    )
    tracer.record_node_timing(task.task_id, timing)

    traces = repo.get_traces(task.task_id)
    assert len(traces) == 2
    kinds = [t.kind for t in traces]
    assert "tool_call" in kinds
    assert "node_timing" in kinds

    tool_trace = [t for t in traces if t.kind == "tool_call"][0]
    assert tool_trace.payload["tool_name"] == "list_project_tree"
    assert tool_trace.payload["duration_ms"] == 42
