"""retrieve_code node: lexical search and bounded file reads.

M2 enhancement: search queries are merged from multiple sources:
    - state["issue_description"] (original user text)
    - issue_analysis.search_terms
    - investigation_plan.steps[].search_terms
    - issue_analysis.exception_types
    - exception class names extracted from error_log

All terms are de-duplicated, capped at MAX_QUERY_TOKENS, then joined
into a single query string for one search_code call. Results continue
to use M1's deterministic lexical scoring (no BM25 in M2).
"""

from __future__ import annotations

import re
from typing import Any

from springfix_agent.graph.state import MAX_SNIPPETS, AgentState, RetrievedSnippet
from springfix_agent.observability.tracer import Tracer
from springfix_agent.tools._invoker import invoke_tool
from springfix_agent.tools.base import ToolContext
from springfix_agent.tools.read_file import ReadFileTool
from springfix_agent.tools.search_code import SearchCodeTool

SEARCH_TOP_K = 5
MAX_HITS_TO_READ = MAX_SNIPPETS
MAX_QUERY_TOKENS = 20

_EXCEPTION_CLASS_RE = re.compile(r"\b([A-Z][A-Za-z0-9_]*Exception)\b")


def _collect_query_terms(state: AgentState) -> list[str]:
    """Merge search terms from all M2 sources, de-duplicated, capped."""
    out: list[str] = []
    seen: set[str] = set()

    def _add(token: str) -> None:
        trimmed = token.strip()
        if not trimmed or len(trimmed) < 2 or trimmed in seen:
            return
        seen.add(trimmed)
        out.append(trimmed)

    # 1. Original issue description - extract Java identifiers
    for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", state["issue_description"]):
        if len(tok) >= 3:
            _add(tok)

    # 2. IssueParser search_terms
    issue_analysis = state.get("issue_analysis") or {}
    raw_search_terms = issue_analysis.get("search_terms")
    if isinstance(raw_search_terms, list):
        for term in raw_search_terms:
            if isinstance(term, str):
                _add(term)

    # 3. TaskPlanner search_terms from each step
    plan = state.get("investigation_plan") or {}
    raw_steps = plan.get("steps")
    if isinstance(raw_steps, list):
        for step in raw_steps:
            if isinstance(step, dict):
                raw_step_terms = step.get("search_terms")
                if isinstance(raw_step_terms, list):
                    for term in raw_step_terms:
                        if isinstance(term, str):
                            _add(term)

    # 4. exception_types from IssueParser
    raw_exception_types = issue_analysis.get("exception_types")
    if isinstance(raw_exception_types, list):
        for et in raw_exception_types:
            if isinstance(et, str):
                _add(et)

    # 5. Exception class names from error_log
    error_log = state.get("error_log")
    if error_log:
        for m in _EXCEPTION_CLASS_RE.finditer(error_log):
            _add(m.group(1))

    return out[:MAX_QUERY_TOKENS]


def retrieve_code(
    state: AgentState,
    *,
    ctx: ToolContext,
    tracer: Tracer,
    search_tool: SearchCodeTool,
    read_tool: ReadFileTool,
) -> dict[str, Any]:
    """Run lexical search and read top candidate files as bounded snippets."""
    if not state["validation_ok"]:
        return {}

    query_terms = _collect_query_terms(state)
    query = " ".join(query_terms) if query_terms else state["issue_description"]

    search_result = invoke_tool(
        search_tool,
        {"query": query, "top_k": SEARCH_TOP_K},
        ctx,
        "retrieve_code",
        tracer,
    )

    snippets: list[RetrievedSnippet] = []
    seen_files: set[str] = set()
    total_hits = 0

    if search_result["status"] == "success":
        hits_raw = search_result["data"].get("hits", [])
        hits: list[dict[str, object]] = (
            [h for h in hits_raw if isinstance(h, dict)] if isinstance(hits_raw, list) else []
        )
        total_hits = len(hits)
        for hit in hits:
            if len(snippets) >= MAX_HITS_TO_READ:
                break
            file_path = str(hit.get("file", ""))
            if not file_path or file_path in seen_files:
                continue
            seen_files.add(file_path)
            read_result = invoke_tool(
                read_tool,
                {"relative_path": file_path},
                ctx,
                "retrieve_code",
                tracer,
            )
            if read_result["status"] != "success":
                continue
            data = read_result["data"]
            line_range_raw = data.get("line_range", [1, 1])
            if isinstance(line_range_raw, list) and len(line_range_raw) >= 2:
                lr0 = line_range_raw[0]
                lr1 = line_range_raw[1]
                line_range_tuple = (
                    int(lr0) if isinstance(lr0, (int, float)) else 1,
                    int(lr1) if isinstance(lr1, (int, float)) else 1,
                )
            else:
                line_range_tuple = (1, 1)
            score_raw = hit.get("score", 0.0)
            matched_raw = hit.get("matched_terms", [])
            snippets.append(
                RetrievedSnippet(
                    file=file_path,
                    line_range=line_range_tuple,
                    content=str(data.get("content", "")),
                    score=float(score_raw) if isinstance(score_raw, (int, float)) else 0.0,
                    symbols=[str(t) for t in matched_raw] if isinstance(matched_raw, list) else [],
                )
            )

    summary = (
        f"search_terms={len(query_terms)}, search_hits={total_hits}, "
        f"snippets={len(snippets)}"
    )
    return {
        "retrieved_snippets": snippets,
        "retrieval_summary": summary,
    }
