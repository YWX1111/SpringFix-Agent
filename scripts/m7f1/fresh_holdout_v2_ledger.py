"""Non-reentrant execution ledger for the M7F-1 runner boundary."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LedgerState = Literal[
    "NOT_STARTED",
    "RUNNING",
    "INVALID_SCHEMA",
    "INVALID_INFRASTRUCTURE",
    "COMPLETED",
]


class FreshHoldoutV2LedgerError(RuntimeError):
    """Raised when the one-shot ledger receives an invalid transition."""


class FreshHoldoutV2LedgerSnapshot(BaseModel):
    """Immutable, redacted ledger state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    state: LedgerState
    start_commit: str | None = None
    end_commit: str | None = None
    reason: str | None = None
    agent_executions: int = Field(ge=0)
    llm_calls: int = Field(ge=0)
    tool_calls: int = Field(ge=0)


class FreshHoldoutV2Ledger:
    """Track one non-replayable Fresh v2 execution attempt."""

    _terminal_states = {"INVALID_SCHEMA", "INVALID_INFRASTRUCTURE", "COMPLETED"}

    def __init__(self) -> None:
        self._state: LedgerState = "NOT_STARTED"
        self._start_commit: str | None = None
        self._end_commit: str | None = None
        self._reason: str | None = None
        self._agent_executions = 0
        self._llm_calls = 0
        self._tool_calls = 0

    @property
    def state(self) -> LedgerState:
        """Return the current state."""
        return self._state

    def start(self, *, start_commit: str) -> None:
        """Enter RUNNING exactly once."""
        self._require_state("NOT_STARTED")
        self._state = "RUNNING"
        self._start_commit = start_commit

    def record_agent_execution(self, *, llm_calls: int, tool_calls: int) -> None:
        """Record one case execution while RUNNING."""
        self._require_state("RUNNING")
        if llm_calls < 0 or tool_calls < 0:
            raise ValueError("execution counters must be non-negative")
        self._agent_executions += 1
        self._llm_calls += llm_calls
        self._tool_calls += tool_calls

    def mark_invalid_schema(self, *, reason: str) -> None:
        """Quarantine a schema failure before any Agent execution."""
        self._mark_invalid("INVALID_SCHEMA", reason)

    def mark_invalid_infrastructure(self, *, reason: str) -> None:
        """Quarantine an infrastructure failure without replay."""
        self._mark_invalid("INVALID_INFRASTRUCTURE", reason)

    def complete(self, *, end_commit: str) -> None:
        """Complete the run and close the ledger."""
        self._require_state("RUNNING")
        self._state = "COMPLETED"
        self._end_commit = end_commit

    def snapshot(self) -> FreshHoldoutV2LedgerSnapshot:
        """Return a redacted immutable snapshot."""
        return FreshHoldoutV2LedgerSnapshot(
            state=self._state,
            start_commit=self._start_commit,
            end_commit=self._end_commit,
            reason=self._reason,
            agent_executions=self._agent_executions,
            llm_calls=self._llm_calls,
            tool_calls=self._tool_calls,
        )

    def _mark_invalid(self, state: LedgerState, reason: str) -> None:
        """Move to one terminal invalid state."""
        if state == "INVALID_SCHEMA" and self._state != "NOT_STARTED":
            raise FreshHoldoutV2LedgerError("schema invalidation is only valid before execution")
        if self._state not in {"NOT_STARTED", "RUNNING"}:
            raise FreshHoldoutV2LedgerError("invalid run cannot be replayed")
        self._state = state
        self._reason = reason

    def _require_state(self, expected: LedgerState) -> None:
        """Reject all invalid or terminal transitions."""
        if self._state != expected or self._state in self._terminal_states:
            raise FreshHoldoutV2LedgerError(
                f"invalid ledger transition: state={self._state}, expected={expected}"
            )
