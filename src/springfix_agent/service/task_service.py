"""TaskService: business layer orchestrating task lifecycle.

Responsibilities:
    - submit_task: validate inputs, create pending task, schedule background run
    - run_task_sync: execute LangGraph synchronously, persist report and final status
    - get_task / get_traces / get_report: read-side queries

Scheduling boundary (must be documented in API and README):
    - In-process threading.Thread with daemon=True
    - Service restart loses any in-flight task
    - No coordination across multiple service instances
    - Will be replaced by Redis Stream or a job queue in a later milestone

M2 adds:
    - An ``LLMClient`` dependency passed at construction.
    - The LLM client is forwarded to ``build_graph``.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from springfix_agent.graph.builder import build_graph
from springfix_agent.graph.state import AgentState, make_initial_state
from springfix_agent.llm.client import LLMClient
from springfix_agent.observability.in_memory_tracer import InMemoryTracer
from springfix_agent.storage.models import Report, Task, TaskStatus, Trace
from springfix_agent.storage.repository import TaskRepository  # Protocol
from springfix_agent.tools._path_safety import PathSafetyError, canonicalize_repository

_LOGGER = logging.getLogger(__name__)

MIN_ISSUE_LEN = 10
MAX_ISSUE_LEN = 2000
MAX_ERROR_LOG_LEN = 10000

SchedulerFn = Callable[[str], None]


class TaskValidationError(ValueError):
    """Raised when submit_task inputs fail validation."""


class TaskService:
    """Business layer for diagnostic task lifecycle."""

    def __init__(
        self,
        repository: TaskRepository,
        allow_root: Path,
        llm: LLMClient,
    ) -> None:
        self._repo = repository
        self._allow_root = allow_root
        self._llm = llm

    @property
    def llm(self) -> LLMClient:
        """The LLM client used by this service's graph invocations."""
        return self._llm

    def submit_task(
        self,
        *,
        repository_path: str,
        issue_description: str,
        error_log: str | None,
        scheduler: SchedulerFn | None = None,
    ) -> Task:
        """Validate inputs, create a pending task, and schedule background run."""
        canonical_path = self._validate_and_canonicalize(
            repository_path=repository_path,
            issue_description=issue_description,
            error_log=error_log,
        )
        task = self._repo.create_task(
            repository_path=canonical_path.as_posix(),
            issue_description=issue_description,
            error_log=error_log,
        )

        sched: SchedulerFn = scheduler if scheduler is not None else self._default_scheduler
        sched(task.task_id)
        return task

    def run_task_sync(self, task_id: str) -> None:
        """Execute a task's LangGraph synchronously and persist the final state."""
        task = self._repo.get_task(task_id)
        if task is None:
            raise TaskValidationError(f"task not found: {task_id}")

        self._repo.update_status(task_id, "running", current_node="validate_input")

        tracer = InMemoryTracer(self._repo)
        try:
            final_state = self._invoke_graph(task, tracer)
        except Exception as e:  # noqa: BLE001
            _LOGGER.exception("graph invocation failed for task %s", task_id)
            self._repo.update_status(task_id, "failed", current_node="error")
            self._save_failure_report(task_id, str(e))
            return

        self._persist_outcome(task_id, final_state)

    def get_task(self, task_id: str) -> Task | None:
        return self._repo.get_task(task_id)

    def get_traces(self, task_id: str) -> list[Trace]:
        return self._repo.get_traces(task_id)

    def get_report(self, task_id: str) -> Report | None:
        return self._repo.get_report(task_id)

    def _validate_and_canonicalize(
        self,
        *,
        repository_path: str,
        issue_description: str,
        error_log: str | None,
    ) -> Path:
        if not repository_path or not repository_path.strip():
            raise TaskValidationError("repository_path is required")
        if not issue_description or not issue_description.strip():
            raise TaskValidationError("issue_description is required")
        issue_stripped = issue_description.strip()
        if not (MIN_ISSUE_LEN <= len(issue_stripped) <= MAX_ISSUE_LEN):
            raise TaskValidationError(
                f"issue_description length must be {MIN_ISSUE_LEN}-{MAX_ISSUE_LEN}"
            )
        if error_log is not None and len(error_log) > MAX_ERROR_LOG_LEN:
            raise TaskValidationError(
                f"error_log length must be <= {MAX_ERROR_LOG_LEN}"
            )

        raw_path = Path(repository_path)
        try:
            return canonicalize_repository(raw_path, self._allow_root)
        except PathSafetyError as e:
            raise TaskValidationError(str(e)) from e

    def _invoke_graph(self, task: Task, tracer: InMemoryTracer) -> AgentState:
        repository_path = Path(task.repository_path)
        graph = build_graph(
            task_id=task.task_id,
            repository_path=repository_path,
            allow_root=self._allow_root,
            tracer=tracer,
            llm=self._llm,
        )
        initial = make_initial_state(
            task_id=task.task_id,
            repository_path=task.repository_path,
            issue_description=task.issue_description,
            error_log=task.error_log,
        )
        result = graph.invoke(initial)
        if not isinstance(result, dict):
            raise RuntimeError("graph.invoke returned non-dict result")
        return result  # type: ignore[return-value]

    def _persist_outcome(self, task_id: str, final_state: AgentState) -> None:
        # Prefer diagnostic_report if present (M2), fall back to basic_report (M1).
        report_body = dict(final_state.get("diagnostic_report") or {})
        if not report_body:
            report_body = dict(final_state.get("basic_report") or {})
        markdown_report = str(final_state.get("markdown_report", "") or "")
        raw_status = str(final_state.get("status", "failed"))
        if raw_status not in ("pending", "running", "completed", "failed"):
            raw_status = "failed"
        status_value: TaskStatus = raw_status  # type: ignore[assignment]

        report = Report(
            task_id=task_id,
            json_report=report_body,
            markdown_report=markdown_report,
            created_at=datetime.now(tz=UTC),
        )
        self._repo.save_report(task_id, report)
        self._repo.update_status(
            task_id,
            status_value,
            current_node=str(final_state.get("current_node", "")),
        )

    def _save_failure_report(self, task_id: str, error_msg: str) -> None:
        report = Report(
            task_id=task_id,
            json_report={
                "status": "failed",
                "diagnosis_status": "insufficient_evidence",
                "error": error_msg,
                "disclaimer": "Task execution failed before report generation.",
            },
            markdown_report=(
                f"# 诊断报告\n\n- status: **failed**\n"
                f"- diagnosis_status: **insufficient_evidence**\n\n"
                f"## 错误\n\n```\n{error_msg}\n```\n"
            ),
            created_at=datetime.now(tz=UTC),
        )
        self._repo.save_report(task_id, report)

    def _default_scheduler(self, task_id: str) -> None:
        thread = threading.Thread(
            target=self._safe_run,
            args=(task_id,),
            daemon=True,
            name=f"task-{task_id[:8]}",
        )
        thread.start()

    def _safe_run(self, task_id: str) -> None:
        try:
            self.run_task_sync(task_id)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("background task %s failed", task_id)
