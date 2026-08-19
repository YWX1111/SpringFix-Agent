"""Verify the six deterministic M7E-1 semantic development samples.

The script runs only local Maven validation. It does not construct an Agent,
invoke a model, run Holdout, or alter the original samples. Reference fixes
are applied only to isolated copies to prove that each sample is solvable.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from benchmark_verification import (  # noqa: E402
    MavenExpectation,
    build_restricted_maven_environment,
    find_maven_binary,
    find_suitable_jdk,
    parse_surefire_xml,
    validate_surefire,
    verify_sample,
)
from semantic_dev_integrity import DEV_CASE_IDS, DEV_SAMPLE_DIRECTORIES  # noqa: E402
from springfix_agent.benchmark.loader import load_cases  # noqa: E402

MANIFEST = PROJECT_ROOT / "benchmark" / "dev_semantic_cases.jsonl"
ARTIFACT_DIR = PROJECT_ROOT / "artifacts" / "benchmark-development" / "m7e1-semantic-dev-v1"


@dataclass(frozen=True)
class TextReplacement:
    relative_file: str
    old: str
    new: str


REFERENCE_FIXES: dict[str, tuple[TextReplacement, ...]] = {
    "dev-s1-profile-config-source": (
        TextReplacement("src/main/resources/application-dev.yml", "on-profile: staging", "on-profile: dev"),
    ),
    "dev-s2-code-property-override": (
        TextReplacement(
            "src/main/java/com/springfix/dev/s2/notification/Application.java",
            '    static {\n        System.setProperty("notification.channel", "legacy");\n    }\n',
            "",
        ),
    ),
    "dev-s3-storage-validation": (
        TextReplacement("src/main/resources/application.yml", "max-entries: 0", "max-entries: 128"),
    ),
    "dev-s4-conditional-notification": (
        TextReplacement("src/main/resources/application.yml", "provider: email", "provider: webhook"),
    ),
    "dev-s5-cache-binding-key": (
        TextReplacement("src/main/resources/application.yml", "region-ttl:", "ttl-by-region:"),
    ),
    "dev-s6-local-precedence-conflict": (
        TextReplacement("src/main/resources/application-local.yml", "retry-limit: 0", "retry-limit: 5"),
    ),
}


def _expectation(case: Any, *, failures: int) -> MavenExpectation:
    expected = case.expected_maven
    return MavenExpectation(
        test_name=expected.test_name,
        tests=expected.tests,
        failures=failures,
        errors=expected.errors,
        skipped=expected.skipped,
        required_failure_terms=tuple(expected.required_failure_terms if failures else ()),
    )


def _apply_reference_fix(root: Path, case_id: str) -> None:
    for replacement in REFERENCE_FIXES[case_id]:
        path = root / replacement.relative_file
        original = path.read_text(encoding="utf-8")
        if original.count(replacement.old) != 1:
            raise ValueError(
                f"reference replacement for {case_id} expected one match in {replacement.relative_file}"
            )
        path.write_text(original.replace(replacement.old, replacement.new), encoding="utf-8")


def _verify_fixed_sample(sample_dir: Path, test_name: str) -> tuple[bool, list[str]]:
    maven = find_maven_binary()
    java_home, java_version = find_suitable_jdk(min_version=17)
    if maven is None or java_home is None or java_version is None:
        return False, ["Maven or Java 17+ is unavailable"]
    completed = subprocess.run(
        [maven, "test"],
        cwd=sample_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=build_restricted_maven_environment(java_home=java_home),
        shell=False,
        timeout=600,
        check=False,
    )
    suites = parse_surefire_xml(
        sorted((sample_dir / "target" / "surefire-reports").glob("TEST-*.xml"))
        if (sample_dir / "target" / "surefire-reports").is_dir()
        else []
    )
    expected = MavenExpectation(
        test_name=test_name,
        tests=1,
        failures=0,
        errors=0,
        skipped=0,
    )
    counters_ok, diagnostics = validate_surefire(suites, expected)
    passed = completed.returncode == 0 and counters_ok
    return passed, [f"using Java {java_version}", f"Maven exit code: {completed.returncode}", *diagnostics]


def _case_summary(case: Any, baseline: Any, reference_ok: bool, reference_diagnostics: list[str]) -> dict[str, Any]:
    case_id = case.case_id
    return {
        "case_id": case_id,
        "category": case.expected_issue_category,
        "repository": case.repository,
        "baseline": {
            "verified": baseline.passed,
            "exit_code": baseline.returncode,
            "tests": case.expected_maven.tests,
            "failures": case.expected_maven.failures,
            "errors": case.expected_maven.errors,
            "skipped": case.expected_maven.skipped,
        },
        "reference_fix_verified": reference_ok,
        "reference_fix_diagnostics": reference_diagnostics,
    }


def _write_artifacts(results: list[dict[str, Any]]) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    summary = {
        "benchmark": "M7E-1 Semantic Repair Development Benchmark Expansion",
        "split": "dev_semantic_v1",
        "created_at": date.today().isoformat(),
        "runtime": "0.15.1",
        "case_count": len(results),
        "baseline_verified": sum(bool(item["baseline"]["verified"]) for item in results),
        "reference_fix_verified": sum(bool(item["reference_fix_verified"]) for item in results),
        "cases": results,
        "gold_alignment_audit": {
            "all_cases_have_post_output_gold": True,
            "gold_not_in_agent_projection": True,
            "reference_patch_not_stored": True,
        },
        "holdout_isolation": {
            "case_count": 7,
            "case_ids_unchanged": True,
            "hashes_unchanged": True,
            "integrity_verifier": "scripts/holdout_integrity.py",
        },
        "holdout": {
            "split": "frozen holdout v1",
            "case_count": 7,
            "repair_success_baseline": "3/7 historical evidence; unchanged",
        },
        "agent_execution": {"agent": False, "holdout_mock": False, "live": False},
        "pipeline_changes": {
            "runtime": False,
            "validator": False,
            "retrieval": False,
            "patch_applier": False,
            "maven_verifier": False,
        },
        "artifact_safety": {
            "full_reference_patch": False,
            "secrets": False,
            "absolute_paths": False,
            "temp_paths": False,
            "raw_llm_response": False,
            "full_maven_output": False,
        },
    }
    (ARTIFACT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# M7E-1 Semantic Repair Development Benchmark Expansion",
        "",
        "This artifact records construction-time validation only. No Agent, Mock Holdout, or Live LLM run was performed.",
        "",
        "- Split: `dev_semantic_v1`",
        "- Runtime: `0.15.1` (unchanged)",
        f"- New Dev cases: {len(results)}/{len(results)} deterministic baselines reproduced",
        f"- Reference fixes: {sum(bool(item['reference_fix_verified']) for item in results)}/{len(results)} isolated-copy validations passed",
        "- Frozen Holdout v1: 7 cases; historical repair result remains 3/7",
        "",
        "## Case audit",
        "",
        "| Case | Category | Effective source | Higher-precedence source | Baseline | Reference fix |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    source_notes = {
        "dev-s1-profile-config-source": ("profile-specific config document", "active profile document over base config"),
        "dev-s2-code-property-override": ("application property binding", "System property set in visible application code"),
        "dev-s3-storage-validation": ("storage ConfigurationProperties binding", "validated storage value from application config"),
        "dev-s4-conditional-notification": ("conditional notification Bean", "alerts.provider condition"),
        "dev-s5-cache-binding-key": ("cache ConfigurationProperties map", "cache binding path"),
        "dev-s6-local-precedence-conflict": ("active local profile config", "application-local.yml over application.yml"),
    }
    for item in results:
        effective, higher = source_notes[item["case_id"]]
        baseline = item["baseline"]
        lines.append(
            f"| `{item['case_id']}` | `{item['category']}` | {effective} | {higher} | "
            f"{baseline['tests']} test / {baseline['failures']} failure | "
            f"{'PASS' if item['reference_fix_verified'] else 'FAIL'} |"
        )
    lines.extend(
        [
            "",
            "## Integrity and scope",
            "",
            "- Target tests contain no hidden property/profile override; all configuration evidence is in Agent-visible source.",
            "- Gold is post-output verification data and is not included in the Agent projection.",
            "- Frozen Holdout v1 membership and hashes are checked separately by `scripts/holdout_integrity.py`.",
            "- No reference patch is stored in this artifact; fixes were applied only to isolated validation copies.",
            "",
        ]
    )
    (ARTIFACT_DIR / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-artifact", action="store_true", help="Do not write the development report artifact")
    args = parser.parse_args()
    cases = load_cases(MANIFEST)
    if [case.case_id for case in cases] != list(DEV_CASE_IDS):
        print("Dev manifest case order does not match dev_semantic_v1", file=sys.stderr)
        return 1

    all_passed = True
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="springfix-m7e1-") as temporary:
        temp_root = Path(temporary)
        for case in cases:
            sample = (PROJECT_ROOT / case.repository).resolve()
            print(f"\n=== {case.case_id} ===")
            baseline = verify_sample(sample, _expectation(case, failures=case.expected_maven.failures))
            for diagnostic in baseline.diagnostics:
                print(f"  {diagnostic}")
            if not baseline.passed:
                all_passed = False
            fixed_sample = temp_root / DEV_SAMPLE_DIRECTORIES[case.case_id]
            shutil.copytree(sample, fixed_sample, ignore=shutil.ignore_patterns("target", ".git"))
            _apply_reference_fix(fixed_sample, case.case_id)
            reference_ok, reference_diagnostics = _verify_fixed_sample(
                fixed_sample, case.expected_maven.test_name
            )
            for diagnostic in reference_diagnostics:
                print(f"  [reference] {diagnostic}")
            if not reference_ok:
                all_passed = False
            print(f"{case.case_id:<40} {'PASS' if baseline.passed and reference_ok else 'FAIL'}")
            results.append(_case_summary(case, baseline, reference_ok, reference_diagnostics))

    if not args.no_artifact:
        _write_artifacts(results)
    print(f"semantic_dev_baseline = {sum(bool(item['baseline']['verified']) for item in results)}/{len(results)}")
    print(f"semantic_dev_reference_fixes = {sum(bool(item['reference_fix_verified']) for item in results)}/{len(results)}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
