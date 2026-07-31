"""Symbol-level retriever wrapping find_java_symbol.

Converts exact symbol matches into RetrievalHits with high priority
in the fusion pipeline. Symbol retrieval is precise but narrow; it
complements the broader BM25 and baseline channels.
"""

from __future__ import annotations

import time
from pathlib import Path

from springfix_agent.retrieval.models import CodeChunk, RetrievalHit
from springfix_agent.retrieval.tokenizer import tokenize_chunk_content
from springfix_agent.tools._java_patterns import match_symbol
from springfix_agent.tools.list_project_tree import DEFAULT_EXCLUDE_DIRS

SUPPORTED_SYMBOL_TYPES = ("class", "interface", "enum", "record", "method", "annotation")


def _elapsed(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


class SymbolRetriever:
    """Exact Java symbol lookup as a retrieval channel.

    Searches .java files for exact symbol declarations using the existing
    ``match_symbol`` regex patterns. Results are returned as RetrievalHits
    with the surrounding code block as the chunk content.
    """

    def search(
        self,
        repo_path: Path,
        symbols: list[str],
        *,
        max_results_per_symbol: int = 5,
        top_k: int = 10,
    ) -> tuple[list[RetrievalHit], int]:
        """Search for exact symbol declarations.

        Returns (hits, duration_ms).
        """
        t0 = time.monotonic()
        if not symbols:
            return [], _elapsed(t0)

        hits: list[RetrievalHit] = []
        seen_chunks: set[str] = set()

        for symbol in symbols:
            for java_path in _iter_java_files(repo_path):
                try:
                    content = java_path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue

                rel = java_path.relative_to(repo_path).as_posix()
                matches = match_symbol(symbol, "any", content)

                for line_no, stype, _context in matches:
                    lines = content.splitlines()
                    # Expand context: take surrounding block.
                    start_idx = max(0, line_no - 1)
                    end_idx = min(len(lines), line_no + 30)

                    # Try to find block end via brace scanning for method/class.
                    if stype in ("class", "interface", "enum", "record", "method"):
                        from springfix_agent.retrieval.chunker import _find_block_end
                        block_end = _find_block_end(lines, line_no - 1)
                        end_idx = min(block_end + 1, len(lines))

                    chunk_content = "\n".join(lines[start_idx:end_idx])
                    if len(chunk_content) > 4000:
                        chunk_content = chunk_content[:4000]
                        last_nl = chunk_content.rfind("\n")
                        if last_nl > 0:
                            chunk_content = chunk_content[:last_nl]

                    start_line = start_idx + 1
                    end_line = end_idx
                    chunk_id = CodeChunk.make_chunk_id(
                        rel, stype, start_line, end_line, symbol,
                    )

                    if chunk_id in seen_chunks:
                        continue
                    seen_chunks.add(chunk_id)

                    ct = _map_symbol_type(stype)
                    tokens = tokenize_chunk_content(chunk_content)
                    chunk = CodeChunk(
                        chunk_id=chunk_id,
                        file=rel,
                        language="java",
                        chunk_type=ct,  # type: ignore[arg-type]
                        symbol_name=symbol,
                        parent_symbol=None,
                        start_line=start_line,
                        end_line=end_line,
                        content=chunk_content,
                        tokens=tokens,
                    )
                    hits.append(RetrievalHit(
                        chunk=chunk,
                        fused_score=0.0,
                        sources=["symbol"],
                        source_ranks={},
                        matched_terms=[symbol],
                    ))

                    if len(hits) >= max_results_per_symbol * len(symbols):
                        break
                if len(hits) >= max_results_per_symbol * len(symbols):
                    break
            if len(hits) >= top_k * 2:
                break

        # Assign ranks.
        for rank, hit in enumerate(hits[:top_k], start=1):
            hit.source_ranks["symbol"] = rank

        return hits[:top_k], _elapsed(t0)


def _map_symbol_type(stype: str) -> str:
    """Map match_symbol output types to CodeChunk chunk_type values."""
    mapping = {
        "class": "class",
        "interface": "interface",
        "enum": "enum",
        "record": "record",
        "method": "method",
        "annotation": "annotation_block",
    }
    return mapping.get(stype, "file_window")


def _iter_java_files(repo: Path) -> list[Path]:
    """Return .java files under repo, excluding build/cache dirs."""
    import os

    out: list[Path] = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = sorted(
            d for d in dirs
            if d not in DEFAULT_EXCLUDE_DIRS and not d.startswith(".")
        )
        for fname in sorted(files):
            if fname.endswith(".java"):
                out.append(Path(root) / fname)
    return out
