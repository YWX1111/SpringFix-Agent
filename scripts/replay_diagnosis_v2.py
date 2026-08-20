"""Replay Diagnosis V1/V2 from frozen, sanitized E2E artifacts only."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path

from springfix_agent.benchmark.diagnosis_v2 import (
    load_diagnosis_v2_specs,
    load_frozen_summary,
    replay_frozen_e2e_summary,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _mapping(value: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def main() -> int:
    """Run deterministic replay with zero Agent and LLM calls."""
    args = _parser().parse_args()
    specs = load_diagnosis_v2_specs(args.metadata)
    replay = replay_frozen_e2e_summary(load_frozen_summary(args.summary), specs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(replay, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    diagnosis_v1 = _mapping(replay["diagnosis_v1"], label="diagnosis_v1")
    diagnosis_v2 = _mapping(replay["diagnosis_v2"], label="diagnosis_v2")
    aggregate = _mapping(diagnosis_v2["aggregate"], label="diagnosis_v2.aggregate")
    print(f"source_run_id={replay['source_run_id']}")
    print(
        "diagnosis_v1="
        f"{diagnosis_v1['passed']}/{diagnosis_v1['total']}"
    )
    print(
        "diagnosis_v2="
        f"{aggregate['cases_passed']}/{aggregate['cases_total']} "
        f"evaluated={aggregate['cases_evaluated']} "
        f"insufficient_artifact={aggregate['cases_insufficient_artifact']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
