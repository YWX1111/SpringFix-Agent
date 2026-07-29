"""TaskPlanner node tests.

Covers:
    15. Output 3-6 steps
    16. Reject plan containing shell commands
    17. LLM failure uses deterministic fallback
    18. Search terms / target symbols are capped
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from springfix_agent.graph.nodes.task_planner import task_planner
from springfix_agent.llm.mock import MockLLMClient
from springfix_agent.llm.schemas import (
    InvestigationPlan,
    InvestigationStep,
    IssueAnalysis,
)
from springfix_agent.observability.in_memory_tracer import InMemoryTracer
from springfix_agent.storage.in_memory import InMemoryTaskRepository


def _state(**overrides):
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
            "extracted_symbols": ["OrderService"],
            "search_terms": ["@Transactional"],
        },
        "extracted_symbols": ["OrderService"],
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
        "current_node": "task_planner",
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


def test_task_planner_returns_3_to_6_steps() -> None:
    """Case 15: plan has between 3 and 6 steps."""
    mock = MockLLMClient()
    mock.set_response(
        InvestigationPlan(
            steps=[
                InvestigationStep(step_id=1, objective="o1", rationale="r1"),
                InvestigationStep(step_id=2, objective="o2", rationale="r2"),
                InvestigationStep(step_id=3, objective="o3", rationale="r3"),
                InvestigationStep(step_id=4, objective="o4", rationale="r4"),
            ]
        )
    )
    tracer = _tracer()
    result = task_planner(_state(), llm=mock, tracer=tracer)
    steps = result["investigation_plan"]["steps"]
    assert 3 <= len(steps) <= 6


def test_task_planner_rejects_shell_commands_in_plan() -> None:
    """Case 16: plans containing shell commands fail validation."""
    with pytest.raises(ValidationError):
        InvestigationStep(
            step_id=1,
            objective="run mvn test",
            rationale="r",
        )
    with pytest.raises(ValidationError):
        InvestigationStep(
            step_id=1,
            objective="o",
            rationale="then run bash -x script.sh",
        )


def test_task_planner_falls_back_on_llm_failure() -> None:
    """Case 17: LLM failure uses deterministic fallback plan."""
    mock = MockLLMClient()
    mock.set_behavior("timeout", for_model=InvestigationPlan, n=1)
    tracer = _tracer()
    result = task_planner(_state(), llm=mock, tracer=tracer)
    steps = result["investigation_plan"]["steps"]
    assert 3 <= len(steps) <= 6
    # Fallback plan does not contain shell commands
    for step in steps:
        assert "mvn" not in step["objective"].lower()
    # Warning is recorded
    assert any("fallback" in w for w in result["warnings"])


def test_task_planner_caps_search_terms_and_symbols() -> None:
    """Case 18: excessive terms / symbols are trimmed."""
    plan = InvestigationPlan(
        steps=[
            InvestigationStep(
                step_id=1,
                objective="o",
                rationale="r",
                search_terms=[f"t{i}" for i in range(50)],
                target_symbols=[f"s{i}" for i in range(50)],
                expected_evidence=[f"e{i}" for i in range(50)],
            ),
            InvestigationStep(step_id=2, objective="o2", rationale="r2"),
            InvestigationStep(step_id=3, objective="o3", rationale="r3"),
        ]
    )
    assert len(plan.steps[0].search_terms) <= 8
    assert len(plan.steps[0].target_symbols) <= 6
    assert len(plan.steps[0].expected_evidence) <= 6


# Silence unused import for mypy.
_ = IssueAnalysis
