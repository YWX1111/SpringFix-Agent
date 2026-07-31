"""retrieve_code node: hybrid multi-channel retrieval (M3).

M3 replaces the M1 line-level lexical search with a multi-channel pipeline:

1. Build RetrievalQuery from state (issue_description, IssueAnalysis, etc.)
2. Chunk the repository into CodeChunks
3. Run Baseline (M1 lexical scoring), BM25, and Symbol retrieval
4. Fuse results via Reciprocal Rank Fusion
5. Return top-K snippets with real file paths and line numbers

On any channel failure, the pipeline degrades gracefully.
RootCauseAnalyzer evidence validation rules remain unchanged.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from springfix_agent.graph.state import MAX_SNIPPETS, AgentState, RetrievedSnippet
from springfix_agent.observability.tracer import Tracer
from springfix_agent.retrieval.diagnostics import diagnostics_to_summary
from springfix_agent.retrieval.index import run_retrieval
from springfix_agent.tools.base import ToolContext

_LOGGER = logging.getLogger(__name__)

SEARCH_TOP_K = MAX_SNIPPETS


def retrieve_code(
    state: AgentState,
    *,
    ctx: ToolContext,
    tracer: Tracer,
    search_tool: Any = None,
    read_tool: Any = None,
) -> dict[str, Any]:
    """Run hybrid multi-channel retrieval and return bounded snippets.

    The ``search_tool`` and ``read_tool`` parameters are accepted for
    backward compatibility but are no longer used in the M3 pipeline.
    """
    if not state["validation_ok"]:
        return {}

    repo_path = Path(ctx["repository_path"])

    try:
        fused_hits, diag, query = run_retrieval(
            repo_path,
            dict(state),
            top_k=SEARCH_TOP_K,
        )
    except Exception as e:  # noqa: BLE001
        _LOGGER.warning("retrieve_code pipeline failed: %s", e)
        return {
            "retrieved_snippets": [],
            "retrieval_summary": f"hybrid retrieval failed: {type(e).__name__}: {str(e)[:200]}",
            "retrieval_strategy": "fallback",
            "retrieval_query": {},
            "retrieval_diagnostics": {"error": str(e)[:500]},
            "warnings": [f"retrieve_code: hybrid retrieval failed: {type(e).__name__}"],
        }

    # Convert RetrievalHits to RetrievedSnippets.
    snippets: list[RetrievedSnippet] = []
    for hit in fused_hits:
        if len(snippets) >= MAX_SNIPPETS:
            break
        chunk = hit.chunk
        snippets.append(RetrievedSnippet(
            file=chunk.file,
            line_range=(chunk.start_line, chunk.end_line),
            content=chunk.content,
            score=hit.fused_score,
            symbols=hit.matched_terms[:20],
        ))

    strategy = "hybrid"
    if diag.fallback_used:
        strategy = "fallback"
    elif not diag.bm25_hits and diag.baseline_hits:
        strategy = "baseline"

    summary = diagnostics_to_summary(diag)
    warnings: list[str] = list(diag.warnings)

    return {
        "retrieved_snippets": snippets,
        "retrieval_summary": summary,
        "retrieval_strategy": strategy,
        "retrieval_query": query.model_dump(),
        "retrieval_diagnostics": diag.model_dump(),
        "warnings": warnings,
    }
