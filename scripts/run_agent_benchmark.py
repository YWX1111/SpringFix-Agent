"""Run the SpringFix M4C benchmark in Mock or Live mode."""

from __future__ import annotations

import argparse
from pathlib import Path

from springfix_agent.benchmark.runner import (
    BenchmarkConfigurationError,
    BenchmarkRunner,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="Run the SpringFix Agent benchmark")
    parser.add_argument("--mode", choices=("mock", "live"), default="mock")
    parser.add_argument("--case", dest="case_id", default=None)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/agent-eval"),
        help="Parent directory containing separate mock/ and live/ artifacts",
    )
    parser.add_argument(
        "--include-tests",
        action="store_true",
        help="Include src/test in the temporary Agent repository view",
    )
    return parser


def main() -> int:
    """Execute the runner and print only a redacted summary."""
    parser = build_parser()
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]
    runner = BenchmarkRunner(
        project_root=project_root,
        manifest_path=project_root / "benchmark" / "agent_cases.jsonl",
        output_dir=args.output_dir,
        mode=args.mode,
        include_tests=args.include_tests,
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
        f"mode={result.mode} cases={aggregate.cases_total} "
        f"completed={aggregate.cases_completed} passed={aggregate.cases_passed} "
        f"case_pass_rate={aggregate.case_pass_rate:.4f} "
        f"artifacts={(runner.output_dir / result.mode).as_posix()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
