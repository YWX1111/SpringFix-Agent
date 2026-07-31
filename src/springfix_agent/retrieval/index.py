"""Retrieval index: orchestrates chunking, multi-channel search, and fusion.

This is the main entry point for the retrieve_code node. It:

1. Builds code chunks from the repository.
2. Constructs a RetrievalQuery from the agent state.
3. Runs Baseline, BM25, and Symbol retrieval channels.
4. Fuses results via Reciprocal Rank Fusion.
5. Returns top-K RetrievalHits with diagnostics.

On any channel failure, the pipeline degrades gracefully (e.g. BM25
failure → Baseline + Symbol only).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from springfix_agent.retrieval.baseline import BaselineLexicalRetriever
from springfix_agent.retrieval.bm25 import BM25Retriever
from springfix_agent.retrieval.chunker import chunk_repository
from springfix_agent.retrieval.diagnostics import make_diagnostics
from springfix_agent.retrieval.fusion import (
    DEFAULT_RRF_K,
    DEFAULT_WEIGHT_BASELINE,
    DEFAULT_WEIGHT_BM25,
    DEFAULT_WEIGHT_SYMBOL,
    reciprocal_rank_fusion,
)
from springfix_agent.retrieval.models import (
    RetrievalDiagnostics,
    RetrievalHit,
    RetrievalQuery,
)
from springfix_agent.retrieval.query_builder import build_query
from springfix_agent.retrieval.symbol import SymbolRetriever

_LOGGER = logging.getLogger(__name__)


def _ns_to_ms(ns: int) -> float:
    """Convert nanoseconds to milliseconds with 3+ decimal precision."""
    return ns / 1_000_000


def run_retrieval(
    repo_path: Path,
    state: dict[str, object],
    *,
    max_files: int = 200,
    max_chunks: int = 1000,
    top_k: int = 10,
    rrf_k: int = DEFAULT_RRF_K,
    rrf_weights: dict[str, float] | None = None,
) -> tuple[list[RetrievalHit], RetrievalDiagnostics, RetrievalQuery]:
    """Execute the full multi-channel retrieval pipeline.

    Returns:
        (hits, diagnostics, query) — hits is the fused top-K list.
    """
    warnings: list[str] = []
    fallback_used = False
    t_total_start = time.perf_counter_ns()

    # 1. Build query.
    query = build_query(state)
    query_terms_used = len(query.normalized_terms)

    # 2. Chunk the repository (file discovery + read + chunk build).
    t_corpus_start = time.perf_counter_ns()
    chunks, chunk_warnings, truncated = chunk_repository(
        repo_path,
        max_files=max_files,
        max_chunks=max_chunks,
    )
    t_corpus_end = time.perf_counter_ns()
    warnings.extend(chunk_warnings)
    corpus_build_ms = _ns_to_ms(t_corpus_end - t_corpus_start)

    # 3. Build BM25 index.
    t_index_start = time.perf_counter_ns()
    bm25 = BM25Retriever(chunks)
    t_index_end = time.perf_counter_ns()
    index_build_ms = _ns_to_ms(t_index_end - t_index_start)
    # Include BM25 internal build time.
    index_build_ms += float(bm25.build_duration_ms)

    # 4. Run retrieval channels.
    channels: dict[str, list[RetrievalHit]] = {}

    # 4a. Baseline lexical search.
    baseline_query = " ".join(query.normalized_terms) if query.normalized_terms else query.raw_text
    baseline = BaselineLexicalRetriever()
    t_bl_start = time.perf_counter_ns()
    baseline_hits, baseline_ms = baseline.search(repo_path, baseline_query, top_k=top_k)
    t_bl_end = time.perf_counter_ns()
    baseline_query_ms = _ns_to_ms(t_bl_end - t_bl_start)
    channels["baseline"] = baseline_hits

    # 4b. BM25 search.
    bm25_hits: list[RetrievalHit] = []
    bm25_ms = 0
    bm25_query_ms = 0.0
    try:
        t_bm_start = time.perf_counter_ns()
        bm25_hits, bm25_ms = bm25.search(query.normalized_terms, top_k=top_k)
        t_bm_end = time.perf_counter_ns()
        bm25_query_ms = _ns_to_ms(t_bm_end - t_bm_start)
        channels["bm25"] = bm25_hits
    except Exception as e:  # noqa: BLE001
        _LOGGER.warning("BM25 search failed: %s", e)
        warnings.append(f"bm25_search_failed: {type(e).__name__}: {str(e)[:200]}")
        fallback_used = True

    # 4c. Symbol search.
    symbol = SymbolRetriever()
    t_sym_start = time.perf_counter_ns()
    symbol_hits, symbol_ms = symbol.search(
        repo_path, query.exact_symbols, top_k=top_k,
    )
    t_sym_end = time.perf_counter_ns()
    symbol_query_ms = _ns_to_ms(t_sym_end - t_sym_start)
    if symbol_hits:
        channels["symbol"] = symbol_hits

    # 5. Fuse results.
    if rrf_weights is None:
        rrf_weights = {
            "baseline": DEFAULT_WEIGHT_BASELINE,
            "bm25": DEFAULT_WEIGHT_BM25,
            "symbol": DEFAULT_WEIGHT_SYMBOL,
        }

    t_fus_start = time.perf_counter_ns()
    fused_hits, fusion_ms = reciprocal_rank_fusion(
        channels, k=rrf_k, weights=rrf_weights, top_k=top_k,
    )
    t_fus_end = time.perf_counter_ns()
    fusion_ms_precise = _ns_to_ms(t_fus_end - t_fus_start)

    # If fusion returned nothing but baseline had results, use baseline directly.
    if not fused_hits and baseline_hits:
        fused_hits = baseline_hits[:top_k]
        fallback_used = True
        warnings.append("fusion_empty, falling back to baseline results")

    t_total_end = time.perf_counter_ns()
    total_retrieval_ms = _ns_to_ms(t_total_end - t_total_start)

    diag = make_diagnostics(
        files_scanned=len(chunks),
        chunks_created=len(chunks),
        chunks_indexed=bm25.indexed_count,
        corpus_build_ms=corpus_build_ms,
        index_build_ms=index_build_ms,
        baseline_query_ms=baseline_query_ms,
        bm25_query_ms=bm25_query_ms,
        symbol_query_ms=symbol_query_ms,
        fusion_ms=fusion_ms_precise,
        total_retrieval_ms=total_retrieval_ms,
        index_build_duration_ms=int(index_build_ms),
        baseline_duration_ms=int(baseline_query_ms),
        bm25_duration_ms=int(bm25_query_ms),
        symbol_duration_ms=int(symbol_query_ms),
        fusion_duration_ms=int(fusion_ms_precise),
        truncated=truncated,
        fallback_used=fallback_used,
        query_terms_used=query_terms_used,
        baseline_hits=len(baseline_hits),
        bm25_hits=len(bm25_hits),
        symbol_hits=len(symbol_hits),
        fusion_hits=len(fused_hits),
        warnings=warnings,
    )

    return fused_hits, diag, query
