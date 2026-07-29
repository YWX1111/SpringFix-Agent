"""MockLLMClient tests.

Covers:
    1.  Normal structured output
    4.  Timeout simulation
    5.  429 after retry success
    6.  Max retries exhausted failure
    9.  API key never enters exceptions / traces
"""

from __future__ import annotations

from pathlib import Path

import pytest

from springfix_agent.llm._retry import (
    AuthError,
    MaxRetriesExceeded,
    RetryableError,
    with_retry,
)
from springfix_agent.llm.mock import MockLLMClient
from springfix_agent.llm.schemas import (
    InvestigationPlan,
    InvestigationStep,
    IssueAnalysis,
    RootCauseAnalysis,
)
from springfix_agent.observability.in_memory_tracer import InMemoryTracer
from springfix_agent.storage.in_memory import InMemoryTaskRepository


def _tracer_repo():
    repo = InMemoryTaskRepository()
    task = repo.create_task(
        repository_path="/tmp/x",
        issue_description="test issue description",
        error_log=None,
    )
    tracer = InMemoryTracer(repo)
    return repo, tracer, task.task_id


def test_mock_returns_configured_response() -> None:
    """Case 1: normal structured output."""
    repo, tracer, task_id = _tracer_repo()
    mock = MockLLMClient()
    analysis = IssueAnalysis(
        issue_category="transaction",
        summary="Transactional self-invocation bypass",
    )
    mock.set_response(analysis)
    ctx = {"task_id": task_id, "node_name": "issue_parser", "tracer": tracer}
    result = mock.invoke_structured(
        system_prompt="sys",
        user_prompt="user",
        response_model=IssueAnalysis,
        trace_context=ctx,
    )
    assert result.issue_category == "transaction"
    # Trace must be recorded
    traces = repo.get_traces(task_id)
    llm_traces = [t for t in traces if t.kind == "llm_call"]
    assert len(llm_traces) == 1
    assert llm_traces[0].payload["status"] == "success"


def test_mock_timeout_simulation() -> None:
    """Case 4: timeout behavior raises RetryableError."""
    repo, tracer, task_id = _tracer_repo()
    mock = MockLLMClient()
    mock.set_behavior("timeout", for_model=IssueAnalysis)
    ctx = {"task_id": task_id, "node_name": "issue_parser", "tracer": tracer}
    with pytest.raises(RetryableError):
        mock.invoke_structured(
            system_prompt="sys",
            user_prompt="user",
            response_model=IssueAnalysis,
            trace_context=ctx,
        )


def test_mock_429_then_success_with_retry() -> None:
    """Case 5: 429 on first attempt, success on retry."""
    repo, tracer, task_id = _tracer_repo()
    mock = MockLLMClient()
    mock.set_behavior("rate_limit", for_model=IssueAnalysis, n=1)
    mock.set_response(IssueAnalysis(issue_category="transaction", summary="ok"))

    calls: list[int] = []

    def attempt() -> IssueAnalysis:
        calls.append(1)
        ctx = {"task_id": task_id, "node_name": "issue_parser", "tracer": tracer}
        return mock.invoke_structured(
            system_prompt="sys",
            user_prompt="user",
            response_model=IssueAnalysis,
            trace_context=ctx,
        )

    # Retry layer on top of mock: first call raises, second succeeds
    def guarded() -> IssueAnalysis:
        return with_retry(attempt, max_retries=1)

    result = guarded()
    assert result.issue_category == "transaction"
    assert len(calls) == 2  # first attempt + retry


def test_mock_max_retries_exhausted() -> None:
    """Case 6: repeated failures exhaust retry budget."""
    repo, tracer, task_id = _tracer_repo()
    mock = MockLLMClient()
    mock.set_behavior("rate_limit", for_model=IssueAnalysis, n=10)
    ctx = {"task_id": task_id, "node_name": "issue_parser", "tracer": tracer}

    def attempt() -> IssueAnalysis:
        return mock.invoke_structured(
            system_prompt="sys",
            user_prompt="user",
            response_model=IssueAnalysis,
            trace_context=ctx,
        )

    with pytest.raises(MaxRetriesExceeded):
        with_retry(attempt, max_retries=2)


def test_mock_auth_never_retries() -> None:
    """Auth errors are not retryable; with_retry propagates immediately."""
    repo, tracer, task_id = _tracer_repo()
    mock = MockLLMClient()
    mock.set_behavior("auth", for_model=IssueAnalysis, n=5)
    ctx = {"task_id": task_id, "node_name": "issue_parser", "tracer": tracer}

    def attempt() -> IssueAnalysis:
        return mock.invoke_structured(
            system_prompt="sys",
            user_prompt="user",
            response_model=IssueAnalysis,
            trace_context=ctx,
        )

    with pytest.raises(AuthError):
        with_retry(attempt, max_retries=3)


def test_mock_no_api_key_in_trace() -> None:
    """Case 9: API key must never appear in any trace field."""
    repo, tracer, task_id = _tracer_repo()
    mock = MockLLMClient()
    # Even if someone tries to poison error_message with a key,
    # sanitize_for_trace strips it.
    mock.set_behavior("timeout", for_model=IssueAnalysis, n=1)
    ctx = {"task_id": task_id, "node_name": "issue_parser", "tracer": tracer}
    with pytest.raises(RetryableError):
        mock.invoke_structured(
            system_prompt="sys",
            user_prompt="user",
            response_model=IssueAnalysis,
            trace_context=ctx,
        )
    traces = repo.get_traces(task_id)
    for t in traces:
        for key, value in t.payload.items():
            if isinstance(value, str):
                assert "sk-" not in value
                assert "secret" not in value.lower() or key == "node"


def test_mock_returns_safe_default_when_no_response_configured() -> None:
    """When no response is set, mock returns a safe default."""
    repo, tracer, task_id = _tracer_repo()
    mock = MockLLMClient()
    ctx = {"task_id": task_id, "node_name": "issue_parser", "tracer": tracer}
    result = mock.invoke_structured(
        system_prompt="sys",
        user_prompt="user",
        response_model=IssueAnalysis,
        trace_context=ctx,
    )
    assert result.issue_category == "unknown"


def test_mock_invalid_json_behavior() -> None:
    """invalid_json behavior raises SchemaValidationError directly."""
    repo, tracer, task_id = _tracer_repo()
    mock = MockLLMClient()
    mock.set_behavior("invalid_json", for_model=IssueAnalysis, n=1)
    ctx = {"task_id": task_id, "node_name": "issue_parser", "tracer": tracer}
    from springfix_agent.llm._retry import SchemaValidationError

    with pytest.raises(SchemaValidationError):
        mock.invoke_structured(
            system_prompt="sys",
            user_prompt="user",
            response_model=IssueAnalysis,
            trace_context=ctx,
        )


# Silence unused imports when mypy scans.
_ = (InvestigationPlan, InvestigationStep, RootCauseAnalysis, Path, MaxRetriesExceeded)
