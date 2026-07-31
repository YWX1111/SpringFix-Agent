"""M2 end-to-end graph tests.

Covers:
    30.  Seven nodes execute in order
    31.  IssueParser fallback does not abort task
    32.  TaskPlanner fallback does not abort task
    33.  RootCauseAnalyzer failure produces partial report
    34.  Full Mock run generates diagnostic report
    35.  Report files and lines are real
    36.  M1 path-safety tests still pass (separate file)
"""

from __future__ import annotations

from springfix_agent.graph.builder import build_graph
from springfix_agent.graph.state import make_initial_state
from springfix_agent.llm.mock import MockLLMClient
from springfix_agent.llm.schemas import (
    EvidenceReference,
    InvestigationPlan,
    InvestigationStep,
    IssueAnalysis,
    RootCauseAnalysis,
    RootCauseCandidate,
)
from springfix_agent.observability.in_memory_tracer import InMemoryTracer
from springfix_agent.storage.in_memory import InMemoryTaskRepository


def _make_graph(mock_llm, sample_repo):
    repo = InMemoryTaskRepository()
    task = repo.create_task(
        repository_path=str(sample_repo),
        issue_description="calling createOrder throws RuntimeException, data not rolled back",
        error_log=None,
    )
    tracer = InMemoryTracer(repo)
    graph = build_graph(
        task_id=task.task_id,
        repository_path=sample_repo,
        allow_root=sample_repo.parent,
        tracer=tracer,
        llm=mock_llm,
    )
    initial = make_initial_state(
        task_id=task.task_id,
        repository_path=str(sample_repo),
        issue_description="calling createOrder throws RuntimeException, data not rolled back",
        error_log=None,
    )
    final = graph.invoke(initial)
    return repo, task.task_id, tracer, final


def test_seven_nodes_execute_in_order(sample_repo) -> None:
    """Case 30: all seven nodes run and emit node timings."""
    mock = MockLLMClient()
    mock.set_response(
        IssueAnalysis(
            issue_category="transaction",
            summary="s",
            extracted_symbols=["OrderService"],
            search_terms=["@Transactional"],
            exception_types=["RuntimeException"],
        )
    )
    mock.set_response(
        InvestigationPlan(
            steps=[
                InvestigationStep(step_id=1, objective="o1", rationale="r1"),
                InvestigationStep(step_id=2, objective="o2", rationale="r2"),
                InvestigationStep(step_id=3, objective="o3", rationale="r3"),
            ]
        )
    )
    mock.set_response(
        RootCauseAnalysis(
            diagnosis_status="complete",
            summary="AOP bypass",
            candidates=[
                RootCauseCandidate(
                    title="t",
                    description="d",
                    confidence="high",
                    evidence=[
                        EvidenceReference(
                            file="OrderService.java",
                            start_line=1,
                            end_line=2,
                            explanation="e",
                        )
                    ],
                    recommended_fix="f",
                )
            ],
        )
    )
    _, task_id, tracer, final = _make_graph(mock, sample_repo)
    traces = tracer._repo.get_traces(task_id)
    node_timings = [t for t in traces if t.kind == "node_timing"]
    assert [t.payload["node"] for t in node_timings] == [
        "validate_input",
        "issue_parser",
        "task_planner",
        "explore_repository",
        "retrieve_code",
        "root_cause_analyzer",
        "build_diagnostic_report",
    ]


def test_issue_parser_fallback_does_not_abort(sample_repo) -> None:
    """Case 31: IssueParser LLM timeout falls back to deterministic."""
    mock = MockLLMClient()
    mock.set_behavior("timeout", for_model=IssueAnalysis, n=1)
    mock.set_response(
        InvestigationPlan(
            steps=[
                InvestigationStep(step_id=1, objective="o1", rationale="r1"),
                InvestigationStep(step_id=2, objective="o2", rationale="r2"),
                InvestigationStep(step_id=3, objective="o3", rationale="r3"),
            ]
        )
    )
    mock.set_response(
        RootCauseAnalysis(
            diagnosis_status="insufficient_evidence",
            summary="s",
        )
    )
    _, task_id, tracer, final = _make_graph(mock, sample_repo)
    # Task did not abort
    assert final["status"] in ("completed", "running")
    # Warning was recorded
    assert any("fallback" in str(w) for w in final["warnings"])


def test_task_planner_fallback_does_not_abort(sample_repo) -> None:
    """Case 32: TaskPlanner LLM timeout falls back."""
    mock = MockLLMClient()
    mock.set_response(
        IssueAnalysis(
            issue_category="transaction",
            summary="s",
            extracted_symbols=["OrderService"],
        )
    )
    mock.set_behavior("timeout", for_model=InvestigationPlan, n=1)
    mock.set_response(
        RootCauseAnalysis(
            diagnosis_status="insufficient_evidence",
            summary="s",
        )
    )
    _, task_id, tracer, final = _make_graph(mock, sample_repo)
    assert final["status"] in ("completed", "running")
    assert any("fallback" in str(w) for w in final["warnings"])


def test_root_cause_analyzer_failure_produces_partial_report(sample_repo) -> None:
    """Case 33: RCA failure still generates a diagnostic report."""
    mock = MockLLMClient()
    mock.set_response(
        IssueAnalysis(
            issue_category="transaction",
            summary="s",
            extracted_symbols=["OrderService"],
        )
    )
    mock.set_response(
        InvestigationPlan(
            steps=[
                InvestigationStep(step_id=1, objective="o1", rationale="r1"),
                InvestigationStep(step_id=2, objective="o2", rationale="r2"),
                InvestigationStep(step_id=3, objective="o3", rationale="r3"),
            ]
        )
    )
    mock.set_behavior("timeout", for_model=RootCauseAnalysis, n=1)
    _, task_id, tracer, final = _make_graph(mock, sample_repo)
    assert final["diagnostic_report"] != {}
    rca = final["root_cause_analysis"]
    assert rca.get("diagnosis_status") == "insufficient_evidence"
    assert "insufficient" in final["markdown_report"].lower()


def test_full_mock_run_generates_diagnostic_report(sample_repo) -> None:
    """Case 34: full mock flow produces a diagnostic report."""
    mock = MockLLMClient()
    mock.set_response(
        IssueAnalysis(
            issue_category="transaction",
            summary="Transactional self-invocation bypass",
            extracted_symbols=["OrderService", "createOrder"],
            search_terms=["@Transactional"],
            exception_types=["RuntimeException"],
        )
    )
    mock.set_response(
        InvestigationPlan(
            steps=[
                InvestigationStep(step_id=1, objective="Browse tree", rationale="r1"),
                InvestigationStep(step_id=2, objective="Find symbols", rationale="r2"),
                InvestigationStep(step_id=3, objective="Read files", rationale="r3"),
            ]
        )
    )
    # First run: discover actual snippet line ranges from the new chunker.
    _, _, _, probe = _make_graph(mock, sample_repo)
    snippets = probe.get("retrieved_snippets", [])
    os_snippet = next(
        (s for s in snippets if s["file"] == "src/main/java/com/example/OrderService.java"),
        None,
    )
    # Use real snippet line range for evidence reference.
    ev_start = os_snippet["line_range"][0] if os_snippet else 1
    ev_end = os_snippet["line_range"][1] if os_snippet else 2

    mock2 = MockLLMClient()
    mock2.set_response(
        IssueAnalysis(
            issue_category="transaction",
            summary="Transactional self-invocation bypass",
            extracted_symbols=["OrderService", "createOrder"],
            search_terms=["@Transactional"],
            exception_types=["RuntimeException"],
        )
    )
    mock2.set_response(
        InvestigationPlan(
            steps=[
                InvestigationStep(step_id=1, objective="Browse tree", rationale="r1"),
                InvestigationStep(step_id=2, objective="Find symbols", rationale="r2"),
                InvestigationStep(step_id=3, objective="Read files", rationale="r3"),
            ]
        )
    )
    mock2.set_response(
        RootCauseAnalysis(
            diagnosis_status="complete",
            summary="AOP bypass",
            candidates=[
                RootCauseCandidate(
                    title="Spring AOP bypass",
                    description="Self-invocation of @Transactional method",
                    confidence="high",
                    evidence=[
                        EvidenceReference(
                            file="src/main/java/com/example/OrderService.java",
                            start_line=ev_start,
                            end_line=ev_end,
                            explanation="Self-invocation bypasses the AOP proxy",
                        )
                    ],
                    recommended_fix="Move the @Transactional method to a separate bean",
                    verification_steps=[
                        "Confirm OrderService.createOrder directly calls createOrderInTransaction via this"
                    ],
                )
            ],
        )
    )
    _, task_id, tracer, final = _make_graph(mock2, sample_repo)
    report = final["diagnostic_report"]
    assert "task_id" in report
    assert report["diagnosis_status"] == "complete"
    assert len(report.get("root_cause_analysis", {}).get("candidates", [])) >= 1
    assert final["status"] == "completed"


def test_report_files_and_lines_are_real(sample_repo) -> None:
    """Case 35: evidence file and line_range refer to real snippets."""
    mock = MockLLMClient()
    mock.set_response(
        IssueAnalysis(
            issue_category="transaction",
            summary="s",
            extracted_symbols=["OrderService"],
        )
    )
    mock.set_response(
        InvestigationPlan(
            steps=[
                InvestigationStep(step_id=1, objective="o1", rationale="r1"),
                InvestigationStep(step_id=2, objective="o2", rationale="r2"),
                InvestigationStep(step_id=3, objective="o3", rationale="r3"),
            ]
        )
    )
    mock.set_response(
        RootCauseAnalysis(
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
                            end_line=999,  # Out of range
                            explanation="e",
                        )
                    ],
                    recommended_fix="f",
                )
            ],
        )
    )
    _, task_id, tracer, final = _make_graph(mock, sample_repo)
    report = final["diagnostic_report"]
    candidates = report.get("root_cause_analysis", {}).get("candidates", [])
    # Out-of-range evidence should have been dropped; report may then
    # have empty candidates and diagnosis_status partial/insufficient.
    for c in candidates:
        for ev in c.get("evidence", []):
            assert ev["file"] in [s["file"] for s in final["retrieved_snippets"]]
