"""Baseline lexical retriever wrapping M1's search_code scoring algorithm.

This module wraps the existing M1 line-level scoring logic and converts
results into the unified CodeChunk / RetrievalHit model. It serves as:

1. A backward-compatible fallback when BM25 fails.
2. A control baseline for M3 retrieval evaluation.
3. One channel in the RRF fusion pipeline.

The M1 scoring algorithm is preserved without modification.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from springfix_agent.retrieval.chunker import EXCLUDED_DIRS
from springfix_agent.retrieval.models import CodeChunk, RetrievalHit
from springfix_agent.retrieval.tokenizer import tokenize_chunk_content

DEFAULT_EXTENSIONS: tuple[str, ...] = (".java", ".xml", ".yml", ".yaml", ".properties")
MAX_HITS_PER_FILE = 100

_ANNOTATION_RE = re.compile(r"^@[A-Z][A-Za-z0-9_]*$")
_EXCEPTION_RE = re.compile(r"^[A-Z][A-Za-z0-9_]*Exception$")
_UPPER_CAMEL_RE = re.compile(r"^[A-Z][A-Za-z0-9_]*$")
_LOWER_CAMEL_RE = re.compile(r"^[a-z][a-zA-Z0-9_]*[A-Z][a-zA-Z0-9_]*$")


def _classify_terms(query: str) -> dict[str, set[str]]:
    """Classify query tokens by lexical shape (M1 algorithm)."""
    tokens = [t for t in re.split(r"\s+", query.strip()) if t]
    buckets: dict[str, set[str]] = {
        "plain": set(),
        "class": set(),
        "method": set(),
        "exception": set(),
        "annotation": set(),
    }
    for tok in tokens:
        if _ANNOTATION_RE.match(tok):
            buckets["annotation"].add(tok)
        elif _EXCEPTION_RE.match(tok):
            buckets["exception"].add(tok)
        elif _UPPER_CAMEL_RE.match(tok):
            buckets["class"].add(tok)
        elif _LOWER_CAMEL_RE.match(tok):
            buckets["method"].add(tok)
        else:
            if 2 <= len(tok) <= 64:
                buckets["plain"].add(tok)
    return buckets


def _score_line(line: str, terms: dict[str, set[str]]) -> tuple[float, set[str]]:
    """Score a single line against classified terms (M1 algorithm)."""
    score = 0.0
    matched: set[str] = set()
    for term in terms["plain"]:
        if term in line:
            score += 1.0
            matched.add(term)
    for term in terms["class"]:
        if term in line:
            score += 2.0
            matched.add(term)
    for term in terms["method"]:
        if term in line:
            score += 2.0
            matched.add(term)
    for term in terms["exception"]:
        if term in line:
            score += 3.0
            matched.add(term)
    for term in terms["annotation"]:
        bare = term[1:]
        if bare in line:
            score += 2.5
            matched.add(term)
    return score, matched


class BaselineLexicalRetriever:
    """M1 line-level lexical scoring wrapped as a retriever.

    Preserves the exact M1 scoring weights and behavior. Used as both
    a standalone fallback and one channel in the hybrid fusion pipeline.
    """

    def search(
        self,
        repo_path: Path,
        query: str,
        *,
        top_k: int = 10,
        extensions: tuple[str, ...] = DEFAULT_EXTENSIONS,
    ) -> tuple[list[RetrievalHit], int]:
        """Run baseline lexical search, returning (hits, duration_ms).

        Results are grouped by file: the highest-scoring line per file
        determines file ranking, and the file's content is returned as
        a single CodeChunk.
        """
        t0 = time.monotonic()
        terms = _classify_terms(query)
        if not any(terms.values()):
            return [], _elapsed(t0)

        file_scores: dict[str, list[tuple[int, float, set[str], str]]] = {}

        for path in _iter_repo_files(repo_path, extensions):
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            rel = path.relative_to(repo_path).as_posix()
            hits_in_file = 0
            for line_no, line in enumerate(content.splitlines(), start=1):
                if hits_in_file >= MAX_HITS_PER_FILE:
                    break
                score, matched = _score_line(line, terms)
                if score > 0:
                    file_scores.setdefault(rel, []).append(
                        (line_no, score, matched, line.strip()[:200])
                    )
                    hits_in_file += 1

        # Aggregate per file: total score, best line, all matched terms.
        hits: list[RetrievalHit] = []
        for rel, line_hits in file_scores.items():
            total_score = sum(s for _, s, _, _ in line_hits)
            all_matched: set[str] = set()
            for _, _, m, _ in line_hits:
                all_matched |= m
            best_line = min(line_hits, key=lambda h: h[0])
            first_line = best_line[0]
            last_line = max(h[0] for h in line_hits)

            # Read the file to create a proper chunk.
            abs_path = repo_path / rel
            try:
                full_content = abs_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            lines_list = full_content.splitlines()
            start_idx = max(0, first_line - 1)
            end_idx = min(len(lines_list), last_line)
            chunk_content = "\n".join(lines_list[start_idx:end_idx])
            if len(chunk_content) > 4000:
                chunk_content = chunk_content[:4000]
                last_nl = chunk_content.rfind("\n")
                if last_nl > 0:
                    chunk_content = chunk_content[:last_nl]

            tokens = tokenize_chunk_content(chunk_content)
            chunk_id = CodeChunk.make_chunk_id(
                rel, "file_window", first_line, end_idx,
            )
            chunk = CodeChunk(
                chunk_id=chunk_id,
                file=rel,
                language=_detect_lang(rel),
                chunk_type="file_window",
                symbol_name=None,
                parent_symbol=None,
                start_line=first_line,
                end_line=end_idx,
                content=chunk_content,
                tokens=tokens,
            )
            hits.append(RetrievalHit(
                chunk=chunk,
                fused_score=total_score,
                sources=["baseline"],
                source_ranks={},
                matched_terms=sorted(all_matched),
            ))

        hits.sort(key=lambda h: (-h.fused_score, h.chunk.file, h.chunk.start_line))
        result = hits[:top_k]
        for rank, hit in enumerate(result, start=1):
            hit.source_ranks["baseline"] = rank

        return result, _elapsed(t0)


def _iter_repo_files(repo: Path, extensions: tuple[str, ...]) -> list[Path]:
    """Return repository files matching extensions, excluding build/cache dirs."""
    import os

    out: list[Path] = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = sorted(
            d for d in dirs
            if d not in EXCLUDED_DIRS and not d.startswith(".")
        )
        for fname in sorted(files):
            if fname.endswith(extensions):
                out.append(Path(root) / fname)
    return out


def _detect_lang(rel_path: str) -> str:
    if rel_path.endswith(".java"):
        return "java"
    if rel_path.endswith(".xml"):
        return "xml"
    if rel_path.endswith((".yml", ".yaml")):
        return "yaml"
    if rel_path.endswith(".properties"):
        return "properties"
    return "text"


def _elapsed(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)
