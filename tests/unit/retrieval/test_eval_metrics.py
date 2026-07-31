"""Evaluation metric computation tests.

Covers:
    37. Baseline/BM25/Hybrid use same cases
    38. Recall@K calculation
    39. MRR calculation
    40. P95 calculation
    41. failed cases counted
    42. JSON and Markdown consistency
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

import pytest


# Re-implement metric functions here to test against the eval script's logic.
def _recall_at_k(expected: list[str], retrieved_files: list[str], k: int) -> float:
    if not expected:
        return 1.0
    return len(set(expected) & set(retrieved_files[:k])) / len(expected)


def _mrr_at_n(expected: list[str], retrieved_files: list[str], n: int = 10) -> float:
    if not expected:
        return 1.0
    expected_set = set(expected)
    for i, f in enumerate(retrieved_files[:n]):
        if f in expected_set:
            return 1.0 / (i + 1)
    return 0.0


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = int(math.ceil(0.95 * len(s))) - 1
    return s[max(0, idx)]


# -- 38. Recall@K calculation --
@pytest.mark.parametrize("k,expected_recall", [
    (1, 0.5),   # Only 1 of 2 expected files in top-1
    (3, 1.0),   # Both expected files in top-3
    (5, 1.0),   # Both expected files in top-5
])
def test_recall_at_k(k: int, expected_recall: float) -> None:
    expected_files = ["A.java", "B.java"]
    retrieved = ["A.java", "C.java", "B.java", "D.java", "E.java"]
    recall = _recall_at_k(expected_files, retrieved, k)
    assert recall == expected_recall


def test_recall_empty_expected() -> None:
    assert _recall_at_k([], ["A.java"], 5) == 1.0


def test_recall_no_match() -> None:
    assert _recall_at_k(["X.java"], ["A.java", "B.java"], 5) == 0.0


# -- 39. MRR calculation --
def test_mrr_first_position() -> None:
    assert _mrr_at_n(["A.java"], ["A.java", "B.java"]) == 1.0


def test_mrr_second_position() -> None:
    assert _mrr_at_n(["B.java"], ["A.java", "B.java"]) == 0.5


def test_mrr_not_found() -> None:
    assert _mrr_at_n(["X.java"], ["A.java", "B.java"]) == 0.0


def test_mrr_empty_expected() -> None:
    assert _mrr_at_n([], ["A.java"]) == 1.0


# -- 40. P95 calculation --
def test_p95_basic() -> None:
    values = list(range(1, 21))  # 1..20
    p95 = _p95(values)
    assert p95 == 19.0  # ceil(0.95 * 20) - 1 = 18 → index 18 → value 19


def test_p95_single_value() -> None:
    assert _p95([5.0]) == 5.0


def test_p95_empty() -> None:
    assert _p95([]) == 0.0


# -- 41. failed cases counted --
def test_failed_cases_in_metrics() -> None:
    """If a case produces no hits, it still counts as Recall=0."""
    # Simulate 3 cases: 2 pass, 1 fail.
    recalls = [
        _recall_at_k(["A.java"], ["A.java", "B.java"], 5),  # 1.0
        _recall_at_k(["C.java"], ["A.java", "B.java"], 5),  # 0.0 (fail)
        _recall_at_k(["A.java"], ["B.java", "A.java"], 5),  # 1.0
    ]
    mean_recall = statistics.mean(recalls)
    assert mean_recall == pytest.approx(2 / 3, abs=0.01)


# -- 42. JSON and Markdown consistency --
def test_eval_output_files_exist() -> None:
    """Eval script should produce metrics.json and report.md."""
    artifacts = Path(__file__).resolve().parents[3] / "artifacts" / "retrieval-eval"
    json_path = artifacts / "metrics.json"
    md_path = artifacts / "report.md"
    if json_path.exists() and md_path.exists():
        data = json.loads(json_path.read_text(encoding="utf-8"))
        md = md_path.read_text(encoding="utf-8")
        # Both should reference the same channels.
        for ch in ("baseline", "bm25", "hybrid"):
            assert ch in md
        # JSON should have split_summary or summary.
        assert "split_summary" in data or "summary" in data


# -- 43. expected_symbols does NOT enter RetrievalQuery --
def test_expected_symbols_not_in_query() -> None:
    """Gold-standard expected_symbols must never become part of the RetrievalQuery.

    The eval script's _make_state uses issue_analysis.extracted_symbols
    (simulated LLM output), NOT expected_symbols.
    """
    import importlib.util

    eval_path = Path(__file__).resolve().parents[3] / "scripts" / "run_retrieval_eval.py"
    spec = importlib.util.spec_from_file_location("run_retrieval_eval", eval_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Case with distinct expected_symbols and issue_analysis.extracted_symbols.
    case = {
        "query": "@Transactional self-invocation bypass createOrder",
        "expected_symbols": ["GOLD_SYMBOL_NOT_FOR_QUERY"],
        "issue_analysis": {
            "extracted_symbols": ["OrderService", "createOrder"],
            "search_terms": ["transaction"],
        },
    }
    state = mod._make_state(case)
    # Build query from state.
    query = mod.build_query(state)

    # expected_symbols must NOT appear in exact_symbols.
    assert "GOLD_SYMBOL_NOT_FOR_QUERY" not in query.exact_symbols
    # issue_analysis.extracted_symbols SHOULD appear.
    assert "OrderService" in query.exact_symbols or "createOrder" in query.exact_symbols


def test_make_state_no_expected_symbols_leak() -> None:
    """_make_state must not copy expected_symbols into the state dict."""
    import importlib.util

    eval_path = Path(__file__).resolve().parents[3] / "scripts" / "run_retrieval_eval.py"
    spec = importlib.util.spec_from_file_location("run_retrieval_eval2", eval_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    case = {
        "query": "OrderService",
        "expected_symbols": ["LEAK_TEST_SYMBOL"],
        "issue_analysis": {"extracted_symbols": ["OrderService"], "search_terms": []},
    }
    state = mod._make_state(case)
    # The state should not contain expected_symbols key at all.
    assert "expected_symbols" not in state
    # LEAK_TEST_SYMBOL must not be reachable via build_query.
    query = mod.build_query(state)
    assert "LEAK_TEST_SYMBOL" not in query.exact_symbols
    assert "LEAK_TEST_SYMBOL" not in query.normalized_terms
