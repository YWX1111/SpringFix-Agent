"""explore_repository node: list project tree and find Java symbols.

M2 enhancement: symbol sources are merged from three origins —
    1. deterministic extraction from issue_description + error_log
    2. IssueParser LLM output (issue_analysis.extracted_symbols)
    3. TaskPlanner target_symbols (investigation_plan.steps[].target_symbols)

All sources are merged, de-duplicated and capped at MAX_SYMBOLS_TO_SEARCH
before invoking find_java_symbol. No symbol names are hardcoded.
"""

from __future__ import annotations

from typing import Any

from springfix_agent.graph.nodes._symbol_extraction import (
    extract_symbols as _deterministic_extract,
)
from springfix_agent.graph.state import AgentState
from springfix_agent.observability.tracer import Tracer
from springfix_agent.tools._invoker import invoke_tool
from springfix_agent.tools.base import ToolContext
from springfix_agent.tools.find_java_symbol import FindJavaSymbolTool
from springfix_agent.tools.list_project_tree import ListProjectTreeTool

TREE_SUMMARY_MAX_CHARS = 2000
MAX_SYMBOLS_TO_SEARCH = 8
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

    deterministic_symbols = _deterministic_extract(
        state["issue_description"], state.get("error_log")
    )

    issue_analysis = state.get("issue_analysis") or {}
    raw_llm_symbols = issue_analysis.get("extracted_symbols")
    llm_symbols: list[str] = []
    if isinstance(raw_llm_symbols, list):
        llm_symbols = [str(s) for s in raw_llm_symbols if isinstance(s, str)][:10]

    plan_raw = state.get("investigation_plan") or {}
    plan_symbols: list[str] = []
    raw_steps = plan_raw.get("steps")
    if isinstance(raw_steps, list):
        for step in raw_steps:
            if isinstance(step, dict):
                raw_target_symbols = step.get("target_symbols")
                if isinstance(raw_target_symbols, list):
                    for sym in raw_target_symbols:
                        if isinstance(sym, str) and sym:
                            plan_symbols.append(sym)
                if len(plan_symbols) >= 10:
                    break

    merged: list[str] = []
    seen: set[str] = set()
    for source in (deterministic_symbols, llm_symbols, plan_symbols):
        for sym in source:
            if sym and sym not in seen:
                seen.add(sym)
                merged.append(sym)
                if len(merged) >= MAX_SYMBOLS_TO_SEARCH:
                    break
        if len(merged) >= MAX_SYMBOLS_TO_SEARCH:
            break

    candidate_files: set[str] = set()
    for sym in merged:
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
        f"symbols_extracted={len(merged)}, "
        f"candidate_files={len(sorted_candidates)}, "
        f"tree_chars={len(tree_summary)}"
    )
    return {
        "extracted_symbols": merged,
        "project_tree_summary": tree_summary,
        "candidate_files": sorted_candidates,
        "retrieval_summary": summary,
    }
