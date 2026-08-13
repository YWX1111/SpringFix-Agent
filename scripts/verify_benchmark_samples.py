"""Run and verify all M4B Maven Samples from the benchmark manifest."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from benchmark_verification import MavenExpectation, verify_sample  # noqa: E402
from springfix_agent.benchmark.loader import load_cases  # noqa: E402

DEFAULT_MANIFEST = PROJECT_ROOT / "benchmark" / "agent_cases.jsonl"
HOLDOUT_MANIFEST = PROJECT_ROOT / "benchmark" / "holdout_cases.jsonl"


def _expectation(case: object) -> MavenExpectation:
    """Convert a typed manifest Maven section to the reusable verifier spec."""
    expected = case.expected_maven  # type: ignore[attr-defined]
    return MavenExpectation(
        test_name=expected.test_name,
        tests=expected.tests,
        failures=expected.failures,
        errors=expected.errors,
        skipped=expected.skipped,
        required_failure_terms=tuple(expected.required_failure_terms),
    )


def main() -> int:
    """Verify every declared Sample and fail unless all cases pass."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Manifest to verify; default verifies legacy and Holdout v1 manifests.",
    )
    args = parser.parse_args()
    manifests = [args.manifest.resolve()] if args.manifest else [DEFAULT_MANIFEST, HOLDOUT_MANIFEST]
    try:
        loaded = [(manifest, load_cases(manifest.resolve())) for manifest in manifests]
    except ValueError as exc:
        print(f"Manifest load failed: {exc}", file=sys.stderr)
        return 1

    all_passed = True
    total = 0
    total_passed = 0
    split_totals: dict[str, tuple[int, int]] = {}
    for manifest, cases in loaded:
        split_label = "holdout" if manifest.resolve() == HOLDOUT_MANIFEST.resolve() else "legacy"
        split_count = 0
        for case in cases:
            total += 1
            sample_dir = (PROJECT_ROOT / case.repository).resolve()
            print(f"\n=== {case.case_id} ({split_label}) ===")
            result = verify_sample(sample_dir, _expectation(case))
            for diagnostic in result.diagnostics:
                print(f"  {diagnostic}")
            if result.passed:
                print(f"{case.case_id:<40} PASS")
                split_count += 1
                total_passed += 1
            else:
                print(f"{case.case_id:<40} FAIL")
                all_passed = False
                if result.stderr and not result.suites:
                    excerpt = "\n".join(result.stderr.splitlines()[-20:])
                    print(f"  Maven stderr excerpt:\n{excerpt}", file=sys.stderr)
        previous_passed, previous_total = split_totals.get(split_label, (0, 0))
        split_totals[split_label] = (
            previous_passed + split_count,
            previous_total + len(cases),
        )

    for split_label in ("legacy", "holdout"):
        if split_label in split_totals:
            passed, declared = split_totals[split_label]
            print(f"{split_label} = {passed}/{declared}")
    if all_passed:
        print(f"total = {total}/{total} benchmark samples verified")
        return 0
    print(f"total = {total_passed}/{total}")
    print("\nBenchmark sample verification failed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
