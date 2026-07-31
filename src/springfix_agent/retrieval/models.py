"""Shared data models for the M3 retrieval module.

All models use Pydantic BaseModel for validation and serialization.
CodeChunk carries real file paths (relative to repository) and real line numbers.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, Field

MAX_CHUNK_CONTENT_CHARS = 4000
MAX_CHUNK_TOKENS = 500
MAX_HIT_MATCHED_TERMS = 50


class CodeChunk(BaseModel):
    """A single code chunk extracted from the repository.

    ``file`` is always a POSIX relative path from the repository root.
    ``start_line`` and ``end_line`` are 1-based inclusive.
    ``chunk_id`` is stable and reproducible for identical repository content.
    """

    chunk_id: str
    file: str
    language: str
    chunk_type: Literal[
        "class",
        "interface",
        "enum",
        "record",
        "method",
        "constructor",
        "annotation_block",
        "config_block",
        "file_window",
    ]
    symbol_name: str | None = None
    parent_symbol: str | None = None
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content: str = Field(max_length=MAX_CHUNK_CONTENT_CHARS)
    tokens: list[str] = Field(default_factory=list)

    @staticmethod
    def make_chunk_id(
        file: str,
        chunk_type: str,
        start_line: int,
        end_line: int,
        symbol_name: str | None = None,
    ) -> str:
        """Build a stable, reproducible chunk_id without absolute paths."""
        raw = f"{file}:{chunk_type}:{symbol_name or ''}:{start_line}:{end_line}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class RetrievalHit(BaseModel):
    """A single fused retrieval result combining multiple search channels."""

    chunk: CodeChunk
    fused_score: float
    sources: list[str] = Field(default_factory=list)
    source_ranks: dict[str, int] = Field(default_factory=dict)
    matched_terms: list[str] = Field(default_factory=list)


class RetrievalQuery(BaseModel):
    """Structured query built from issue description, LLM outputs, and symbols."""

    raw_text: str
    normalized_terms: list[str] = Field(default_factory=list)
    exact_symbols: list[str] = Field(default_factory=list)
    exception_types: list[str] = Field(default_factory=list)
    annotations: list[str] = Field(default_factory=list)


class RetrievalDiagnostics(BaseModel):
    """Timing, scale, and fallback metadata for a single retrieval run.

    All timing fields use milliseconds with at least 3 decimal places
    of precision (measured via ``time.perf_counter`` internally).

    Timing pipeline (no duplicate semantics):
        corpus_build_ms  — file discovery + file read + chunk extraction
        index_build_ms   — BM25 index construction from chunks
        baseline_query_ms — baseline lexical search duration
        bm25_query_ms    — BM25 search duration
        symbol_query_ms  — symbol lookup duration
        fusion_ms        — RRF fusion + chunk dedup duration
        total_retrieval_ms — wall-clock total (includes orchestration)
    """

    files_scanned: int = 0
    chunks_created: int = 0
    chunks_indexed: int = 0
    # Primary phase timings (ms, float for sub-ms precision).
    corpus_build_ms: float = 0.0
    index_build_ms: float = 0.0
    baseline_query_ms: float = 0.0
    bm25_query_ms: float = 0.0
    symbol_query_ms: float = 0.0
    fusion_ms: float = 0.0
    total_retrieval_ms: float = 0.0
    # Legacy int fields for backward compatibility (deprecated; use float fields).
    index_build_duration_ms: int = 0
    baseline_duration_ms: int = 0
    bm25_duration_ms: int = 0
    symbol_duration_ms: int = 0
    fusion_duration_ms: int = 0
    truncated: bool = False
    fallback_used: bool = False
    query_terms_used: int = 0
    query_terms_discarded: int = 0
    baseline_hits: int = 0
    bm25_hits: int = 0
    symbol_hits: int = 0
    fusion_hits: int = 0
    warnings: list[str] = Field(default_factory=list)
