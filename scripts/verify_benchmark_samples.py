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
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    try:
        cases = load_cases(args.manifest.resolve())
    except ValueError as exc:
        print(f"Manifest load failed: {exc}", file=sys.stderr)
        return 1

    all_passed = True
    for case in cases:
        sample_dir = (PROJECT_ROOT / case.repository).resolve()
        print(f"\n=== {case.case_id} ===")
        result = verify_sample(sample_dir, _expectation(case))
        for diagnostic in result.diagnostics:
            print(f"  {diagnostic}")
        if result.passed:
            print(f"{case.case_id:<40} PASS")
        else:
            print(f"{case.case_id:<40} FAIL")
            all_passed = False
            if result.stderr and not result.suites:
                excerpt = "\n".join(result.stderr.splitlines()[-20:])
                print(f"  Maven stderr excerpt:\n{excerpt}", file=sys.stderr)

    if all_passed:
        print(f"\n{len(cases)}/{len(cases)} benchmark samples verified")
        return 0
    print("\nBenchmark sample verification failed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
