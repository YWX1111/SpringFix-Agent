"""Post-execution scoring boundary for Fresh Holdout v2."""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field
from scripts.m7f1.fresh_holdout_v2_runner import FreshHoldoutV2RunResult


class FreshHoldoutV2Score(BaseModel):
    """Scores produced only after the Agent result is frozen."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    repair_score: float | None = Field(default=None, ge=0.0, le=1.0)
    diagnosis_score: float | None = Field(default=None, ge=0.0, le=1.0)
    failure_classification: str | None = None


ScoringFunction = Callable[[FreshHoldoutV2RunResult], FreshHoldoutV2Score]


class FreshHoldoutV2Scoring:
    """Invoke a separately supplied scorer after execution completion."""

    def __init__(self, *, scoring_function: ScoringFunction) -> None:
        self.scoring_function = scoring_function

    def score(self, run_result: FreshHoldoutV2RunResult) -> FreshHoldoutV2Score:
        """Reject invalid/incomplete runs before any scoring function call."""
        if run_result.status != "COMPLETED":
            raise ValueError("Fresh v2 scoring requires a completed Agent run")
        if run_result.repair_score is not None or run_result.diagnosis_score is not None:
            raise ValueError("Fresh v2 run result must not contain precomputed scores")
        return self.scoring_function(run_result)
