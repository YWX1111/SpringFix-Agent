"""list_project_tree tests (cases 7-11)."""

from __future__ import annotations

from pathlib import Path

from springfix_agent.tools.base import ToolContext
from springfix_agent.tools.list_project_tree import ListProjectTreeTool


def _ctx(repo_path: Path, allow_root: Path | None = None) -> ToolContext:
    return ToolContext(
        task_id="test-task",
        repository_path=repo_path,
        allow_root=allow_root if allow_root is not None else repo_path.parent,
    )


def test_generates_tree(sample_repo: Path) -> None:
    """Case 7: a valid repo produces a non-empty tree with java files."""
    tool = ListProjectTreeTool()
    result = tool.run({"max_depth": 7, "max_files": 100}, _ctx(sample_repo))
    assert result["status"] == "success"
    data = result["data"]
    assert data["file_count"] >= 3
    assert data["java_file_count"] >= 3
    assert "OrderService.java" in data["tree"]
    assert "OtherService.java" in data["tree"]


def test_excludes_target_and_git(sample_repo: Path) -> None:
    """Case 8: target, build, .git are excluded; generated files do not appear."""
    tool = ListProjectTreeTool()
    result = tool.run({"max_depth": 5, "max_files": 100}, _ctx(sample_repo))
    tree = result["data"]["tree"]
    assert "target" not in tree
    assert "build" not in tree
    assert ".git" not in tree
    assert "generated.java" not in tree
    assert "out.java" not in tree


def test_max_depth_limits_output(sample_repo: Path) -> None:
    """Case 9: max_depth=1 limits output to root-level entries only."""
    tool = ListProjectTreeTool()
    result = tool.run({"max_depth": 1, "max_files": 100}, _ctx(sample_repo))
    tree = result["data"]["tree"]
    assert "OrderService.java" not in tree
    assert "pom.xml" in tree


def test_max_files_truncation(sample_repo: Path) -> None:
    """Case 10: max_files stops listing and marks truncated=True."""
    tool = ListProjectTreeTool()
    result = tool.run({"max_files": 2, "max_depth": 5}, _ctx(sample_repo))
    data = result["data"]
    assert data["truncated"] is True
    assert data["file_count"] == 2


def test_output_ordering_stable(sample_repo: Path) -> None:
    """Case 11: identical inputs produce identical tree outputs."""
    tool = ListProjectTreeTool()
    ctx = _ctx(sample_repo)
    r1 = tool.run({"max_depth": 5, "max_files": 100}, ctx)
    r2 = tool.run({"max_depth": 5, "max_files": 100}, ctx)
    assert r1["data"]["tree"] == r2["data"]["tree"]
