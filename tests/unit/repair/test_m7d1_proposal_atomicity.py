"""M7D-1 fail-closed proposal validation and application-gate regressions."""

from __future__ import annotations

from pathlib import Path

import pytest

from springfix_agent.repair import e2e_runner as e2e_runner_module
from springfix_agent.repair.e2e_runner import EndToEndRepairBenchmarkRunner
from springfix_agent.repair.generator import PatchGenerationResult
from springfix_agent.repair.maven_verifier import MavenVerificationOutcome
from springfix_agent.repair.models import (
    EvidenceSnippet,
    PatchEdit,
    PatchProposal,
    PatchValidationResult,
    RejectedPatchEdit,
)
from springfix_agent.repair.observability import ProposalGenerationAudit
from springfix_agent.repair.validator import validate_patch_proposal
from springfix_agent.repair.verification_models import (
    BaselineVerificationResult,
    MavenTestResult,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _proposal(*edits: PatchEdit) -> PatchProposal:
    return PatchProposal(
        status="proposed",
        summary="M7D-1 synthetic proposal",
        root_cause_reference="candidate:0",
        edits=list(edits),
    )


def _edit(
    file: str,
    start_line: int,
    end_line: int,
    old_code: str,
    new_code: str,
) -> PatchEdit:
    return PatchEdit(
        file=file,
        start_line=start_line,
        end_line=end_line,
        old_code=old_code,
        new_code=new_code,
        rationale="synthetic M7D-1 regression edit",
    )


def _source_root(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    path = root / "src/main/java/App.java"
    path.parent.mkdir(parents=True)
    path.write_text("line one\nline two\nline three\nline four\n", encoding="utf-8")
    return root


def _evidence(start_line: int = 2, end_line: int = 4) -> list[EvidenceSnippet]:
    return [
        EvidenceSnippet(
            file="src/main/java/App.java",
            start_line=start_line,
            end_line=end_line,
            content="synthetic source evidence",
        )
    ]


def test_partial_rejection_fails_atomic_proposal(tmp_path: Path) -> None:
    root = _source_root(tmp_path)
    result = validate_patch_proposal(
        _proposal(
            _edit("src/main/java/App.java", 2, 2, "line two", "line two changed"),
            _edit("src/main/java/App.java", 3, 3, "stale old code", "line three changed"),
        ),
        root,
        _evidence(),
    )

    assert result.proposal.status == "proposed"
    assert result.original_edit_count == 2
    assert result.accepted_edit_count == 1
    assert result.rejected_edit_count == 1
    assert result.original_edit_count == result.accepted_edit_count + result.rejected_edit_count
    assert result.rejected_edits[0].reason == "old_code_mismatch"
    assert result.passed is False


def test_non_import_rejection_also_blocks_proposal(tmp_path: Path) -> None:
    root = _source_root(tmp_path)
    result = validate_patch_proposal(
        _proposal(
            _edit("src/main/java/App.java", 2, 2, "line two", "line two changed"),
            _edit("src/test/AppTest.java", 1, 1, "x", "y"),
        ),
        root,
        _evidence(),
    )

    assert result.accepted_edit_count == 1
    assert result.rejected_edit_count == 1
    assert result.original_edit_count == result.accepted_edit_count + result.rejected_edit_count
    assert result.rejected_edits[0].reason == "path_not_allowed"
    assert result.passed is False


def test_partial_missing_import_rejection_is_atomic(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    path = root / "src/main/java/example/App.java"
    path.parent.mkdir(parents=True)
    path.write_text(
        "package example;\n\n"
        "public class App {\n"
        "    void run() {}\n"
        "    void keep() {}\n"
        "}\n",
        encoding="utf-8",
    )
    file = "src/main/java/example/App.java"
    result = validate_patch_proposal(
        _proposal(
            _edit(file, 4, 4, "    void run() {}", "    SomeFrameworkAnnotation value;"),
            _edit(file, 5, 5, "    void keep() {}", "    void keep() { /* kept */ }"),
        ),
        root,
        [EvidenceSnippet(file=file, start_line=4, end_line=5, content="synthetic Java evidence")],
    )

    assert result.proposal.status == "proposed"
    assert result.original_edit_count == 2
    assert result.accepted_edit_count == 1
    assert result.rejected_edit_count == 1
    assert result.original_edit_count == result.accepted_edit_count + result.rejected_edit_count
    assert result.rejected_edits[0].reason == "missing_required_import"
    assert result.passed is False


def test_zero_edit_proposal_fails(tmp_path: Path) -> None:
    result = validate_patch_proposal(_proposal(), _source_root(tmp_path), [])

    assert result.original_edit_count == 0
    assert result.accepted_edit_count == 0
    assert result.rejected_edit_count == 0
    assert result.original_edit_count == result.accepted_edit_count + result.rejected_edit_count
    assert result.passed is False


def test_single_valid_edit_still_passes(tmp_path: Path) -> None:
    result = validate_patch_proposal(
        _proposal(_edit("src/main/java/App.java", 2, 2, "line two", "line two changed")),
        _source_root(tmp_path),
        _evidence(),
    )

    assert result.passed is True


def test_all_edits_accepted_passes(tmp_path: Path) -> None:
    result = validate_patch_proposal(
        _proposal(
            _edit("src/main/java/App.java", 2, 2, "line two", "line two changed"),
            _edit("src/main/java/App.java", 3, 3, "line three", "line three changed"),
        ),
        _source_root(tmp_path),
        _evidence(),
    )

    assert result.original_edit_count == 2
    assert result.accepted_edit_count == 2
    assert result.rejected_edit_count == 0
    assert result.original_edit_count == result.accepted_edit_count + result.rejected_edit_count
    assert result.passed is True


class _FakeVerifier:
    """Keep the synthetic E2E gate test independent of Maven."""

    def verify_baseline(self, _repository: Path, _expectation: object) -> BaselineVerificationResult:
        return BaselineVerificationResult(
            verified=True,
            maven_result=MavenTestResult(
                executed=True,
                timed_out=False,
                exit_code=1,
                failures=1,
                tests=1,
                target_test_found=True,
                surefire_report_found=True,
            ),
        )

    def verify_patched_workspace(
        self, _workspace: Path, _expectation: object
    ) -> MavenVerificationOutcome:
        return MavenVerificationOutcome(
            result=MavenTestResult(
                executed=True,
                timed_out=False,
                exit_code=0,
                tests=1,
                target_test_found=True,
                surefire_report_found=True,
            )
        )


def _partial_generation_result() -> PatchGenerationResult:
    file = "src/main/java/com/springfix/sample/transaction/service/OrderService.java"
    accepted_edit = _edit(file, 31, 31, "    public void createOrder() {", "    @Transactional\n    public void createOrder() {")
    proposal = _proposal(accepted_edit)
    validation = PatchValidationResult(
        proposal=proposal,
        rejected_edits=[
            RejectedPatchEdit(
                edit_index=1,
                file=file,
                line_range=(32, 32),
                reason="old_code_mismatch",
            )
        ],
        original_edit_count=2,
        accepted_edit_count=1,
    )
    return PatchGenerationResult(
        validation=validation,
        evidence=(),
        generation_error=None,
        patch_llm_calls=1,
        proposal_generation_audit=ProposalGenerationAudit(),
    )


def test_partial_rejection_does_not_call_patch_applier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0
    partial_result = _partial_generation_result()

    def fake_propose(self: object, **_kwargs: object) -> PatchGenerationResult:
        del self
        return partial_result

    def spy_apply(self: object, validation: PatchValidationResult, workspace: object) -> object:
        del self, validation, workspace
        raise AssertionError("PatchApplier must not be reached for a partial proposal")

    def counting_apply(self: object, validation: PatchValidationResult, workspace: object) -> object:
        nonlocal calls
        calls += 1
        return spy_apply(self, validation, workspace)

    monkeypatch.setattr(e2e_runner_module.PatchProposalService, "propose", fake_propose)
    monkeypatch.setattr(e2e_runner_module.PatchApplier, "apply", counting_apply)
    runner = EndToEndRepairBenchmarkRunner(
        project_root=PROJECT_ROOT,
        manifest_path=PROJECT_ROOT / "benchmark/agent_cases.jsonl",
        repair_gold_path=PROJECT_ROOT / "benchmark/repair_gold.jsonl",
        output_dir=tmp_path / "artifacts",
        mode="mock",
        case_id="transaction-self-invocation",
        verifier=_FakeVerifier(),  # type: ignore[arg-type]
    )

    result = runner.run()
    case = result.cases[0]

    assert calls == 0
    assert case.proposal_generated is True
    assert case.proposal_valid is False
    assert case.failed_stage == "proposal"
    assert case.failure_reason == "proposal_partial_rejection"
    assert case.patch_applied is False
    assert case.application_status == "not_run"
    assert case.rejected_edit_count == 1


def test_manual_partial_result_is_not_valid_even_if_status_is_proposed() -> None:
    result = _partial_generation_result().validation

    assert result.proposal.status == "proposed"
    assert result.original_edit_count == 2
    assert result.accepted_edit_count == 1
    assert result.rejected_edit_count == 1
    assert result.passed is False
