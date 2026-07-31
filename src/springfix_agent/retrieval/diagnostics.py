"""Retrieval diagnostics: timing, scale, and fallback metadata.

Records per-channel durations, hit counts, and degradation reasons
for observability and evaluation.
"""

from __future__ import annotations

from springfix_agent.retrieval.models import RetrievalDiagnostics


def make_diagnostics(
    *,
    files_scanned: int = 0,
    chunks_created: int = 0,
    chunks_indexed: int = 0,
    corpus_build_ms: float = 0.0,
    index_build_ms: float = 0.0,
    baseline_query_ms: float = 0.0,
    bm25_query_ms: float = 0.0,
    symbol_query_ms: float = 0.0,
    fusion_ms: float = 0.0,
    total_retrieval_ms: float = 0.0,
    index_build_duration_ms: int = 0,
    baseline_duration_ms: int = 0,
    bm25_duration_ms: int = 0,
    symbol_duration_ms: int = 0,
    fusion_duration_ms: int = 0,
    truncated: bool = False,
    fallback_used: bool = False,
    query_terms_used: int = 0,
    query_terms_discarded: int = 0,
    baseline_hits: int = 0,
    bm25_hits: int = 0,
    symbol_hits: int = 0,
    fusion_hits: int = 0,
    warnings: list[str] | None = None,
) -> RetrievalDiagnostics:
    """Construct a RetrievalDiagnostics record."""
    return RetrievalDiagnostics(
        files_scanned=files_scanned,
        chunks_created=chunks_created,
        chunks_indexed=chunks_indexed,
        corpus_build_ms=corpus_build_ms,
        index_build_ms=index_build_ms,
        baseline_query_ms=baseline_query_ms,
        bm25_query_ms=bm25_query_ms,
        symbol_query_ms=symbol_query_ms,
        fusion_ms=fusion_ms,
        total_retrieval_ms=total_retrieval_ms,
        index_build_duration_ms=index_build_duration_ms,
        baseline_duration_ms=baseline_duration_ms,
        bm25_duration_ms=bm25_duration_ms,
        symbol_duration_ms=symbol_duration_ms,
        fusion_duration_ms=fusion_duration_ms,
        truncated=truncated,
        fallback_used=fallback_used,
        query_terms_used=query_terms_used,
        query_terms_discarded=query_terms_discarded,
        baseline_hits=baseline_hits,
        bm25_hits=bm25_hits,
        symbol_hits=symbol_hits,
        fusion_hits=fusion_hits,
        warnings=warnings or [],
    )


def diagnostics_to_summary(diag: RetrievalDiagnostics) -> str:
    """Format diagnostics as a compact summary string for retrieval_summary."""
    parts = [
        "strategy=hybrid",
        f"files={diag.files_scanned}",
        f"chunks={diag.chunks_created}",
        f"indexed={diag.chunks_indexed}",
        f"corpus_ms={diag.corpus_build_ms:.3f}",
        f"index_ms={diag.index_build_ms:.3f}",
        f"baseline_ms={diag.baseline_query_ms:.3f}({diag.baseline_hits})",
        f"bm25_ms={diag.bm25_query_ms:.3f}({diag.bm25_hits})",
        f"symbol_ms={diag.symbol_query_ms:.3f}({diag.symbol_hits})",
        f"fusion_ms={diag.fusion_ms:.3f}({diag.fusion_hits})",
        f"total_ms={diag.total_retrieval_ms:.3f}",
        f"terms={diag.query_terms_used}",
    ]
    if diag.truncated:
        parts.append("truncated=yes")
    if diag.fallback_used:
        parts.append("fallback=yes")
    if diag.warnings:
        parts.append(f"warnings={len(diag.warnings)}")
    return ", ".join(parts)
