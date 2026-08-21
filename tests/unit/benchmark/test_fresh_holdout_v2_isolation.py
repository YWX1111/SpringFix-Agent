"""Fresh Holdout v2 Gold/reference isolation and invalid-run tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.m7f1.fresh_holdout_v2_ledger import FreshHoldoutV2Ledger
from scripts.m7f1.fresh_holdout_v2_loader import FreshHoldoutV2Loader
from scripts.m7f1.fresh_holdout_v2_runner import (
    FreshHoldoutV2AgentResult,
    FreshHoldoutV2Runner,
    FreshHoldoutV2RunResult,
)
from scripts.m7f1.fresh_holdout_v2_schema import (
    FRESH_HOLDOUT_V2_PROJECTION_FIELDS,
    AgentCaseInput,
)
from scripts.m7f1.fresh_holdout_v2_scoring import (
    FreshHoldoutV2Score,
    FreshHoldoutV2Scoring,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FRESH_MANIFEST = PROJECT_ROOT / "benchmark" / "fresh_holdout_v2_manifest.json"


def test_gold_and_reference_paths_are_not_read(monkeypatch: pytest.MonkeyPatch) -> None:
    original_read_text = Path.read_text

    def guarded_read_text(self: Path, *args: object, **kwargs: object) -> str:
        lowered = self.as_posix().lower()
        if "gold" in lowered or "reference_patch" in lowered:
            raise AssertionError(f"forbidden file read: {self}")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    manifest, cases = FreshHoldoutV2Loader(project_root=PROJECT_ROOT).load(FRESH_MANIFEST)

    assert manifest.gold_projection == "excluded"
    assert len(cases) == 8


def test_agent_projection_contains_no_gold_or_reference_fields() -> None:
    projection = AgentCaseInput(
        case_id="fresh-v2-test",
        repository="samples/sample-springboot-fresh-v2-h01-conditional-registration",
        issue_description="A bounded issue.",
        error_log="test failure",
        error_log_version="sanitized-v1",
    )

    assert tuple(projection.model_dump()) == FRESH_HOLDOUT_V2_PROJECTION_FIELDS
    assert all("gold" not in field for field in projection.model_dump())
    assert all("reference" not in field for field in projection.model_dump())


def test_schema_failure_prevents_agent_execution_and_is_not_replayable(tmp_path: Path) -> None:
    malformed_manifest = tmp_path / "malformed.json"
    malformed_manifest.write_text("{\"schema_version\": \"wrong\"}", encoding="utf-8")
    calls: list[str] = []

    def executor(_: AgentCaseInput) -> FreshHoldoutV2AgentResult:
        calls.append("agent")
        return FreshHoldoutV2AgentResult(
            case_id="unexpected",
            execution_status="agent_completed",
            llm_calls=1,
            tool_calls=1,
        )

    ledger = FreshHoldoutV2Ledger()
    runner = FreshHoldoutV2Runner(
        loader=FreshHoldoutV2Loader(project_root=tmp_path),
        agent_executor=executor,
        ledger=ledger,
    )

    result = runner.run(
        manifest_path=malformed_manifest,
        start_commit="start",
        end_commit="end",
    )

    assert result.status == "INVALID_SCHEMA"
    assert result.repair_score is None
    assert result.diagnosis_score is None
    assert calls == []
    assert result.ledger.agent_executions == 0
    with pytest.raises(RuntimeError, match="schema invalidation|replayed"):
        ledger.mark_invalid_schema(reason="second attempt")


def test_scoring_is_rejected_before_frozen_completed_result() -> None:
    called: list[str] = []

    def scorer(_: object) -> FreshHoldoutV2Score:
        called.append("scoring")
        return FreshHoldoutV2Score(repair_score=1.0)

    scoring = FreshHoldoutV2Scoring(scoring_function=scorer)
    ledger = FreshHoldoutV2Ledger()
    ledger.mark_invalid_schema(reason="schema mismatch")
    invalid_result = FreshHoldoutV2RunResult(
        status="INVALID_SCHEMA",
        ledger=ledger.snapshot(),
    )

    with pytest.raises(ValueError, match="completed Agent run"):
        scoring.score(invalid_result)
    assert called == []
