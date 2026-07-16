"""In-memory Tracer implementation.

Writes ToolCall and NodeTiming records into a TaskRepository via save_trace.
Failures are swallowed (logged via stdlib logging) so observability never
breaks the main flow.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Final

from springfix_agent.observability.tracer import NodeTiming
from springfix_agent.storage.models import Trace
from springfix_agent.storage.repository import TaskRepository  # Protocol only
from springfix_agent.tools.base import ToolCall

_LOGGER: Final[logging.Logger] = logging.getLogger(__name__)


class InMemoryTracer:
    """Tracer that persists to a TaskRepository (any implementation).

    Suitable for M1 (InMemoryTaskRepository) and M4 (SqliteTaskRepository)
    alike, since the Tracer only depends on the TaskRepository Protocol.
    """

    def __init__(self, repository: TaskRepository) -> None:
        self._repo = repository

    def record_tool_call(self, task_id: str, call: ToolCall) -> None:
        try:
            trace = Trace(
                task_id=task_id,
                kind="tool_call",
                recorded_at=datetime.now(tz=UTC),
                payload=_tool_call_payload(call),
            )
            self._repo.save_trace(task_id, trace)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("failed to record tool_call for task %s", task_id)

    def record_node_timing(self, task_id: str, timing: NodeTiming) -> None:
        try:
            trace = Trace(
                task_id=task_id,
                kind="node_timing",
                recorded_at=datetime.now(tz=UTC),
                payload=_node_timing_payload(timing),
            )
            self._repo.save_trace(task_id, trace)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("failed to record node_timing for task %s", task_id)


def _tool_call_payload(call: ToolCall) -> dict[str, object]:
    return {
        "node": call["node"],
        "tool_name": call["tool_name"],
        "params": call["params"],
        "duration_ms": call["duration_ms"],
        "status": call["status"],
        "result_summary": call["result_summary"],
        "error": call["error"],
    }


def _node_timing_payload(timing: NodeTiming) -> dict[str, object]:
    return {
        "node": timing["node"],
        "start": timing["start"],
        "end": timing["end"],
        "duration_ms": timing["duration_ms"],
    }
