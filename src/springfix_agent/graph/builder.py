"""LangGraph builder.

Constructs a compiled 4-node static linear graph with closures that
capture the Tracer, ToolContext, and tool instances. The graph itself
is per-task (a new ToolContext per task_id), but tool instances are
stateless and reused across tasks.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph

from springfix_agent.graph.nodes.build_basic_report import build_basic_report
from springfix_agent.graph.nodes.explore_repository import explore_repository
from springfix_agent.graph.nodes.retrieve_code import retrieve_code
from springfix_agent.graph.nodes.validate_input import validate_input
from springfix_agent.graph.state import AgentState
from springfix_agent.observability.tracer import NodeTiming, Tracer
from springfix_agent.tools.base import ToolContext
from springfix_agent.tools.find_java_symbol import FindJavaSymbolTool
from springfix_agent.tools.list_project_tree import ListProjectTreeTool
from springfix_agent.tools.read_file import ReadFileTool
from springfix_agent.tools.search_code import SearchCodeTool

NodeFn = Callable[[AgentState], dict[str, Any]]


def build_graph(
    *,
    task_id: str,
    repository_path: Path,
    allow_root: Path,
    tracer: Tracer,
) -> Any:
    """Build a compiled LangGraph for one diagnostic task.

    Each call returns a fresh compiled graph bound to the given task_id
    and repository. Tool instances are stateless; the closures capture
    only references, so this is cheap.

    The return type is the compiled LangGraph runnable; we leave the
    precise generic parameters to the langgraph library and use Any
    here because the langgraph 0.2 type signatures are not stable.
    """
    ctx = ToolContext(
        task_id=task_id,
        repository_path=repository_path,
        allow_root=allow_root,
    )

    list_tree = ListProjectTreeTool()
    search = SearchCodeTool()
    read = ReadFileTool()
    find_sym = FindJavaSymbolTool()

    def make_node(name: str, fn: Callable[..., dict[str, Any]]) -> NodeFn:
        def wrapped(state: AgentState) -> dict[str, Any]:
            start_perf = time.monotonic()
            start_iso = datetime.now(tz=UTC).isoformat()
            try:
                result = fn(state)
            except Exception as e:  # noqa: BLE001
                result = {
                    "errors": [f"node {name} raised {type(e).__name__}: {e}"],
                    "status": "failed",
                }
            end_perf = time.monotonic()
            end_iso = datetime.now(tz=UTC).isoformat()
            timing = NodeTiming(
                node=name,
                start=start_iso,
                end=end_iso,
                duration_ms=int((end_perf - start_perf) * 1000),
            )
            tracer.record_node_timing(task_id, timing)
            merged = dict(result)
            merged.setdefault("current_node", name)
            return merged

        return wrapped

    def _validate(state: AgentState) -> dict[str, Any]:
        return validate_input(
            state,
            repository_path=repository_path,
            allow_root=allow_root,
        )

    def _explore(state: AgentState) -> dict[str, Any]:
        return explore_repository(
            state,
            ctx=ctx,
            tracer=tracer,
            list_tree_tool=list_tree,
            find_symbol_tool=find_sym,
        )

    def _retrieve(state: AgentState) -> dict[str, Any]:
        return retrieve_code(
            state,
            ctx=ctx,
            tracer=tracer,
            search_tool=search,
            read_tool=read,
        )

    def _report(state: AgentState) -> dict[str, Any]:
        return build_basic_report(state)

    graph: StateGraph[AgentState] = StateGraph(AgentState)
    graph.add_node("validate_input", make_node("validate_input", _validate))  # type: ignore[call-overload]
    graph.add_node("explore_repository", make_node("explore_repository", _explore))  # type: ignore[call-overload]
    graph.add_node("retrieve_code", make_node("retrieve_code", _retrieve))  # type: ignore[call-overload]
    graph.add_node("build_basic_report", make_node("build_basic_report", _report))  # type: ignore[call-overload]

    graph.add_edge(START, "validate_input")
    graph.add_edge("validate_input", "explore_repository")
    graph.add_edge("explore_repository", "retrieve_code")
    graph.add_edge("retrieve_code", "build_basic_report")
    graph.add_edge("build_basic_report", END)

    return graph.compile()
