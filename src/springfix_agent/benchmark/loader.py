"""Strict JSONL loader for offline benchmark manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from springfix_agent.benchmark.models import BenchmarkCase


class BenchmarkManifestError(ValueError):
    """Raised when a benchmark manifest cannot be loaded safely."""


def load_cases(path: Path) -> list[BenchmarkCase]:
    """Load and validate a JSONL manifest, rejecting duplicate case IDs."""
    cases: list[BenchmarkCase] = []
    seen_ids: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise BenchmarkManifestError(f"cannot read manifest {path}: {exc}") from exc

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload: Any = json.loads(line)
            case = BenchmarkCase.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            raise BenchmarkManifestError(
                f"invalid benchmark case at line {line_number}: {exc}"
            ) from exc
        if case.case_id in seen_ids:
            raise BenchmarkManifestError(
                f"duplicate case_id {case.case_id!r} at line {line_number}"
            )
        seen_ids.add(case.case_id)
        cases.append(case)

    if not cases:
        raise BenchmarkManifestError(f"manifest contains no cases: {path}")
    return cases


load_benchmark_cases = load_cases
load_jsonl = load_cases
load_manifest = load_cases
