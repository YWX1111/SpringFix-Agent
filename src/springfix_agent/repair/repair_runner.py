"""M5C deterministic isolated Maven repair verification runner."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Literal

from springfix_agent.benchmark.loader import load_cases
from springfix_agent.benchmark.models import BenchmarkCase
from springfix_agent.repair.application_models import PatchApplicationResult
from springfix_agent.repair.application_runner import (
    _mock_validated_proposal,
    _proposal_from_payload,
)
from springfix_agent.repair.applier import PatchApplier
from springfix_agent.repair.maven_verifier import MavenRepairVerifier, MavenVerificationOutcome
from springfix_agent.repair.models import PatchValidationResult
from springfix_agent.repair.repair_metrics import (
    aggregate_repair_metrics,
    write_repair_verification_artifacts,
)
from springfix_agent.repair.validator import validate_patch_proposal
from springfix_agent.repair.verification_models import (
    MavenTestResult,
    RepairCaseMetrics,
    RepairVerificationResult,
    RepairVerificationRunResult,
    VerificationStatus,
)
from springfix_agent.repair.workspace import (
    IsolatedPatchWorkspace,
    compute_repository_manifest,
    create_isolated_patch_workspace,
)
from springfix_agent.tools._path_safety import PathSafetyError, canonicalize_repository

RepairVerificationMode = Literal["mock"]


def _normalise_path(value: str) -> str:
    return value.replace("\\", "/")


def _fixture_proposal(repository_root: Path, case: BenchmarkCase) -> PatchValidationResult:
    """Obtain the deterministic M5A Mock proposal and rerun its validator."""
    # Reuse the established M5B fixture helper; it calls the M5A Mock service
    # and validator, so M5C never trusts a proposal merely because it is a file.
    return _mock_validated_proposal(repository_root, case)


def _proposal_file(path: Path, repository_root: Path) -> PatchValidationResult:
    """Read an untrusted proposal file and always validate it against the copy."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    proposal, evidence = _proposal_from_payload(payload)
    return validate_patch_proposal(proposal, repository_root, evidence)


def _tree_slice(manifest: dict[str, str], prefix: str) -> dict[str, str]:
    normalized = _normalise_path(prefix).rstrip("/") + "/"
    return {key: value for key, value in manifest.items() if key.startswith(normalized)}


def _pom_hash(manifest: dict[str, str]) -> str | None:
    return manifest.get("pom.xml")


def _changed_files(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(
        key
        for key in set(before) | set(after)
        if before.get(key) != after.get(key)
    )


def _default_maven_result() -> MavenTestResult:
    return MavenTestResult(executed=False, timed_out=False)


def _case_metrics(result: RepairVerificationResult) -> RepairCaseMetrics:
    maven = result.maven_result
    return RepairCaseMetrics(
        case_id=result.case_id,
        baseline_verified=result.baseline_verified,
        proposal_valid=result.proposal_valid,
        patch_applied=result.patch_applied,
        all_edits_applied=result.all_edits_applied,
        original_repository_unchanged=result.original_repository_unchanged,
        maven_executed=maven.executed,
        maven_exit_code=maven.exit_code,
        maven_timed_out=maven.timed_out,
        target_test_found=maven.target_test_found,
        tests=maven.tests,
        failures=maven.failures,
        errors=maven.errors,
        skipped=maven.skipped,
        repair_success=result.repair_success,
        failure_reason=result.failure_reason,
        verification_status=result.verification_status,
        verification_duration_ms=result.verification_duration_ms,
        workspace_cleanup_success=result.workspace_cleanup_success,
    )


class RepairVerificationRunner:
    """Run M5C cases without accepting arbitrary commands or live LLM calls."""

    def __init__(
        self,
        *,
        project_root: Path,
        manifest_path: Path,
        output_dir: Path,
        mode: RepairVerificationMode = "mock",
        case_id: str | None = None,
        proposal_file: Path | None = None,
        verifier: MavenRepairVerifier | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.manifest_path = manifest_path.resolve()
        self.output_dir = output_dir.resolve()
        self.mode = mode
        self.case_id = case_id
        self.proposal_file = proposal_file.resolve() if proposal_file is not None else None
        self.verifier = verifier if verifier is not None else MavenRepairVerifier()

    def run(self) -> RepairVerificationRunResult:
        """Verify each selected case and write sanitized deterministic artifacts."""
        if self.mode != "mock":
            raise ValueError("M5C supports deterministic mock mode only")
        cases = load_cases(self.manifest_path)
        if self.case_id is not None:
            cases = [case for case in cases if case.case_id == self.case_id]
            if not cases:
                raise ValueError(f"case not found in manifest: {self.case_id}")
        if self.proposal_file is not None and len(cases) != 1:
            raise ValueError("--proposal-file requires --case")

        case_results: list[RepairVerificationResult] = []
        details: dict[str, dict[str, object]] = {}
        for case in cases:
            case_result, case_details = self._run_case(case)
            case_results.append(case_result)
            details[case.case_id] = case_details

        metrics = [_case_metrics(item) for item in case_results]
        result = RepairVerificationRunResult(
            mode="mock",
            cases=metrics,
            aggregate=aggregate_repair_metrics(metrics),
        )
        write_repair_verification_artifacts(
            result,
            details,
            self.output_dir / self.mode,
        )
        return result

    def _run_case(
        self,
        case: BenchmarkCase,
    ) -> tuple[RepairVerificationResult, dict[str, object]]:
        started = time.monotonic()
        source = self._resolve_case_repository(case)
        original_before = compute_repository_manifest(source)
        baseline = self.verifier.verify_baseline(source, case.expected_maven)
        original_after_baseline = compute_repository_manifest(source)
        original_unchanged = original_before == original_after_baseline
        cleanup_success = True
        application: PatchApplicationResult | None = None
        maven_result = _default_maven_result()
        maven_failure_reason: str | None = None
        proposal_valid = False
        patch_applied = False
        all_edits_applied = False
        test_integrity = False
        pom_integrity = False
        source_integrity = False
        failure_reason: str | None

        if not baseline.verified:
            failure_reason = baseline.failure_reason or "baseline_bug_not_reproduced"
        else:
            try:
                (
                    application,
                    proposal_valid,
                    patch_applied,
                    all_edits_applied,
                    test_integrity,
                    pom_integrity,
                    source_integrity,
                    maven_result,
                    maven_failure_reason,
                    cleanup_success,
                ) = self._apply_and_verify(case, source)
                failure_reason = self._failure_reason(
                    proposal_valid=proposal_valid,
                    patch_applied=patch_applied,
                    all_edits_applied=all_edits_applied,
                    original_unchanged=original_unchanged,
                    test_integrity=test_integrity,
                    pom_integrity=pom_integrity,
                    source_integrity=source_integrity,
                    cleanup_success=cleanup_success,
                    outcome_reason=maven_failure_reason,
                )
            except Exception:  # noqa: BLE001 - one bad case must be reported, not hidden
                failure_reason = "verification_internal_error"
                cleanup_success = False

        original_unchanged = original_unchanged and self._source_is_unchanged(
            source,
            original_before,
        )
        duration_ms = max(0, int((time.monotonic() - started) * 1000))
        repair_success = (
            baseline.verified
            and proposal_valid
            and patch_applied
            and all_edits_applied
            and original_unchanged
            and test_integrity
            and pom_integrity
            and source_integrity
            and maven_result.executed
            and not maven_result.timed_out
            and maven_result.exit_code == 0
            and maven_result.target_test_found
            and maven_result.tests > 0
            and maven_result.failures == 0
            and maven_result.errors == 0
            and maven_result.skipped == 0
            and cleanup_success
        )
        verification_status: VerificationStatus
        if repair_success:
            failure_reason = None
        elif failure_reason is None:
            failure_reason = "verification_internal_error"
        if repair_success:
            verification_status = "success"
        elif maven_result.timed_out:
            verification_status = "timeout"
        elif not maven_result.executed:
            verification_status = "not_executed"
        else:
            verification_status = "failed"

        result = RepairVerificationResult(
            case_id=case.case_id,
            baseline_verified=baseline.verified,
            proposal_valid=proposal_valid,
            patch_applied=patch_applied,
            all_edits_applied=all_edits_applied,
            original_repository_unchanged=original_unchanged,
            test_integrity_verified=test_integrity,
            pom_integrity_verified=pom_integrity,
            source_integrity_verified=source_integrity,
            maven_result=maven_result,
            repair_success=repair_success,
            failure_reason=failure_reason,
            verification_status=verification_status,
            workspace_cleanup_success=cleanup_success,
            verification_duration_ms=duration_ms,
        )
        detail: dict[str, object] = {"baseline": baseline.model_dump()}
        if application is not None:
            application_payload = application.model_dump()
            application_payload.pop("unified_diff", None)
            detail["application"] = application_payload
        detail["maven"] = maven_result.model_dump()
        return result, detail

    def _apply_and_verify(
        self,
        case: BenchmarkCase,
        source: Path,
    ) -> tuple[
        PatchApplicationResult,
        bool,
        bool,
        bool,
        bool,
        bool,
        bool,
        MavenTestResult,
        str | None,
        bool,
    ]:
        workspace: IsolatedPatchWorkspace = create_isolated_patch_workspace(source)
        application: PatchApplicationResult
        validation: PatchValidationResult
        maven_result = _default_maven_result()
        maven_failure_reason: str | None = None
        with workspace:
            if workspace.path is None:
                raise RuntimeError("isolated workspace was not initialized")
            before = compute_repository_manifest(workspace.path)
            test_before = _tree_slice(before, "src/test")
            pom_before = _pom_hash(before)
            if self.proposal_file is not None:
                validation = _proposal_file(self.proposal_file, workspace.path)
            else:
                validation = _fixture_proposal(workspace.path, case)
            application = PatchApplier().apply(validation, workspace)
            after_patch = compute_repository_manifest(workspace.path)
            changed_files = _changed_files(before, after_patch)
            expected_changed = sorted(_normalise_path(item) for item in application.changed_files)
            source_integrity = changed_files == expected_changed
            test_integrity = (
                test_before == _tree_slice(after_patch, "src/test")
            )
            pom_integrity = pom_before == _pom_hash(after_patch)
            proposal_valid = validation.passed
            patch_applied = application.status == "applied"
            all_edits_applied = (
                patch_applied
                and application.edits_requested > 0
                and application.edits_applied == application.edits_requested
                and not application.rejected_edits
            )
            if proposal_valid and patch_applied and source_integrity and test_integrity and pom_integrity:
                outcome: MavenVerificationOutcome = self.verifier.verify_patched_workspace(
                    workspace.path,
                    case.expected_maven,
                )
                maven_result = outcome.result
                maven_failure_reason = outcome.failure_reason
            after_maven = compute_repository_manifest(workspace.path)
            test_integrity = test_integrity and test_before == _tree_slice(after_maven, "src/test")
            pom_integrity = pom_integrity and pom_before == _pom_hash(after_maven)
            source_integrity = source_integrity and after_patch == after_maven
            cleanup_success_before_exit = workspace.cleanup_succeeded
        cleanup_success = cleanup_success_before_exit is not False
        application = application.model_copy(update={"workspace_cleaned": cleanup_success})
        return (
            application,
            proposal_valid,
            patch_applied,
            all_edits_applied,
            test_integrity,
            pom_integrity,
            source_integrity,
            maven_result,
            maven_failure_reason,
            cleanup_success,
        )

    @staticmethod
    def _failure_reason(
        *,
        proposal_valid: bool,
        patch_applied: bool,
        all_edits_applied: bool,
        original_unchanged: bool,
        test_integrity: bool,
        pom_integrity: bool,
        source_integrity: bool,
        cleanup_success: bool,
        outcome_reason: str | None,
    ) -> str | None:
        if not proposal_valid:
            return "proposal_invalid"
        if not patch_applied or not all_edits_applied:
            return "patch_application_failed"
        if not original_unchanged:
            return "original_repository_modified"
        if not test_integrity:
            return "test_integrity_failed"
        if not pom_integrity:
            return "pom_integrity_failed"
        if not source_integrity:
            return "source_integrity_failed"
        if not cleanup_success:
            return "workspace_cleanup_failed"
        return outcome_reason

    @staticmethod
    def _source_is_unchanged(source: Path, before: dict[str, str]) -> bool:
        try:
            return before == compute_repository_manifest(source)
        except (OSError, ValueError):
            return False

    def _resolve_case_repository(self, case: BenchmarkCase) -> Path:
        candidate = self.project_root / Path(case.repository)
        try:
            return canonicalize_repository(candidate, self.project_root)
        except PathSafetyError as exc:
            raise ValueError(f"invalid repository for case {case.case_id}: {exc}") from exc


def run_repair_verification(
    *,
    project_root: Path,
    manifest_path: Path,
    output_dir: Path,
    mode: RepairVerificationMode = "mock",
    case_id: str | None = None,
    proposal_file: Path | None = None,
) -> RepairVerificationRunResult:
    """Convenience entry point for the M5C CLI and tests."""
    return RepairVerificationRunner(
        project_root=project_root,
        manifest_path=manifest_path,
        output_dir=output_dir,
        mode=mode,
        case_id=case_id,
        proposal_file=proposal_file,
    ).run()


__all__ = [
    "RepairVerificationRunner",
    "run_repair_verification",
]
