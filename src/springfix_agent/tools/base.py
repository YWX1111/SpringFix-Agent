"""Tool Protocol and shared types.

This module defines the long-stable interface contract for all tools.
M1 will implement the four concrete tools against this contract.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol, TypedDict, runtime_checkable


class ToolContext(TypedDict):
    """Context injected into every tool call.

    Attributes:
        task_id: Identifier of the owning diagnostic task.
        repository_path: Canonicalized absolute path of the user-submitted
            repository. The API layer validates that this path is inside
            ``allow_root`` before constructing the context.
        allow_root: System-wide allowed root directory. Tools must not
            read any file outside ``repository_path`` (which itself must
            be inside ``allow_root``).

    Design constraints (enforced by tools/_path_safety.py in M1):

    - Tools only read files under ``repository_path``.
    - Tool params must not contain ``repository_path`` or any absolute path.
    - ``read_file`` accepts only ``relative_path`` (relative to
      ``repository_path``); the resolved path must remain inside
      ``repository_path`` after canonicalization.
    - ``repository_path`` itself must be inside ``allow_root``.
    """

    task_id: str
    repository_path: Path
    allow_root: Path


class ToolCall(TypedDict):
    """A single recorded tool invocation, persisted to the trace store.

    Constraints:

    - ``result_summary`` is truncated to 500 characters; the full result
      is never persisted in the trace.
    - ``params`` must not contain large inputs (full file contents, etc).
    """

    node: str
    tool_name: str
    params: dict[str, object]
    duration_ms: int
    status: Literal["success", "error"]
    result_summary: str
    error: str | None


class ToolResult(TypedDict):
    """Return value of every Tool.run invocation."""

    status: Literal["success", "error"]
    data: dict[str, object]
    result_summary: str
    error: str | None


@runtime_checkable
class Tool(Protocol):
    """Contract for all SpringFix Agent tools.

    Implementations are expected to:

    - Be stateless across calls (state lives in AgentState and the repository).
    - Read paths only via ``ctx.repository_path``; never accept absolute
      paths as parameters.
    - Return ``ToolResult(status="error", error=...)`` on failure rather
      than raising. The calling node decides whether to degrade.
    """

    name: str
    description: str

    def run(self, params: dict[str, object], ctx: ToolContext) -> ToolResult:
        """Execute the tool. Implementations must be idempotent for the same input."""
        ...
