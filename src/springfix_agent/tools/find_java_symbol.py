"""find_java_symbol tool.

M1 implementation: regex-based exact symbol matching via _java_patterns.
M3 will swap in Tree-sitter AST parsing without changing the public API.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TypedDict

from springfix_agent.tools._java_patterns import match_symbol
from springfix_agent.tools.base import Tool, ToolContext, ToolResult
from springfix_agent.tools.list_project_tree import DEFAULT_EXCLUDE_DIRS

DEFAULT_MAX_RESULTS = 50
SUPPORTED_TYPES: frozenset[str] = frozenset(
    {"class", "interface", "enum", "record", "method", "annotation", "any"}
)


class SymbolMatch(TypedDict):
    """A single Java symbol match record."""

    file: str
    line: int
    symbol_type: str
    context: str


def _ok(
    matches: list[SymbolMatch],
    name: str,
    stype: str,
    *,
    truncated: bool,
) -> ToolResult:
    summary = f"symbol={name}, type={stype}, matches={len(matches)}, truncated={truncated}"
    return ToolResult(
        status="success",
        data={"matches": list(matches), "truncated": truncated},
        result_summary=summary,
        error=None,
    )


class FindJavaSymbolTool(Tool):
    """Find Java symbols by exact name across .java files in the repository."""

    name = "find_java_symbol"
    description = (
        "Find Java symbols by exact name (class, interface, enum, record, "
        "method, or annotation). Returns matches with file path, line number, "
        "symbol type, and short context. Empty list when no match. M1 uses regex; "
        "M3 will swap in Tree-sitter."
    )

    def run(self, params: dict[str, object], ctx: ToolContext) -> ToolResult:
        name_raw = params.get("symbol_name")
        if not isinstance(name_raw, str) or not name_raw:
            return ToolResult(
                status="error",
                data={"matches": []},
                result_summary="",
                error="symbol_name is required",
            )
        symbol_type = str(params.get("symbol_type", "any")).lower()
        if symbol_type not in SUPPORTED_TYPES:
            return ToolResult(
                status="error",
                data={"matches": []},
                result_summary="",
                error=f"unsupported symbol_type: {symbol_type}",
            )
        max_results_raw = params.get("max_results", DEFAULT_MAX_RESULTS)
        max_results = (
            int(max_results_raw) if isinstance(max_results_raw, (int, float)) else DEFAULT_MAX_RESULTS
        )

        repo = ctx["repository_path"]
        matches: list[SymbolMatch] = []

        for path in _iter_java_files(repo):
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            rel = path.relative_to(repo).as_posix()
            for line_no, stype, context in match_symbol(name_raw, symbol_type, content):
                matches.append(
                    SymbolMatch(
                        file=rel,
                        line=line_no,
                        symbol_type=stype,
                        context=context.strip()[:200],
                    )
                )
                if len(matches) >= max_results:
                    matches.sort(key=lambda m: (m["file"], m["line"]))
                    return _ok(matches, name_raw, symbol_type, truncated=True)

        matches.sort(key=lambda m: (m["file"], m["line"]))
        return _ok(matches, name_raw, symbol_type, truncated=False)


def _iter_java_files(repo: Path) -> list[Path]:
    """Return .java files under repo, excluding build/cache dirs. Sorted."""
    out: list[Path] = []
    for root, dirs, files in os.walk(repo):
        dirs[:] = sorted(
            d for d in dirs if d not in DEFAULT_EXCLUDE_DIRS and not d.startswith(".")
        )
        for fname in sorted(files):
            if fname.endswith(".java"):
                out.append(Path(root) / fname)
    return out
