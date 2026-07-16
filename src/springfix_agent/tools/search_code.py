"""search_code tool.

M1 implementation: deterministic lexical scoring (not BM25, not multi-term AND).

Scoring rules:
    - Spring annotation match (e.g. @Transactional): +2.5
    - Exception class match (e.g. NullPointerException): +3.0
    - Class name match (UpperCamelCase): +2.0
    - Method name match (lowerCamelCase): +2.0
    - Plain keyword match: +1.0

Returns Top K by score desc, then file path asc, then line number asc.
No matches returns an empty hits list (never synthesizes candidates).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from springfix_agent.tools.base import Tool, ToolContext, ToolResult
from springfix_agent.tools.list_project_tree import DEFAULT_EXCLUDE_DIRS

DEFAULT_EXTENSIONS: tuple[str, ...] = (".java", ".xml", ".yml", ".yaml", ".properties")
DEFAULT_TOP_K = 10
MAX_HITS_PER_FILE = 100

_ANNOTATION_RE = re.compile(r"^@[A-Z][A-Za-z0-9_]*$")
_EXCEPTION_RE = re.compile(r"^[A-Z][A-Za-z0-9_]*Exception$")
_UPPER_CAMEL_RE = re.compile(r"^[A-Z][A-Za-z0-9_]*$")
# Must contain at least one uppercase after the initial lowercase, so plain all-lowercase
# identifiers (e.g. "hello", "main", "data") are classified as plain, not method.
_LOWER_CAMEL_RE = re.compile(r"^[a-z][a-zA-Z0-9_]*[A-Z][a-zA-Z0-9_]*$")


class SearchCodeTool(Tool):
    """Lexical relevance search across .java/.xml/.yml/.yaml/.properties files."""

    name = "search_code"
    description = (
        "Lexical relevance search across source files in the repository. "
        "Scores matches by term type (annotation > exception > class/method > keyword). "
        "Returns Top K by score. Not a semantic search."
    )

    def run(self, params: dict[str, object], ctx: ToolContext) -> ToolResult:
        query_raw = params.get("query")
        if not isinstance(query_raw, str) or not query_raw.strip():
            return ToolResult(
                status="error",
                data={"hits": []},
                result_summary="query is empty",
                error="query must be a non-empty string",
            )
        top_k_raw = params.get("top_k", DEFAULT_TOP_K)
        top_k = (
            int(top_k_raw)
            if isinstance(top_k_raw, (int, float)) and not isinstance(top_k_raw, bool)
            else DEFAULT_TOP_K
        )
        exts_raw = params.get("file_extensions", DEFAULT_EXTENSIONS)
        if isinstance(exts_raw, list):
            extensions = tuple(str(e) for e in exts_raw)
        else:
            extensions = (
                tuple(exts_raw) if isinstance(exts_raw, tuple) else DEFAULT_EXTENSIONS
            )

        terms = _classify_terms(query_raw)
        if not terms:
            return ToolResult(
                status="success",
                data={"hits": []},
                result_summary="no usable terms in query",
                error=None,
            )

        repo = ctx["repository_path"]
        hits = _scan(repo, terms, extensions)

        hits.sort(key=lambda h: (-h["score"], h["file"], h["line"]))
        top = hits[:top_k]

        summary = (
            f"query_terms={len(terms)}, total_hits={len(hits)}, top_k_returned={len(top)}"
        )
        return ToolResult(
            status="success",
            data={"hits": top},
            result_summary=summary,
            error=None,
        )


def _classify_terms(query: str) -> dict[str, set[str]]:
    """Split query and classify terms into buckets by lexical shape.

    Returns dict with keys: 'plain', 'class', 'method', 'exception', 'annotation'.
    Each value is a set of unique terms. A term can appear in multiple buckets
    only if it matches multiple patterns (rare for valid identifiers).
    """
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


def _scan(
    repo: Path,
    terms: dict[str, set[str]],
    extensions: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Scan all matching files; return a list of hit dicts."""
    hits: list[dict[str, Any]] = []
    for path in _iter_repo_files(repo, extensions):
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(repo).as_posix()
        hits_per_file = 0
        for line_no, line in enumerate(content.splitlines(), start=1):
            if hits_per_file >= MAX_HITS_PER_FILE:
                break
            score, matched = _score_line(line, terms)
            if score <= 0:
                continue
            hits.append(
                {
                    "file": rel,
                    "line": line_no,
                    "content": line.strip()[:200],
                    "context": line.strip()[:200],
                    "score": score,
                    "matched_terms": sorted(matched),
                }
            )
            hits_per_file += 1
    return hits


def _score_line(
    line: str,
    terms: dict[str, set[str]],
) -> tuple[float, set[str]]:
    """Return (score, matched_terms) for a single line."""
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


def _iter_repo_files(repo: Path, extensions: tuple[str, ...]) -> list[Path]:
    """Return repository files matching extensions, excluding build/cache dirs. Sorted."""
    import os

    out: list[Path] = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = sorted(
            d for d in dirs if d not in DEFAULT_EXCLUDE_DIRS and not d.startswith(".")
        )
        for fname in sorted(files):
            if fname.endswith(extensions):
                out.append(Path(root) / fname)
    return out
