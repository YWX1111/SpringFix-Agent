"""Strict loader for the separate M5A Repair Gold manifest."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from springfix_agent.repair.evaluator import RepairGold


def load_repair_gold(path: Path) -> dict[str, RepairGold]:
    """Load Gold after, and only for, deterministic evaluation."""
    result: dict[str, RepairGold] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            gold = RepairGold.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid repair gold at line {line_number}: {exc}") from exc
        if gold.case_id in result:
            raise ValueError(f"duplicate repair Gold case_id: {gold.case_id}")
        result[gold.case_id] = gold
    if not result:
        raise ValueError(f"repair Gold manifest contains no cases: {path}")
    return result
