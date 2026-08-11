"""Deterministic Repair Gold/evaluator tests."""

from __future__ import annotations

from pathlib import Path

from springfix_agent.repair.evaluator import (
    RepairGold,
    aggregate_repair_metrics,
    evaluate_repair_proposal,
)
from springfix_agent.repair.models import EvidenceSnippet, PatchEdit, PatchProposal
from springfix_agent.repair.validator import validate_patch_proposal


def _validated(*edits: PatchEdit):
    root = Path(__file__).resolve().parents[3] / "samples" / "sample-springboot-bug-configuration-properties-prefix-mismatch"
    evidence = [EvidenceSnippet(file="src/main/resources/application.yml", start_line=1, end_line=3, content="code")]
    return validate_patch_proposal(
        PatchProposal(
            status="proposed",
            summary="Align the configuration hierarchy and springfix.mail prefix.",
            root_cause_reference="candidate:0",
            edits=list(edits),
        ),
        root,
        evidence,
    )


def test_evaluator_hits_acceptable_concept_and_aggregate() -> None:
    validation = _validated(
        PatchEdit(
            file="src/main/resources/application.yml",
            start_line=2,
            end_line=2,
            old_code="  email:",
            new_code="  mail:",
            rationale="Align springfix.email with springfix.mail prefix.",
        )
    )
    gold = RepairGold(
        case_id="configuration-properties-prefix-mismatch",
        acceptable_files=["src/main/resources/application.yml"],
        acceptable_change_concepts=["prefix alignment"],
        forbidden_files=["README.md", "src/test"],
    )
    result = evaluate_repair_proposal(
        gold,
        validation,
        model="mock-fixed",
        diagnostic_llm_calls=3,
        patch_llm_calls=1,
        http_attempts=4,
        input_tokens=None,
        output_tokens=None,
        duration_ms=1,
    )
    aggregate = aggregate_repair_metrics([result])
    assert result.metrics.acceptable_change_concept_hit
    assert result.metrics.proposal_validation_passed
    assert aggregate.proposal_validation_rate == 1.0
    assert aggregate.unsafe_proposal_rate == 0.0


def test_evaluator_marks_forbidden_file_edits() -> None:
    root = Path(__file__).resolve().parents[3] / "samples" / "sample-springboot-bug-configuration-properties-prefix-mismatch"
    validation = validate_patch_proposal(
        PatchProposal(
            status="proposed",
            summary="bad",
            root_cause_reference="candidate:0",
            edits=[],
        ),
        root,
        [],
    )
    gold = RepairGold(
        case_id="case",
        acceptable_files=["src/main/resources/application.yml"],
        acceptable_change_concepts=["prefix"],
        forbidden_files=["README.md"],
    )
    result = evaluate_repair_proposal(
        gold,
        validation,
        model="mock-fixed",
        diagnostic_llm_calls=0,
        patch_llm_calls=0,
        http_attempts=0,
        input_tokens=None,
        output_tokens=None,
        duration_ms=0,
    )
    assert not result.metrics.proposal_generated
    assert not result.metrics.forbidden_file_edits
