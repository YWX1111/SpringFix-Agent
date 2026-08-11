"""M5A Mock/Live Patch Proposal benchmark runner."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Literal, cast

from springfix_agent.benchmark.loader import load_cases
from springfix_agent.benchmark.models import BenchmarkCase
from springfix_agent.benchmark.repository_view import create_repository_view
from springfix_agent.benchmark.runner import (
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
from springfix_agent.repair.artifacts import write_repair_artifacts
from springfix_agent.repair.evaluator import (
    RepairBenchmarkRunResult,
    RepairCaseResult,
    RepairGold,
    aggregate_repair_metrics,
    evaluate_repair_proposal,
)
from springfix_agent.repair.generator import PatchProposalService
from springfix_agent.repair.loader import load_repair_gold
from springfix_agent.storage.in_memory import InMemoryTaskRepository
from springfix_agent.storage.models import Trace
from springfix_agent.tools._path_safety import PathSafetyError, canonicalize_repository

RepairMode = Literal["mock", "live"]


def _token_sum(traces: list[Trace], key: str) -> int | None:
    values = [
        payload.get(key)
        for trace in traces
        if trace.kind == "llm_call"
        for payload in [trace.payload]
        if isinstance(payload.get(key), int)
    ]
    return sum(value for value in values if isinstance(value, int)) if values else None


def _trace_count(traces: list[Trace], node_names: set[str]) -> int:
    return sum(
        1
        for trace in traces
        if trace.kind == "llm_call" and trace.payload.get("node") in node_names
    )


def _http_attempts(traces: list[Trace]) -> int:
    total = 0
    for trace in traces:
        if trace.kind != "llm_call":
            continue
        attempt = trace.payload.get("attempt")
        provider = trace.payload.get("provider")
        total += 1 if provider == "mock" else max(1, attempt if isinstance(attempt, int) else 1)
    return total


class RepairProposalRunner:
    """Run diagnostics plus one independent Patch Proposal call per case."""

    def __init__(
        self,
        *,
        project_root: Path,
        manifest_path: Path,
        repair_gold_path: Path,
        output_dir: Path,
        mode: RepairMode = "mock",
        case_id: str | None = None,
        llm: LLMClient | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.manifest_path = manifest_path.resolve()
        self.repair_gold_path = repair_gold_path.resolve()
        self.output_dir = output_dir.resolve()
        self.mode = mode
        self.case_id = case_id
        self._provided_llm = llm

    def run(self) -> RepairBenchmarkRunResult:
        """Execute cases and write only redacted proposal artifacts."""
        cases = load_cases(self.manifest_path)
        gold = load_repair_gold(self.repair_gold_path)
        if self.case_id is not None:
            cases = [case for case in cases if case.case_id == self.case_id]
            if not cases:
                raise ValueError(f"case not found in manifest: {self.case_id}")
        for case in cases:
            if case.case_id not in gold:
                raise ValueError(f"repair Gold missing for case: {case.case_id}")

        shared_llm: LLMClient | None = self._provided_llm
        live_config: LiveConfiguration | None = None
        live_settings: Settings | None = None
        if self.mode == "live":
            live_settings = Settings()
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

        started = time.monotonic()
        results: list[RepairCaseResult] = []
        for case in cases:
            llm_for_case = shared_llm
            if self.mode == "mock" and llm_for_case is None:
                mock = MockLLMClient()
                mock.use_profile(benchmark_profile_for_case(case.case_id))
                llm_for_case = mock
            if llm_for_case is None:
                raise RuntimeError("repair benchmark LLM client was not initialized")
            results.append(self._run_case(case, gold[case.case_id], llm_for_case))

        model = shared_llm.model if shared_llm is not None else "mock-fixed"
        metadata: dict[str, object] = {
            "mode": self.mode,
            "model": model,
            "cases": [case.case_id for case in cases],
            "duration_ms": int((time.monotonic() - started) * 1000),
            "diagnostic_llm_calls_per_case": 3,
            "patch_llm_calls_per_case": 1,
            "maven_executed": False,
            "repository_modified": False,
        }
        if live_config is not None:
            metadata.update(live_config.safe_dict())
        else:
            metadata.update(
                {
                    "provider": "mock",
                    "base_url_host": None,
                    "api_key_configured": False,
                }
            )
        result = RepairBenchmarkRunResult(
            mode=self.mode,
            run_metadata=metadata,
            cases=results,
            aggregate=aggregate_repair_metrics(results),
        )
        write_repair_artifacts(result, self.output_dir / self.mode)
        return result

    def _run_case(
        self,
        case: BenchmarkCase,
        gold: RepairGold,
        llm: LLMClient,
    ) -> RepairCaseResult:
        source = self._resolve_case_repository(case)
        with create_repository_view(source, include_tests=False) as view:
            if view.path is None:
                raise RuntimeError("repository view was not initialized")
            repository = InMemoryTaskRepository()
            task = repository.create_task(
                repository_path=view.path.as_posix(),
                issue_description=case.issue_description,
                error_log=case.error_log,
            )
            tracer = InMemoryTracer(repository)
            started = time.monotonic()
            state: AgentState
            try:
                graph = build_graph(
                    task_id=task.task_id,
                    repository_path=view.path,
                    allow_root=view.path.parent,
                    tracer=tracer,
                    llm=llm,
                )
                raw_state = graph.invoke(
                    make_initial_state(
                        task_id=task.task_id,
                        repository_path=view.path.as_posix(),
                        issue_description=case.issue_description,
                        error_log=case.error_log,
                    )
                )
                if not isinstance(raw_state, dict):
                    raise RuntimeError("diagnostic graph returned non-dict result")
                state = cast(AgentState, raw_state)
            except Exception as exc:  # noqa: BLE001
                state = cast(
                    AgentState,
                    {
                        "status": "failed",
                        "root_cause_analysis": {},
                        "retrieved_snippets": [],
                        "errors": [f"diagnostic execution failed: {type(exc).__name__}"],
                    },
                )

            service = PatchProposalService(llm)
            patch_result = service.propose(
                repository_root=view.path,
                root_cause_analysis=dict(state.get("root_cause_analysis") or {}),
                retrieved_snippets=[
                    dict(snippet) for snippet in (state.get("retrieved_snippets") or [])
                ],
                task_id=task.task_id,
                tracer=tracer,
            )
            traces = repository.get_traces(task.task_id)
            duration_ms = int((time.monotonic() - started) * 1000)

            return evaluate_repair_proposal(
                gold,
                patch_result.validation,
                model=llm.model,
                diagnostic_llm_calls=_trace_count(
                    traces, {"issue_parser", "task_planner", "root_cause_analyzer"}
                ),
                patch_llm_calls=_trace_count(traces, {"patch_proposal"}),
                http_attempts=_http_attempts(traces),
                input_tokens=_token_sum(traces, "input_tokens"),
                output_tokens=_token_sum(traces, "output_tokens"),
                duration_ms=duration_ms,
            )

    def _resolve_case_repository(self, case: BenchmarkCase) -> Path:
        candidate = self.project_root / Path(case.repository)
        try:
            return canonicalize_repository(candidate, self.project_root)
        except PathSafetyError as exc:
            raise ValueError(f"invalid repository for case {case.case_id}: {exc}") from exc


def run_repair_benchmark(
    *,
    project_root: Path,
    manifest_path: Path,
    repair_gold_path: Path,
    output_dir: Path,
    mode: RepairMode = "mock",
    case_id: str | None = None,
) -> RepairBenchmarkRunResult:
    """Convenience entry point for M5A callers."""
    return RepairProposalRunner(
        project_root=project_root,
        manifest_path=manifest_path,
        repair_gold_path=repair_gold_path,
        output_dir=output_dir,
        mode=mode,
        case_id=case_id,
    ).run()
