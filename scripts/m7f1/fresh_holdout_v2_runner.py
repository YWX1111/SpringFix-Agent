"""Dedicated Fresh Holdout v2 Agent execution boundary.

The runner is intentionally callback-based.  Loading Gold or reference
patches is impossible through this interface; scoring is a separate phase.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from scripts.m7f1.fresh_holdout_v2_ledger import (
    FreshHoldoutV2Ledger,
    FreshHoldoutV2LedgerError,
    FreshHoldoutV2LedgerSnapshot,
)
from scripts.m7f1.fresh_holdout_v2_loader import (
    FreshHoldoutV2InfrastructureError,
    FreshHoldoutV2Loader,
    FreshHoldoutV2SchemaError,
)
from scripts.m7f1.fresh_holdout_v2_schema import AgentCaseInput

AgentCaseExecutor = Callable[[AgentCaseInput], "FreshHoldoutV2AgentResult"]
ExecutionResultStatus = Literal["agent_completed", "agent_failed", "timeout"]
RunResultStatus = Literal[
    "INVALID_SCHEMA",
    "INVALID_INFRASTRUCTURE",
    "COMPLETED",
]


class FreshHoldoutV2AgentResult(BaseModel):
    """Sanitized result returned by one Agent-facing case execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1)
    execution_status: ExecutionResultStatus
    llm_calls: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    artifact_path: str | None = None
    failure_classification: str | None = None


class FreshHoldoutV2RunResult(BaseModel):
    """Frozen execution output with no Gold-derived score fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: RunResultStatus
    start_commit: str | None = None
    end_commit: str | None = None
    cases: tuple[FreshHoldoutV2AgentResult, ...] = ()
    ledger: FreshHoldoutV2LedgerSnapshot
    repair_score: None = None
    diagnosis_score: None = None


class FreshHoldoutV2Runner:
    """Run the Agent-facing phase without importing Gold or reference patches."""

    def __init__(
        self,
        *,
        loader: FreshHoldoutV2Loader,
        agent_executor: AgentCaseExecutor,
        ledger: FreshHoldoutV2Ledger | None = None,
    ) -> None:
        self.loader = loader
        self.agent_executor = agent_executor
        self.ledger = ledger or FreshHoldoutV2Ledger()

    def run(
        self,
        *,
        manifest_path: Path,
        start_commit: str,
        end_commit: str,
    ) -> FreshHoldoutV2RunResult:
        """Validate, execute once, and freeze sanitized Agent results."""
        try:
            _, cases = self.loader.load(manifest_path)
        except FreshHoldoutV2SchemaError as exc:
            self.ledger.mark_invalid_schema(reason=str(exc))
            return self._result()
        except FreshHoldoutV2InfrastructureError as exc:
            self.ledger.mark_invalid_infrastructure(reason=str(exc))
            return self._result()

        try:
            self.ledger.start(start_commit=start_commit)
        except FreshHoldoutV2LedgerError:
            raise

        results: list[FreshHoldoutV2AgentResult] = []
        for case in cases:
            try:
                agent_result = self.agent_executor(case.agent_input())
                if agent_result.case_id != case.case_id:
                    raise ValueError(
                        f"Agent result case mismatch: expected {case.case_id}"
                    )
                self.ledger.record_agent_execution(
                    llm_calls=agent_result.llm_calls,
                    tool_calls=agent_result.tool_calls,
                )
            except Exception as exc:  # noqa: BLE001
                self.ledger.mark_invalid_infrastructure(
                    reason=f"Fresh v2 Agent execution failed: {type(exc).__name__}"
                )
                return self._result(cases=tuple(results))
            results.append(agent_result)

        self.ledger.complete(end_commit=end_commit)
        return self._result(cases=tuple(results))

    def _result(
        self,
        *,
        cases: tuple[FreshHoldoutV2AgentResult, ...] = (),
    ) -> FreshHoldoutV2RunResult:
        """Build a result from the ledger without scoring."""
        snapshot = self.ledger.snapshot()
        if snapshot.state not in {"INVALID_SCHEMA", "INVALID_INFRASTRUCTURE", "COMPLETED"}:
            raise RuntimeError(f"run result is not terminal: {snapshot.state}")
        return FreshHoldoutV2RunResult(
            status=snapshot.state,
            start_commit=snapshot.start_commit,
            end_commit=snapshot.end_commit,
            cases=cases,
            ledger=snapshot,
        )
