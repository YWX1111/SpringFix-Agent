"""LangGraph builder for M2.

Seven-node static linear graph:

    START
    -> validate_input
    -> issue_parser
    -> task_planner
    -> explore_repository
    -> retrieve_code
    -> root_cause_analyzer
    -> build_diagnostic_report
    -> END

The builder receives a pre-configured ``LLMClient``. When the client is
a ``MockLLMClient`` the graph runs entirely offline; when it is an
``OpenAICompatibleLLMClient`` it talks to a real model provider.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph

from springfix_agent.graph.nodes.build_diagnostic_report import build_diagnostic_report
from springfix_agent.graph.nodes.explore_repository import explore_repository
from springfix_agent.graph.nodes.issue_parser import issue_parser
from springfix_agent.graph.nodes.retrieve_code import retrieve_code
from springfix_agent.graph.nodes.root_cause_analyzer import root_cause_analyzer
from springfix_agent.graph.nodes.task_planner import task_planner
from springfix_agent.graph.nodes.validate_input import validate_input
from springfix_agent.graph.state import AgentState
from springfix_agent.llm.client import LLMClient
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
    llm: LLMClient,
) -> Any:
    """Build a compiled 7-node LangGraph for one diagnostic task."""
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
            # Accumulate warnings (append reducer)
            warnings = list(merged.get("warnings") or [])
            merged["warnings"] = warnings
            return merged

        return wrapped

    def _validate(state: AgentState) -> dict[str, Any]:
        return validate_input(
            state,
            repository_path=repository_path,
            allow_root=allow_root,
        )

    def _parse(state: AgentState) -> dict[str, Any]:
        return issue_parser(state, llm=llm, tracer=tracer)

    def _plan(state: AgentState) -> dict[str, Any]:
        return task_planner(state, llm=llm, tracer=tracer)

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

    def _rca(state: AgentState) -> dict[str, Any]:
        return root_cause_analyzer(state, llm=llm, tracer=tracer)

    def _report(state: AgentState) -> dict[str, Any]:
        return build_diagnostic_report(state)

    graph: StateGraph[AgentState] = StateGraph(AgentState)
    # langgraph 0.2 add_node overloads require _Node[_NodeInputT] or Runnable;
    # our closures return Callable[[AgentState], dict[str, Any]], which is the
    # correct runtime shape but not one of the overloads. Kept as a narrow
    # ignore until langgraph publishes a stable node callable protocol.
    graph.add_node("validate_input", make_node("validate_input", _validate))  # type: ignore[call-overload]
    graph.add_node("issue_parser", make_node("issue_parser", _parse))  # type: ignore[call-overload]
    graph.add_node("task_planner", make_node("task_planner", _plan))  # type: ignore[call-overload]
    graph.add_node("explore_repository", make_node("explore_repository", _explore))  # type: ignore[call-overload]
    graph.add_node("retrieve_code", make_node("retrieve_code", _retrieve))  # type: ignore[call-overload]
    graph.add_node("root_cause_analyzer", make_node("root_cause_analyzer", _rca))  # type: ignore[call-overload]
    graph.add_node("build_diagnostic_report", make_node("build_diagnostic_report", _report))  # type: ignore[call-overload]

    graph.add_edge(START, "validate_input")
    graph.add_edge("validate_input", "issue_parser")
    graph.add_edge("issue_parser", "task_planner")
    graph.add_edge("task_planner", "explore_repository")
    graph.add_edge("explore_repository", "retrieve_code")
    graph.add_edge("retrieve_code", "root_cause_analyzer")
    graph.add_edge("root_cause_analyzer", "build_diagnostic_report")
    graph.add_edge("build_diagnostic_report", END)

    return graph.compile()
