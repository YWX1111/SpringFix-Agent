"""M6B bounded proposal observability fixtures and regression tests."""

from __future__ import annotations

import json
from pathlib import Path

from springfix_agent.llm._retry import MaxRetriesExceeded, RetryableError, SchemaValidationError
from springfix_agent.llm.mock import MockLLMClient
from springfix_agent.observability.in_memory_tracer import InMemoryTracer
from springfix_agent.repair.generator import PatchProposalService
from springfix_agent.repair.models import PatchEdit, PatchProposal
from springfix_agent.repair.observability import classify_proposal_exception
from springfix_agent.storage.in_memory import InMemoryTaskRepository


def _root_cause() -> dict[str, object]:
    return {
        "diagnosis_status": "complete",
        "summary": "A transactional method is called internally.",
        "candidates": [
            {
                "title": "proxy bypass",
                "evidence": [
                    {
                        "file": "src/main/java/App.java",
                        "start_line": 2,
                        "end_line": 2,
                        "explanation": "validated fixture line",
                    }
                ],
            }
        ],
    }


def _repository(tmp_path: Path) -> tuple[Path, list[dict[str, object]]]:
    root = tmp_path / "repo"
    source = root / "src" / "main" / "java" / "App.java"
    source.parent.mkdir(parents=True)
    source.write_text("line one\nline two\n", encoding="utf-8")
    snippets = [{"file": "src/main/java/App.java", "line_range": (1, 2), "content": "line one\nline two"}]
    return root, snippets


def _tracer(root: Path) -> tuple[InMemoryTaskRepository, InMemoryTracer, str]:
    repository = InMemoryTaskRepository()
    task = repository.create_task(
        repository_path=root.as_posix(),
        issue_description="fixture issue",
        error_log=None,
    )
    return repository, InMemoryTracer(repository), task.task_id


def _run_service(
    tmp_path: Path,
    mock: MockLLMClient,
) -> tuple[object, InMemoryTaskRepository, str]:
    root, snippets = _repository(tmp_path)
    repository, tracer, task_id = _tracer(root)
    result = PatchProposalService(mock).propose(
        repository_root=root,
        root_cause_analysis=_root_cause(),
        retrieved_snippets=snippets,
        task_id=task_id,
        tracer=tracer,
    )
    return result, repository, task_id


def test_explicit_insufficient_evidence_is_distinct_from_parser_failure(tmp_path: Path) -> None:
    mock = MockLLMClient()
    mock.set_response(
        PatchProposal(
            status="insufficient_evidence",
            summary="The evidence does not identify a safe edit.",
            root_cause_reference="none",
        )
    )
    result, repository, task_id = _run_service(tmp_path, mock)
    audit = result.proposal_generation_audit.model_dump()
    assert audit["failure_category"] == "proposal_status_insufficient_evidence"
    assert audit["logical_llm_calls"] == 1
    assert audit["parse_attempts"] == 1
    assert audit["parse_success"] is True
    assert audit["schema_success"] is True
    assert audit["outcome"] == "insufficient_evidence"
    assert audit["structured_parse_succeeded"] is True
    assert audit["schema_validation_succeeded"] is True
    trace_payloads = [
        trace.payload for trace in repository.get_traces(task_id) if trace.kind == "llm_call"
    ]
    assert trace_payloads[0]["proposal_audit"]["failure_category"] == (
        "proposal_status_insufficient_evidence"
    )
    assert "raw_response" not in json.dumps(trace_payloads)


def test_unsafe_proposal_is_recorded_as_unsafe(tmp_path: Path) -> None:
    mock = MockLLMClient()
    mock.set_response(
        PatchProposal(
            status="unsafe_to_propose",
            summary="The requested change is unsafe.",
            root_cause_reference="candidate:0",
        )
    )
    result, _, _ = _run_service(tmp_path, mock)
    assert result.proposal_generation_audit.failure_category == "proposal_status_unsafe"


def test_invalid_json_schema_and_provider_timeout_keep_distinct_categories(tmp_path: Path) -> None:
    for behavior, category in (
        ("invalid_json", "invalid_json"),
        ("schema_error", "schema_validation_failure"),
        ("timeout", "provider_timeout"),
    ):
        mock = MockLLMClient()
        mock.set_behavior(behavior, for_model=PatchProposal)  # type: ignore[arg-type]
        result, repository, task_id = _run_service(tmp_path / behavior, mock)
        audit = result.proposal_generation_audit
        assert audit.failure_category == category
        assert audit.source_exception_class in {"SchemaValidationError", "RetryableError"}
        payload_text = json.dumps([trace.payload for trace in repository.get_traces(task_id)])
        assert "raw_response" not in payload_text
        assert "system_prompt" not in payload_text


def test_all_rejected_edits_are_classified_after_deterministic_validation(tmp_path: Path) -> None:
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
                    old_code="not the source",
                    new_code="changed",
                    rationale="fixture rejection",
                )
            ],
        )
    )
    result, _, _ = _run_service(tmp_path, mock)
    assert result.validation.accepted_edit_count == 0
    assert result.validation.original_edit_count == (
        result.validation.accepted_edit_count + result.validation.rejected_edit_count
    )
    assert result.validation.passed is False
    assert result.proposal_generation_audit.failure_category == "validator_no_valid_edits"
    assert result.proposal_generation_audit.failure_detail == "all_edits_rejected"
    assert result.proposal_generation_audit.outcome == "validator_rejected_all_edits"


def test_exception_classifier_does_not_use_insufficient_evidence_for_other_failures() -> None:
    timeout = MaxRetriesExceeded("exhausted")
    timeout.__cause__ = RetryableError("upstream timeout")
    assert classify_proposal_exception(timeout)[0] == "provider_timeout"
    assert classify_proposal_exception(MaxRetriesExceeded("exhausted"))[0] == "provider_failure"
    assert classify_proposal_exception(SchemaValidationError("expected object"))[0] == "structured_parse_failure"
    assert classify_proposal_exception(ValueError("bad internal state"))[0] == "internal_error"
