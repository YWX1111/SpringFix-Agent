"""M5A three-case Mock benchmark regression."""

from __future__ import annotations

from pathlib import Path

from springfix_agent.repair.runner import RepairProposalRunner

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_mock_repair_benchmark_generates_and_validates_three_cases(tmp_path: Path) -> None:
    result = RepairProposalRunner(
        project_root=PROJECT_ROOT,
        manifest_path=PROJECT_ROOT / "benchmark" / "agent_cases.jsonl",
        repair_gold_path=PROJECT_ROOT / "benchmark" / "repair_gold.jsonl",
        output_dir=tmp_path / "artifacts",
        mode="mock",
    ).run()
    assert result.aggregate.sample_size == 3
    assert result.aggregate.proposal_generation_rate == 1.0
    assert result.aggregate.proposal_validation_rate == 1.0
    assert result.aggregate.total_diagnostic_llm_calls == 9
    assert result.aggregate.total_patch_llm_calls == 3
    assert result.aggregate.total_logical_llm_calls == 12
    assert (tmp_path / "artifacts" / "mock" / "transaction-self-invocation" / "proposal.json").exists()
