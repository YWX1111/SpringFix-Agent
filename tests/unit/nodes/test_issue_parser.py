"""IssueParser node tests.

Covers:
    10.  Normal problem classification
    11.  Extracts exception types
    12.  Merges LLM and deterministic symbols
    13.  LLM failure degrades correctly
    14.  Does not claim root cause located
"""

from __future__ import annotations

from springfix_agent.graph.nodes.issue_parser import issue_parser
from springfix_agent.llm.mock import MockLLMClient
from springfix_agent.llm.schemas import IssueAnalysis
from springfix_agent.observability.in_memory_tracer import InMemoryTracer
from springfix_agent.storage.in_memory import InMemoryTaskRepository


def _state(**overrides):
    base = {
        "task_id": "t-1",
        "repository_path": "/tmp/repo",
        "issue_description": "calling createOrder throws RuntimeException, data not rolled back",
        "error_log": "java.lang.RuntimeException: simulated failure",
        "validation_ok": True,
        "validation_errors": [],
        "issue_analysis": {},
        "extracted_symbols": [],
        "project_tree_summary": "",
        "candidate_files": [],
        "investigation_plan": {},
        "retrieved_snippets": [],
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
        "current_node": "issue_parser",
    }
    base.update(overrides)
    return base


def _tracer_ctx():
    repo = InMemoryTaskRepository()
    repo.create_task(
        repository_path="/tmp/x",
        issue_description="test issue description",
        error_log=None,
    )
    tracer = InMemoryTracer(repo)
    return tracer


def test_issue_parser_normal_classification() -> None:
    """Case 10: LLM returns transaction category."""
    mock = MockLLMClient()
    mock.set_response(
        IssueAnalysis(
            issue_category="transaction",
            summary="Transactional self-invocation",
            symptoms=["no rollback"],
            exception_types=["RuntimeException"],
            extracted_symbols=["OrderService", "createOrder"],
            search_terms=["@Transactional"],
            spring_concepts=["AOP proxy"],
        )
    )
    tracer = _tracer_ctx()
    result = issue_parser(_state(), llm=mock, tracer=tracer)
    assert result["issue_analysis"]["issue_category"] == "transaction"
    # Symbols must be merged with deterministic output
    assert "OrderService" in result["extracted_symbols"]
    assert "createOrder" in result["extracted_symbols"]


def test_issue_parser_extracts_exception_type() -> None:
    """Case 11: exception_types contains RuntimeException."""
    mock = MockLLMClient()
    mock.set_response(
        IssueAnalysis(
            issue_category="transaction",
            summary="s",
            exception_types=["RuntimeException", "IllegalArgumentException"],
        )
    )
    tracer = _tracer_ctx()
    result = issue_parser(_state(), llm=mock, tracer=tracer)
    assert "RuntimeException" in result["issue_analysis"]["exception_types"]


def test_issue_parser_merges_llm_and_deterministic() -> None:
    """Case 12: both LLM and deterministic symbols are preserved."""
    mock = MockLLMClient()
    mock.set_response(
        IssueAnalysis(
            issue_category="transaction",
            summary="s",
            extracted_symbols=["OrderService"],
        )
    )
    tracer = _tracer_ctx()
    state = _state(
        issue_description="calling createOrder throws RuntimeException"
    )
    result = issue_parser(state, llm=mock, tracer=tracer)
    # LLM added OrderService; deterministic added createOrder
    assert "OrderService" in result["extracted_symbols"]
    assert "createOrder" in result["extracted_symbols"]


def test_issue_parser_llm_failure_degrades() -> None:
    """Case 13: LLM failure falls back to deterministic extraction."""
    mock = MockLLMClient()
    mock.set_behavior("timeout", for_model=IssueAnalysis, n=1)
    tracer = _tracer_ctx()
    result = issue_parser(_state(), llm=mock, tracer=tracer)
    assert result["issue_analysis"]["issue_category"] == "unknown"
    assert len(result["warnings"]) > 0
    # Deterministic extraction still works
    assert len(result["extracted_symbols"]) > 0


def test_issue_parser_does_not_claim_root_cause() -> None:
    """Case 14: IssueAnalysis output never mentions root cause."""
    mock = MockLLMClient()
    mock.set_response(
        IssueAnalysis(
            issue_category="transaction",
            summary="Transaction rollback failed due to AOP bypass",
        )
    )
    tracer = _tracer_ctx()
    result = issue_parser(_state(), llm=mock, tracer=tracer)
    summary = str(result["issue_analysis"].get("summary", ""))
    # The summary may mention the suspected cause as a symptom,
    # but must not claim "根因已确定". We check the absence of the
    # explicit root-cause confirmation language.
    assert "根因已确定" not in summary
    assert "root cause determined" not in summary.lower()
