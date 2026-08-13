"""Offline regression tests for the frozen unseen Holdout v1 benchmark."""

from __future__ import annotations

import json
from pathlib import Path
from shutil import copytree

from scripts import holdout_integrity

from springfix_agent.benchmark.loader import load_cases
from springfix_agent.benchmark.repository_view import create_repository_view

PROJECT_ROOT = Path(__file__).resolve().parents[3]
HOLDOUT_MANIFEST = PROJECT_ROOT / "benchmark" / "holdout_cases.jsonl"


def test_holdout_split_and_agent_projection_are_frozen() -> None:
    cases = holdout_integrity.load_cases_for_split("holdout", PROJECT_ROOT)
    assert [case.case_id for case in cases] == list(holdout_integrity.HOLDOUT_CASE_IDS)
    assert all(set(case.agent_input()) == {"repository", "issue_description", "error_log"}
               for case in cases)
    assert all("expected_" not in str(case.agent_input()) for case in cases)


def test_holdout_issue_and_error_text_has_no_answer_leakage() -> None:
    cases = load_cases(HOLDOUT_MANIFEST)
    for case in cases:
        public_text = f"{case.issue_description}\n{case.error_log or ''}".lower()
        expected_files = [Path(path).name.lower() for path in case.expected_files]
        expected_symbols = [
            symbol.lower()
            for symbol in case.expected_symbols
            if len(symbol) >= 8 and symbol.lower() not in {"application"}
        ]
        repair_gold = holdout_integrity._load_gold(
            PROJECT_ROOT / "benchmark" / "holdout_repair_gold.jsonl"
        )[case.case_id]
        repair_concepts = [concept.lower() for concept in repair_gold["acceptable_change_concepts"]]
        assert not any(value in public_text for value in expected_files)
        assert not any(value in public_text for value in expected_symbols)
        assert not any(value in public_text for value in repair_concepts)
        assert "add " not in public_text
        assert "change line" not in public_text


def test_all_benchmark_splits_are_disjoint_and_total_ten() -> None:
    cases = holdout_integrity.load_cases_for_split("all", PROJECT_ROOT)
    assert len(cases) == 10
    assert len({case.case_id for case in cases}) == 10


def test_holdout_integrity_manifest_passes() -> None:
    passed, diagnostics = holdout_integrity.verify_holdout_manifest(PROJECT_ROOT)
    assert passed, "\n".join(diagnostics)


def test_holdout_gold_is_not_in_sanitized_repository_view() -> None:
    cases = load_cases(HOLDOUT_MANIFEST)
    for case in cases:
        source = (PROJECT_ROOT / case.repository).resolve()
        with create_repository_view(source) as view:
            assert view.path is not None
            names = {path.relative_to(view.path).as_posix() for path in view.path.rglob("*")}
            assert "README.md" not in names
            assert all(not name.startswith("src/test/") for name in names)
            assert all(not name.lower().endswith(".md") for name in names)
            assert "benchmark" not in names
            assert "artifacts" not in names
            assert all(not name.startswith("target/") for name in names)
            assert all(not name.startswith(".git/") for name in names)
            assert "holdout_repair_gold.jsonl" not in names


def test_holdout_cases_have_no_mock_profile() -> None:
    from springfix_agent.benchmark.runner import benchmark_profile_for_case

    for case_id in holdout_integrity.HOLDOUT_CASE_IDS:
        try:
            benchmark_profile_for_case(case_id)
        except ValueError as exc:
            assert str(exc) == f"no benchmark Mock profile for case '{case_id}'"
        else:
            raise AssertionError(f"Holdout case unexpectedly has a Mock profile: {case_id}")


def test_holdout_integrity_detects_source_test_and_gold_tampering(tmp_path: Path) -> None:
    root = tmp_path / "project"
    (root / "benchmark").mkdir(parents=True)
    (root / "samples").mkdir()
    copytree(PROJECT_ROOT / "benchmark", root / "benchmark", dirs_exist_ok=True)
    for directory in holdout_integrity.HOLDOUT_SAMPLE_DIRECTORIES.values():
        copytree(PROJECT_ROOT / "samples" / directory, root / "samples" / directory)

    frozen = json.loads((root / "benchmark" / "holdout_manifest.json").read_text())
    baseline = holdout_integrity.compute_hashes(root, holdout_integrity.HOLDOUT_CASE_IDS)
    baseline["diagnosis_gold_hashes"] = holdout_integrity._diagnosis_gold_hashes(
        root / "benchmark" / "holdout_cases.jsonl"
    )
    baseline["gold_hashes"] = holdout_integrity._gold_hashes(
        root / "benchmark" / "holdout_repair_gold.jsonl"
    )
    for key in baseline:
        assert baseline[key] == frozen[key]

    mutations = [
        (
            root / "samples" / holdout_integrity.HOLDOUT_SAMPLE_DIRECTORIES[
                "missing-constructor-bean"
            ] / "src/main/java/com/springfix/holdout/missingbean/EmailAuditClient.java",
            "source_hashes",
        ),
        (
            root / "samples" / holdout_integrity.HOLDOUT_SAMPLE_DIRECTORIES[
                "missing-constructor-bean"
            ] / "src/test/java/com/springfix/holdout/missingbean/MissingConstructorBeanTest.java",
            "test_hashes",
        ),
        (root / "benchmark" / "holdout_cases.jsonl", "diagnosis_gold_hashes"),
        (root / "benchmark" / "holdout_repair_gold.jsonl", "gold_hashes"),
    ]
    for path, hash_key in mutations:
        original = path.read_text(encoding="utf-8")
        if path.suffix == ".jsonl":
            records = [json.loads(line) for line in original.splitlines() if line.strip()]
            if hash_key == "diagnosis_gold_hashes":
                records[0]["expected_issue_category"] = "tampered"
            else:
                records[0]["acceptable_change_concepts"][0] = "tampered"
            path.write_text(
                "\n".join(json.dumps(record) for record in records) + "\n",
                encoding="utf-8",
            )
        else:
            path.write_text(original + "\n// tampered\n", encoding="utf-8")
        changed = holdout_integrity.compute_hashes(root, holdout_integrity.HOLDOUT_CASE_IDS)
        changed["diagnosis_gold_hashes"] = holdout_integrity._diagnosis_gold_hashes(
            root / "benchmark" / "holdout_cases.jsonl"
        )
        changed["gold_hashes"] = holdout_integrity._gold_hashes(
            root / "benchmark" / "holdout_repair_gold.jsonl"
        )
        assert changed[hash_key] != frozen[hash_key]
        passed, _ = holdout_integrity.verify_holdout_manifest(root)
        assert not passed
        path.write_text(original, encoding="utf-8")
