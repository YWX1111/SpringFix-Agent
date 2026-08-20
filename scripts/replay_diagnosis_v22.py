"""Replay frozen V1/V2.0/V2.1/V2.2 from bounded E2E artifacts only."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path

from springfix_agent.benchmark.diagnosis_v2 import load_diagnosis_v2_specs
from springfix_agent.benchmark.diagnosis_v22 import (
    load_diagnosis_v22_specs,
    load_frozen_summary,
    replay_frozen_e2e_summary_v22,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--v20-metadata", type=Path, required=True)
    parser.add_argument("--v22-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _mapping(value: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def main() -> int:
    """Run deterministic replay with zero Agent and LLM calls."""
    args = _parser().parse_args()
    replay = replay_frozen_e2e_summary_v22(
        load_frozen_summary(args.summary),
        load_diagnosis_v22_specs(args.v22_metadata),
        load_diagnosis_v2_specs(args.v20_metadata),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(replay, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    aggregate = _mapping(replay["diagnosis_v2_2"], label="diagnosis_v2_2")["aggregate"]
    aggregate = _mapping(aggregate, label="diagnosis_v2_2.aggregate")
    print(f"source_run_id={replay['source_run_id']}")
    print(
        "diagnosis_v2_2="
        f"{aggregate['cases_passed']}/{aggregate['cases_total']} "
        f"evaluated={aggregate['cases_evaluated']} "
        f"insufficient_artifact={aggregate['cases_insufficient_artifact']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
