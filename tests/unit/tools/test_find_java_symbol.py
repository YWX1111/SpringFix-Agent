"""find_java_symbol tests (cases 23-27)."""

from __future__ import annotations

from pathlib import Path

from springfix_agent.tools.base import ToolContext
from springfix_agent.tools.find_java_symbol import FindJavaSymbolTool


def _ctx(repo_path: Path, allow_root: Path | None = None) -> ToolContext:
    return ToolContext(
        task_id="test-task",
        repository_path=repo_path,
        allow_root=allow_root if allow_root is not None else repo_path.parent,
    )


def test_find_class(sample_repo: Path) -> None:
    """Case 23: finds a class symbol."""
    tool = FindJavaSymbolTool()
    result = tool.run(
        {"symbol_name": "OrderService", "symbol_type": "class"},
        _ctx(sample_repo),
    )
    assert result["status"] == "success"
    matches = result["data"]["matches"]
    assert len(matches) > 0
    assert all(m["symbol_type"] == "class" for m in matches)
    assert any("OrderService.java" in m["file"] for m in matches)


def test_find_method(sample_repo: Path) -> None:
    """Case 24: finds a method symbol."""
    tool = FindJavaSymbolTool()
    result = tool.run(
        {"symbol_name": "createOrder", "symbol_type": "method"},
        _ctx(sample_repo),
    )
    matches = result["data"]["matches"]
    assert len(matches) > 0
    assert all(m["symbol_type"] == "method" for m in matches)
    assert any("OrderService.java" in m["file"] for m in matches)


def test_find_annotation(sample_repo: Path) -> None:
    """Case 25: finds an annotation symbol."""
    tool = FindJavaSymbolTool()
    result = tool.run(
        {"symbol_name": "Transactional", "symbol_type": "annotation"},
        _ctx(sample_repo),
    )
    matches = result["data"]["matches"]
    assert len(matches) > 0
    assert all(m["symbol_type"] == "annotation" for m in matches)
    assert any("OrderService.java" in m["file"] for m in matches)


def test_no_match_returns_empty(sample_repo: Path) -> None:
    """Case 26: no match returns empty matches list."""
    tool = FindJavaSymbolTool()
    result = tool.run(
        {"symbol_name": "NoSuchSymbol", "symbol_type": "any"},
        _ctx(sample_repo),
    )
    assert result["status"] == "success"
    assert result["data"]["matches"] == []


def test_no_hardcoded_saveorder(sample_repo: Path) -> None:
    """Case 27: tool works for arbitrary symbols, not 'saveOrder'."""
    tool = FindJavaSymbolTool()
    result = tool.run(
        {"symbol_name": "createOrderInTransaction", "symbol_type": "method"},
        _ctx(sample_repo),
    )
    matches = result["data"]["matches"]
    assert len(matches) > 0
    files = {m["file"] for m in matches}
    assert any("OrderService.java" in f for f in files)
    # Ensure tool has no hardcoded 'saveOrder' default
    assert "saveOrder" not in (tool.name, tool.description)
