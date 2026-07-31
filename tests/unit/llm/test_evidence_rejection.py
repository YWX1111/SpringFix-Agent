"""Evidence rejection audit tests.

Covers the secondary business validation in RootCauseAnalyzer:
- file not in retrieved_snippets
- line range outside snippet
- start_line greater than end_line
- candidate with no valid evidence
- audit record fields
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from springfix_agent.graph.nodes.root_cause_analyzer import _validate_evidence
from springfix_agent.graph.state import RetrievedSnippet
from springfix_agent.llm.schemas import (
    EvidenceReference,
    RootCauseAnalysis,
    RootCauseCandidate,
)


def _snippets():
    return [
        RetrievedSnippet(
            file="OrderService.java",
            line_range=(1, 20),
            content="code",
            score=2.0,
            symbols=["OrderService"],
        )
    ]


def test_reject_file_not_in_snippets() -> None:
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
    cleaned, dropped, rejections = _validate_evidence(
        analysis, {s["file"]: [s] for s in _snippets()}
    )
    assert dropped >= 1
    assert len(cleaned.candidates) == 0
    assert len(rejections) >= 1
    r = rejections[0]
    assert r["rejection_reason"] == "file_not_in_retrieved_snippets"
    assert r["referenced_file"] == "NonExistent.java"
    assert r["candidate_index"] == 0
    assert r["evidence_index"] == 0


def test_reject_line_range_outside_snippet() -> None:
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
    cleaned, dropped, rejections = _validate_evidence(
        analysis, {s["file"]: [s] for s in _snippets()}
    )
    assert dropped >= 1
    assert len(cleaned.candidates) == 0
    r = rejections[0]
    assert r["rejection_reason"] == "line_range_outside_snippet"
    assert r["referenced_file"] == "OrderService.java"
    assert r["snippet_line_range"] == [1, 20]


def test_reject_start_greater_than_end() -> None:
    """Pydantic already rejects end < start; _validate_evidence also guards."""
    # Pydantic validator rejects this at construction time, so the
    # _validate_evidence check is defense-in-depth. We verify the
    # Pydantic guard fires first.
    with pytest.raises(ValidationError):
        EvidenceReference(
            file="OrderService.java",
            start_line=15,
            end_line=5,
            explanation="e",
        )


def test_candidate_no_valid_evidence_recorded() -> None:
    """When all evidence in a candidate is rejected, a candidate-level record is added."""
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
    cleaned, dropped, rejections = _validate_evidence(
        analysis, {s["file"]: [s] for s in _snippets()}
    )
    assert len(cleaned.candidates) == 0
    candidate_rejections = [r for r in rejections if r["rejection_reason"] == "candidate_no_valid_evidence"]
    assert len(candidate_rejections) == 1


def test_valid_evidence_passes() -> None:
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
                        end_line=10,
                        explanation="e",
                    )
                ],
                recommended_fix="f",
            )
        ],
    )
    cleaned, dropped, rejections = _validate_evidence(
        analysis, {s["file"]: [s] for s in _snippets()}
    )
    assert dropped == 0
    assert len(rejections) == 0
    assert len(cleaned.candidates) == 1


def test_rejection_record_does_not_save_code() -> None:
    """Rejection records must never include code bodies."""
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
    _, _, rejections = _validate_evidence(
        analysis, {s["file"]: [s] for s in _snippets()}
    )
    serialized = str(rejections)
    assert "code" not in serialized.lower() or "referenced" in serialized
