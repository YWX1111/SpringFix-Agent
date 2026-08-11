"""M4A manual SQLite restart verification and performance benchmark.

Usage: uv run python scripts/verify_m4a_sqlite.py

Creates a temporary SQLite database, simulates a task lifecycle, restarts
the repository, and measures basic operation timings.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

# Ensure src is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from springfix_agent.storage.migration import migrate
from springfix_agent.storage.models import Report, Trace
from springfix_agent.storage.sqlite_repository import SqliteTaskRepository


def _perf_ms(label: str, fn: object) -> float:  # type: ignore[type-arg]
    start = time.perf_counter_ns()
    fn()  # type: ignore[operator]
    elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
    print(f"  {label}: {elapsed_ms:.2f} ms")
    return elapsed_ms


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="springfix_m4a_") as tmpdir:
        db_path = Path(tmpdir) / "verify.db"
        print("=== M4A SQLite Verification ===")
        print("DB path (temp): verify.db")

        # Phase 1: Migration
        print("\n--- Phase 1: Migration ---")
        _perf_ms("migrate", lambda: migrate(db_path))

        # Phase 2: Create repo and task
        print("\n--- Phase 2: Create & populate ---")
        repo = SqliteTaskRepository(db_path)
        task = None

        def create() -> None:
            nonlocal task
            task = repo.create_task(
                repository_path="/fake/samples/repo",
                issue_description="calling createOrder throws but data not rolled back",
                error_log="java.lang.RuntimeException: simulated failure",
            )

        _perf_ms("create_task", create)
        assert task is not None
        task_id = task.task_id
        print(f"  task_id: {task_id}")

        # Save traces
        traces = [
            Trace(task_id=task_id, kind="node_timing",
                  payload={"node": "validate_input", "duration_ms": 10}),
            Trace(task_id=task_id, kind="node_timing",
                  payload={"node": "issue_parser", "duration_ms": 200}),
            Trace(task_id=task_id, kind="tool_call",
                  payload={"tool_name": "list_project_tree", "status": "success",
                           "node": "explore_repository", "duration_ms": 50}),
            Trace(task_id=task_id, kind="llm_call",
                  payload={"node": "root_cause_analyzer", "provider": "mock",
                           "model": "mock", "status": "success", "duration_ms": 1500}),
        ]
        for t in traces:
            _perf_ms(f"save_trace ({t.kind})", lambda t=t: repo.save_trace(task_id, t))

        # Save report
        report = Report(
            task_id=task_id,
            json_report={
                "diagnosis_status": "complete",
                "root_causes": [{"summary": "Spring AOP self-invocation"}],
            },
            markdown_report="# Diagnostic Report\n\nRoot cause: self-invocation bypasses proxy.",
            created_at=datetime.now(tz=UTC),
        )
        _perf_ms("save_report", lambda: repo.save_report(task_id, report))

        # Update to completed
        repo.update_status(task_id, "running", current_node="validate_input")
        _perf_ms("update_status → completed",
                 lambda: repo.update_status(task_id, "completed",
                                            current_node="build_diagnostic_report"))

        # Phase 3: Query before restart
        print("\n--- Phase 3: Query before restart ---")
        before_task = None
        before_traces: list[Trace] = []
        before_report = None

        _perf_ms("get_task", lambda: globals().update(before_task=repo.get_task(task_id)))
        _perf_ms("get_traces", lambda: globals().update(before_traces=repo.get_traces(task_id)))
        _perf_ms("get_report", lambda: globals().update(before_report=repo.get_report(task_id)))

        before_task = repo.get_task(task_id)
        before_traces = repo.get_traces(task_id)
        before_report = repo.get_report(task_id)

        print(f"  status: {before_task.status if before_task else 'N/A'}")
        print(f"  trace_count: {len(before_traces)}")
        print(f"  report_available: {before_report is not None}")

        # Phase 4: Restart (create new repo instance)
        print("\n--- Phase 4: Restart (new SqliteTaskRepository) ---")
        repo2 = SqliteTaskRepository(db_path)
        interrupted = repo2.mark_interrupted_tasks()
        print(f"  interrupted_tasks: {interrupted}")

        # Phase 5: Query after restart
        print("\n--- Phase 5: Query after restart ---")
        after_task = repo2.get_task(task_id)
        after_traces = repo2.get_traces(task_id)
        after_report = repo2.get_report(task_id)

        print(f"  status: {after_task.status if after_task else 'N/A'}")
        print(f"  trace_count: {len(after_traces)}")
        print(f"  report_available: {after_report is not None}")
        if after_report:
            print(f"  diagnosis_status: {after_report.json_report.get('diagnosis_status')}")

        # Phase 6: Test interrupted task scenario
        print("\n--- Phase 6: Pending task interruption test ---")
        pending_task = repo2.create_task(
            repository_path="/fake/samples/repo",
            issue_description="test pending task for interruption",
            error_log=None,
        )
        repo2.update_status(pending_task.task_id, "running", current_node="issue_parser")
        count = repo2.mark_interrupted_tasks()
        print(f"  interrupted: {count}")
        interrupted_task = repo2.get_task(pending_task.task_id)
        if interrupted_task:
            print(f"  status: {interrupted_task.status}")
            print(f"  error_message: {interrupted_task.error_message}")
            print(f"  current_node: {interrupted_task.current_node}")

        # Summary
        print("\n=== Summary ===")
        summary = {
            "task_id": task_id,
            "before_restart_status": before_task.status if before_task else None,
            "after_restart_status": after_task.status if after_task else None,
            "trace_count_before": len(before_traces),
            "trace_count_after": len(after_traces),
            "report_available_before": before_report is not None,
            "report_available_after": after_report is not None,
        }
        print(json.dumps(summary, indent=2))

        # Assertions
        assert before_task is not None and before_task.status == "completed"
        assert after_task is not None and after_task.status == "completed"
        assert len(before_traces) == len(after_traces) == 4
        assert before_report is not None
        assert after_report is not None
        assert interrupted == 0  # completed task should not be interrupted
        assert interrupted_task is not None and interrupted_task.status == "failed"
        assert interrupted_task.error_message == "interrupted_by_service_restart"

        print("\n=== All assertions passed ===")


if __name__ == "__main__":
    main()
