"""TaskRepository Protocol.

Defines the long-stable persistence interface. Implementations:

- M1: ``InMemoryTaskRepository`` (dict-backed, process-local)
- M4: ``SqliteTaskRepository`` (SQLite-backed)

The Protocol is fully typed so that swapping implementations requires no
changes at call sites.
"""

from __future__ import annotations

from typing import Protocol

from springfix_agent.storage.models import Report, Task, TaskStatus, Trace


class TaskRepository(Protocol):
    """Persistence boundary for diagnostic tasks, traces, and reports."""

    def create_task(
        self,
        repository_path: str,
        issue_description: str,
        error_log: str | None,
    ) -> Task:
        """Create a new task in ``pending`` status and return it."""
        ...

    def get_task(self, task_id: str) -> Task | None:
        """Return the task with the given id, or None if not found."""
        ...

    def list_tasks(self) -> list[Task]:
        """Return all tasks, ordered by submitted_at descending."""
        ...

    def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        current_node: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update a task's status and optionally its current_node / error_message."""
        ...

    def save_trace(self, task_id: str, trace: Trace) -> None:
        """Append a trace record (tool_call or node_timing) to the task."""
        ...

    def get_traces(self, task_id: str) -> list[Trace]:
        """Return all traces for the task, ordered by recorded_at ascending."""
        ...

    def save_report(self, task_id: str, report: Report) -> None:
        """Persist the diagnostic report for the task."""
        ...

    def get_report(self, task_id: str) -> Report | None:
        """Return the report for the task, or None if not yet generated."""
        ...
