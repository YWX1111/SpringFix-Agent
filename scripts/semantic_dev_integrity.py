"""Verify the development-only semantic repair split and its freeze hashes.

This checker is offline-only. It validates split isolation, Agent-facing
projection, target-test hygiene, Gold structure, and the deterministic hashes
for the six M7E-1 development samples. It never imports the repair graph or
calls an LLM.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEV_SPLIT = "dev_semantic_v1"
DEV_CASES = PROJECT_ROOT / "benchmark" / "dev_semantic_cases.jsonl"
DEV_GOLD = PROJECT_ROOT / "benchmark" / "dev_semantic_repair_gold.jsonl"
DEV_FREEZE = PROJECT_ROOT / "benchmark" / "dev_semantic_manifest.json"
SPLITS = PROJECT_ROOT / "benchmark" / "splits.json"
HASH_ALGORITHM = "sha256"
CONTENT_NORMALIZATION = "utf8-lf-v1"

DEV_CASE_IDS = (
    "dev-s1-profile-config-source",
    "dev-s2-code-property-override",
    "dev-s3-storage-validation",
    "dev-s4-conditional-notification",
    "dev-s5-cache-binding-key",
    "dev-s6-local-precedence-conflict",
)
DEV_SAMPLE_DIRECTORIES = {
    "dev-s1-profile-config-source": "sample-springboot-dev-s1-profile-config-source",
    "dev-s2-code-property-override": "sample-springboot-dev-s2-code-property-override",
    "dev-s3-storage-validation": "sample-springboot-dev-s3-storage-validation",
    "dev-s4-conditional-notification": "sample-springboot-dev-s4-conditional-notification",
    "dev-s5-cache-binding-key": "sample-springboot-dev-s5-cache-binding-key",
    "dev-s6-local-precedence-conflict": "sample-springboot-dev-s6-local-precedence-conflict",
}
HOLDOUT_CASE_IDS = {
    "missing-constructor-bean",
    "constructor-circular-dependency",
    "invalid-config-property-value",
    "wrong-active-profile",
    "component-scan-boundary",
    "transaction-proxy-visibility",
    "ambiguous-request-mapping",
}
HOLDOUT_SPECIFIC_IDENTIFIERS = {
    "AuditClient",
    "EmailAuditClient",
    "CheckoutCoordinator",
    "ReceiptCoordinator",
    "ReportService",
    "DashboardService",
    "ReportController",
    "SummaryController",
}
HOLDOUT_IDENTIFIERS = {
    "BillingProperties",
    "ProductionCatalog",
    "CatalogService",
    *HOLDOUT_CASE_IDS,
    *HOLDOUT_SPECIFIC_IDENTIFIERS,
}
TARGET_TEST_OVERRIDE_TOKENS = (
    ".withPropertyValues(",
    ".withSystemProperties(",
    "TestPropertyValues.",
    "System.setProperty(",
    "System.getProperties().put(",
    "System.getProperties().setProperty(",
    "@ActiveProfiles(",
    "@TestPropertySource(",
    "@DynamicPropertySource",
    "DynamicPropertyRegistry",
    "SpringApplication.setDefaultProperties(",
    "ConfigurableEnvironment",
    "MutablePropertySources",
    "MockEnvironment",
    "MockPropertySource",
)
PUBLIC_GENERIC_SYMBOLS = {"application", "endpoint", "provider", "connectiontimeout", "retrylimit"}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _iter_files(root: Path, *, tests_only: bool | None = None) -> Iterable[Path]:
    excluded = {".git", "target", "artifacts", "benchmark"}
    paths: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in excluded for part in path.parts):
            continue
        relative = path.relative_to(root).as_posix()
        is_test = relative.startswith("src/test/")
        if tests_only is True and not is_test:
            continue
        if tests_only is False and is_test:
            continue
        paths.append(path)
    yield from sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def canonical_content_bytes(path: Path) -> bytes:
    """Normalize only line endings, matching the frozen benchmark discipline."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _hash_files(root: Path, files: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(canonical_content_bytes(path))
        digest.update(b"\0")
    return digest.hexdigest()


def _gold_hashes(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for payload in _load_jsonl(path):
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        result[payload["case_id"]] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return result


def compute_hashes(project_root: Path = PROJECT_ROOT) -> dict[str, dict[str, str]]:
    """Compute development sample source, test, sample, and Gold hashes."""
    sample_hashes: dict[str, str] = {}
    source_hashes: dict[str, str] = {}
    test_hashes: dict[str, str] = {}
    for case_id in DEV_CASE_IDS:
        sample = project_root / "samples" / DEV_SAMPLE_DIRECTORIES[case_id]
        if not sample.is_dir():
            raise ValueError(f"sample directory not found for {case_id}: {sample}")
        sample_hashes[case_id] = _hash_files(sample, _iter_files(sample))
        source_hashes[case_id] = _hash_files(sample, _iter_files(sample, tests_only=False))
        test_hashes[case_id] = _hash_files(sample, _iter_files(sample, tests_only=True))
    return {
        "sample_hashes": sample_hashes,
        "source_hashes": source_hashes,
        "test_hashes": test_hashes,
        "gold_hashes": _gold_hashes(project_root / "benchmark" / "dev_semantic_repair_gold.jsonl"),
    }


def _check_gold(records: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    required = {"case_id", "acceptable_files", "acceptable_change_concepts", "forbidden_files"}
    if [record.get("case_id") for record in records] != list(DEV_CASE_IDS):
        errors.append("development Gold case order does not match the frozen Dev split")
    for record in records:
        case_id = record.get("case_id", "<missing>")
        missing = sorted(required - set(record))
        if missing:
            errors.append(f"{case_id}: missing Gold field(s): {', '.join(missing)}")
        for field in ("acceptable_files", "acceptable_change_concepts", "forbidden_files"):
            value = record.get(field)
            if not isinstance(value, list) or not value or not all(
                isinstance(item, str) and item.strip() for item in value
            ):
                errors.append(f"{case_id}: {field} must be a non-empty string list")
    return errors


def verify_dev_split(project_root: Path = PROJECT_ROOT) -> tuple[bool, list[str]]:
    """Return deterministic diagnostics for the M7E-1 development split."""
    diagnostics: list[str] = []
    ok = True
    try:
        splits = _load_json(project_root / "benchmark" / "splits.json")
        frozen = _load_json(project_root / "benchmark" / "dev_semantic_manifest.json")
        cases = _load_jsonl(project_root / "benchmark" / "dev_semantic_cases.jsonl")
        gold = _load_jsonl(project_root / "benchmark" / "dev_semantic_repair_gold.jsonl")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        return False, [f"[FAIL] development metadata load: {exc}"]

    checks = [
        ("Dev split IDs", splits.get(DEV_SPLIT) == list(DEV_CASE_IDS)),
        ("Dev freeze IDs", frozen.get("case_ids") == list(DEV_CASE_IDS)),
        ("six Dev cases loaded", [case.get("case_id") for case in cases] == list(DEV_CASE_IDS)),
        ("six Dev Gold records", [record.get("case_id") for record in gold] == list(DEV_CASE_IDS)),
        ("hash algorithm", frozen.get("hash_algorithm") == HASH_ALGORITHM),
        ("content normalization", frozen.get("content_normalization") == CONTENT_NORMALIZATION),
        (
            "Holdout membership is unchanged",
            splits.get("holdout") == [
                "missing-constructor-bean",
                "constructor-circular-dependency",
                "invalid-config-property-value",
                "wrong-active-profile",
                "component-scan-boundary",
                "transaction-proxy-visibility",
                "ambiguous-request-mapping",
            ],
        ),
        (
            "Legacy membership is unchanged",
            splits.get("legacy") == [
                "transaction-self-invocation",
                "no-unique-bean-definition",
                "configuration-properties-prefix-mismatch",
            ],
        ),
    ]
    for label, passed in checks:
        diagnostics.append(f"[{'PASS' if passed else 'FAIL'}] {label}")
        ok = ok and passed

    gold_errors = _check_gold(gold)
    diagnostics.append(f"[{'PASS' if not gold_errors else 'FAIL'}] Gold structure")
    if gold_errors:
        diagnostics.extend(f"  - {error}" for error in gold_errors)
    ok = ok and not gold_errors
    gold_by_case = {record["case_id"]: record for record in gold}

    case_ids = {case.get("case_id") for case in cases}
    for case in cases:
        case_id = str(case.get("case_id"))
        repository = project_root / str(case.get("repository"))
        agent_keys = set(case) & {"repository", "issue_description", "error_log"}
        projection_ok = agent_keys == {"repository", "issue_description", "error_log"}
        diagnostics.append(f"[{'PASS' if projection_ok else 'FAIL'}] Agent projection isolated: {case_id}")
        ok = ok and projection_ok
        public_text = f"{case.get('issue_description', '')}\n{case.get('error_log') or ''}".lower()
        gold_record = gold_by_case.get(case_id, {})
        public_leaks = [
            f"file:{Path(str(path)).name}"
            for path in case.get("expected_files", [])
            if Path(str(path)).name.lower() in public_text
        ]
        public_leaks.extend(
            f"symbol:{symbol}"
            for symbol in case.get("expected_symbols", [])
            if len(str(symbol)) >= 8 and str(symbol).lower() not in PUBLIC_GENERIC_SYMBOLS
            and str(symbol).lower() in public_text
        )
        public_leaks.extend(
            f"concept:{concept}"
            for concept in gold_record.get("acceptable_change_concepts", [])
            if str(concept).lower() in public_text
        )
        leakage_ok = not public_leaks
        diagnostics.append(f"[{'PASS' if leakage_ok else 'FAIL'}] public issue/error has no answer leakage: {case_id}")
        if public_leaks:
            diagnostics.extend(f"  - {leak}" for leak in public_leaks)
        ok = ok and leakage_ok
        if not repository.is_dir():
            diagnostics.append(f"[FAIL] repository exists: {case_id}")
            ok = False
            continue
        diagnostics.append(f"[PASS] repository exists: {case_id}")
        test_files = list(_iter_files(repository, tests_only=True))
        override_hits = [
            f"{path.relative_to(repository).as_posix()}: {token}"
            for path in test_files
            for token in TARGET_TEST_OVERRIDE_TOKENS
            if token in path.read_text(encoding="utf-8")
        ]
        override_ok = not override_hits
        diagnostics.append(f"[{'PASS' if override_ok else 'FAIL'}] target test has no hidden config override: {case_id}")
        if override_hits:
            diagnostics.extend(f"  - {hit}" for hit in override_hits)
        ok = ok and override_ok
        identifier_hits = [
            f"{path.relative_to(repository).as_posix()}: {identifier}"
            for path in _iter_files(repository)
            if path.name != "README.md"
            for identifier in HOLDOUT_IDENTIFIERS
            if identifier in path.read_text(encoding="utf-8")
        ]
        identifiers_ok = not identifier_hits
        diagnostics.append(f"[{'PASS' if identifiers_ok else 'FAIL'}] no frozen Holdout identifiers copied: {case_id}")
        if identifier_hits:
            diagnostics.extend(f"  - {hit}" for hit in identifier_hits)
        ok = ok and identifiers_ok

    disjoint_ok = not (case_ids & HOLDOUT_CASE_IDS)
    diagnostics.append(f"[{'PASS' if disjoint_ok else 'FAIL'}] Dev/Holdout case IDs are disjoint")
    ok = ok and disjoint_ok

    try:
        actual_hashes = compute_hashes(project_root)
    except (OSError, KeyError, ValueError) as exc:
        return False, diagnostics + [f"[FAIL] hash computation: {exc}"]
    for key, actual in actual_hashes.items():
        passed = actual == frozen.get(key)
        diagnostics.append(f"[{'PASS' if passed else 'FAIL'}] {key}")
        ok = ok and passed
    return ok, diagnostics


def main() -> int:
    """Run the offline development-split integrity verifier."""
    passed, diagnostics = verify_dev_split()
    for diagnostic in diagnostics:
        print(diagnostic)
    print(
        "Semantic development split integrity verified"
        if passed
        else "Semantic development split integrity verification failed"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
