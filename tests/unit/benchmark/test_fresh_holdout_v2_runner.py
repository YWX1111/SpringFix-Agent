"""Fresh Holdout v2 ledger and scoring boundary tests."""

from __future__ import annotations

import pytest
from scripts.m7f1.fresh_holdout_v2_ledger import (
    FreshHoldoutV2Ledger,
    FreshHoldoutV2LedgerError,
)
from scripts.m7f1.fresh_holdout_v2_runner import FreshHoldoutV2AgentResult


def test_ledger_supports_required_states_and_terminal_transitions() -> None:
    ledger = FreshHoldoutV2Ledger()
    assert ledger.state == "NOT_STARTED"

    ledger.start(start_commit="start")
    assert ledger.state == "RUNNING"
    ledger.record_agent_execution(llm_calls=4, tool_calls=2)
    ledger.complete(end_commit="end")

    snapshot = ledger.snapshot()
    assert snapshot.state == "COMPLETED"
    assert snapshot.start_commit == "start"
    assert snapshot.end_commit == "end"
    assert snapshot.agent_executions == 1
    assert snapshot.llm_calls == 4
    assert snapshot.tool_calls == 2
    with pytest.raises(FreshHoldoutV2LedgerError, match="invalid ledger transition"):
        ledger.start(start_commit="replay")


@pytest.mark.parametrize("invalid_state", ["schema", "infrastructure"])
def test_ledger_quarantines_invalid_runs(invalid_state: str) -> None:
    ledger = FreshHoldoutV2Ledger()

    if invalid_state == "schema":
        ledger.mark_invalid_schema(reason="schema mismatch")
    else:
        ledger.mark_invalid_infrastructure(reason="runner failure")

    snapshot = ledger.snapshot()
    assert snapshot.state == f"INVALID_{invalid_state.upper()}"
    assert snapshot.agent_executions == 0
    assert snapshot.llm_calls == 0
    assert snapshot.tool_calls == 0


def test_agent_result_is_sanitized_and_score_free() -> None:
    result = FreshHoldoutV2AgentResult(
        case_id="fresh-v2-test",
        execution_status="agent_failed",
        llm_calls=0,
        tool_calls=0,
        failure_classification="infrastructure",
    )

    assert "gold" not in result.model_dump()
    assert "reference_patch" not in result.model_dump()
