"""read_file tests (cases 18-22)."""

from __future__ import annotations

from pathlib import Path

from springfix_agent.tools.base import ToolContext
from springfix_agent.tools.read_file import ReadFileTool


def _ctx(repo_path: Path, allow_root: Path | None = None) -> ToolContext:
    return ToolContext(
        task_id="test-task",
        repository_path=repo_path,
        allow_root=allow_root if allow_root is not None else repo_path.parent,
    )


def test_read_normal_lines(sample_repo: Path) -> None:
    """Case 18: normal read returns file content and line range."""
    tool = ReadFileTool()
    rel = "src/main/java/com/example/OrderService.java"
    result = tool.run({"relative_path": rel}, _ctx(sample_repo))
    assert result["status"] == "success"
    data = result["data"]
    assert "createOrder" in data["content"]
    assert data["total_lines"] > 0
    assert data["line_range"][0] == 1


def test_truncate_at_60_lines(sample_repo: Path) -> None:
    """Case 19: file > 60 lines is truncated and flagged."""
    big = sample_repo / "Big.java"
    big.write_text("\n".join(f"// line {i}" for i in range(100)), encoding="utf-8")
    tool = ReadFileTool()
    result = tool.run({"relative_path": "Big.java"}, _ctx(sample_repo))
    data = result["data"]
    assert data["truncated"] is True
    assert len(data["content"].splitlines()) <= 60


def test_truncate_at_4000_chars(sample_repo: Path) -> None:
    """Case 20: content > 4000 chars is truncated and flagged."""
    big = sample_repo / "Big2.java"
    big.write_text("x" * 5000, encoding="utf-8")
    tool = ReadFileTool()
    result = tool.run({"relative_path": "Big2.java"}, _ctx(sample_repo))
    data = result["data"]
    assert data["truncated"] is True
    assert len(data["content"]) <= 4000


def test_reject_outside_repository(sample_repo: Path) -> None:
    """Case 21: path traversal outside repository is rejected."""
    tool = ReadFileTool()
    result = tool.run({"relative_path": "../../etc/passwd"}, _ctx(sample_repo))
    assert result["status"] == "error"
    assert "path_safety" in (result.get("error") or "")


def test_reject_disallowed_extension(sample_repo: Path) -> None:
    """Case 22: a non-whitelisted extension is rejected."""
    bad = sample_repo / "Evil.class"
    bad.write_text("// fake bytecode", encoding="utf-8")
    tool = ReadFileTool()
    result = tool.run({"relative_path": "Evil.class"}, _ctx(sample_repo))
    assert result["status"] == "error"
    assert "extension" in (result.get("error") or "")
