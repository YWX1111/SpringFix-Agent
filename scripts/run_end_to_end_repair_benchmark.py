"""Run the M5D single-shot end-to-end repair benchmark."""

from __future__ import annotations

import argparse
from pathlib import Path

from springfix_agent.benchmark.runner import BenchmarkConfigurationError
from springfix_agent.repair.e2e_runner import EndToEndRepairBenchmarkRunner


def build_parser() -> argparse.ArgumentParser:
    """Build the fixed-scope M5D CLI parser."""
    parser = argparse.ArgumentParser(description="Run SpringFix M5D End-to-End Repair Benchmark")
    parser.add_argument("--mode", choices=("mock", "live"), default="mock")
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
    project_root = Path(__file__).resolve().parents[1]
    runner = EndToEndRepairBenchmarkRunner(
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
        f"mode={result.mode} run_id={result.run_id} sample_size={aggregate.sample_size} "
        f"pipeline_completed={aggregate.cases_completed} "
        f"repair_success={aggregate.repair_success_count} "
        f"artifacts={(runner.output_dir / result.mode / result.run_id).as_posix()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
