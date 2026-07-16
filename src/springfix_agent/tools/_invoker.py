"""Tool invoker: wraps Tool.run with automatic timing and tracing.

Nodes call ``invoke_tool`` instead of calling ``Tool.run`` directly so
that every tool invocation is uniformly recorded in the trace store
with a stable schema. Tools themselves stay free of tracing concerns.
"""

from __future__ import annotations

import time
from typing import Any

from springfix_agent.observability.tracer import Tracer
from springfix_agent.tools._path_safety import PathSafetyError
from springfix_agent.tools.base import Tool, ToolCall, ToolContext, ToolResult

_MAX_TRACE_SUMMARY_CHARS = 500


def _truncate(text: str, limit: int = _MAX_TRACE_SUMMARY_CHARS) -> str:
    """Truncate text to limit characters, appending an ellipsis if cut."""
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _summarize_params(params: dict[str, Any]) -> dict[str, object]:
    """Return a params dict safe for trace persistence.

    Drops large string values (issue_description, error_log, etc.) by
    truncating any string param >200 chars to 200 chars + ellipsis.
    """
    summary: dict[str, object] = {}
    for key, value in params.items():
        if isinstance(value, str) and len(value) > 200:
            summary[key] = value[:197] + "..."
        else:
            summary[key] = value
    return summary


def invoke_tool(
    tool: Tool,
    params: dict[str, object],
    ctx: ToolContext,
    node_name: str,
    tracer: Tracer,
) -> ToolResult:
    """Execute ``tool.run`` with timing and trace recording.

    Always records a ToolCall, regardless of success or failure.
    Tool-internal errors (including PathSafetyError) are converted to
    ToolResult(status="error") so the calling node can degrade gracefully.
    """
    start_perf = time.monotonic()

    try:
        result = tool.run(params, ctx)
    except PathSafetyError as e:
        result = ToolResult(
            status="error",
            data={},
            result_summary="",
            error=f"path_safety: {e}",
        )
    except Exception as e:  # noqa: BLE001
        result = ToolResult(
            status="error",
            data={},
            result_summary="",
            error=f"{type(e).__name__}: {e}",
        )

    end_perf = time.monotonic()
    duration_ms = int((end_perf - start_perf) * 1000)

    call = ToolCall(
        node=node_name,
        tool_name=tool.name,
        params=_summarize_params(params),
        duration_ms=duration_ms,
        status=result["status"],
        result_summary=_truncate(result.get("result_summary", "")),
        error=result.get("error"),
    )
    tracer.record_tool_call(ctx["task_id"], call)
    return result
