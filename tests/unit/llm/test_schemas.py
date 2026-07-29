"""LLM schemas validation tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from springfix_agent.llm.schemas import (
    EvidenceReference,
    InvestigationPlan,
    InvestigationStep,
    IssueAnalysis,
    RootCauseAnalysis,
    RootCauseCandidate,
)


def test_issue_analysis_rejects_unknown_category() -> None:
    with pytest.raises(ValidationError):
        IssueAnalysis(issue_category="bogus", summary="s")


def test_issue_analysis_accepts_unknown_category() -> None:
    analysis = IssueAnalysis(issue_category="unknown", summary="s")
    assert analysis.issue_category == "unknown"


def test_issue_analysis_trims_long_symbols() -> None:
    analysis = IssueAnalysis(
        issue_category="unknown",
        summary="s",
        extracted_symbols=[f"sym{i}" for i in range(50)],
    )
    assert len(analysis.extracted_symbols) <= 15


def test_investigation_plan_rejects_wrong_step_ids() -> None:
    with pytest.raises(ValidationError):
        InvestigationPlan(
            steps=[
                InvestigationStep(step_id=2, objective="o", rationale="r"),
                InvestigationStep(step_id=1, objective="o", rationale="r"),
                InvestigationStep(step_id=3, objective="o", rationale="r"),
            ]
        )


def test_investigation_plan_rejects_too_few_steps() -> None:
    with pytest.raises(ValidationError):
        InvestigationPlan(
            steps=[
                InvestigationStep(step_id=1, objective="o", rationale="r"),
                InvestigationStep(step_id=2, objective="o", rationale="r"),
            ]
        )


def test_investigation_step_rejects_shell_command() -> None:
    with pytest.raises(ValidationError):
        InvestigationStep(
            step_id=1,
            objective="o",
            rationale="run mvn test to check",
        )


def test_evidence_reference_end_ge_start() -> None:
    with pytest.raises(ValidationError):
        EvidenceReference(file="f.java", start_line=10, end_line=5, explanation="e")


def test_root_cause_candidate_rejects_empty_evidence() -> None:
    with pytest.raises(ValidationError):
        RootCauseCandidate(
            title="t",
            description="d",
            confidence="high",
            evidence=[],
            recommended_fix="f",
        )


def test_root_cause_candidate_rejects_shell_in_fix() -> None:
    with pytest.raises(ValidationError):
        RootCauseCandidate(
            title="t",
            description="d",
            confidence="high",
            evidence=[EvidenceReference(file="f", start_line=1, end_line=2, explanation="e")],
            recommended_fix="run mvn clean install",
        )


def test_root_cause_analysis_caps_candidates() -> None:
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


def test_insufficient_evidence_clears_candidates() -> None:
    """An insufficient diagnosis cannot expose an evidence-backed root cause."""
    analysis = RootCauseAnalysis(
        diagnosis_status="insufficient_evidence",
        summary="Repository evidence does not cover the reported subsystem.",
        candidates=[
            RootCauseCandidate(
                title="Unsupported hypothesis",
                description="The repository does not contain the reported integration.",
                confidence="low",
                evidence=[
                    EvidenceReference(
                        file="pom.xml",
                        start_line=1,
                        end_line=2,
                        explanation="The dependency is absent.",
                    )
                ],
                recommended_fix="Collect the missing implementation details.",
            )
        ],
        missing_information=["The relevant implementation is missing."],
    )
    assert analysis.candidates == []
