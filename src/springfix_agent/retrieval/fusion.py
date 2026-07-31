"""Reciprocal Rank Fusion (RRF) for multi-channel retrieval results.

Combines Baseline, BM25, and Symbol retrieval results into a single
ranked list. Different retrievers produce incomparable raw scores, so
RRF uses rank positions instead:

    RRF_score(d) = \u03a3 weight_i / (k + rank_i)

where k is a smoothing constant (default 60) and weight_i is the
channel weight.

After RRF scoring, overlapping chunks (same file, overlapping line
ranges) are merged to avoid inflating ranks with duplicate content
from different chunking strategies.

References:
    Cormack, Clarke & Butt (2009). "Reciprocal Rank Fusion outperforms
    Condorcet and individual Rank Learning Methods."
"""

from __future__ import annotations

import time
from collections import defaultdict

from springfix_agent.retrieval.models import RetrievalHit

# Default RRF parameters — not claimed to be tuned.
DEFAULT_RRF_K = 60
DEFAULT_WEIGHT_BASELINE = 1.0
DEFAULT_WEIGHT_BM25 = 1.0
DEFAULT_WEIGHT_SYMBOL = 1.5  # Symbol matches are precise; give slightly more weight.

# Minimum overlap ratio for chunk deduplication.
_OVERLAP_THRESHOLD = 0.5


def _elapsed(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


def reciprocal_rank_fusion(
    channels: dict[str, list[RetrievalHit]],
    *,
    k: int = DEFAULT_RRF_K,
    weights: dict[str, float] | None = None,
    top_k: int = 10,
) -> tuple[list[RetrievalHit], int]:
    """Fuse multiple retrieval channels using Reciprocal Rank Fusion.

    Args:
        channels: Dict mapping channel name to its ranked hit list.
            Expected keys: "baseline", "bm25", "symbol" (any may be absent).
        k: RRF smoothing constant.
        weights: Per-channel weights. Missing keys default to 1.0.
        top_k: Maximum results to return.

    Returns:
        (fused_hits, duration_ms) sorted by RRF score descending.
    """
    t0 = time.monotonic()
    if weights is None:
        weights = {
            "baseline": DEFAULT_WEIGHT_BASELINE,
            "bm25": DEFAULT_WEIGHT_BM25,
            "symbol": DEFAULT_WEIGHT_SYMBOL,
        }

    # Accumulate RRF scores per chunk_id.
    rrf_scores: dict[str, float] = defaultdict(float)
    hit_by_chunk: dict[str, RetrievalHit] = {}
    sources_by_chunk: dict[str, list[str]] = defaultdict(list)
    ranks_by_chunk: dict[str, dict[str, int]] = defaultdict(dict)
    terms_by_chunk: dict[str, set[str]] = defaultdict(set)

    for channel_name, hits in channels.items():
        w = weights.get(channel_name, 1.0)
        for rank, hit in enumerate(hits, start=1):
            cid = hit.chunk.chunk_id
            rrf_scores[cid] += w / (k + rank)
            sources_by_chunk[cid].append(channel_name)
            ranks_by_chunk[cid][channel_name] = rank
            terms_by_chunk[cid].update(hit.matched_terms)

            # Keep the first (highest-ranked) hit per chunk as representative.
            if cid not in hit_by_chunk:
                hit_by_chunk[cid] = hit

    # Build fused results.
    fused: list[RetrievalHit] = []
    for cid, score in rrf_scores.items():
        base_hit = hit_by_chunk[cid]
        fused.append(RetrievalHit(
            chunk=base_hit.chunk,
            fused_score=score,
            sources=sources_by_chunk[cid],
            source_ranks=ranks_by_chunk[cid],
            matched_terms=sorted(terms_by_chunk[cid])[:50],
        ))

    # Stable sort: score desc, then file asc, then start_line asc, then chunk_id.
    fused.sort(
        key=lambda h: (
            -h.fused_score,
            h.chunk.file,
            h.chunk.start_line,
            h.chunk.chunk_id,
        )
    )

    # Merge overlapping chunks from same file to avoid rank inflation.
    fused = merge_overlapping_chunks(fused)

    result = fused[:top_k]
    return result, _elapsed(t0)


def _ranges_overlap(
    start1: int, end1: int, start2: int, end2: int,
) -> float:
    """Compute the overlap ratio between two line ranges.

    Returns the Jaccard-like overlap: intersection / min(length1, length2).
    """
    intersection = max(0, min(end1, end2) - max(start1, start2) + 1)
    min_len = min(end1 - start1 + 1, end2 - start2 + 1)
    if min_len <= 0:
        return 0.0
    return intersection / min_len


def merge_overlapping_chunks(
    hits: list[RetrievalHit],
    *,
    overlap_threshold: float = _OVERLAP_THRESHOLD,
) -> list[RetrievalHit]:
    """Merge RetrievalHits that cover overlapping regions of the same file.

    Two hits are considered overlapping if:
    - They are in the same file.
    - Their line ranges overlap by more than ``overlap_threshold`` of the
      shorter range.

    When merging:
    - The hit with the wider line range is kept as the representative.
    - Sources and source_ranks are combined.
    - Matched terms are combined.
    - The higher fused_score is preserved.

    This prevents the same code region from appearing multiple times
    due to different chunking strategies (file_window vs method vs class).
    """
    if len(hits) <= 1:
        return hits

    merged: list[RetrievalHit] = []
    consumed: set[int] = set()

    for i, hit_i in enumerate(hits):
        if i in consumed:
            continue

        best = hit_i
        for j in range(i + 1, len(hits)):
            if j in consumed:
                continue
            hit_j = hits[j]

            # Same file check.
            if best.chunk.file != hit_j.chunk.file:
                continue

            # Line range overlap check.
            ratio = _ranges_overlap(
                best.chunk.start_line, best.chunk.end_line,
                hit_j.chunk.start_line, hit_j.chunk.end_line,
            )
            if ratio < overlap_threshold:
                continue

            # Merge: keep the wider chunk, combine metadata.
            consumed.add(j)

            # Keep the chunk with more lines (more evidence).
            i_lines = best.chunk.end_line - best.chunk.start_line
            j_lines = hit_j.chunk.end_line - hit_j.chunk.start_line
            keep_chunk = hit_j.chunk if j_lines > i_lines else best.chunk

            # Combine sources (deduplicated, preserving order).
            combined_sources: list[str] = list(best.sources)
            for s in hit_j.sources:
                if s not in combined_sources:
                    combined_sources.append(s)

            # Combine source_ranks.
            combined_ranks = {**best.source_ranks, **hit_j.source_ranks}

            # Combine matched_terms.
            combined_terms: set[str] = set(best.matched_terms) | set(hit_j.matched_terms)

            # Keep the higher fused_score.
            combined_score = max(best.fused_score, hit_j.fused_score)

            best = RetrievalHit(
                chunk=keep_chunk,
                fused_score=combined_score,
                sources=combined_sources,
                source_ranks=combined_ranks,
                matched_terms=sorted(combined_terms)[:50],
            )

        merged.append(best)

    return merged
