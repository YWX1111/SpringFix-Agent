"""Run the M5A Patch Proposal benchmark without modifying a repository."""

from __future__ import annotations

import argparse
from pathlib import Path

from springfix_agent.benchmark.runner import BenchmarkConfigurationError
from springfix_agent.repair.runner import RepairProposalRunner


def build_parser() -> argparse.ArgumentParser:
    """Build the M5A CLI parser."""
    parser = argparse.ArgumentParser(description="Run SpringFix Patch Proposal generation")
    parser.add_argument("--mode", choices=("mock", "live"), default="mock")
    parser.add_argument("--case", dest="case_id", default=None)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/repair-proposals"),
        help="Parent directory containing separate mock/ and live artifacts",
    )
    return parser


def main() -> int:
    """Run the selected proposal benchmark and print a redacted summary."""
    parser = build_parser()
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]
    runner = RepairProposalRunner(
        project_root=project_root,
        manifest_path=project_root / "benchmark" / "agent_cases.jsonl",
        repair_gold_path=project_root / "benchmark" / "repair_gold.jsonl",
        output_dir=args.output_dir,
        mode=args.mode,
        case_id=args.case_id,
    )
    try:
        result = runner.run()
    except BenchmarkConfigurationError as exc:
        parser.error(str(exc))
        return 2
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
        return 2
    aggregate = result.aggregate
    print(
        f"mode={result.mode} sample_size={aggregate.sample_size} "
        f"proposal_generated={aggregate.proposal_generation_rate:.4f} "
        f"proposal_validation={aggregate.proposal_validation_rate:.4f} "
        f"artifacts={(runner.output_dir / result.mode).as_posix()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
