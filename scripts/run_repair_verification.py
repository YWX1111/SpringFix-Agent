"""Run deterministic M5C Maven Repair Verification."""

from __future__ import annotations

import argparse
from pathlib import Path

from springfix_agent.repair.repair_runner import RepairVerificationRunner


def build_parser() -> argparse.ArgumentParser:
    """Build the fixed-scope M5C CLI parser."""
    parser = argparse.ArgumentParser(description="Run SpringFix M5C Repair Verification")
    parser.add_argument("--mode", choices=("mock",), default="mock")
    parser.add_argument("--case", dest="case_id", default=None)
    parser.add_argument(
        "--proposal-file",
        type=Path,
        default=None,
        help="JSON proposal plus evidence; M5A validation is always rerun",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/repair-verification"),
        help="Parent directory containing separate mock artifacts",
    )
    return parser


def main() -> int:
    """Run selected cases and print only aggregate metrics."""
    parser = build_parser()
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]
    runner = RepairVerificationRunner(
        project_root=project_root,
        manifest_path=project_root / "benchmark" / "agent_cases.jsonl",
        output_dir=args.output_dir,
        mode=args.mode,
        case_id=args.case_id,
        proposal_file=args.proposal_file,
    )
    try:
        result = runner.run()
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
        return 2
    aggregate = result.aggregate
    print(
        f"mode={result.mode} sample_size={aggregate.sample_size} "
        f"baseline_verified={sum(case.baseline_verified for case in result.cases)} "
        f"patch_applied={sum(case.patch_applied for case in result.cases)} "
        f"maven_executed={sum(case.maven_executed for case in result.cases)} "
        f"target_test_executed={sum(case.target_test_found for case in result.cases)} "
        f"repair_success={sum(case.repair_success for case in result.cases)} "
        f"workspace_cleanup={sum(case.workspace_cleanup_success for case in result.cases)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
