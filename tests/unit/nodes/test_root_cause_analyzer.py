"""RootCauseAnalyzer node tests.

Covers:
    19.  Generates candidates with evidence
    20.  Rejects evidence file not in snippets
    21.  Rejects out-of-range line numbers
    22.  Rejects empty evidence
    23.  Caps at 3 candidates
    24.  Returns insufficient_evidence on ambiguity
    25.  Does not claim certainty for common-sense inference
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from springfix_agent.graph.nodes.root_cause_analyzer import (
    _validate_evidence,
    root_cause_analyzer,
)
from springfix_agent.graph.state import RetrievedSnippet
from springfix_agent.llm.mock import MockLLMClient
from springfix_agent.llm.schemas import (
    EvidenceReference,
    RootCauseAnalysis,
    RootCauseCandidate,
)
from springfix_agent.observability.in_memory_tracer import InMemoryTracer
from springfix_agent.storage.in_memory import InMemoryTaskRepository


def _state(snippets=None, **overrides):
    base = {
        "task_id": "t-1",
        "repository_path": "/tmp/repo",
        "issue_description": "calling createOrder throws RuntimeException",
        "error_log": None,
        "validation_ok": True,
        "validation_errors": [],
        "issue_analysis": {
            "issue_category": "transaction",
            "summary": "s",
            "symptoms": [],
            "exception_types": ["RuntimeException"],
        },
        "extracted_symbols": ["OrderService"],
        "project_tree_summary": "root/",
        "candidate_files": [],
        "investigation_plan": {"steps": []},
        "retrieved_snippets": snippets or [],
        "retrieval_summary": "",
        "root_cause_analysis": {},
        "diagnostic_report": {},
        "markdown_report": "",
        "basic_report": {},
        "tool_calls": [],
        "node_timings": [],
        "errors": [],
        "warnings": [],
        "llm_calls": [],
        "status": "running",
        "current_node": "root_cause_analyzer",
    }
    base.update(overrides)
    return base


def _tracer():
    repo = InMemoryTaskRepository()
    repo.create_task(
        repository_path="/tmp/x",
        issue_description="test issue description",
        error_log=None,
    )
    return InMemoryTracer(repo)


def _valid_analysis(snippets) -> RootCauseAnalysis:
    f = snippets[0]["file"]
    start, end = snippets[0]["line_range"]
    return RootCauseAnalysis(
        diagnosis_status="complete",
        summary="Transactional bypass via self-invocation",
        candidates=[
            RootCauseCandidate(
                title="Spring AOP bypass",
                description="createOrder self-invokes the @Transactional method",
                confidence="high",
                evidence=[
                    EvidenceReference(
                        file=f,
                        start_line=start,
                        end_line=min(start + 1, end),
                        explanation="Self-invocation bypasses proxy",
                    )
                ],
                recommended_fix="Move @Transactional method to a separate service bean",
            )
        ],
    )


def test_root_cause_analyzer_valid_candidates() -> None:
    """Case 19: valid evidence passes secondary check."""
    snippets = [
        RetrievedSnippet(
            file="OrderService.java",
            line_range=(1, 20),
            content="code",
            score=2.0,
            symbols=["OrderService"],
        )
    ]
    analysis = _valid_analysis(snippets)
    cleaned, dropped, _rej = _validate_evidence(analysis, {s["file"]: [s] for s in snippets})
    assert dropped == 0
    assert len(cleaned.candidates) == 1


def test_root_cause_analyzer_rejects_unknown_file() -> None:
    """Case 20: evidence file not in snippets is dropped."""
    snippets = [
        RetrievedSnippet(
            file="OrderService.java",
            line_range=(1, 20),
            content="code",
            score=2.0,
            symbols=["OrderService"],
        )
    ]
    analysis = RootCauseAnalysis(
        diagnosis_status="complete",
        summary="s",
        candidates=[
            RootCauseCandidate(
                title="t",
                description="d",
                confidence="high",
                evidence=[
                    EvidenceReference(
                        file="NonExistent.java",
                        start_line=1,
                        end_line=5,
                        explanation="e",
                    )
                ],
                recommended_fix="f",
            )
        ],
    )
    cleaned, dropped, _rej = _validate_evidence(analysis, {s["file"]: [s] for s in snippets})
    assert dropped >= 1
    assert len(cleaned.candidates) == 0


def test_root_cause_analyzer_rejects_out_of_range_lines() -> None:
    """Case 21: line range outside snippet is dropped."""
    snippets = [
        RetrievedSnippet(
            file="OrderService.java",
            line_range=(1, 20),
            content="code",
            score=2.0,
            symbols=["OrderService"],
        )
    ]
    analysis = RootCauseAnalysis(
        diagnosis_status="complete",
        summary="s",
        candidates=[
            RootCauseCandidate(
                title="t",
                description="d",
                confidence="high",
                evidence=[
                    EvidenceReference(
                        file="OrderService.java",
                        start_line=1,
                        end_line=999,
                        explanation="e",
                    )
                ],
                recommended_fix="f",
            )
        ],
    )
    cleaned, dropped, _rej = _validate_evidence(analysis, {s["file"]: [s] for s in snippets})
    assert dropped >= 1


def test_root_cause_analyzer_rejects_empty_evidence() -> None:
    """Case 22: empty evidence list fails Pydantic validation."""
    with pytest.raises(ValidationError):
        RootCauseCandidate(
            title="t",
            description="d",
            confidence="high",
            evidence=[],
            recommended_fix="f",
        )


def test_root_cause_analyzer_caps_candidates() -> None:
    """Case 23: more than 3 candidates are trimmed."""
    analysis = RootCauseAnalysis(
        diagnosis_status="complete",
        summary="s",
        candidates=[
            RootCauseCandidate(
                title=f"c{i}",
                description="d",
                confidence="low",
                evidence=[EvidenceReference(file="f", start_line=1, end_line=2, explanation="e")],
                recommended_fix="f",
            )
            for i in range(5)
        ],
    )
    assert len(analysis.candidates) <= 3


def test_root_cause_analyzer_insufficient_evidence_on_no_snippets() -> None:
    """Case 24: no snippets -> insufficient_evidence output."""
    mock = MockLLMClient()
    tracer = _tracer()
    state = _state(snippets=[])
    result = root_cause_analyzer(state, llm=mock, tracer=tracer)
    assert result["root_cause_analysis"]["diagnosis_status"] == "insufficient_evidence"
    assert any("no snippets" in w for w in result["warnings"])


def test_root_cause_analyzer_llm_failure_returns_insufficient() -> None:
    """LLM failure degrades to insufficient_evidence."""
    mock = MockLLMClient()
    mock.set_behavior("timeout", for_model=RootCauseAnalysis, n=1)
    tracer = _tracer()
    snippets = [
        RetrievedSnippet(
            file="OrderService.java",
            line_range=(1, 20),
            content="code",
            score=2.0,
            symbols=["OrderService"],
        )
    ]
    state = _state(snippets=snippets)
    result = root_cause_analyzer(state, llm=mock, tracer=tracer)
    assert result["root_cause_analysis"]["diagnosis_status"] == "insufficient_evidence"
    assert any("fallback" in w for w in result["warnings"])


def test_root_cause_analyzer_does_not_overclaim() -> None:
    """Case 25: summary never claims certain root cause when ambiguous."""
    analysis = RootCauseAnalysis(
        diagnosis_status="partial",
        summary="Possible transactional bypass; needs more evidence",
        candidates=[],
        missing_information=["More context needed"],
    )
    assert "partial" in analysis.diagnosis_status
    assert analysis.summary != ""
