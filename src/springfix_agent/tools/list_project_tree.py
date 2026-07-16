"""list_project_tree tool.

Walks the repository and returns a deterministic directory tree.
M1 implementation: os.walk + exclude filter + depth/file limits.
"""

from __future__ import annotations

import os
from pathlib import Path

from springfix_agent.tools.base import Tool, ToolContext, ToolResult

DEFAULT_EXCLUDE_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        "target",
        "build",
        "dist",
        "node_modules",
        ".idea",
        ".vscode",
        "__pycache__",
        ".mvn",
        ".gradle",
    }
)

DEFAULT_MAX_DEPTH = 3
DEFAULT_MAX_FILES = 200


class ListProjectTreeTool(Tool):
    """List repository file tree up to max_depth, excluding build/cache dirs."""

    name = "list_project_tree"
    description = (
        "List the project file tree up to max_depth, excluding common build and "
        "IDE directories. Returns a deterministic, sorted tree string with file "
        "counts and a truncated flag if max_files is reached."
    )

    def run(self, params: dict[str, object], ctx: ToolContext) -> ToolResult:
        max_depth_raw = params.get("max_depth", DEFAULT_MAX_DEPTH)
        max_depth = (
            int(max_depth_raw)
            if isinstance(max_depth_raw, (int, float)) and not isinstance(max_depth_raw, bool)
            else DEFAULT_MAX_DEPTH
        )
        max_files_raw = params.get("max_files", DEFAULT_MAX_FILES)
        max_files = (
            int(max_files_raw)
            if isinstance(max_files_raw, (int, float)) and not isinstance(max_files_raw, bool)
            else DEFAULT_MAX_FILES
        )
        exclude = params.get("exclude")
        if not isinstance(exclude, list) or not exclude:
            exclude_set = DEFAULT_EXCLUDE_DIRS
        else:
            exclude_set = frozenset(str(e) for e in exclude) | DEFAULT_EXCLUDE_DIRS

        repo = ctx["repository_path"]
        try:
            lines, file_count, java_file_count, truncated = _walk(
                repo, max_depth=max_depth, max_files=max_files, exclude=exclude_set
            )
        except OSError as e:
            return ToolResult(
                status="error",
                data={},
                result_summary="",
                error=f"{type(e).__name__}: {e}",
            )

        tree = "\n".join(lines)
        summary = (
            f"tree_lines={len(lines)}, file_count={file_count}, "
            f"java_file_count={java_file_count}, truncated={truncated}"
        )
        return ToolResult(
            status="success",
            data={
                "tree": tree,
                "file_count": file_count,
                "java_file_count": java_file_count,
                "truncated": truncated,
            },
            result_summary=summary,
            error=None,
        )


def _walk(
    root: Path,
    *,
    max_depth: int,
    max_files: int,
    exclude: frozenset[str],
) -> tuple[list[str], int, int, bool]:
    """Walk root, returning (tree_lines, file_count, java_file_count, truncated).

    Tree format: one entry per line, indented by depth*2 spaces. Directories
    end with '/'. Files are listed after their parent directory's children.
    Entries within a directory are sorted alphabetically (dirs first, then files).
    """
    lines: list[str] = [f"{root.name}/"]
    file_count = 0
    java_file_count = 0
    truncated = False

    stack: list[tuple[Path, int]] = [(root, 0)]
    visited_dirs: set[Path] = {root.resolve()}

    while stack:
        current, depth = stack.pop()
        if depth >= max_depth:
            continue

        try:
            entries = sorted(os.listdir(current), key=lambda s: s.lower())
        except OSError:
            continue

        subdirs: list[Path] = []
        files: list[Path] = []

        for entry_name in entries:
            entry_path = current / entry_name
            if entry_path.is_dir():
                if entry_name in exclude:
                    continue
                resolved = entry_path.resolve()
                if resolved in visited_dirs:
                    continue
                if not _is_within_resolve(resolved, current.resolve()):
                    continue
                visited_dirs.add(resolved)
                subdirs.append(entry_path)
            else:
                files.append(entry_path)

        for d in subdirs:
            if file_count >= max_files:
                truncated = True
                break
            indent = "  " * (depth + 1)
            lines.append(f"{indent}{d.name}/")
            stack.append((d, depth + 1))

        if truncated:
            break

        for f in files:
            if file_count >= max_files:
                truncated = True
                break
            file_count += 1
            if f.suffix == ".java":
                java_file_count += 1
            indent = "  " * (depth + 1)
            lines.append(f"{indent}{f.name}")

        if truncated:
            break

    return lines, file_count, java_file_count, truncated


def _is_within_resolve(child: Path, parent: Path) -> bool:
    """True if child is parent or inside parent after resolution."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False
