"""Run deterministic M5B Patch Application against temporary repository copies."""

from __future__ import annotations

import argparse
from pathlib import Path

from springfix_agent.repair.application_runner import PatchApplicationRunner


def build_parser() -> argparse.ArgumentParser:
    """Build the M5B application CLI parser."""
    parser = argparse.ArgumentParser(description="Run SpringFix M5B Patch Application")
    parser.add_argument("--mode", choices=("mock",), default="mock")
    parser.add_argument("--case", dest="case_id", default=None)
    parser.add_argument(
        "--proposal-file",
        type=Path,
        default=None,
        help="JSON proposal plus validated_evidence; M5A validation is always rerun",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/patch-applications"),
        help="Parent directory containing separate mock artifacts",
    )
    return parser


def main() -> int:
    """Run the selected offline applications and print redacted metrics."""
    parser = build_parser()
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]
    runner = PatchApplicationRunner(
        project_root=project_root,
        manifest_path=project_root / "benchmark" / "agent_cases.jsonl",
        repair_gold_path=project_root / "benchmark" / "repair_gold.jsonl",
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
        f"applications={sum(case.application_status == 'applied' for case in result.cases)} "
        f"all_edits_applied={sum(case.all_edits_applied for case in result.cases)} "
        f"original_repository_unchanged={sum(case.original_repository_unchanged for case in result.cases)} "
        f"diff_generated={sum(case.diff_generated for case in result.cases)} "
        f"workspace_cleanup={sum(case.workspace_cleanup_success for case in result.cases)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
