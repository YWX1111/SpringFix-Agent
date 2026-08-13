"""Freeze and verify the unseen Holdout v1 benchmark inventory.

This module is offline-only.  It validates split metadata, Gold separation,
sample/test/gold hashes, and the Agent-facing projection without importing
the graph or calling an LLM.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HOLDOUT_CASES = PROJECT_ROOT / "benchmark" / "holdout_cases.jsonl"
HOLDOUT_GOLD = PROJECT_ROOT / "benchmark" / "holdout_repair_gold.jsonl"
SPLITS = PROJECT_ROOT / "benchmark" / "splits.json"
FREEZE_MANIFEST = PROJECT_ROOT / "benchmark" / "holdout_manifest.json"

LEGACY_CASE_IDS = (
    "transaction-self-invocation",
    "no-unique-bean-definition",
    "configuration-properties-prefix-mismatch",
)
HOLDOUT_CASE_IDS = (
    "missing-constructor-bean",
    "constructor-circular-dependency",
    "invalid-config-property-value",
    "wrong-active-profile",
    "component-scan-boundary",
    "transaction-proxy-visibility",
    "ambiguous-request-mapping",
)
HOLDOUT_SAMPLE_DIRECTORIES = {
    "missing-constructor-bean": "sample-springboot-holdout-missing-constructor-bean",
    "constructor-circular-dependency": "sample-springboot-holdout-circular-dependency",
    "invalid-config-property-value": "sample-springboot-holdout-invalid-config-property-value",
    "wrong-active-profile": "sample-springboot-holdout-wrong-active-profile",
    "component-scan-boundary": "sample-springboot-holdout-component-scan-boundary",
    "transaction-proxy-visibility": "sample-springboot-holdout-transaction-proxy-visibility",
    "ambiguous-request-mapping": "sample-springboot-holdout-ambiguous-request-mapping",
}
GOLD_REQUIRED_KEYS = {
    "case_id",
    "acceptable_files",
    "acceptable_change_concepts",
    "forbidden_files",
}
DIAGNOSIS_GOLD_FIELDS = (
    "expected_issue_category",
    "expected_diagnosis_status",
    "expected_root_cause_keywords",
    "keyword_groups",
    "expected_files",
    "expected_symbols",
    "evidence_targets",
    "expected_maven",
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_gold(path: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            result[item["case_id"]] = item
    return result


def load_holdout_cases(project_root: Path = PROJECT_ROOT):
    """Load only the seven frozen Holdout v1 cases."""
    import sys

    sys.path.insert(0, str(project_root / "src"))
    from springfix_agent.benchmark.loader import load_cases

    return load_cases(project_root / "benchmark" / "holdout_cases.jsonl")


def load_cases_for_split(split: str, project_root: Path = PROJECT_ROOT):
    """Load legacy, holdout, or all benchmark cases for offline verification."""
    import sys

    sys.path.insert(0, str(project_root / "src"))
    from springfix_agent.benchmark.loader import load_cases

    if split == "legacy":
        return load_cases(project_root / "benchmark" / "agent_cases.jsonl")
    if split == "holdout":
        return load_cases(project_root / "benchmark" / "holdout_cases.jsonl")
    if split == "all":
        legacy = load_cases(project_root / "benchmark" / "agent_cases.jsonl")
        holdout = load_cases(project_root / "benchmark" / "holdout_cases.jsonl")
        ids = [case.case_id for case in legacy + holdout]
        if len(ids) != len(set(ids)):
            raise ValueError("legacy and holdout manifests contain duplicate case IDs")
        return legacy + holdout
    raise ValueError(f"unknown benchmark split: {split}")


def _iter_files(root: Path, *, tests_only: bool | None = None) -> Iterable[Path]:
    excluded = {".git", "target", "artifacts", "benchmark"}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in excluded for part in path.parts):
            continue
        relative = path.relative_to(root).as_posix()
        is_test = relative.startswith("src/test/")
        if tests_only is True and not is_test:
            continue
        if tests_only is False and is_test:
            continue
        yield path


def _hash_files(root: Path, files: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _gold_hashes(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        result[payload["case_id"]] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return result


def _diagnosis_gold_hashes(path: Path) -> dict[str, str]:
    """Hash only diagnosis verification fields, separate from Agent input."""
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        diagnosis_gold = {key: payload.get(key) for key in DIAGNOSIS_GOLD_FIELDS}
        canonical = json.dumps(
            diagnosis_gold,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        result[payload["case_id"]] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return result


def _validate_gold_records(gold: dict[str, dict[str, Any]]) -> list[str]:
    """Return structural errors for Holdout Repair Gold without evaluating answers."""
    errors: list[str] = []
    for case_id, record in gold.items():
        missing = sorted(GOLD_REQUIRED_KEYS - set(record))
        if missing:
            errors.append(f"{case_id}: missing Gold field(s): {', '.join(missing)}")
        for field in ("acceptable_files", "acceptable_change_concepts", "forbidden_files"):
            value = record.get(field)
            if not isinstance(value, list) or not value or not all(
                isinstance(item, str) and item.strip() for item in value
            ):
                errors.append(f"{case_id}: {field} must be a non-empty string list")
    return errors


def compute_hashes(project_root: Path, case_ids: Iterable[str]) -> dict[str, dict[str, str]]:
    """Compute stable sample, source, and test hashes for each holdout case."""
    sample_hashes: dict[str, str] = {}
    source_hashes: dict[str, str] = {}
    test_hashes: dict[str, str] = {}
    for case_id in case_ids:
        directory = HOLDOUT_SAMPLE_DIRECTORIES.get(case_id)
        if directory is None:
            raise ValueError(f"sample directory mapping not found for {case_id}")
        sample = project_root / "samples" / directory
        if not sample.is_dir():
            raise ValueError(f"sample directory not found for {case_id}: {sample}")
        sample_hashes[case_id] = _hash_files(sample, _iter_files(sample))
        source_hashes[case_id] = _hash_files(sample, _iter_files(sample, tests_only=False))
        test_hashes[case_id] = _hash_files(sample, _iter_files(sample, tests_only=True))
    return {
        "sample_hashes": sample_hashes,
        "source_hashes": source_hashes,
        "test_hashes": test_hashes,
    }


def build_freeze_manifest(project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    """Build the deterministic JSON object stored as the Holdout freeze."""
    splits = _load_json(project_root / "benchmark" / "splits.json")
    case_ids = list(splits["holdout"])
    hashes = compute_hashes(project_root, case_ids)
    hashes["diagnosis_gold_hashes"] = _diagnosis_gold_hashes(
        project_root / "benchmark" / "holdout_cases.jsonl"
    )
    hashes["gold_hashes"] = _gold_hashes(project_root / "benchmark" / "holdout_repair_gold.jsonl")
    return {
        "benchmark_version": splits["benchmark_version"],
        "created_at": "2026-08-13",
        "case_ids": case_ids,
        **hashes,
    }


def verify_holdout_manifest(project_root: Path = PROJECT_ROOT) -> tuple[bool, list[str]]:
    """Verify split, Gold, projection, and all frozen hashes."""
    diagnostics: list[str] = []
    ok = True
    try:
        splits = _load_json(project_root / "benchmark" / "splits.json")
        frozen = _load_json(project_root / "benchmark" / "holdout_manifest.json")
        cases = load_holdout_cases(project_root)
        gold = _load_gold(project_root / "benchmark" / "holdout_repair_gold.jsonl")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return False, [f"[FAIL] holdout metadata load: {exc}"]

    expected = list(HOLDOUT_CASE_IDS)
    actual = list(splits.get("holdout", []))
    checks = [
        ("benchmark_version", splits.get("benchmark_version") == "holdout_v1"),
        ("legacy split count", splits.get("legacy") == list(LEGACY_CASE_IDS)),
        ("holdout split IDs", actual == expected),
        ("freeze case IDs", frozen.get("case_ids") == expected),
        ("seven holdout cases loaded", [case.case_id for case in cases] == expected),
        ("seven holdout Gold records", list(gold) == expected),
    ]
    for label, passed in checks:
        diagnostics.append(f"[{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed

    gold_errors = _validate_gold_records(gold)
    diagnostics.append(f"[{'PASS' if not gold_errors else 'FAIL'}] Gold structure")
    if gold_errors:
        diagnostics.extend(f"  - {error}" for error in gold_errors)
    ok = ok and not gold_errors

    for case in cases:
        projection = case.agent_input()
        passed = set(projection) == {"repository", "issue_description", "error_log"}
        passed = passed and not any(key.startswith("expected_") for key in projection)
        diagnostics.append(f"[{'PASS' if passed else 'FAIL'}] Agent projection isolated: {case.case_id}")
        ok = ok and passed

    try:
        actual_hashes = compute_hashes(project_root, expected)
        actual_hashes["diagnosis_gold_hashes"] = _diagnosis_gold_hashes(
            project_root / "benchmark" / "holdout_cases.jsonl"
        )
        actual_hashes["gold_hashes"] = _gold_hashes(
            project_root / "benchmark" / "holdout_repair_gold.jsonl"
        )
    except (OSError, ValueError, KeyError) as exc:
        return False, diagnostics + [f"[FAIL] hash computation: {exc}"]
    for key in (
        "sample_hashes",
        "source_hashes",
        "test_hashes",
        "diagnosis_gold_hashes",
        "gold_hashes",
    ):
        passed = actual_hashes[key] == frozen.get(key)
        diagnostics.append(f"[{'PASS' if passed else 'FAIL'}] {key}")
        ok = ok and passed
    return ok, diagnostics


def main() -> int:
    """Run the Holdout v1 integrity verifier."""
    passed, diagnostics = verify_holdout_manifest()
    for diagnostic in diagnostics:
        print(diagnostic)
    print("Holdout v1 integrity verified" if passed else "Holdout v1 integrity verification failed")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
