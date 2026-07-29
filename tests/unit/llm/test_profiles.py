"""Mock Profile tests.

Covers the five profiles defined in ``llm/profiles.py``:

- happy_path
- insufficient_evidence
- invalid_evidence
- timeout
- invalid_json
"""

from __future__ import annotations

import pytest

from springfix_agent.llm._retry import RetryableError, SchemaValidationError
from springfix_agent.llm.mock import MockLLMClient
from springfix_agent.llm.profiles import (
    HAPPY_PATH_FILE,
    SUPPORTED_PROFILES,
    get_profile_response,
    is_failure_profile,
)
from springfix_agent.llm.schemas import (
    InvestigationPlan,
    IssueAnalysis,
    RootCauseAnalysis,
)
from springfix_agent.observability.in_memory_tracer import InMemoryTracer
from springfix_agent.storage.in_memory import InMemoryTaskRepository


def _tracer_ctx():
    repo = InMemoryTaskRepository()
    task = repo.create_task(
        repository_path="/tmp/x",
        issue_description="test issue description",
        error_log=None,
    )
    tracer = InMemoryTracer(repo)
    return repo, tracer, task.task_id


def test_supported_profiles_listed() -> None:
    assert "happy_path" in SUPPORTED_PROFILES
    assert "insufficient_evidence" in SUPPORTED_PROFILES
    assert "invalid_evidence" in SUPPORTED_PROFILES
    assert "timeout" in SUPPORTED_PROFILES
    assert "invalid_json" in SUPPORTED_PROFILES


def test_happy_path_issue_analysis() -> None:
    mock = MockLLMClient()
    mock.use_profile("happy_path")
    repo, tracer, task_id = _tracer_ctx()
    ctx = {"task_id": task_id, "node_name": "issue_parser", "tracer": tracer}
    result = mock.invoke_structured(
        system_prompt="s",
        user_prompt="u",
        response_model=IssueAnalysis,
        trace_context=ctx,
    )
    assert result.issue_category == "transaction"


def test_happy_path_investigation_plan() -> None:
    mock = MockLLMClient()
    mock.use_profile("happy_path")
    repo, tracer, task_id = _tracer_ctx()
    ctx = {"task_id": task_id, "node_name": "task_planner", "tracer": tracer}
    plan = mock.invoke_structured(
        system_prompt="s",
        user_prompt="u",
        response_model=InvestigationPlan,
        trace_context=ctx,
    )
    assert 3 <= len(plan.steps) <= 6


def test_happy_path_rca_has_evidence() -> None:
    mock = MockLLMClient()
    mock.use_profile("happy_path")
    rca = get_profile_response("happy_path", RootCauseAnalysis)
    assert rca is not None
    assert rca.diagnosis_status == "complete"
    assert len(rca.candidates) >= 1
    ev = rca.candidates[0].evidence[0]
    assert ev.file == HAPPY_PATH_FILE


def test_insufficient_evidence_profile() -> None:
    mock = MockLLMClient()
    mock.use_profile("insufficient_evidence")
    repo, tracer, task_id = _tracer_ctx()
    ctx = {"task_id": task_id, "node_name": "root_cause_analyzer", "tracer": tracer}
    rca = mock.invoke_structured(
        system_prompt="s",
        user_prompt="u",
        response_model=RootCauseAnalysis,
        trace_context=ctx,
    )
    assert rca.diagnosis_status == "insufficient_evidence"
    assert len(rca.candidates) == 0


def test_invalid_evidence_profile_returns_fabricated_file() -> None:
    mock = MockLLMClient()
    mock.use_profile("invalid_evidence")
    rca = get_profile_response("invalid_evidence", RootCauseAnalysis)
    assert rca is not None
    ev = rca.candidates[0].evidence[0]
    assert ev.file == "NonExistentService.java"


def test_timeout_profile_raises() -> None:
    mock = MockLLMClient()
    mock.use_profile("timeout")
    repo, tracer, task_id = _tracer_ctx()
    ctx = {"task_id": task_id, "node_name": "issue_parser", "tracer": tracer}
    with pytest.raises(RetryableError):
        mock.invoke_structured(
            system_prompt="s",
            user_prompt="u",
            response_model=IssueAnalysis,
            trace_context=ctx,
        )


def test_invalid_json_profile_raises() -> None:
    mock = MockLLMClient()
    mock.use_profile("invalid_json")
    repo, tracer, task_id = _tracer_ctx()
    ctx = {"task_id": task_id, "node_name": "issue_parser", "tracer": tracer}
    with pytest.raises(SchemaValidationError):
        mock.invoke_structured(
            system_prompt="s",
            user_prompt="u",
            response_model=IssueAnalysis,
            trace_context=ctx,
        )


def test_failure_profile_classification() -> None:
    assert is_failure_profile("timeout") is True
    assert is_failure_profile("invalid_json") is True
    assert is_failure_profile("happy_path") is False


def test_unknown_profile_raises() -> None:
    mock = MockLLMClient()
    with pytest.raises(ValueError):
        mock.use_profile("bogus")


def test_set_response_overrides_profile() -> None:
    """Explicit set_response wins over Profile."""
    mock = MockLLMClient()
    mock.use_profile("happy_path")
    mock.set_response(IssueAnalysis(issue_category="unknown", summary="override"))
    repo, tracer, task_id = _tracer_ctx()
    ctx = {"task_id": task_id, "node_name": "issue_parser", "tracer": tracer}
    result = mock.invoke_structured(
        system_prompt="s",
        user_prompt="u",
        response_model=IssueAnalysis,
        trace_context=ctx,
    )
    assert result.issue_category == "unknown"
