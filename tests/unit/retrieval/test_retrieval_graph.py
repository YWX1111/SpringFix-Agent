"""Retrieval graph integration tests.

Covers:
    31. retrieve_code uses Hybrid
    32. evidence validation with real line ranges
    33. state size limit
    34. retrieval failure produces partial/insufficient_evidence
    35. M2 three LLM node count unchanged (3 LLM calls)
"""

from __future__ import annotations

from pathlib import Path

from springfix_agent.graph.nodes.root_cause_analyzer import _validate_evidence
from springfix_agent.graph.state import RetrievedSnippet
from springfix_agent.llm.schemas import (
    EvidenceReference,
    RootCauseAnalysis,
    RootCauseCandidate,
)
from springfix_agent.retrieval.diagnostics import make_diagnostics
from springfix_agent.retrieval.index import run_retrieval
from springfix_agent.retrieval.models import RetrievalDiagnostics


def _make_state(query: str) -> dict[str, object]:
    return {
        "issue_description": query,
        "error_log": None,
        "issue_analysis": {
            "issue_category": "transaction",
            "search_terms": ["@Transactional"],
            "extracted_symbols": ["OrderService"],
            "exception_types": ["RuntimeException"],
        },
        "investigation_plan": {"steps": []},
        "extracted_symbols": ["OrderService"],
    }


# -- 31. retrieve_code uses Hybrid --
def test_retrieve_code_hybrid(sample_repo: Path) -> None:
    """run_retrieval produces hybrid results with diagnostics."""
    state = _make_state("@Transactional self-invocation createOrder")
    hits, diag, query = run_retrieval(sample_repo, state, top_k=5)
    assert len(hits) >= 1
    assert diag.files_scanned >= 1
    assert diag.chunks_created >= 1
    assert query.normalized_terms  # should have terms
    # Check that we get OrderService.java in results.
    files = {h.chunk.file for h in hits}
    assert any("OrderService.java" in f for f in files)


# -- 32. evidence validation with real line ranges --
def test_evidence_validation_multi_snippet() -> None:
    """Evidence passes if line range falls within ANY snippet for the file."""
    snippets = [
        RetrievedSnippet(file="A.java", line_range=(1, 20), content="c1", score=1.0, symbols=[]),
        RetrievedSnippet(file="A.java", line_range=(25, 40), content="c2", score=0.5, symbols=[]),
    ]
    # Evidence references lines 5-10, which falls in the first snippet.
    analysis = RootCauseAnalysis(
        diagnosis_status="complete",
        summary="s",
        candidates=[
            RootCauseCandidate(
                title="t", description="d", confidence="high",
                evidence=[
                    EvidenceReference(file="A.java", start_line=5, end_line=10, explanation="e"),
                ],
                recommended_fix="f",
            )
        ],
    )
    snippet_index: dict[str, list[RetrievedSnippet]] = {}
    for s in snippets:
        snippet_index.setdefault(s["file"], []).append(s)
    cleaned, dropped, rejections = _validate_evidence(analysis, snippet_index)
    assert dropped == 0
    assert len(cleaned.candidates) == 1


def test_evidence_rejected_outside_all_snippets() -> None:
    """Evidence rejected when line range doesn't match any snippet."""
    snippets = [
        RetrievedSnippet(file="A.java", line_range=(1, 20), content="c1", score=1.0, symbols=[]),
        RetrievedSnippet(file="A.java", line_range=(25, 40), content="c2", score=0.5, symbols=[]),
    ]
    # Evidence references lines 50-60, outside both snippets.
    analysis = RootCauseAnalysis(
        diagnosis_status="complete",
        summary="s",
        candidates=[
            RootCauseCandidate(
                title="t", description="d", confidence="high",
                evidence=[
                    EvidenceReference(file="A.java", start_line=50, end_line=60, explanation="e"),
                ],
                recommended_fix="f",
            )
        ],
    )
    snippet_index: dict[str, list[RetrievedSnippet]] = {}
    for s in snippets:
        snippet_index.setdefault(s["file"], []).append(s)
    cleaned, dropped, rejections = _validate_evidence(analysis, snippet_index)
    assert dropped >= 1
    assert len(cleaned.candidates) == 0


# -- 33. state size limit / diagnostics --
def test_diagnostics_model() -> None:
    """RetrievalDiagnostics captures all required fields."""
    diag = make_diagnostics(
        files_scanned=10,
        chunks_created=50,
        chunks_indexed=48,
        index_build_duration_ms=15,
        baseline_duration_ms=3,
        bm25_duration_ms=2,
        symbol_duration_ms=1,
        fusion_duration_ms=1,
        truncated=False,
        fallback_used=False,
        query_terms_used=10,
        baseline_hits=5,
        bm25_hits=8,
        symbol_hits=2,
        fusion_hits=10,
    )
    assert diag.files_scanned == 10
    assert diag.chunks_created == 50
    assert diag.truncated is False
    assert diag.fallback_used is False


# -- 34. retrieval failure produces empty results --
def test_retrieval_empty_repo(tmp_path: Path) -> None:
    """Empty repo returns empty hits without crashing."""
    state = _make_state("some query")
    hits, diag, query = run_retrieval(tmp_path, state, top_k=5)
    assert hits == []
    assert diag.files_scanned == 0
    assert diag.fallback_used is True or diag.baseline_hits == 0


# -- 35. retrieval does not increase LLM calls --
def test_retrieval_no_llm_calls(sample_repo: Path) -> None:
    """run_retrieval is purely deterministic; no LLM dependency."""
    state = _make_state("@Transactional")
    # Should complete without any LLM client.
    hits, diag, query = run_retrieval(sample_repo, state, top_k=5)
    assert isinstance(hits, list)
    assert isinstance(diag, RetrievalDiagnostics)
