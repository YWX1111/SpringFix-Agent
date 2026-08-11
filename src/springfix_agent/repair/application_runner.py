"""Offline M5B Patch Application runner and deterministic aggregate metrics."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from springfix_agent.benchmark.loader import load_cases
from springfix_agent.benchmark.models import BenchmarkCase
from springfix_agent.benchmark.runner import benchmark_profile_for_case
from springfix_agent.llm.mock import MockLLMClient
from springfix_agent.llm.profiles import get_profile_response
from springfix_agent.llm.schemas import RootCauseAnalysis
from springfix_agent.repair.application_models import (
    PatchApplicationAggregateMetrics,
    PatchApplicationCaseMetrics,
    PatchApplicationResult,
    PatchApplicationRunResult,
)
from springfix_agent.repair.applier import PatchApplier
from springfix_agent.repair.artifacts import write_patch_application_artifacts
from springfix_agent.repair.evaluator import RepairGold
from springfix_agent.repair.generator import PatchProposalService
from springfix_agent.repair.loader import load_repair_gold
from springfix_agent.repair.models import EvidenceSnippet, PatchProposal, PatchValidationResult
from springfix_agent.repair.validator import validate_patch_proposal
from springfix_agent.repair.workspace import IsolatedPatchWorkspace, create_isolated_patch_workspace
from springfix_agent.tools._path_safety import PathSafetyError, canonicalize_repository

PatchApplicationMode = Literal["mock"]


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _normalise_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _read_range(path: Path, start_line: int, end_line: int) -> str:
    """Read a fixture evidence range without searching or fuzzy matching."""
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    lines = _normalise_newlines(raw.decode("utf-8")).split("\n")
    return "\n".join(lines[start_line - 1 : end_line])


def _fixture_evidence(repository_root: Path, rca: RootCauseAnalysis) -> list[dict[str, object]]:
    """Materialize the M5A Mock profile's references as retrieved snippets."""
    result: list[dict[str, object]] = []
    raw = rca.model_dump()
    candidates = raw.get("candidates")
    if not isinstance(candidates, list):
        return result
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        references = candidate.get("evidence")
        if not isinstance(references, list):
            continue
        for reference in references:
            if not isinstance(reference, dict):
                continue
            file = reference.get("file")
            start = reference.get("start_line")
            end = reference.get("end_line")
            if not isinstance(file, str) or not isinstance(start, int) or not isinstance(end, int):
                continue
            path = repository_root / Path(file)
            if not path.is_file():
                continue
            result.append(
                {
                    "file": file,
                    "line_range": (start, end),
                    "content": _read_range(path, start, end),
                }
            )
    return result


def _mock_validated_proposal(repository_root: Path, case: BenchmarkCase) -> PatchValidationResult:
    """Generate and validate one deterministic M5A Mock proposal fixture."""
    profile = benchmark_profile_for_case(case.case_id)
    rca = get_profile_response(profile, RootCauseAnalysis)
    if not isinstance(rca, RootCauseAnalysis):
        raise ValueError(f"Mock profile has no RootCauseAnalysis: {profile}")
    mock = MockLLMClient()
    mock.use_profile(profile)
    result = PatchProposalService(mock).propose(
        repository_root=repository_root,
        root_cause_analysis=rca,
        retrieved_snippets=_fixture_evidence(repository_root, rca),
        task_id=f"m5b-{case.case_id}",
    )
    return result.validation


def _proposal_from_payload(payload: object) -> tuple[PatchProposal, list[EvidenceSnippet]]:
    """Read an untrusted proposal payload; validation is always performed later."""
    if not isinstance(payload, dict):
        raise ValueError("proposal file must contain a JSON object")
    proposal_payload = payload.get("proposal")
    if proposal_payload is None:
        allowed = set(PatchProposal.model_fields)
        proposal_payload = {key: value for key, value in payload.items() if key in allowed}
    evidence_payload = payload.get("validated_evidence", payload.get("evidence", []))
    if not isinstance(evidence_payload, list):
        raise ValueError("validated_evidence must be a list")
    try:
        proposal = PatchProposal.model_validate(proposal_payload)
        evidence = [EvidenceSnippet.model_validate(item) for item in evidence_payload]
    except (ValidationError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid proposal file: {exc}") from exc
    return proposal, evidence


def _validated_proposal_file(path: Path, repository_root: Path) -> PatchValidationResult:
    """Load a proposal file and re-run the M5A deterministic validator."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    proposal, evidence = _proposal_from_payload(payload)
    return validate_patch_proposal(proposal, repository_root, evidence)


def _expected_file_hit(application: PatchApplicationResult, gold: RepairGold) -> bool:
    acceptable = {file.replace("\\", "/").casefold() for file in gold.acceptable_files}
    changed = {file.replace("\\", "/").casefold() for file in application.changed_files}
    return bool(changed) and changed.issubset(acceptable)


def _metrics(
    case: BenchmarkCase,
    validation: PatchValidationResult,
    application: PatchApplicationResult,
    gold: RepairGold | None,
    cleanup_success: bool,
    duration_ms: int,
) -> PatchApplicationCaseMetrics:
    requested = application.edits_requested
    applied = application.edits_applied
    return PatchApplicationCaseMetrics(
        case_id=case.case_id,
        proposal_valid=validation.passed,
        proposal_status=application.proposal_status,
        application_status=application.status,
        requested_edit_count=requested,
        applied_edit_count=applied,
        rejected_edit_count=application.edits_rejected,
        all_edits_applied=requested > 0 and applied == requested,
        original_repository_unchanged=application.original_repository_unchanged,
        changed_file_count=len(application.changed_files),
        expected_changed_file_hit=_expected_file_hit(application, gold) if gold is not None else None,
        diff_generated=application.status == "applied",
        diff_non_empty=bool(application.unified_diff),
        workspace_cleanup_success=cleanup_success,
        application_duration_ms=max(0, duration_ms),
    )


def aggregate_patch_application_metrics(
    cases: list[PatchApplicationCaseMetrics],
) -> PatchApplicationAggregateMetrics:
    """Aggregate M5B metrics using the executed cases as denominators."""
    size = len(cases)
    return PatchApplicationAggregateMetrics(
        sample_size=size,
        proposal_validation_rate=_ratio(sum(item.proposal_valid for item in cases), size),
        application_success_rate=_ratio(
            sum(item.application_status == "applied" for item in cases), size
        ),
        all_edits_applied_rate=_ratio(sum(item.all_edits_applied for item in cases), size),
        original_repository_integrity_rate=_ratio(
            sum(item.original_repository_unchanged for item in cases), size
        ),
        diff_generation_rate=_ratio(sum(item.diff_generated for item in cases), size),
        workspace_cleanup_rate=_ratio(sum(item.workspace_cleanup_success for item in cases), size),
    )


class PatchApplicationRunner:
    """Run deterministic M5B applications without executing project commands."""

    def __init__(
        self,
        *,
        project_root: Path,
        manifest_path: Path,
        repair_gold_path: Path,
        output_dir: Path,
        mode: PatchApplicationMode = "mock",
        case_id: str | None = None,
        proposal_file: Path | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.manifest_path = manifest_path.resolve()
        self.repair_gold_path = repair_gold_path.resolve()
        self.output_dir = output_dir.resolve()
        self.mode = mode
        self.case_id = case_id
        self.proposal_file = proposal_file.resolve() if proposal_file is not None else None

    def run(self) -> PatchApplicationRunResult:
        """Apply every selected proposal and write only redacted artifacts."""
        if self.mode != "mock":
            raise ValueError("M5B runner supports deterministic mock mode only")
        cases = load_cases(self.manifest_path)
        if self.case_id is not None:
            cases = [case for case in cases if case.case_id == self.case_id]
            if not cases:
                raise ValueError(f"case not found in manifest: {self.case_id}")
        if self.proposal_file is not None and len(cases) != 1:
            raise ValueError("--proposal-file requires --case")
        applications: dict[str, PatchApplicationResult] = {}
        metrics: list[PatchApplicationCaseMetrics] = []
        for case in cases:
            application, case_metrics = self._run_case(case)
            applications[case.case_id] = application
            metrics.append(case_metrics)
        result = PatchApplicationRunResult(
            mode="mock",
            cases=metrics,
            aggregate=aggregate_patch_application_metrics(metrics),
        )
        write_patch_application_artifacts(
            result,
            applications,
            self.output_dir / self.mode,
        )
        return result

    def _run_case(
        self,
        case: BenchmarkCase,
    ) -> tuple[PatchApplicationResult, PatchApplicationCaseMetrics]:
        source = self._resolve_case_repository(case)
        started = time.monotonic()
        application: PatchApplicationResult
        validation: PatchValidationResult
        workspace: IsolatedPatchWorkspace
        with create_isolated_patch_workspace(source) as workspace:
            if workspace.path is None:
                raise RuntimeError("isolated workspace was not initialized")
            if self.proposal_file is not None:
                validation = _validated_proposal_file(self.proposal_file, workspace.path)
            else:
                validation = _mock_validated_proposal(workspace.path, case)
            # Gold is intentionally not passed to PatchApplier.  It is used only
            # by _metrics after application for the post-application file check.
            application = PatchApplier().apply(validation, workspace)
            cleanup_success_before_exit = workspace.cleanup_succeeded
        cleanup_success = cleanup_success_before_exit is not False
        application = application.model_copy(update={"workspace_cleaned": cleanup_success})
        # Repair Gold is loaded only after the temporary application has
        # completed and is never passed to PatchApplier.
        gold_by_case = load_repair_gold(self.repair_gold_path)
        try:
            gold = gold_by_case[case.case_id]
        except KeyError as exc:
            raise ValueError(f"repair Gold missing for case: {case.case_id}") from exc
        metrics = _metrics(
            case,
            validation,
            application,
            gold,
            cleanup_success,
            int((time.monotonic() - started) * 1000),
        )
        return application, metrics

    def _resolve_case_repository(self, case: BenchmarkCase) -> Path:
        candidate = self.project_root / Path(case.repository)
        try:
            return canonicalize_repository(candidate, self.project_root)
        except PathSafetyError as exc:
            raise ValueError(f"invalid repository for case {case.case_id}: {exc}") from exc


def run_patch_application(
    *,
    project_root: Path,
    manifest_path: Path,
    repair_gold_path: Path,
    output_dir: Path,
    mode: PatchApplicationMode = "mock",
    case_id: str | None = None,
    proposal_file: Path | None = None,
) -> PatchApplicationRunResult:
    """Convenience entry point for the M5B CLI and tests."""
    return PatchApplicationRunner(
        project_root=project_root,
        manifest_path=manifest_path,
        repair_gold_path=repair_gold_path,
        output_dir=output_dir,
        mode=mode,
        case_id=case_id,
        proposal_file=proposal_file,
    ).run()


__all__ = [
    "PatchApplicationRunner",
    "aggregate_patch_application_metrics",
    "run_patch_application",
]
