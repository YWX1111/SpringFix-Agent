"""Replay V1, frozen V2.0, and independent Diagnosis V2.1 artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from springfix_agent.benchmark.diagnosis_v2 import load_diagnosis_v2_specs
from springfix_agent.benchmark.diagnosis_v21 import (
    load_diagnosis_v21_specs,
    load_frozen_summary,
    replay_frozen_e2e_summary_v21,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--v20-metadata", type=Path, required=True)
    parser.add_argument("--v21-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    """Run deterministic replay with zero Agent and LLM calls."""
    args = _parser().parse_args()
    replay = replay_frozen_e2e_summary_v21(
        load_frozen_summary(args.summary),
        load_diagnosis_v21_specs(args.v21_metadata),
        load_diagnosis_v2_specs(args.v20_metadata),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(replay, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    v20 = replay["diagnosis_v2_0"]["aggregate"]
    v21 = replay["diagnosis_v2_1"]["aggregate"]
    print(f"source_run_id={replay['source_run_id']}")
    print(f"diagnosis_v1={replay['diagnosis_v1']['passed']}/{replay['diagnosis_v1']['total']}")
    print(
        "diagnosis_v2_0="
        f"{v20['cases_passed']}/{v20['cases_total']} "
        f"evaluated={v20['cases_evaluated']} "
        f"insufficient_artifact={v20['cases_insufficient_artifact']}"
    )
    print(
        "diagnosis_v2_1="
        f"{v21['cases_passed']}/{v21['cases_total']} "
        f"evaluated={v21['cases_evaluated']} "
        f"insufficient_artifact={v21['cases_insufficient_artifact']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
