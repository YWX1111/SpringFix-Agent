"""search_code tests (cases 12-17)."""

from __future__ import annotations

from pathlib import Path

from springfix_agent.tools.base import ToolContext
from springfix_agent.tools.search_code import SearchCodeTool


def _ctx(repo_path: Path, allow_root: Path | None = None) -> ToolContext:
    return ToolContext(
        task_id="test-task",
        repository_path=repo_path,
        allow_root=allow_root if allow_root is not None else repo_path.parent,
    )


def test_single_keyword_matches(sample_repo: Path) -> None:
    """Case 12: any single valid keyword returns hits (no AND required)."""
    tool = SearchCodeTool()
    result = tool.run({"query": "createOrder"}, _ctx(sample_repo))
    assert result["status"] == "success"
    hits = result["data"]["hits"]
    assert len(hits) > 0
    assert any("OrderService.java" in h["file"] for h in hits)


def test_method_name_ranks_higher_than_plain(sample_repo: Path) -> None:
    """Case 13: method-name match scores higher than plain-word match per hit."""
    tool = SearchCodeTool()
    # "hello" is lowercase plain word -> +1.0 per hit
    r_plain = tool.run({"query": "hello"}, _ctx(sample_repo))
    # "createOrder" is lowerCamelCase method -> +2.0 per hit
    r_method = tool.run({"query": "createOrder"}, _ctx(sample_repo))
    plain_max = max((h["score"] for h in r_plain["data"]["hits"]), default=0.0)
    method_max = max((h["score"] for h in r_method["data"]["hits"]), default=0.0)
    assert method_max > plain_max


def test_no_match_returns_empty(sample_repo: Path) -> None:
    """Case 14: no matches returns an empty hits list."""
    tool = SearchCodeTool()
    result = tool.run({"query": "nonExistentSymbol"}, _ctx(sample_repo))
    assert result["status"] == "success"
    assert result["data"]["hits"] == []


def test_top_k_limit(sample_repo: Path) -> None:
    """Case 15: top_k limits the number of returned hits."""
    tool = SearchCodeTool()
    result = tool.run({"query": "public void", "top_k": 2}, _ctx(sample_repo))
    assert len(result["data"]["hits"]) <= 2


def test_real_line_numbers(sample_repo: Path) -> None:
    """Case 16: line numbers are real 1-based integers."""
    tool = SearchCodeTool()
    result = tool.run({"query": "createOrder"}, _ctx(sample_repo))
    hits = result["data"]["hits"]
    assert all(isinstance(h["line"], int) and h["line"] > 0 for h in hits)


def test_stable_ordering(sample_repo: Path) -> None:
    """Case 17: identical inputs produce identical hit order."""
    tool = SearchCodeTool()
    ctx = _ctx(sample_repo)
    r1 = tool.run({"query": "OrderService"}, ctx)
    r2 = tool.run({"query": "OrderService"}, ctx)
    assert r1["data"]["hits"] == r2["data"]["hits"]
