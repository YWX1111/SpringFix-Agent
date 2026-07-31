"""BM25 retriever using rank_bm25.BM25Okapi over code chunks.

Builds an in-memory BM25 index from CodeChunk.tokens and searches it
with normalized query tokens. This is lexical (keyword) retrieval,
NOT semantic search.

The index is built per-task and not persisted across tasks.
"""

from __future__ import annotations

import time
from typing import Any

from springfix_agent.retrieval.models import CodeChunk, RetrievalHit


def _elapsed(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


class BM25Retriever:
    """BM25Okapi retriever over pre-tokenized code chunks.

    Construction takes the chunk corpus; search returns RetrievalHits
    with BM25 scores. All scores come from real BM25Okapi computation.
    """

    def __init__(self, chunks: list[CodeChunk]) -> None:
        self._chunks = list(chunks)
        self._index: Any = None
        self._build_duration_ms = 0
        self._build()

    def _build(self) -> None:
        """Build BM25 index from chunk tokens."""
        t0 = time.monotonic()
        if not self._chunks:
            self._index = None
            self._build_duration_ms = _elapsed(t0)
            return

        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            self._index = None
            self._build_duration_ms = _elapsed(t0)
            return

        corpus = [c.tokens for c in self._chunks]
        # Filter empty token lists — BM25Okapi requires non-empty docs.
        valid_indices = [i for i, tokens in enumerate(corpus) if tokens]
        if not valid_indices:
            self._index = None
            self._build_duration_ms = _elapsed(t0)
            return

        valid_corpus = [corpus[i] for i in valid_indices]
        self._valid_chunks = [self._chunks[i] for i in valid_indices]
        self._index = BM25Okapi(valid_corpus)
        self._build_duration_ms = _elapsed(t0)

    @property
    def build_duration_ms(self) -> int:
        return self._build_duration_ms

    @property
    def indexed_count(self) -> int:
        if self._index is None:
            return 0
        return len(self._valid_chunks)

    def search(
        self,
        query_tokens: list[str],
        *,
        top_k: int = 10,
    ) -> tuple[list[RetrievalHit], int]:
        """Search the BM25 index with query tokens.

        Returns (hits_sorted_by_score_desc, duration_ms).
        Empty query or empty index returns ([], duration).
        """
        t0 = time.monotonic()
        if self._index is None or not query_tokens:
            return [], _elapsed(t0)

        scores = self._index.get_scores(query_tokens)

        # Pair scores with chunks, filter zero scores.
        scored: list[tuple[float, int]] = []
        for idx, score in enumerate(scores):
            if score > 0:
                scored.append((score, idx))

        # Sort by score desc, then file asc, then start_line asc, then chunk_id.
        scored.sort(
            key=lambda pair: (
                -pair[0],
                self._valid_chunks[pair[1]].file,
                self._valid_chunks[pair[1]].start_line,
                self._valid_chunks[pair[1]].chunk_id,
            )
        )

        hits: list[RetrievalHit] = []
        for rank, (score, idx) in enumerate(scored[:top_k], start=1):
            chunk = self._valid_chunks[idx]
            # Determine matched terms: intersection of query tokens and chunk tokens.
            chunk_token_set = set(chunk.tokens)
            matched = [t for t in query_tokens if t in chunk_token_set]

            hit = RetrievalHit(
                chunk=chunk,
                fused_score=float(score),
                sources=["bm25"],
                source_ranks={"bm25": rank},
                matched_terms=matched[:50],
            )
            hits.append(hit)

        return hits, _elapsed(t0)
