"""read_file tool.

Reads a restricted file snippet from the repository sandbox. Enforces:
    - Only relative paths (no absolute paths)
    - Path canonicalization stays inside repository_path
    - Only whitelisted text extensions
    - UTF-8 decoding (reject non-UTF-8)
    - Max 60 lines and 4000 chars per snippet
"""

from __future__ import annotations

from springfix_agent.tools._path_safety import PathSafetyError, resolve_relative_path
from springfix_agent.tools.base import Tool, ToolContext, ToolResult

MAX_SNIPPET_LINES = 60
MAX_SNIPPET_CHARS = 4000

ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".java",
        ".xml",
        ".yml",
        ".yaml",
        ".properties",
        ".sql",
        ".txt",
        ".md",
        ".json",
        ".toml",
        ".gradle",
        ".gitignore",
    }
)


class ReadFileTool(Tool):
    """Read a file by relative path within the repository sandbox."""

    name = "read_file"
    description = (
        "Read a text file by relative path within the repository. Returns at "
        "most 60 lines and 4000 characters, with truncation flagging. Rejects "
        "absolute paths, path traversal, symlinks escaping the repository, "
        "and non-text extensions."
    )

    def run(self, params: dict[str, object], ctx: ToolContext) -> ToolResult:
        relative_raw = params.get("relative_path")
        if not isinstance(relative_raw, str) or not relative_raw:
            return ToolResult(
                status="error",
                data={},
                result_summary="",
                error="relative_path is required",
            )
        start_line_raw = params.get("start_line", 0)
        start_line = (
            int(start_line_raw)
            if isinstance(start_line_raw, (int, float)) and not isinstance(start_line_raw, bool)
            else 0
        )
        end_line_raw = params.get("end_line", -1)
        end_line = (
            int(end_line_raw)
            if isinstance(end_line_raw, (int, float)) and not isinstance(end_line_raw, bool)
            else -1
        )

        repo = ctx["repository_path"]

        try:
            target = resolve_relative_path(relative_raw, repo)
        except PathSafetyError as e:
            return ToolResult(
                status="error",
                data={},
                result_summary="",
                error=f"path_safety: {e}",
            )

        if target.suffix and target.suffix not in ALLOWED_EXTENSIONS:
            return ToolResult(
                status="error",
                data={},
                result_summary="",
                error=f"extension not allowed: {target.suffix}",
            )

        if not target.exists():
            return ToolResult(
                status="error",
                data={},
                result_summary="",
                error=f"file does not exist: {relative_raw}",
            )
        if not target.is_file():
            return ToolResult(
                status="error",
                data={},
                result_summary="",
                error=f"not a regular file: {relative_raw}",
            )

        try:
            content_raw = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            return ToolResult(
                status="error",
                data={},
                result_summary="",
                error=f"not_utf8: {e}",
            )
        except OSError as e:
            return ToolResult(
                status="error",
                data={},
                result_summary="",
                error=f"{type(e).__name__}: {e}",
            )

        return _slice(content_raw, start_line, end_line, relative_raw)


def _slice(
    content: str,
    start_line: int,
    end_line: int,
    relative_path: str,
) -> ToolResult:
    """Slice content by lines; enforce max-line and max-char limits."""
    all_lines = content.splitlines()
    total_lines = len(all_lines)

    if start_line < 0:
        start_line = 0
    if start_line > total_lines:
        start_line = total_lines

    if end_line < 0 or end_line > total_lines:
        end_line = total_lines

    requested = all_lines[start_line:end_line]
    truncated_lines = False
    truncated_chars = False

    if len(requested) > MAX_SNIPPET_LINES:
        requested = requested[:MAX_SNIPPET_LINES]
        truncated_lines = True
    end_line_actual = start_line + len(requested)

    body = "\n".join(requested)
    if len(body) > MAX_SNIPPET_CHARS:
        cut = MAX_SNIPPET_CHARS
        last_nl = body.rfind("\n", 0, cut)
        body = body[:last_nl] if last_nl > 0 else body[:cut]
        truncated_chars = True

    summary = (
        f"file={relative_path}, lines_returned={body.count(chr(10)) + 1}, "
        f"total_lines={total_lines}, "
        f"truncated={'yes' if (truncated_lines or truncated_chars) else 'no'}"
    )
    return ToolResult(
        status="success",
        data={
            "content": body,
            "total_lines": total_lines,
            "line_range": [start_line + 1, end_line_actual],
            "truncated": truncated_lines or truncated_chars,
        },
        result_summary=summary,
        error=None,
    )
