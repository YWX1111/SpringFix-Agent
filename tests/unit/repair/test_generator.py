"""Generator, no-evidence, prompt-boundary, and service tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from springfix_agent.llm.mock import MockLLMClient
from springfix_agent.repair.generator import PatchProposalGenerator, PatchProposalService
from springfix_agent.repair.models import EvidenceSnippet, PatchEdit, PatchProposal


def _rca() -> dict[str, object]:
    return {
        "diagnosis_status": "complete",
        "summary": "A transactional method is called internally.",
        "candidates": [
            {
                "title": "proxy bypass",
                "description": "self invocation bypasses AOP",
                "evidence": [
                    {
                        "file": "src/main/java/App.java",
                        "start_line": 2,
                        "end_line": 2,
                        "explanation": "real line",
                    }
                ],
            }
        ],
    }


def _evidence() -> list[EvidenceSnippet]:
    return [EvidenceSnippet(file="src/main/java/App.java", start_line=2, end_line=2, content="line two")]


def test_generator_returns_insufficient_without_evidence() -> None:
    mock = MockLLMClient()
    proposal = PatchProposalGenerator(mock).generate(root_cause_analysis=_rca(), validated_evidence=[])
    assert proposal.status == "insufficient_evidence"
    assert proposal.edits == []


def test_generator_structured_mock_response_and_one_patch_call() -> None:
    mock = MockLLMClient()
    mock.set_response(
        PatchProposal(
            status="proposed",
            summary="add annotation",
            root_cause_reference="candidate:0",
            edits=[
                PatchEdit(
                    file="src/main/java/App.java",
                    start_line=2,
                    end_line=2,
                    old_code="line two",
                    new_code="@Transactional\nline two",
                    rationale="proxy boundary",
                )
            ],
        )
    )
    proposal = PatchProposalGenerator(mock).generate(
        root_cause_analysis=_rca(), validated_evidence=_evidence()
    )
    assert proposal.status == "proposed"
    assert proposal.edits[0].old_code == "line two"


@pytest.mark.parametrize("behavior", ["timeout", "invalid_json"])
def test_generator_failure_degrades_without_applying(behavior: str) -> None:
    mock = MockLLMClient()
    mock.set_behavior(behavior, for_model=PatchProposal, n=1)  # type: ignore[arg-type]
    proposal = PatchProposalGenerator(mock).generate(
        root_cause_analysis=_rca(), validated_evidence=_evidence()
    )
    assert proposal.status == "insufficient_evidence"
    assert proposal.edits == []


class _PromptCapture(MockLLMClient):
    def __init__(self) -> None:
        super().__init__()
        self.prompt = ""

    def invoke_structured(self, **kwargs):  # type: ignore[no-untyped-def]
        self.prompt = str(kwargs["user_prompt"])
        return super().invoke_structured(**kwargs)


def test_patch_prompt_contains_only_validated_inputs() -> None:
    mock = _PromptCapture()
    PatchProposalGenerator(mock).generate(root_cause_analysis=_rca(), validated_evidence=_evidence())
    assert "line two" in mock.prompt
    assert "expected_files" not in mock.prompt
    assert "Benchmark Gold" not in mock.prompt
    assert "README" in mock.prompt


def test_service_materializes_real_evidence_and_validates_old_code(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    path = root / "src/main/java/App.java"
    path.parent.mkdir(parents=True)
    path.write_text("line one\nline two\n", encoding="utf-8")
    mock = MockLLMClient()
    mock.set_response(
        PatchProposal(
            status="proposed",
            summary="change",
            root_cause_reference="candidate:0",
            edits=[
                PatchEdit(
                    file="src/main/java/App.java",
                    start_line=2,
                    end_line=2,
                    old_code="line two",
                    new_code="line changed",
                    rationale="minimal",
                )
            ],
        )
    )
    result = PatchProposalService(mock).propose(
        repository_root=root,
        root_cause_analysis=_rca(),
        retrieved_snippets=[
            {"file": "src/main/java/App.java", "line_range": (1, 2), "content": "line one\nline two"}
        ],
    )
    assert result.proposal.status == "proposed"
    assert result.validation.passed
    assert result.evidence[0].content == "line two"
