"""Fusion tests for Reciprocal Rank Fusion.

Covers:
    25. multi-channel duplicate merge
    26. RRF calculation
    27. symbol priority but not exclusive
    28. BM25 failure fallback
    29. source and rank recording
    30. stable sort
    Chunk deduplication (merge_overlapping_chunks)
    Timing diagnostics
"""

from __future__ import annotations

from springfix_agent.retrieval.fusion import (
    merge_overlapping_chunks,
    reciprocal_rank_fusion,
)
from springfix_agent.retrieval.models import CodeChunk, RetrievalHit
from springfix_agent.retrieval.tokenizer import tokenize_chunk_content


def _hit(
    file: str,
    chunk_type: str = "method",
    start: int = 1,
    end: int = 10,
    source: str = "baseline",
    score: float = 1.0,
) -> RetrievalHit:
    content = f"public void {file.replace('.', '_')}() {{}}"
    tokens = tokenize_chunk_content(content)
    cid = CodeChunk.make_chunk_id(file, chunk_type, start, end)
    return RetrievalHit(
        chunk=CodeChunk(
            chunk_id=cid, file=file, language="java",
            chunk_type=chunk_type,  # type: ignore[arg-type]
            start_line=start, end_line=end,
            content=content, tokens=tokens,
        ),
        fused_score=score,
        sources=[source],
        source_ranks={source: 1},
        matched_terms=["test"],
    )


# -- 25. multi-channel duplicate merge --
def test_duplicate_merge() -> None:
    """Same chunk from different channels should be merged."""
    h_bl = _hit("Svc.java", source="baseline")
    h_bm = _hit("Svc.java", source="bm25")
    channels = {"baseline": [h_bl], "bm25": [h_bm]}
    fused, ms = reciprocal_rank_fusion(channels, top_k=5)
    # Should be merged into one result.
    assert len(fused) == 1
    assert "baseline" in fused[0].sources
    assert "bm25" in fused[0].sources


# -- 26. RRF calculation --
def test_rrf_calculation() -> None:
    """Verify RRF formula: weight / (k + rank)."""
    h1 = _hit("A.java", source="baseline")
    h2 = _hit("B.java", source="bm25")
    channels = {"baseline": [h1], "bm25": [h2]}
    k = 60
    fused, _ = reciprocal_rank_fusion(channels, k=k, top_k=5)
    # A.java: baseline rank 1 → 1.0 / (60 + 1) ≈ 0.01639
    # B.java: bm25 rank 1 → 1.0 / (60 + 1) ≈ 0.01639
    for hit in fused:
        assert hit.fused_score > 0
        assert hit.fused_score <= 1.0 / (k + 1) + 0.001


# -- 27. symbol priority but not exclusive --
def test_symbol_priority_not_exclusive() -> None:
    """Symbol hits get higher weight but don't exclude other channels."""
    h_sym = _hit("Sym.java", source="symbol")
    h_bl = _hit("Other.java", source="baseline")
    channels = {
        "symbol": [h_sym],
        "baseline": [h_bl],
    }
    weights = {"baseline": 1.0, "bm25": 1.0, "symbol": 1.5}
    fused, _ = reciprocal_rank_fusion(channels, weights=weights, top_k=5)
    assert len(fused) == 2
    # Symbol should rank higher due to weight.
    assert fused[0].chunk.file == "Sym.java"


# -- 28. BM25 failure fallback --
def test_bm25_failure_fallback() -> None:
    """When BM25 channel is absent, baseline and symbol still fuse."""
    h_bl = _hit("A.java", source="baseline")
    channels = {"baseline": [h_bl]}  # no bm25
    fused, _ = reciprocal_rank_fusion(channels, top_k=5)
    assert len(fused) == 1
    assert fused[0].chunk.file == "A.java"


# -- 29. source and rank recording --
def test_source_and_rank_recording() -> None:
    h_bl = _hit("A.java", source="baseline")
    h_bm = _hit("A.java", source="bm25")
    channels = {"baseline": [h_bl], "bm25": [h_bm]}
    fused, _ = reciprocal_rank_fusion(channels, top_k=5)
    assert len(fused) == 1
    hit = fused[0]
    assert "baseline" in hit.source_ranks
    assert "bm25" in hit.source_ranks
    assert hit.source_ranks["baseline"] == 1
    assert hit.source_ranks["bm25"] == 1


# -- 30. stable sort --
def test_stable_sort() -> None:
    """Repeated fusion should produce same ordering."""
    h1 = _hit("A.java", source="baseline")
    h2 = _hit("B.java", source="bm25")
    channels = {"baseline": [h1], "bm25": [h2]}
    f1, _ = reciprocal_rank_fusion(channels, top_k=5)
    f2, _ = reciprocal_rank_fusion(channels, top_k=5)
    assert [h.chunk.chunk_id for h in f1] == [h.chunk.chunk_id for h in f2]


def test_empty_channels() -> None:
    fused, ms = reciprocal_rank_fusion({}, top_k=5)
    assert fused == []


def test_top_k_limit() -> None:
    channels = {
        "baseline": [_hit(f"File{i}.java", source="baseline") for i in range(20)]
    }
    fused, _ = reciprocal_rank_fusion(channels, top_k=5)
    assert len(fused) <= 5


# -- Chunk deduplication tests --


def _make_hit(
    file: str,
    start: int,
    end: int,
    source: str = "baseline",
    chunk_type: str = "method",
    symbol_name: str | None = None,
) -> RetrievalHit:
    content = f"// {file} L{start}-{end}"
    tokens = tokenize_chunk_content(content)
    cid = CodeChunk.make_chunk_id(file, chunk_type, start, end, symbol_name)
    return RetrievalHit(
        chunk=CodeChunk(
            chunk_id=cid, file=file, language="java",
            chunk_type=chunk_type,  # type: ignore[arg-type]
            symbol_name=symbol_name,
            start_line=start, end_line=end,
            content=content, tokens=tokens,
        ),
        fused_score=1.0 / (60 + 1),
        sources=[source],
        source_ranks={source: 1},
        matched_terms=["test"],
    )


def test_merge_overlapping_same_file() -> None:
    """Overlapping chunks in same file should be merged."""
    h1 = _make_hit("A.java", 10, 30, source="baseline", chunk_type="file_window")
    h2 = _make_hit("A.java", 15, 35, source="bm25", chunk_type="method")
    merged = merge_overlapping_chunks([h1, h2])
    assert len(merged) == 1
    assert "baseline" in merged[0].sources
    assert "bm25" in merged[0].sources


def test_merge_keeps_wider_chunk() -> None:
    """Merged result keeps the chunk with more lines."""
    h1 = _make_hit("A.java", 10, 20, source="baseline")
    h2 = _make_hit("A.java", 5, 25, source="bm25")
    merged = merge_overlapping_chunks([h1, h2])
    assert len(merged) == 1
    # h2 is wider (21 lines vs 11 lines).
    assert merged[0].chunk.start_line == 5
    assert merged[0].chunk.end_line == 25


def test_no_merge_different_files() -> None:
    """Chunks in different files should NOT be merged."""
    h1 = _make_hit("A.java", 10, 30, source="baseline")
    h2 = _make_hit("B.java", 10, 30, source="bm25")
    merged = merge_overlapping_chunks([h1, h2])
    assert len(merged) == 2


def test_no_merge_non_overlapping_same_file() -> None:
    """Non-overlapping chunks in same file should NOT be merged."""
    h1 = _make_hit("A.java", 10, 20, source="baseline")
    h2 = _make_hit("A.java", 50, 60, source="bm25")
    merged = merge_overlapping_chunks([h1, h2])
    assert len(merged) == 2


def test_merge_combines_matched_terms() -> None:
    h1 = _make_hit("A.java", 10, 30, source="baseline")
    h1.matched_terms = ["foo", "bar"]
    h2 = _make_hit("A.java", 15, 35, source="bm25")
    h2.matched_terms = ["baz", "foo"]
    merged = merge_overlapping_chunks([h1, h2])
    assert len(merged) == 1
    terms = set(merged[0].matched_terms)
    assert "foo" in terms
    assert "bar" in terms
    assert "baz" in terms


def test_merge_empty_list() -> None:
    assert merge_overlapping_chunks([]) == []


def test_merge_single_hit() -> None:
    h = _make_hit("A.java", 1, 10)
    assert merge_overlapping_chunks([h]) == [h]


# -- Timing diagnostics tests --


def test_diagnostics_timing_fields_exist() -> None:
    """RetrievalDiagnostics should have all timing fields."""
    from springfix_agent.retrieval.models import RetrievalDiagnostics

    diag = RetrievalDiagnostics()
    assert diag.corpus_build_ms >= 0
    assert diag.index_build_ms >= 0
    assert diag.baseline_query_ms >= 0
    assert diag.bm25_query_ms >= 0
    assert diag.symbol_query_ms >= 0
    assert diag.fusion_ms >= 0
    assert diag.total_retrieval_ms >= 0


def test_diagnostics_total_ge_sub_phases() -> None:
    """total_retrieval_ms should be >= main sub-phase timings."""
    from springfix_agent.retrieval.models import RetrievalDiagnostics

    diag = RetrievalDiagnostics(
        corpus_build_ms=1.0,
        index_build_ms=2.0,
        baseline_query_ms=3.0,
        bm25_query_ms=4.0,
        fusion_ms=5.0,
        total_retrieval_ms=20.0,
    )
    assert diag.total_retrieval_ms >= diag.baseline_query_ms
    assert diag.total_retrieval_ms >= diag.bm25_query_ms
    assert diag.total_retrieval_ms >= diag.fusion_ms


def test_diagnostics_no_duplicate_semantics() -> None:
    """corpus_build_ms replaces repository_scan_ms + chunk_build_ms (no duplicates)."""
    from springfix_agent.retrieval.models import RetrievalDiagnostics

    diag = RetrievalDiagnostics()
    # These fields should NOT exist (they had duplicate semantics).
    assert not hasattr(diag, "repository_scan_ms")
    assert not hasattr(diag, "chunk_build_ms")
    # corpus_build_ms should exist as the replacement.
    assert hasattr(diag, "corpus_build_ms")
