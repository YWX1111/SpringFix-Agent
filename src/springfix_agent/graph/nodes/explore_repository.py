"""explore_repository node: list project tree and find Java symbols.

Symbols are extracted deterministically from issue_description and
error_log. find_java_symbol is only called when at least one symbol
is extracted. No hardcoded symbol names.
"""

from __future__ import annotations

from typing import Any

from springfix_agent.graph.nodes._symbol_extraction import extract_symbols
from springfix_agent.graph.state import AgentState
from springfix_agent.observability.tracer import Tracer
from springfix_agent.tools._invoker import invoke_tool
from springfix_agent.tools.base import ToolContext
from springfix_agent.tools.find_java_symbol import FindJavaSymbolTool
from springfix_agent.tools.list_project_tree import ListProjectTreeTool

TREE_SUMMARY_MAX_CHARS = 2000
MAX_SYMBOLS_TO_SEARCH = 3
MAX_CANDIDATE_FILES = 30


def explore_repository(
    state: AgentState,
    *,
    ctx: ToolContext,
    tracer: Tracer,
    list_tree_tool: ListProjectTreeTool,
    find_symbol_tool: FindJavaSymbolTool,
) -> dict[str, Any]:
    """Walk the repository and locate candidate files by symbol."""
    if not state["validation_ok"]:
        return {}

    tree_result = invoke_tool(
        list_tree_tool,
        {"max_depth": 3, "max_files": 200},
        ctx,
        "explore_repository",
        tracer,
    )
    tree_summary = ""
    if tree_result["status"] == "success":
        full_tree = str(tree_result["data"].get("tree", ""))
        tree_summary = full_tree[:TREE_SUMMARY_MAX_CHARS]

    symbols = extract_symbols(state["issue_description"], state.get("error_log"))

    candidate_files: set[str] = set()
    for sym in symbols[:MAX_SYMBOLS_TO_SEARCH]:
        result = invoke_tool(
            find_symbol_tool,
            {
                "symbol_name": sym,
                "symbol_type": "any",
                "max_results": 20,
            },
            ctx,
            "explore_repository",
            tracer,
        )
        if result["status"] != "success":
            continue
        matches_raw = result["data"].get("matches", [])
        matches: list[dict[str, object]] = (
            [m for m in matches_raw if isinstance(m, dict)]
            if isinstance(matches_raw, list)
            else []
        )
        for m in matches:
            file_raw = m.get("file", "")
            file_path = str(file_raw) if file_raw else ""
            if file_path:
                candidate_files.add(file_path)
            if len(candidate_files) >= MAX_CANDIDATE_FILES:
                break
        if len(candidate_files) >= MAX_CANDIDATE_FILES:
            break

    sorted_candidates = sorted(candidate_files)
    summary = (
        f"symbols_extracted={len(symbols)}, "
        f"candidate_files={len(sorted_candidates)}, "
        f"tree_chars={len(tree_summary)}"
    )
    return {
        "extracted_symbols": symbols,
        "project_tree_summary": tree_summary,
        "candidate_files": sorted_candidates,
        "retrieval_summary": summary,
    }
