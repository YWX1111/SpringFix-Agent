"""retrieve_code node: lexical search and bounded file reads.

Pulls top-K hits from search_code, then reads up to MAX_SNIPPETS files
via read_file. Each snippet content is already truncated by the read_file
tool to MAX_SNIPPET_LINES / MAX_SNIPPET_CHARS.
"""

from __future__ import annotations

from typing import Any

from springfix_agent.graph.state import MAX_SNIPPETS, AgentState, RetrievedSnippet
from springfix_agent.observability.tracer import Tracer
from springfix_agent.tools._invoker import invoke_tool
from springfix_agent.tools.base import ToolContext
from springfix_agent.tools.read_file import ReadFileTool
from springfix_agent.tools.search_code import SearchCodeTool

SEARCH_TOP_K = 5
MAX_HITS_TO_READ = MAX_SNIPPETS


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

    query = state["issue_description"]
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
                line_range_tuple = (int(lr0) if isinstance(lr0, (int, float)) else 1,
                                    int(lr1) if isinstance(lr1, (int, float)) else 1)
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

    summary = f"search_hits={total_hits}, snippets={len(snippets)}"
    return {
        "retrieved_snippets": snippets,
        "retrieval_summary": summary,
    }
