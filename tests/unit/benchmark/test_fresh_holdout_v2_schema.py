"""Fresh Holdout v2 schema and legacy compatibility tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from scripts.m7f1.fresh_holdout_v2_loader import FreshHoldoutV2Loader
from scripts.m7f1.fresh_holdout_v2_schema import (
    FRESH_HOLDOUT_V2_PROJECTION_FIELDS,
    FreshHoldoutV2Case,
)

from springfix_agent.benchmark.loader import load_cases

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FRESH_MANIFEST = PROJECT_ROOT / "benchmark" / "fresh_holdout_v2_manifest.json"
LEGACY_CASES = PROJECT_ROOT / "benchmark" / "agent_cases.jsonl"


def test_fresh_v2_loader_accepts_eight_blinded_cases() -> None:
    manifest, cases = FreshHoldoutV2Loader(project_root=PROJECT_ROOT).load(FRESH_MANIFEST)

    assert manifest.case_count == 8
    assert len(cases) == 8
    assert manifest.gold_projection == "excluded"
    assert tuple(manifest.agent_projection_fields) == FRESH_HOLDOUT_V2_PROJECTION_FIELDS
    assert all(isinstance(case, FreshHoldoutV2Case) for case in cases)


def test_fresh_v2_case_rejects_gold_fields() -> None:
    payload = {
        "case_id": "fresh-v2-test",
        "repository": "samples/sample-springboot-fresh-v2-h01-conditional-registration",
        "issue_description": "A bounded issue.",
        "error_log": "test failure",
        "error_log_version": "sanitized-v1",
        "expected_files": ["src/main/java/Example.java"],
    }

    with pytest.raises(ValidationError):
        FreshHoldoutV2Case.model_validate(payload)


def test_agent_case_input_is_exact_allow_list() -> None:
    case = FreshHoldoutV2Case(
        case_id="fresh-v2-test",
        repository="samples/sample-springboot-fresh-v2-h01-conditional-registration",
        issue_description="A bounded issue.",
        error_log="test failure",
        error_log_version="sanitized-v1",
    )

    projection = case.agent_input()

    assert tuple(projection.model_dump()) == FRESH_HOLDOUT_V2_PROJECTION_FIELDS
    assert set(projection.model_dump()) == set(FRESH_HOLDOUT_V2_PROJECTION_FIELDS)
    assert "gold" not in projection.model_dump()
    assert "reference_patch" not in projection.model_dump()


def test_legacy_loader_and_benchmark_case_remain_unchanged() -> None:
    legacy_cases = load_cases(LEGACY_CASES)

    assert len(legacy_cases) == 3
    assert all("expected_issue_category" in case.model_fields_set for case in legacy_cases)
    assert all(case.agent_input().keys() == {"repository", "issue_description", "error_log"} for case in legacy_cases)


def test_loader_does_not_require_gold_or_reference_files(tmp_path: Path) -> None:
    cases_path = tmp_path / "fresh-cases.jsonl"
    manifest_path = tmp_path / "fresh-manifest.json"
    case = {
        "case_id": "fresh-v2-test",
        "repository": "samples/sample-springboot-fresh-v2-h01-conditional-registration",
        "issue_description": "A bounded issue.",
        "error_log": "test failure",
        "error_log_version": "sanitized-v1",
    }
    manifest = {
        "schema_version": "fresh-holdout-v2-agent-manifest-v1",
        "benchmark_version": "fresh_holdout_v2",
        "status": "REGISTERED_BEFORE_AGENT_EXECUTION",
        "case_count": 1,
        "case_ids": ["fresh-v2-test"],
        "cases_path": "fresh-cases.jsonl",
        "execution_contract": {
            "agent_executions": 0,
            "mock_executions": 0,
            "live_executions": 0,
            "llm_benchmark_calls": 0,
            "maven_target": "mvn test",
            "fresh_holdout_execution": False,
        },
        "agent_projection_fields": list(FRESH_HOLDOUT_V2_PROJECTION_FIELDS),
        "gold_projection": "excluded",
        "reference_material": "sealed/gold-and-reference-material",
    }
    cases_path.write_text(json.dumps(case) + "\n", encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    loaded_manifest, loaded_cases = FreshHoldoutV2Loader(project_root=tmp_path).load(manifest_path)

    assert loaded_manifest.gold_projection == "excluded"
    assert loaded_cases[0].case_id == "fresh-v2-test"
