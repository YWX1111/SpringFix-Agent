"""Deterministic code chunker for M3.

Java files: identifies class / interface / enum / record / constructor /
method / annotation blocks using regex declaration detection and brace-depth
scanning. Falls back to fixed-line windows when parsing fails.

Non-Java files (XML, YAML, Properties): fixed-line windows with overlap.

This is NOT a full AST parser. It handles common patterns and degrades
gracefully on edge cases.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from springfix_agent.retrieval.models import MAX_CHUNK_CONTENT_CHARS, CodeChunk
from springfix_agent.retrieval.tokenizer import tokenize_chunk_content

_LOGGER = logging.getLogger(__name__)

# ── Limits ──────────────────────────────────────────────────────────────
DEFAULT_CHUNK_MAX_LINES = 60
DEFAULT_CHUNK_MAX_CHARS = MAX_CHUNK_CONTENT_CHARS
DEFAULT_CHUNK_OVERLAP_LINES = 5
DEFAULT_WINDOW_LINES = 40
DEFAULT_WINDOW_OVERLAP = 5
MAX_FILE_BYTES = 200_000

# ── Java declaration patterns ──────────────────────────────────────────
_MODS = (
    r"(?:public|protected|private|abstract|final|static|synchronized|"
    r"native|default|strictfp|[ \t])*"
)

_DECL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "class",
        re.compile(
            rf"^{_MODS}(?:class)\s+(?P<name>[A-Z][A-Za-z0-9_]*)",
            re.MULTILINE,
        ),
    ),
    (
        "interface",
        re.compile(
            rf"^{_MODS}(?:interface)\s+(?P<name>[A-Z][A-Za-z0-9_]*)",
            re.MULTILINE,
        ),
    ),
    (
        "enum",
        re.compile(
            rf"^{_MODS}(?:enum)\s+(?P<name>[A-Z][A-Za-z0-9_]*)",
            re.MULTILINE,
        ),
    ),
    (
        "record",
        re.compile(
            rf"^{_MODS}(?:record)\s+(?P<name>[A-Z][A-Za-z0-9_]*)",
            re.MULTILINE,
        ),
    ),
    (
        "constructor",
        re.compile(
            rf"^{_MODS}(?P<name>[A-Z][A-Za-z0-9_]*)\s*\(",
            re.MULTILINE,
        ),
    ),
    (
        "method",
        re.compile(
            rf"^{_MODS}"
            r"(?:[A-Z][A-Za-z0-9_<>\[\],\s]*|[a-z][A-Za-z0-9_<>\[\],\s]*|void)\s+"
            r"(?P<name>[a-z][A-Za-z0-9_]*)\s*\(",
            re.MULTILINE,
        ),
    ),
]

_ANNOTATION_DECL_RE = re.compile(
    r"@(?P<name>[A-Z][A-Za-z0-9_]*)\s*(?:\(|$)",
    re.MULTILINE,
)

# Supported file extensions.
JAVA_EXTENSIONS = frozenset({".java"})
CONFIG_EXTENSIONS = frozenset({".xml", ".yml", ".yaml", ".properties"})
INDEXABLE_EXTENSIONS = JAVA_EXTENSIONS | CONFIG_EXTENSIONS | frozenset({".sql", ".json", ".toml", ".gradle"})

# ── Excluded directories (same as list_project_tree) ─────────────────────
EXCLUDED_DIRS: frozenset[str] = frozenset({
    ".git", "target", "build", "dist", "node_modules",
    ".idea", ".vscode", "__pycache__", ".mvn", ".gradle",
})


# ── Brace-depth scanner ─────────────────────────────────────────────────
def _find_block_end(lines: list[str], start_idx: int) -> int:
    """Scan from start_idx to find the matching closing brace (0-based index, inclusive).

    Handles string literals, char literals, line comments, and block comments
    to avoid counting braces inside them. Returns the last line index of the
    block, or len(lines) - 1 if no match found.
    """
    depth = 0
    found_open = False
    in_block_comment = False

    for i in range(start_idx, len(lines)):
        line = lines[i]
        j = 0
        while j < len(line):
            # Block comment state.
            if in_block_comment:
                if j + 1 < len(line) and line[j] == "*" and line[j + 1] == "/":
                    in_block_comment = False
                    j += 2
                    continue
                j += 1
                continue

            ch = line[j]

            # Start of block comment.
            if j + 1 < len(line) and ch == "/" and line[j + 1] == "*":
                in_block_comment = True
                j += 2
                continue

            # Line comment — skip rest of line.
            if j + 1 < len(line) and ch == "/" and line[j + 1] == "/":
                break

            # String literal.
            if ch == '"':
                j += 1
                while j < len(line):
                    if line[j] == "\\":
                        j += 2
                        continue
                    if line[j] == '"':
                        j += 1
                        break
                    j += 1
                continue

            # Char literal.
            if ch == "'":
                j += 1
                while j < len(line):
                    if line[j] == "\\":
                        j += 2
                        continue
                    if line[j] == "'":
                        j += 1
                        break
                    j += 1
                continue

            if ch == "{":
                depth += 1
                found_open = True
            elif ch == "}":
                depth -= 1
                if found_open and depth == 0:
                    return i

            j += 1

    return len(lines) - 1


# ── Annotation grouping ─────────────────────────────────────────────────
def _annotation_start_line(lines: list[str], decl_idx: int) -> int:
    """Walk backwards from decl_idx to collect consecutive annotation lines."""
    start = decl_idx
    for i in range(decl_idx - 1, max(decl_idx - 10, -1), -1):
        stripped = lines[i].strip()
        if stripped.startswith("@") or stripped == "" or stripped.startswith("*") or stripped.startswith("//"):
            start = i
        else:
            break
    return start


# ── Java chunker ─────────────────────────────────────────────────────────
def _chunk_java(
    rel_path: str,
    content: str,
    *,
    max_lines: int,
    max_chars: int,
    overlap_lines: int,
) -> list[CodeChunk]:
    """Parse a Java file into CodeChunks. Falls back to file_window on failure."""
    lines = content.splitlines()
    if not lines:
        return []

    chunks: list[CodeChunk] = []
    used_ranges: list[tuple[int, int]] = []  # track covered line ranges

    try:
        for chunk_type, pattern in _DECL_PATTERNS:
            for m in pattern.finditer(content):
                name = m.group("name")
                # Convert match offset to 0-based line index.
                line_idx = content.count("\n", 0, m.start())
                ann_start = _annotation_start_line(lines, line_idx)
                block_end_idx = _find_block_end(lines, line_idx)

                # 1-based line numbers.
                start_line = ann_start + 1
                end_line = block_end_idx + 1
                chunk_lines = end_line - start_line + 1

                if chunk_lines < 2 and chunk_type not in ("method", "constructor"):
                    continue

                # Skip if this range is entirely inside an already-captured block.
                overlaps = False
                for us, ue in used_ranges:
                    if start_line >= us and end_line <= ue and chunk_type in ("method", "constructor"):
                        overlaps = True
                        break
                if overlaps and chunk_type in ("method", "constructor"):
                    # Methods inside a class are fine; only skip exact duplicates.
                    pass

                body = "\n".join(lines[ann_start:block_end_idx + 1])

                # Handle oversized blocks by splitting into windows.
                if chunk_lines > max_lines or len(body) > max_chars:
                    sub_chunks = _split_oversized(
                        rel_path=rel_path,
                        lines=lines,
                        start_idx=ann_start,
                        end_idx=block_end_idx,
                        chunk_type=chunk_type,
                        symbol_name=name,
                        parent_symbol=None,
                        max_lines=max_lines,
                        max_chars=max_chars,
                        overlap_lines=overlap_lines,
                    )
                    chunks.extend(sub_chunks)
                else:
                    truncated_body = body[:max_chars]
                    tokens = tokenize_chunk_content(truncated_body)
                    chunk_id = CodeChunk.make_chunk_id(
                        rel_path, chunk_type, start_line, end_line, name,
                    )
                    chunks.append(CodeChunk(
                        chunk_id=chunk_id,
                        file=rel_path,
                        language="java",
                        chunk_type=chunk_type,  # type: ignore[arg-type]
                        symbol_name=name,
                        parent_symbol=None,
                        start_line=start_line,
                        end_line=end_line,
                        content=truncated_body,
                        tokens=tokens,
                    ))

                used_ranges.append((start_line, end_line))

    except Exception:  # noqa: BLE001
        _LOGGER.debug("Java chunking failed for %s, falling back to windows", rel_path)
        return _chunk_windows(
            rel_path=rel_path,
            lines=lines,
            language="java",
            chunk_type="file_window",
            max_lines=max_lines,
            max_chars=max_chars,
            overlap_lines=overlap_lines,
        )

    if not chunks:
        return _chunk_windows(
            rel_path=rel_path,
            lines=lines,
            language="java",
            chunk_type="file_window",
            max_lines=max_lines,
            max_chars=max_chars,
            overlap_lines=overlap_lines,
        )

    return chunks


def _split_oversized(
    *,
    rel_path: str,
    lines: list[str],
    start_idx: int,
    end_idx: int,
    chunk_type: str,
    symbol_name: str | None,
    parent_symbol: str | None,
    max_lines: int,
    max_chars: int,
    overlap_lines: int,
) -> list[CodeChunk]:
    """Split an oversized block into overlapping sub-windows."""
    result: list[CodeChunk] = []
    cursor = start_idx
    window_num = 0

    while cursor <= end_idx:
        win_end = min(cursor + max_lines - 1, end_idx)
        body = "\n".join(lines[cursor:win_end + 1])

        if len(body) > max_chars:
            # Trim by chars at a line boundary.
            cut = max_chars
            last_nl = body.rfind("\n", 0, cut)
            if last_nl > 0:
                body = body[:last_nl]
                trimmed_lines = body.count("\n") + 1
                win_end = cursor + trimmed_lines - 1

        start_line = cursor + 1
        end_line = win_end + 1
        tokens = tokenize_chunk_content(body)
        chunk_id = CodeChunk.make_chunk_id(
            rel_path, chunk_type, start_line, end_line,
            f"{symbol_name or ''}_w{window_num}",
        )
        result.append(CodeChunk(
            chunk_id=chunk_id,
            file=rel_path,
            language="java",
            chunk_type=chunk_type,  # type: ignore[arg-type]
            symbol_name=symbol_name,
            parent_symbol=parent_symbol,
            start_line=start_line,
            end_line=end_line,
            content=body,
            tokens=tokens,
        ))
        window_num += 1

        if win_end >= end_idx:
            break
        cursor = win_end + 1 - overlap_lines
        if cursor <= win_end - max_lines + 1:
            cursor = win_end + 1

    return result


# ── Window chunker (non-Java or fallback) ──────────────────────────────
def _chunk_windows(
    *,
    rel_path: str,
    lines: list[str],
    language: str,
    chunk_type: str,
    max_lines: int,
    max_chars: int,
    overlap_lines: int,
) -> list[CodeChunk]:
    """Create fixed-size overlapping windows from a list of lines."""
    if not lines:
        return []

    window_size = min(DEFAULT_WINDOW_LINES, max_lines)
    overlap = min(DEFAULT_WINDOW_OVERLAP, overlap_lines)
    result: list[CodeChunk] = []
    cursor = 0

    while cursor < len(lines):
        win_end = min(cursor + window_size, len(lines))
        body = "\n".join(lines[cursor:win_end])

        if len(body) > max_chars:
            cut = max_chars
            last_nl = body.rfind("\n", 0, cut)
            body = body[:last_nl] if last_nl > 0 else body[:max_chars]

        start_line = cursor + 1
        end_line = win_end
        tokens = tokenize_chunk_content(body)
        chunk_id = CodeChunk.make_chunk_id(rel_path, chunk_type, start_line, end_line)

        lang = language if language else _detect_language(rel_path)
        ct = chunk_type if chunk_type in ("config_block", "file_window") else "file_window"
        result.append(CodeChunk(
            chunk_id=chunk_id,
            file=rel_path,
            language=lang,
            chunk_type=ct,  # type: ignore[arg-type]
            symbol_name=None,
            parent_symbol=None,
            start_line=start_line,
            end_line=end_line,
            content=body,
            tokens=tokens,
        ))

        if win_end >= len(lines):
            break
        cursor = win_end - overlap
        if cursor <= (win_end - window_size):
            cursor = win_end

    return result


def _detect_language(rel_path: str) -> str:
    """Detect language from file extension."""
    if rel_path.endswith(".java"):
        return "java"
    if rel_path.endswith(".xml"):
        return "xml"
    if rel_path.endswith((".yml", ".yaml")):
        return "yaml"
    if rel_path.endswith(".properties"):
        return "properties"
    if rel_path.endswith(".sql"):
        return "sql"
    return "text"


# ── Public API ──────────────────────────────────────────────────────────
def chunk_file(
    repo_path: Path,
    rel_path: str,
    *,
    max_lines: int = DEFAULT_CHUNK_MAX_LINES,
    max_chars: int = DEFAULT_CHUNK_MAX_CHARS,
    overlap_lines: int = DEFAULT_CHUNK_OVERLAP_LINES,
    max_file_bytes: int = MAX_FILE_BYTES,
) -> tuple[list[CodeChunk], list[str]]:
    """Read and chunk a single file. Returns (chunks, warnings).

    ``repo_path`` is the absolute repository root; ``rel_path`` is the
    POSIX relative path. The file must exist and be within repo_path.
    """
    warnings: list[str] = []
    abs_path = repo_path / rel_path

    try:
        size = abs_path.stat().st_size
    except OSError as e:
        return [], [f"stat failed for {rel_path}: {e}"]

    if size > max_file_bytes:
        warnings.append(f"file {rel_path} exceeds {max_file_bytes} bytes, truncated")
        try:
            raw = abs_path.read_text(encoding="utf-8")[:max_file_bytes]
        except (OSError, UnicodeDecodeError) as e:
            return [], [f"read failed for {rel_path}: {e}"]
    else:
        try:
            raw = abs_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            return [], [f"read failed for {rel_path}: {e}"]

    language = _detect_language(rel_path)

    if language == "java":
        chunks = _chunk_java(
            rel_path, raw,
            max_lines=max_lines,
            max_chars=max_chars,
            overlap_lines=overlap_lines,
        )
    else:
        lines = raw.splitlines()
        ct = "config_block" if rel_path.endswith(tuple(CONFIG_EXTENSIONS)) else "file_window"
        chunks = _chunk_windows(
            rel_path=rel_path,
            lines=lines,
            language=language,
            chunk_type=ct,
            max_lines=max_lines,
            max_chars=max_chars,
            overlap_lines=overlap_lines,
        )

    return chunks, warnings


def chunk_repository(
    repo_path: Path,
    *,
    max_files: int = 200,
    max_chunks: int = 1000,
    max_lines: int = DEFAULT_CHUNK_MAX_LINES,
    max_chars: int = DEFAULT_CHUNK_MAX_CHARS,
    overlap_lines: int = DEFAULT_CHUNK_OVERLAP_LINES,
    max_file_bytes: int = MAX_FILE_BYTES,
) -> tuple[list[CodeChunk], list[str], bool]:
    """Scan repository and chunk all indexable files.

    Returns (chunks, warnings, truncated).
    """
    import os

    all_chunks: list[CodeChunk] = []
    all_warnings: list[str] = []
    truncated = False
    files_scanned = 0

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = sorted(
            d for d in dirs
            if d not in EXCLUDED_DIRS and not d.startswith(".")
        )
        for fname in sorted(files):
            ext = Path(fname).suffix
            if ext not in INDEXABLE_EXTENSIONS:
                continue

            abs_path = Path(root) / fname
            try:
                rel = abs_path.relative_to(repo_path).as_posix()
            except ValueError:
                continue

            files_scanned += 1
            if files_scanned > max_files:
                truncated = True
                all_warnings.append(f"max_files={max_files} reached, truncating")
                return all_chunks, all_warnings, truncated

            file_chunks, file_warnings = chunk_file(
                repo_path, rel,
                max_lines=max_lines,
                max_chars=max_chars,
                overlap_lines=overlap_lines,
                max_file_bytes=max_file_bytes,
            )
            all_warnings.extend(file_warnings)
            all_chunks.extend(file_chunks)

            if len(all_chunks) > max_chunks:
                truncated = True
                all_warnings.append(f"max_chunks={max_chunks} reached, truncating")
                all_chunks = all_chunks[:max_chunks]
                return all_chunks, all_warnings, truncated

    return all_chunks, all_warnings, truncated
