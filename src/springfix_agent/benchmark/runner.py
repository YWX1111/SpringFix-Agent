"""M4C benchmark runner with strict Agent/Gold isolation."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast
from urllib.parse import urlparse

from springfix_agent.benchmark.evaluator import evaluate_case
from springfix_agent.benchmark.loader import load_cases
from springfix_agent.benchmark.metrics import write_run_artifacts
from springfix_agent.benchmark.models import BenchmarkCase
from springfix_agent.benchmark.repository_view import create_repository_view
from springfix_agent.benchmark.result_models import BenchmarkRunResult, CaseResult
from springfix_agent.config import Settings
from springfix_agent.graph.builder import build_graph
from springfix_agent.graph.state import AgentState, make_initial_state
from springfix_agent.llm.client import LLMClient
from springfix_agent.llm.mock import MockLLMClient
from springfix_agent.observability.in_memory_tracer import InMemoryTracer
from springfix_agent.storage.in_memory import InMemoryTaskRepository
from springfix_agent.tools._path_safety import PathSafetyError, canonicalize_repository

BenchmarkMode = Literal["mock", "live"]


class BenchmarkConfigurationError(ValueError):
    """Raised when a Live benchmark lacks required provider configuration."""


@dataclass(frozen=True)
class LiveConfiguration:
    """Safe Live configuration summary; the API key value is never retained."""

    provider: str
    base_url: str
    api_key_configured: bool
    model: str
    timeout_seconds: int
    max_retries: int
    temperature: float
    max_output_tokens: int

    @property
    def base_url_host(self) -> str | None:
        """Return only the URL host for artifact/log output."""
        return urlparse(self.base_url).hostname

    def safe_dict(self) -> dict[str, object]:
        """Serialize configuration without secret material or URL paths."""
        return {
            "provider": self.provider,
            "base_url_host": self.base_url_host,
            "model": self.model,
            "api_key_configured": self.api_key_configured,
            "timeout": self.timeout_seconds,
            "max_retries": self.max_retries,
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
        }


def read_live_configuration(settings: Settings | None = None) -> LiveConfiguration:
    """Read Live settings through the project's unified Settings loader."""
    resolved = settings if settings is not None else Settings()
    provider = resolved.llm_provider.strip()
    base_url = resolved.llm_base_url.strip()
    api_key = resolved.llm_api_key
    model = resolved.llm_model.strip()
    missing: list[str] = []
    if provider != "openai_compatible":
        missing.append("LLM_PROVIDER=openai_compatible")
    if not base_url:
        missing.append("LLM_BASE_URL")
    if not api_key:
        missing.append("LLM_API_KEY")
    if not model:
        missing.append("LLM_MODEL")
    if missing:
        raise BenchmarkConfigurationError(
            "Live benchmark configuration missing: " + ", ".join(missing)
        )

    return LiveConfiguration(
        provider=provider,
        base_url=base_url,
        api_key_configured=True,
        model=model,
        timeout_seconds=resolved.llm_timeout_seconds,
        max_retries=resolved.llm_max_retries,
        temperature=resolved.llm_temperature,
        max_output_tokens=resolved.llm_max_output_tokens,
    )


def benchmark_profile_for_case(case_id: str) -> str:
    """Map only the offline fixture to its deterministic Mock profile."""
    profiles = {
        "transaction-self-invocation": "benchmark_transaction",
        "no-unique-bean-definition": "benchmark_no_unique_bean",
        "configuration-properties-prefix-mismatch": "benchmark_config_prefix",
    }
    try:
        return profiles[case_id]
    except KeyError as exc:
        raise ValueError(f"no benchmark Mock profile for case {case_id!r}") from exc


class BenchmarkRunner:
    """Run each Manifest case against a sanitized copy of the repository."""

    def __init__(
        self,
        *,
        project_root: Path,
        manifest_path: Path,
        output_dir: Path,
        mode: BenchmarkMode = "mock",
        include_tests: bool = False,
        case_id: str | None = None,
        llm: LLMClient | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.manifest_path = manifest_path.resolve()
        self.output_dir = output_dir.resolve()
        self.mode = mode
        self.include_tests = include_tests
        self.case_id = case_id
        self._provided_llm = llm

    def run(self) -> BenchmarkRunResult:
        """Execute selected cases, evaluate them, and write redacted artifacts."""
        cases = load_cases(self.manifest_path)
        if self.case_id is not None:
            cases = [case for case in cases if case.case_id == self.case_id]
            if not cases:
                raise ValueError(f"case not found in manifest: {self.case_id}")

        live_config: LiveConfiguration | None = None
        live_settings: Settings | None = None
        shared_llm: LLMClient | None = self._provided_llm
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

        run_started = time.monotonic()
        results = []
        for case in cases:
            llm_for_case = shared_llm
            if self.mode == "mock" and llm_for_case is None:
                mock = MockLLMClient()
                mock.use_profile(benchmark_profile_for_case(case.case_id))
                llm_for_case = mock
            if llm_for_case is None:
                raise RuntimeError("benchmark LLM client was not initialized")
            results.append(self._run_case(case, llm_for_case))

        model_name = shared_llm.model if shared_llm is not None else "mock-fixed"
        metadata: dict[str, object] = {
            "mode": self.mode,
            "include_tests": self.include_tests,
            "model": model_name,
            "cases": [case.case_id for case in cases],
            "duration_ms": int((time.monotonic() - run_started) * 1000),
        }
        if live_config is not None:
            metadata.update(live_config.safe_dict())
        else:
            metadata.update(
                {
                    "provider": "mock",
                    "base_url_host": None,
                    "api_key_configured": False,
                    "timeout": None,
                    "max_retries": None,
                    "temperature": None,
                    "max_output_tokens": None,
                }
            )

        from springfix_agent.benchmark.evaluator import aggregate_metrics

        result = BenchmarkRunResult(
            mode=self.mode,
            include_tests=self.include_tests,
            run_metadata=metadata,
            cases=results,
            aggregate=aggregate_metrics(results),
        )
        write_run_artifacts(result, self.output_dir / self.mode)
        return result

    def _run_case(self, case: BenchmarkCase, llm: LLMClient) -> CaseResult:
        """Run a single case while keeping its temporary path out of results."""
        source = self._resolve_case_repository(case)
        with create_repository_view(source, include_tests=self.include_tests) as view:
            if view.path is None:
                raise RuntimeError("repository view was not initialized")
            repository = InMemoryTaskRepository()
            task = repository.create_task(
                repository_path=view.path.as_posix(),
                issue_description=case.issue_description,
                error_log=case.error_log,
            )
            task_id = task.task_id
            tracer = InMemoryTracer(repository)
            started = time.monotonic()
            final_state: AgentState
            timed_out = False
            try:
                graph = build_graph(
                    task_id=task_id,
                    repository_path=view.path,
                    allow_root=view.path.parent,
                    tracer=tracer,
                    llm=llm,
                )
                initial = make_initial_state(
                    task_id=task_id,
                    repository_path=view.path.as_posix(),
                    issue_description=case.issue_description,
                    error_log=case.error_log,
                )
                raw_state = graph.invoke(initial)
                if not isinstance(raw_state, dict):
                    raise RuntimeError("graph.invoke returned non-dict result")
                final_state = cast(AgentState, raw_state)
            except Exception as exc:  # noqa: BLE001
                message = f"benchmark execution failed: {type(exc).__name__}: {str(exc)[:300]}"
                final_state = cast(
                    AgentState,
                    {
                        "status": "failed",
                        "errors": [message],
                        "warnings": [],
                        "root_cause_analysis": {},
                        "issue_analysis": {},
                    },
                )
                timed_out = isinstance(exc, TimeoutError)
            traces = repository.get_traces(task_id)
            duration_ms = int((time.monotonic() - started) * 1000)

        return evaluate_case(
            case,
            final_state,
            traces,
            total_duration_ms=duration_ms,
            model=llm.model,
            timed_out=timed_out,
        )

    def _resolve_case_repository(self, case: BenchmarkCase) -> Path:
        """Resolve a Manifest repository while preserving the project boundary."""
        candidate = self.project_root / Path(case.repository)
        try:
            return canonicalize_repository(candidate, self.project_root)
        except PathSafetyError as exc:
            raise ValueError(f"invalid repository for case {case.case_id}: {exc}") from exc


def run_benchmark(
    *,
    project_root: Path,
    manifest_path: Path,
    output_dir: Path,
    mode: BenchmarkMode = "mock",
    include_tests: bool = False,
    case_id: str | None = None,
) -> BenchmarkRunResult:
    """Convenience entry point used by the CLI and integration tests."""
    return BenchmarkRunner(
        project_root=project_root,
        manifest_path=manifest_path,
        output_dir=output_dir,
        mode=mode,
        include_tests=include_tests,
        case_id=case_id,
    ).run()
