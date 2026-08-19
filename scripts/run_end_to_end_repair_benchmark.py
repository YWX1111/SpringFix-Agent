"""Run the M5D single-shot end-to-end repair benchmark."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Literal

from springfix_agent.benchmark.runner import BenchmarkConfigurationError
from springfix_agent.repair.e2e_runner import EndToEndRepairBenchmarkRunner

BenchmarkSplit = Literal["legacy", "holdout"]


def split_paths(project_root: Path, split: BenchmarkSplit) -> tuple[Path, Path]:
    """Return the frozen case and Repair Gold manifests for one split."""
    if split == "holdout":
        return (
            project_root / "benchmark" / "holdout_cases.jsonl",
            project_root / "benchmark" / "holdout_repair_gold.jsonl",
        )
    return (
        project_root / "benchmark" / "agent_cases.jsonl",
        project_root / "benchmark" / "repair_gold.jsonl",
    )


def validate_split_args(split: BenchmarkSplit, case_id: str | None) -> None:
    """Reject scoped execution for the all-case Holdout evaluation split."""
    if split == "holdout" and case_id is not None:
        raise ValueError("--case is not allowed with --split holdout; run all seven cases together")


def build_parser() -> argparse.ArgumentParser:
    """Build the fixed-scope single-shot E2E CLI parser."""
    parser = argparse.ArgumentParser(description="Run SpringFix M5D End-to-End Repair Benchmark")
    parser.add_argument("--mode", choices=("mock", "live"), default="mock")
    parser.add_argument("--split", choices=("legacy", "holdout"), default="legacy")
    parser.add_argument("--case", dest="case_id", default=None)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/end-to-end-repair"),
        help="Parent directory containing separate mock/live Run artifacts",
    )
    return parser


def main() -> int:
    """Run one fresh M5D Run and print only aggregate metrics."""
    parser = build_parser()
    args = parser.parse_args()
    try:
        validate_split_args(args.split, args.case_id)
    except ValueError as exc:
        parser.error(str(exc))
    project_root = Path(__file__).resolve().parents[1]
    manifest_path, repair_gold_path = split_paths(project_root, args.split)
    runner = EndToEndRepairBenchmarkRunner(
        project_root=project_root,
        manifest_path=manifest_path,
        repair_gold_path=repair_gold_path,
        output_dir=args.output_dir,
        mode=args.mode,
        case_id=args.case_id,
        benchmark_split=args.split,
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
        f"split={args.split} mode={result.mode} run_id={result.run_id} "
        f"sample_size={aggregate.sample_size} "
        f"pipeline_completed={aggregate.cases_completed} "
        f"repair_success={aggregate.repair_success_count} "
        f"artifacts={(runner.output_dir / result.mode / result.run_id).as_posix()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
