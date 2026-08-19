"""Offline integrity tests for the M7E-1 semantic development split."""

from __future__ import annotations

from pathlib import Path

from scripts import holdout_integrity, semantic_dev_integrity

from springfix_agent.benchmark.loader import load_cases
from springfix_agent.benchmark.repository_view import create_repository_view

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEV_MANIFEST = PROJECT_ROOT / "benchmark" / "dev_semantic_cases.jsonl"


def test_semantic_dev_manifest_has_six_cases_and_is_agent_safe() -> None:
    cases = load_cases(DEV_MANIFEST)
    assert [case.case_id for case in cases] == list(semantic_dev_integrity.DEV_CASE_IDS)
    assert all(set(case.agent_input()) == {"repository", "issue_description", "error_log"}
               for case in cases)
    assert all("expected_" not in str(case.agent_input()) for case in cases)


def test_semantic_dev_split_is_disjoint_from_legacy_and_holdout() -> None:
    splits = semantic_dev_integrity._load_json(PROJECT_ROOT / "benchmark" / "splits.json")
    dev = set(splits[semantic_dev_integrity.DEV_SPLIT])
    legacy = set(splits["legacy"])
    holdout = set(splits["holdout"])
    assert len(dev) == 6
    assert dev.isdisjoint(legacy)
    assert dev.isdisjoint(holdout)
    assert holdout == set(holdout_integrity.HOLDOUT_CASE_IDS)
    assert len(legacy) == 3


def test_semantic_dev_target_tests_have_no_hidden_configuration_override() -> None:
    for case in load_cases(DEV_MANIFEST):
        sample = PROJECT_ROOT / case.repository
        for path in semantic_dev_integrity._iter_files(sample, tests_only=True):
            text = path.read_text(encoding="utf-8")
            assert not any(token in text for token in semantic_dev_integrity.TARGET_TEST_OVERRIDE_TOKENS)


def test_semantic_dev_public_issue_and_error_do_not_leak_answer_fields() -> None:
    cases = load_cases(DEV_MANIFEST)
    gold = {
        record["case_id"]: record
        for record in semantic_dev_integrity._load_jsonl(
            PROJECT_ROOT / "benchmark" / "dev_semantic_repair_gold.jsonl"
        )
    }
    for case in cases:
        public_text = f"{case.issue_description}\n{case.error_log or ''}".lower()
        assert not any(Path(path).name.lower() in public_text for path in case.expected_files)
        assert not any(
            len(symbol) >= 8
            and symbol.lower() not in semantic_dev_integrity.PUBLIC_GENERIC_SYMBOLS
            and symbol.lower() in public_text
            for symbol in case.expected_symbols
        )
        assert not any(
            concept.lower() in public_text
            for concept in gold[case.case_id]["acceptable_change_concepts"]
        )


def test_semantic_dev_samples_do_not_copy_frozen_holdout_identifiers() -> None:
    for case in load_cases(DEV_MANIFEST):
        sample = PROJECT_ROOT / case.repository
        for path in semantic_dev_integrity._iter_files(sample):
            if path.name == "README.md":
                continue
            text = path.read_text(encoding="utf-8")
            assert not any(identifier in text for identifier in semantic_dev_integrity.HOLDOUT_IDENTIFIERS)


def test_semantic_dev_repository_view_excludes_gold_and_target_test() -> None:
    case = load_cases(DEV_MANIFEST)[0]
    with create_repository_view(PROJECT_ROOT / case.repository) as view:
        assert view.path is not None
        names = {path.relative_to(view.path).as_posix() for path in view.path.rglob("*")}
        assert "README.md" not in names
        assert all(not name.startswith("src/test/") for name in names)
        assert all(not name.startswith("target/") for name in names)
        assert "benchmark" not in names


def test_semantic_dev_freeze_manifest_passes() -> None:
    passed, diagnostics = semantic_dev_integrity.verify_dev_split(PROJECT_ROOT)
    assert passed, "\n".join(diagnostics)
