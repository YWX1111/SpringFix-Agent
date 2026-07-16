"""Tracer Protocol and timing types.

The Tracer is the long-stable interface used by every Graph node and Tool
to record observability data. Implementations:

- M1: ``InMemoryTracer`` (writes to TaskRepository in-process)
- M4+: Redis Stream publisher for cross-service streaming
"""

from __future__ import annotations

from typing import Protocol, TypedDict

from springfix_agent.tools.base import ToolCall


class NodeTiming(TypedDict):
    """Timing record for a single Graph node execution."""

    node: str
    start: str
    end: str
    duration_ms: int


class Tracer(Protocol):
    """Contract for observability recorders.

    Implementations must be safe to call from any Graph node and any Tool.
    Recording must not raise; failures should be logged and swallowed so
    that observability never breaks the main flow.
    """

    def record_tool_call(self, task_id: str, call: ToolCall) -> None:
        """Persist a single tool call record."""
        ...

    def record_node_timing(self, task_id: str, timing: NodeTiming) -> None:
        """Persist a single node timing record."""
        ...
