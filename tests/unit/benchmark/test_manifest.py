"""Tests for M4B manifest models, loader, and gold-field isolation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from springfix_agent.benchmark.loader import BenchmarkManifestError, load_cases
from springfix_agent.benchmark.models import BenchmarkCase, EvidenceTarget

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MANIFEST = PROJECT_ROOT / "benchmark" / "agent_cases.jsonl"


def test_manifest_loads_three_cases() -> None:
    cases = load_cases(MANIFEST)
    assert [case.case_id for case in cases] == [
        "transaction-self-invocation",
        "no-unique-bean-definition",
        "configuration-properties-prefix-mismatch",
    ]
    assert all(set(case.agent_input()) == {"repository", "issue_description", "error_log"}
               for case in cases)


def test_gold_fields_are_not_in_agent_projection() -> None:
    case = load_cases(MANIFEST)[0]
    agent_input = case.agent_input()
    assert "expected_files" not in agent_input
    assert "evidence_targets" not in agent_input
    assert "expected_maven" not in agent_input


def test_duplicate_case_id_is_rejected(tmp_path: Path) -> None:
    first = json.loads(MANIFEST.read_text(encoding="utf-8").splitlines()[0])
    manifest = tmp_path / "duplicate.jsonl"
    manifest.write_text(json.dumps(first) + "\n" + json.dumps(first), encoding="utf-8")
    with pytest.raises(BenchmarkManifestError, match="duplicate case_id"):
        load_cases(manifest)


def test_invalid_evidence_range_is_rejected() -> None:
    with pytest.raises(ValidationError, match="end_line"):
        EvidenceTarget(
            file="src/Main.java",
            start_line=4,
            end_line=3,
            required_text=["class"],
        )


def test_non_empty_required_text_is_enforced() -> None:
    with pytest.raises(ValidationError, match="required_text"):
        EvidenceTarget(
            file="src/Main.java",
            start_line=1,
            end_line=1,
            required_text=[],
        )


def test_repository_absolute_path_is_rejected() -> None:
    with pytest.raises(ValidationError, match="relative path"):
        BenchmarkCase(
            case_id="case",
            repository="C:/outside",
            issue_description="A valid issue description.",
            expected_issue_category="configuration",
            expected_diagnosis_status="complete",
            expected_files=["src/Main.java"],
            expected_symbols=["Main"],
            evidence_targets=[
                EvidenceTarget(
                    file="src/Main.java",
                    start_line=1,
                    end_line=1,
                    required_text=["class"],
                )
            ],
            expected_maven={
                "test_name": "testMain",
                "tests": 1,
                "failures": 1,
                "errors": 0,
                "skipped": 0,
            },
        )


def test_expected_file_parent_traversal_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must not contain"):
        BenchmarkCase(
            case_id="case",
            repository="samples/case",
            issue_description="A valid issue description.",
            expected_issue_category="configuration",
            expected_diagnosis_status="complete",
            expected_files=["../outside.java"],
            expected_symbols=["Main"],
            evidence_targets=[
                EvidenceTarget(
                    file="src/Main.java",
                    start_line=1,
                    end_line=1,
                    required_text=["class"],
                )
            ],
            expected_maven={
                "test_name": "testMain",
                "tests": 1,
                "failures": 1,
                "errors": 0,
                "skipped": 0,
            },
        )
