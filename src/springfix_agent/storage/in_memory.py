"""In-memory TaskRepository implementation.

M1 backing store: process-local dicts protected by a reentrant lock.
This implementation is intentionally ephemeral: a service restart loses
all in-flight and completed tasks. M4 will replace it with SQLite.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Final

from springfix_agent.storage.models import Report, Task, TaskStatus, Trace

_TASKS_KEY: Final[str] = "tasks"
_TRACES_KEY: Final[str] = "traces"
_REPORTS_KEY: Final[str] = "reports"


class TaskNotFoundError(KeyError):
    """Raised when a task_id is unknown to the repository."""


class InMemoryTaskRepository:
    """Process-local dict-backed TaskRepository.

    Thread-safe via a single reentrant lock. Suitable for MVP single-process
    operation; does not coordinate across instances.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self._traces: dict[str, list[Trace]] = {}
        self._reports: dict[str, Report] = {}
        self._lock = threading.RLock()

    def create_task(
        self,
        repository_path: str,
        issue_description: str,
        error_log: str | None,
    ) -> Task:
        import uuid

        task_id = str(uuid.uuid4())
        now = datetime.now(tz=UTC)
        task = Task(
            task_id=task_id,
            repository_path=repository_path,
            issue_description=issue_description,
            error_log=error_log,
            status="pending",
            submitted_at=now,
            started_at=None,
            finished_at=None,
            current_node=None,
        )
        with self._lock:
            self._tasks[task_id] = task
            self._traces[task_id] = []
        return task

    def get_task(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self) -> list[Task]:
        with self._lock:
            tasks = list(self._tasks.values())
        tasks.sort(key=lambda t: t.submitted_at, reverse=True)
        return tasks

    def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        current_node: str | None = None,
        error_message: str | None = None,
    ) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            update_data: dict[str, object] = {"status": status}
            if status == "running" and task.started_at is None:
                update_data["started_at"] = datetime.now(tz=UTC)
            if status in {"completed", "failed"} and task.finished_at is None:
                update_data["finished_at"] = datetime.now(tz=UTC)
            if current_node is not None:
                update_data["current_node"] = current_node
            if error_message is not None:
                update_data["error_message"] = error_message
            updated = task.model_copy(update=update_data)
            self._tasks[task_id] = updated

    def save_trace(self, task_id: str, trace: Trace) -> None:
        with self._lock:
            if task_id not in self._tasks:
                raise TaskNotFoundError(task_id)
            self._traces.setdefault(task_id, []).append(trace)

    def get_traces(self, task_id: str) -> list[Trace]:
        with self._lock:
            traces = list(self._traces.get(task_id, []))
        traces.sort(key=lambda t: t.recorded_at)
        return traces

    def save_report(self, task_id: str, report: Report) -> None:
        with self._lock:
            if task_id not in self._tasks:
                raise TaskNotFoundError(task_id)
            self._reports[task_id] = report

    def get_report(self, task_id: str) -> Report | None:
        with self._lock:
            return self._reports.get(task_id)

    def clear(self) -> None:
        """Drop all in-memory state. Used by tests to avoid cross-test bleed."""
        with self._lock:
            self._tasks.clear()
            self._traces.clear()
            self._reports.clear()
