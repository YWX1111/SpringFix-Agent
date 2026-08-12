"""M5D single-shot end-to-end benchmark orchestration.

This module composes the existing M4C diagnostic graph, M5A proposal service,
M5B isolated applier, and M5C Maven verifier.  It deliberately contains no
case-specific repair knowledge; benchmark-specific behavior remains in the
manifest and deterministic Mock profiles.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from springfix_agent import __version__
from springfix_agent.benchmark.evaluator import evaluate_case
from springfix_agent.benchmark.loader import load_cases
from springfix_agent.benchmark.models import BenchmarkCase
from springfix_agent.benchmark.repository_view import create_repository_view
from springfix_agent.benchmark.runner import (
    BenchmarkConfigurationError,
    LiveConfiguration,
    benchmark_profile_for_case,
    read_live_configuration,
)
from springfix_agent.config import Settings
from springfix_agent.graph.builder import build_graph
from springfix_agent.graph.state import AgentState, make_initial_state
from springfix_agent.llm.client import LLMClient
from springfix_agent.llm.mock import MockLLMClient
from springfix_agent.observability.in_memory_tracer import InMemoryTracer
from springfix_agent.repair.application_models import PatchApplicationResult
from springfix_agent.repair.applier import PatchApplier
from springfix_agent.repair.e2e_artifacts import write_end_to_end_artifacts
from springfix_agent.repair.e2e_metrics import aggregate_end_to_end_metrics
from springfix_agent.repair.e2e_models import EndToEndCaseResult, EndToEndRunResult
from springfix_agent.repair.evaluator import RepairGold, evaluate_repair_proposal
from springfix_agent.repair.generator import PatchProposalService
from springfix_agent.repair.loader import load_repair_gold
from springfix_agent.repair.maven_verifier import (
    MavenRepairVerifier,
    build_restricted_maven_environment,
    find_maven_binary,
    find_suitable_jdk,
)
from springfix_agent.repair.models import PatchValidationResult
from springfix_agent.repair.verification_models import MavenTestResult
from springfix_agent.repair.workspace import (
    IsolatedPatchWorkspace,
    compute_repository_manifest,
    create_isolated_patch_workspace,
)
from springfix_agent.storage.in_memory import InMemoryTaskRepository
from springfix_agent.storage.models import Trace
from springfix_agent.tools._path_safety import PathSafetyError, canonicalize_repository

E2EMode = Literal["mock", "live"]
_MAVEN_VERSION_RE = re.compile(r"Apache Maven\s+([0-9][^\s]+)")
_COMPILATION_FAILURE_RE = re.compile(r"(?i)(compilation failure|compilation error|compilation failure)")


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _trace_payloads(traces: list[Trace], node: str | None = None) -> list[dict[str, object]]:
    return [
        trace.payload
        for trace in traces
        if trace.kind == "llm_call" and (node is None or trace.payload.get("node") == node)
    ]


def _llm_counts(payloads: list[dict[str, object]]) -> tuple[int, int, int | None, int | None]:
    input_values = [item.get("input_tokens") for item in payloads]
    output_values = [item.get("output_tokens") for item in payloads]
    inputs = [value for value in input_values if isinstance(value, int)]
    outputs = [value for value in output_values if isinstance(value, int)]
    return (
        len(payloads),
        sum(
            max(1, cast(int, item.get("attempt", 1)))
            if item.get("provider") != "mock" and isinstance(item.get("attempt", 1), int)
            else 1
            for item in payloads
        ),
        sum(inputs) if len(inputs) == len(payloads) else None,
        sum(outputs) if len(outputs) == len(payloads) else None,
    )


def _provider_failed(payloads: list[dict[str, object]]) -> bool:
    return bool(payloads) and not any(item.get("status") == "success" for item in payloads)


def _optional_sum(values: list[int | None]) -> int | None:
    if not values or any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def _stage_durations(traces: list[Trace]) -> dict[str, int]:
    result: dict[str, int] = {}
    for trace in traces:
        if trace.kind != "node_timing":
            continue
        value = trace.payload.get("duration_ms")
        node = trace.payload.get("node")
        if isinstance(node, str) and isinstance(value, int):
            result[node] = max(0, value)
    return result


def _normalise_path(value: str) -> str:
    return value.replace("\\", "/")


def _changed_files(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))


def _tree_slice(manifest: dict[str, str], prefix: str) -> dict[str, str]:
    normalized = _normalise_path(prefix).rstrip("/") + "/"
    return {key: value for key, value in manifest.items() if key.startswith(normalized)}


def _pom_hash(manifest: dict[str, str]) -> str | None:
    return manifest.get("pom.xml")


def _compile_success(maven: MavenTestResult) -> bool | None:
    if maven.surefire_report_found and maven.target_test_found:
        return True
    if _COMPILATION_FAILURE_RE.search(f"{maven.stdout_tail}\n{maven.stderr_tail}"):
        return False
    return None


def _run_id() -> str:
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid.uuid4().hex[:8]}"


def _git_value(project_root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value or None


def _maven_version(project_root: Path, environment: dict[str, str]) -> str | None:
    binary = find_maven_binary(environment)
    if binary is None:
        return None
    try:
        result = subprocess.run(
            [binary, "--version"],
            cwd=project_root,
            env=build_restricted_maven_environment(source_env=environment),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = _MAVEN_VERSION_RE.search(f"{result.stdout}\n{result.stderr}")
    return match.group(1) if match else None


class EndToEndRepairBenchmarkRunner:
    """Run one fresh, non-iterative M5D benchmark Run."""

    def __init__(
        self,
        *,
        project_root: Path,
        manifest_path: Path,
        repair_gold_path: Path,
        output_dir: Path,
        mode: E2EMode = "mock",
        case_id: str | None = None,
        llm: LLMClient | None = None,
        settings: Settings | None = None,
        verifier: MavenRepairVerifier | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.manifest_path = manifest_path.resolve()
        self.repair_gold_path = repair_gold_path.resolve()
        self.output_dir = output_dir.resolve()
        self.mode = mode
        self.case_id = case_id
        self._provided_llm = llm
        self._settings = settings
        self.verifier = verifier if verifier is not None else MavenRepairVerifier()

    def run(self) -> EndToEndRunResult:
        """Execute all selected cases once and write one isolated Run artifact."""
        cases = load_cases(self.manifest_path)
        if self.case_id is not None:
            cases = [case for case in cases if case.case_id == self.case_id]
            if not cases:
                raise ValueError(f"case not found in manifest: {self.case_id}")
        repair_gold = load_repair_gold(self.repair_gold_path)
        for case in cases:
            if case.case_id not in repair_gold:
                raise ValueError(f"repair Gold missing for case: {case.case_id}")

        live_config: LiveConfiguration | None = None
        live_settings = None
        shared_llm = self._provided_llm
        if self.mode == "live":
            live_settings = self._settings if self._settings is not None else Settings()
            live_config = read_live_configuration(live_settings)
            if shared_llm is None:
                from springfix_agent.llm.openai_compatible import OpenAICompatibleLLMClient

                shared_llm = OpenAICompatibleLLMClient(
                    base_url=live_config.base_url,
                    api_key=live_settings.llm_api_key,
                    model=live_config.model,
                    timeout=float(live_config.timeout_seconds),
                    max_retries=live_config.max_retries,
                    temperature=live_config.temperature,
                    max_output_tokens=live_config.max_output_tokens,
                )

        frozen_config = (
            self._llm_signature(shared_llm, live_config)
            if self.mode == "live"
            else ("mock", "mock-fixed")
        )

        started = time.monotonic()
        results: list[EndToEndCaseResult] = []
        for case in cases:
            case_llm = shared_llm
            if self.mode == "mock" and case_llm is None:
                mock = MockLLMClient()
                mock.use_profile(benchmark_profile_for_case(case.case_id))
                case_llm = mock
            if case_llm is None:
                raise RuntimeError("M5D LLM client was not initialized")
            if self.mode == "live" and self._llm_signature(case_llm, live_config) != frozen_config:
                raise ValueError("LLM provider/model/config changed within one M5D Run")
            try:
                results.append(self._run_case(case, repair_gold[case.case_id], case_llm))
            except Exception as exc:  # noqa: BLE001 - preserve one-case attribution
                results.append(
                    EndToEndCaseResult(
                        case_id=case.case_id,
                        model=case_llm.model,
                        final_status="failed",
                        failed_stage="infrastructure",
                        failure_reason=f"infrastructure_internal_error:{type(exc).__name__}",
                        outcome="infrastructure_failed",
                    )
                )

        model = shared_llm.model if shared_llm is not None else "mock-fixed"
        metadata = self._run_metadata(
            run_id=self._current_run_id,
            model=model,
            cases=cases,
            live_config=live_config,
            settings=live_settings,
        )
        metadata["duration_ms"] = max(0, int((time.monotonic() - started) * 1000))
        result = EndToEndRunResult(
            mode=self.mode,
            run_id=self._current_run_id,
            run_metadata=metadata,
            cases=results,
            aggregate=aggregate_end_to_end_metrics(results),
        )
        write_end_to_end_artifacts(result, self.output_dir / self.mode / result.run_id)
        return result

    @property
    def _current_run_id(self) -> str:
        if not hasattr(self, "__run_id"):
            object.__setattr__(self, "__run_id", _run_id())
        return cast(str, getattr(self, "__run_id"))

    def _run_metadata(
        self,
        *,
        run_id: str,
        model: str,
        cases: list[BenchmarkCase],
        live_config: LiveConfiguration | None,
        settings: Settings | None,
    ) -> dict[str, object]:
        java_home, java_version = find_suitable_jdk()
        del java_home
        metadata: dict[str, object] = {
            "run_id": run_id,
            "version": __version__,
            "git_commit": _git_value(self.project_root, "rev-parse", "HEAD"),
            "git_tag": _git_value(self.project_root, "describe", "--tags", "--always"),
            "mode": self.mode,
            "provider": "mock",
            "base_url_host": None,
            "api_key_configured": False,
            "model": model,
            "temperature": None,
            "max_retries": None,
            "timeout": None,
            "max_output_tokens": None,
            "java_version": java_version,
            "maven_version": _maven_version(self.project_root, dict(os.environ)),
            "sample_size": len(cases),
            "include_tests": False,
        }
        if live_config is not None:
            safe = live_config.safe_dict()
            metadata.update(safe)
        return metadata

    def _run_case(
        self,
        case: BenchmarkCase,
        repair_gold: RepairGold,
        llm: LLMClient,
    ) -> EndToEndCaseResult:
        source = self._resolve_case_repository(case)
        started = time.monotonic()
        original_before = compute_repository_manifest(source)
        try:
            baseline = self.verifier.verify_baseline(source, case.expected_maven)
        except Exception as exc:  # noqa: BLE001 - attribute provider/verifier failures
            return self._infrastructure_case(
                EndToEndCaseResult(
                    case_id=case.case_id,
                    model=llm.model,
                    baseline_status="failed",
                ),
                f"baseline_verifier_error:{type(exc).__name__}",
                started,
            )
        original_unchanged = original_before == compute_repository_manifest(source)
        base = EndToEndCaseResult(
            case_id=case.case_id,
            model=llm.model,
            baseline_verified=baseline.verified,
            baseline_status="passed" if baseline.verified else "failed",
            original_repository_unchanged=original_unchanged,
            baseline_verification_ms=baseline.maven_result.duration_ms,
            baseline_maven=baseline.maven_result,
            warnings=[],
        )
        if not baseline.verified or not original_unchanged:
            base.failed_stage = "baseline"
            base.failure_reason = baseline.failure_reason or "original_repository_modified"
            base.outcome = "infrastructure_failed" if baseline.failure_reason in {
                "maven_not_found", "java_not_compatible"
            } else "verification_failed"
            base.total_pipeline_duration_ms = max(0, int((time.monotonic() - started) * 1000))
            return base

        with create_repository_view(source, include_tests=False) as view:
            if view.path is None:
                return self._infrastructure_case(base, "repository_view_not_initialized", started)
            repository = InMemoryTaskRepository()
            task = repository.create_task(
                repository_path=view.path.as_posix(),
                issue_description=case.issue_description,
                error_log=case.error_log,
            )
            tracer = InMemoryTracer(repository)
            diagnosis_started = time.monotonic()
            state = self._run_diagnosis(case, llm, view.path, task.task_id, tracer)
            traces = repository.get_traces(task.task_id)
            diagnosis_duration = max(0, int((time.monotonic() - diagnosis_started) * 1000))
            m4c = evaluate_case(
                case,
                state,
                traces,
                total_duration_ms=diagnosis_duration,
                model=llm.model,
            )
            diagnostic_payloads = _trace_payloads(traces)
            diagnostic_calls, diagnostic_attempts, diagnostic_inputs, diagnostic_outputs = _llm_counts(
                diagnostic_payloads
            )
            phase = _stage_durations(traces)
            base.diagnosis_completed = m4c.metrics.agent_completed
            base.diagnosis_status = "passed" if base.diagnosis_completed else "failed"
            base.diagnosis_benchmark_pass = m4c.metrics.case_pass
            base.agent_diagnosis_status = m4c.diagnosis_status
            base.issue_category_match = m4c.metrics.issue_category_match
            base.diagnosis_status_match = m4c.metrics.diagnosis_status_match
            base.root_cause_keyword_coverage = m4c.metrics.root_cause_keyword_coverage
            base.expected_file_hit = m4c.metrics.expected_file_hit
            base.expected_file_recall = m4c.metrics.expected_file_recall
            base.evidence_target_recall = m4c.metrics.evidence_target_recall
            base.model_evidence_count = m4c.metrics.model_evidence_count
            base.validated_evidence_count = m4c.metrics.validated_evidence_count
            base.rejected_evidence_count = m4c.metrics.rejected_evidence_count
            base.valid_evidence_rate = m4c.metrics.valid_evidence_rate
            base.hallucinated_evidence_reference_rate = m4c.metrics.hallucinated_evidence_rate
            base.retrieval_expected_file_recall_at_1 = m4c.metrics.expected_file_retrieved_at_1
            base.retrieval_expected_file_recall_at_3 = m4c.metrics.expected_file_retrieved_at_3
            base.retrieval_expected_file_recall_at_5 = m4c.metrics.expected_file_retrieved_at_5
            base.diagnosis_duration_ms = diagnosis_duration
            base.issue_parser_ms = phase.get("issue_parser")
            base.task_planner_ms = phase.get("task_planner")
            base.retrieval_ms = phase.get("retrieve_code")
            base.root_cause_analyzer_ms = phase.get("root_cause_analyzer")
            base.diagnostic_logical_llm_calls = diagnostic_calls
            base.diagnostic_http_attempts = diagnostic_attempts
            base.diagnostic_input_tokens = diagnostic_inputs
            base.diagnostic_output_tokens = diagnostic_outputs

            if _provider_failed(diagnostic_payloads):
                base.diagnosis_completed = False
                base.diagnosis_status = "failed"
                base.failed_stage = "diagnosis"
                base.failure_reason = "provider_failure"
                base.outcome = "provider_failed"
                return self._finish(base, started)
            if not base.diagnosis_completed:
                base.failed_stage = "diagnosis"
                base.failure_reason = "provider_failure" if _provider_failed(diagnostic_payloads) else "diagnosis_execution_failed"
                base.outcome = "provider_failed" if base.failure_reason == "provider_failure" else "diagnosis_failed"
                return self._finish(base, started)

            patch_started = time.monotonic()
            patch_result = PatchProposalService(llm).propose(
                repository_root=view.path,
                root_cause_analysis=dict(state.get("root_cause_analysis") or {}),
                retrieved_snippets=[dict(item) for item in (state.get("retrieved_snippets") or [])],
                task_id=task.task_id,
                tracer=tracer,
            )
            patch_duration = max(0, int((time.monotonic() - patch_started) * 1000))
            traces = repository.get_traces(task.task_id)
            patch_payloads = _trace_payloads(traces, "patch_proposal")
            patch_calls, patch_attempts, patch_inputs, patch_outputs = _llm_counts(patch_payloads)
            proposal_metrics = evaluate_repair_proposal(
                repair_gold,
                patch_result.validation,
                model=llm.model,
                diagnostic_llm_calls=diagnostic_calls,
                patch_llm_calls=patch_calls,
                http_attempts=diagnostic_attempts + patch_attempts,
                input_tokens=_optional_sum([diagnostic_inputs, patch_inputs]),
                output_tokens=_optional_sum([diagnostic_outputs, patch_outputs]),
                duration_ms=patch_duration,
            ).metrics
            base.proposal_generated = patch_result.proposal.status == "proposed"
            base.proposal_valid = patch_result.validation.passed and not proposal_metrics.forbidden_file_edits
            base.proposal_status = "passed" if base.proposal_valid else "failed"
            base.proposal_result_status = patch_result.proposal.status
            base.edit_count = proposal_metrics.edit_count
            base.validated_edit_count = proposal_metrics.validated_edit_count
            base.rejected_edit_count = proposal_metrics.rejected_edit_count
            base.valid_edit_rate = proposal_metrics.valid_edit_rate
            base.evidence_supported_edit_rate = proposal_metrics.evidence_supported_edit_rate
            base.acceptable_change_concept_hit = proposal_metrics.acceptable_change_concept_hit
            base.forbidden_file_edits = proposal_metrics.forbidden_file_edits
            base.patch_proposal_duration_ms = patch_duration
            base.patch_validation_ms = patch_result.patch_validation_duration_ms
            base.patch_logical_llm_calls = patch_calls
            base.patch_http_attempts = patch_attempts
            base.patch_input_tokens = patch_inputs
            base.patch_output_tokens = patch_outputs

            if not base.proposal_valid:
                base.failed_stage = "proposal"
                provider_failure = _provider_failed(patch_payloads) and not base.proposal_generated
                base.failure_reason = "provider_failure" if provider_failure else "proposal_invalid"
                base.outcome = "provider_failed" if provider_failure else "proposal_failed"
                return self._finish(base, started)

            try:
                application, maven_result, application_values = self._apply_and_verify(
                    source, case, patch_result.validation
                )
            except Exception as exc:  # noqa: BLE001 - preserve one-case short-circuit metrics
                base.failed_stage = "application"
                base.failure_reason = f"application_internal_error:{type(exc).__name__}"
                base.outcome = "application_failed"
                return self._finish(base, started)
            (
                original_unchanged_after,
                test_integrity,
                pom_integrity,
                source_integrity,
                cleanup_success,
                maven_failure_reason,
                application_duration,
            ) = application_values
            base.patch_applied = application.status == "applied"
            base.application_status = "passed" if base.patch_applied else "failed"
            base.all_edits_applied = (
                base.patch_applied
                and application.edits_requested > 0
                and application.edits_applied == application.edits_requested
                and not application.rejected_edits
            )
            base.requested_edit_count = application.edits_requested
            base.applied_edit_count = application.edits_applied
            base.rejected_application_edit_count = application.edits_rejected
            base.changed_files = list(application.changed_files)
            base.original_repository_unchanged = original_unchanged_after
            base.diff_generated = bool(application.unified_diff)
            base.workspace_cleanup_success = cleanup_success
            base.patch_application_ms = application_duration
            base.maven = maven_result
            base.maven_executed = maven_result.executed
            base.maven_exit_code = maven_result.exit_code
            base.maven_timeout = maven_result.timed_out
            base.surefire_report_found = maven_result.surefire_report_found
            base.target_test_found = maven_result.target_test_found
            base.tests = maven_result.tests
            base.failures = maven_result.failures
            base.errors = maven_result.errors
            base.skipped = maven_result.skipped
            base.compile_success = _compile_success(maven_result)
            base.test_integrity_preserved = test_integrity
            base.pom_integrity_preserved = pom_integrity
            base.verification_failure_reason = maven_failure_reason
            base.maven_verification_ms = maven_result.duration_ms
            base.patch_diff = application.unified_diff or None
            base.verification_status = "passed" if maven_result.exit_code == 0 and maven_result.target_test_found else "failed"
            base.total_logical_llm_calls = diagnostic_calls + patch_calls
            base.total_http_attempts = diagnostic_attempts + patch_attempts
            base.total_input_tokens = _optional_sum([diagnostic_inputs, patch_inputs])
            base.total_output_tokens = _optional_sum([diagnostic_outputs, patch_outputs])
            base.total_tokens = (
                base.total_input_tokens + base.total_output_tokens
                if base.total_input_tokens is not None and base.total_output_tokens is not None
                else None
            )
            base.repair_success = self._repair_success(base, source_integrity)
            base.end_to_end_repair_success = base.repair_success
            base.final_status = "passed" if base.repair_success else "failed"
            if base.repair_success:
                base.outcome = (
                    "complete_success"
                    if base.diagnosis_benchmark_pass
                    else "repair_success_with_diagnostic_metric_miss"
                )
                base.failed_stage = None
                base.failure_reason = None
            else:
                base.failed_stage = "application" if not base.patch_applied else "verification"
                base.failure_reason = (
                    "patch_application_failed" if base.failed_stage == "application"
                    else maven_failure_reason or "verification_failed"
                )
                base.outcome = "application_failed" if base.failed_stage == "application" else "verification_failed"
            return self._finish(base, started)

    def _run_diagnosis(
        self,
        case: BenchmarkCase,
        llm: LLMClient,
        repository: Path,
        task_id: str,
        tracer: InMemoryTracer,
    ) -> AgentState:
        try:
            graph = build_graph(
                task_id=task_id,
                repository_path=repository,
                allow_root=repository.parent,
                tracer=tracer,
                llm=llm,
            )
            raw = graph.invoke(
                make_initial_state(
                    task_id=task_id,
                    repository_path=repository.as_posix(),
                    issue_description=case.issue_description,
                    error_log=case.error_log,
                )
            )
            if not isinstance(raw, dict):
                raise RuntimeError("diagnostic graph returned non-dict result")
            return cast(AgentState, raw)
        except Exception as exc:  # noqa: BLE001
            return cast(
                AgentState,
                {
                    "status": "failed",
                    "issue_analysis": {},
                    "root_cause_analysis": {},
                    "retrieved_snippets": [],
                    "warnings": [],
                    "errors": [f"diagnosis execution failed: {type(exc).__name__}"],
                },
            )

    @staticmethod
    def _llm_signature(
        client: LLMClient | None,
        live_config: LiveConfiguration | None,
    ) -> tuple[object, ...]:
        if client is None:
            return (None, None, None)
        config = (
            live_config.safe_dict()
            if live_config is not None
            else {"provider": client.provider, "model": client.model}
        )
        return (client.provider, client.model, tuple(sorted(config.items())))

    def _apply_and_verify(
        self,
        source: Path,
        case: BenchmarkCase,
        validation: PatchValidationResult,
    ) -> tuple[
        PatchApplicationResult,
        MavenTestResult,
        tuple[bool, bool, bool, bool, bool, str | None, int],
    ]:
        workspace: IsolatedPatchWorkspace = create_isolated_patch_workspace(source)
        maven_result = MavenTestResult(executed=False, timed_out=False)
        maven_failure_reason: str | None = None
        application: PatchApplicationResult
        with workspace:
            if workspace.path is None:
                raise RuntimeError("isolated workspace was not initialized")
            before = compute_repository_manifest(workspace.path)
            test_before = _tree_slice(before, "src/test")
            pom_before = _pom_hash(before)
            application_started = time.monotonic()
            application = PatchApplier().apply(validation, workspace)
            after_patch = compute_repository_manifest(workspace.path)
            application_duration = max(0, int((time.monotonic() - application_started) * 1000))
            changed_files = _changed_files(before, after_patch)
            expected_changed = sorted(_normalise_path(item) for item in application.changed_files)
            source_integrity = changed_files == expected_changed
            test_integrity = test_before == _tree_slice(after_patch, "src/test")
            pom_integrity = pom_before == _pom_hash(after_patch)
            if (
                application.status == "applied"
                and source_integrity
                and test_integrity
                and pom_integrity
            ):
                outcome = self.verifier.verify_patched_workspace(workspace.path, case.expected_maven)
                maven_result = outcome.result
                maven_failure_reason = outcome.failure_reason
            after_maven = compute_repository_manifest(workspace.path)
            test_integrity = test_integrity and test_before == _tree_slice(after_maven, "src/test")
            pom_integrity = pom_integrity and pom_before == _pom_hash(after_maven)
            source_integrity = source_integrity and after_patch == after_maven
        cleanup_success = workspace.cleanup_succeeded is True
        application = application.model_copy(update={"workspace_cleaned": cleanup_success})
        original_unchanged = workspace.verify_source_unchanged()
        return application, maven_result, (
            original_unchanged,
            test_integrity,
            pom_integrity,
            source_integrity,
            cleanup_success,
            maven_failure_reason,
            application_duration,
        )

    @staticmethod
    def _repair_success(case: EndToEndCaseResult, source_integrity: bool) -> bool:
        return (
            case.baseline_verified
            and case.diagnosis_completed
            and case.proposal_generated
            and case.proposal_valid
            and case.patch_applied
            and case.all_edits_applied
            and case.original_repository_unchanged
            and source_integrity
            and case.test_integrity_preserved
            and case.pom_integrity_preserved
            and case.workspace_cleanup_success
            and case.target_test_found
            and case.tests > 0
            and case.maven_executed
            and not case.maven_timeout
            and case.maven_exit_code == 0
            and case.failures == 0
            and case.errors == 0
            and case.skipped == 0
        )

    @staticmethod
    def _finish(case: EndToEndCaseResult, started: float) -> EndToEndCaseResult:
        case.total_logical_llm_calls = case.diagnostic_logical_llm_calls + case.patch_logical_llm_calls
        case.total_http_attempts = case.diagnostic_http_attempts + case.patch_http_attempts
        case.total_input_tokens = _optional_sum([case.diagnostic_input_tokens, case.patch_input_tokens])
        case.total_output_tokens = _optional_sum([case.diagnostic_output_tokens, case.patch_output_tokens])
        case.total_tokens = (
            case.total_input_tokens + case.total_output_tokens
            if case.total_input_tokens is not None and case.total_output_tokens is not None
            else None
        )
        case.total_pipeline_duration_ms = max(0, int((time.monotonic() - started) * 1000))
        return case

    @staticmethod
    def _infrastructure_case(
        case: EndToEndCaseResult, reason: str, started: float
    ) -> EndToEndCaseResult:
        case.failed_stage = "infrastructure"
        case.failure_reason = reason
        case.outcome = "infrastructure_failed"
        return EndToEndRepairBenchmarkRunner._finish(case, started)

    def _resolve_case_repository(self, case: BenchmarkCase) -> Path:
        candidate = self.project_root / Path(case.repository)
        try:
            return canonicalize_repository(candidate, self.project_root)
        except PathSafetyError as exc:
            raise ValueError(f"invalid repository for case {case.case_id}: {exc}") from exc


def run_end_to_end_repair_benchmark(
    *,
    project_root: Path,
    manifest_path: Path,
    repair_gold_path: Path,
    output_dir: Path,
    mode: E2EMode = "mock",
    case_id: str | None = None,
) -> EndToEndRunResult:
    """Convenience entry point for the M5D CLI and tests."""
    return EndToEndRepairBenchmarkRunner(
        project_root=project_root,
        manifest_path=manifest_path,
        repair_gold_path=repair_gold_path,
        output_dir=output_dir,
        mode=mode,
        case_id=case_id,
    ).run()


__all__ = [
    "BenchmarkConfigurationError",
    "EndToEndRepairBenchmarkRunner",
    "run_end_to_end_repair_benchmark",
]
