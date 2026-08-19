"""Deterministic tests for selecting frozen E2E benchmark splits."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.run_end_to_end_repair_benchmark import (
    build_parser,
    split_paths,
    validate_split_args,
)

from springfix_agent.repair.e2e_artifacts import render_end_to_end_report
from springfix_agent.repair.e2e_metrics import aggregate_end_to_end_metrics
from springfix_agent.repair.e2e_models import EndToEndRunResult

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_holdout_split_selects_only_frozen_holdout_manifests() -> None:
    cases, gold = split_paths(PROJECT_ROOT, "holdout")
    assert cases == PROJECT_ROOT / "benchmark" / "holdout_cases.jsonl"
    assert gold == PROJECT_ROOT / "benchmark" / "holdout_repair_gold.jsonl"


def test_legacy_split_remains_default() -> None:
    args = build_parser().parse_args([])
    assert args.split == "legacy"
    cases, gold = split_paths(PROJECT_ROOT, args.split)
    assert cases == PROJECT_ROOT / "benchmark" / "agent_cases.jsonl"
    assert gold == PROJECT_ROOT / "benchmark" / "repair_gold.jsonl"


def test_holdout_split_rejects_case_scoping() -> None:
    with pytest.raises(ValueError, match="run all seven cases together"):
        validate_split_args("holdout", "missing-constructor-bean")
    validate_split_args("holdout", None)


def test_holdout_report_uses_split_scope_and_sample_size() -> None:
    result = EndToEndRunResult(
        mode="live",
        run_id="m7b-test",
        run_metadata={"split": "holdout"},
        cases=[],
        aggregate=aggregate_end_to_end_metrics([]),
    )
    report = render_end_to_end_report(result)
    assert "SpringFix Holdout End-to-End Repair Benchmark" in report
    assert "frozen unseen Holdout v1 benchmark" in report
    assert "sample_size is 0" in report
