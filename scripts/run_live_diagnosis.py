"""Live diagnosis runner: runs the full M2 graph against a real LLM.

Usage:
    uv run python scripts/run_live_diagnosis.py \\
        --repository samples/sample-springboot-bug-transaction-self-invocation \\
        --issue "calling createOrder throws RuntimeException, data not rolled back"

Environment variables (must be set before running):
    LLM_PROVIDER=openai_compatible
    LLM_BASE_URL=https://api.openai.com/v1   (or compatible endpoint)
    LLM_API_KEY=sk-...                         (never logged)
    LLM_MODEL=gpt-4o-mini                     (or compatible)
    LLM_TIMEOUT_SECONDS=60
    LLM_MAX_RETRIES=2
    LLM_TEMPERATURE=0
    LLM_MAX_OUTPUT_TOKENS=2000
    ALLOW_ROOT=samples                         (or absolute path)

The script:
    - Refuses to run when LLM_PROVIDER != "openai_compatible" or when
      API key / base URL / model are missing.
    - Loads the error log from --error-log-file if provided.
    - Executes the graph synchronously.
    - Prints task_id, diagnosis_status, LLM call count, total duration
      and token usage (when the model returns usage).
    - Writes the Markdown report to stdout and the JSON report to
      --output (default: live_report.json).
    - Never prints the API key.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _load_error_log(path: str | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        print(f"[live-diagnosis] error log file not found: {path}", file=sys.stderr)
        sys.exit(1)
    try:
        return p.read_text(encoding="utf-8")
    except OSError as e:
        print(f"[live-diagnosis] failed to read error log: {e}", file=sys.stderr)
        sys.exit(1)


def _check_llm_config() -> None:
    provider = os.environ.get("LLM_PROVIDER", "mock")
    if provider != "openai_compatible":
        print(
            "[live-diagnosis] LLM_PROVIDER must be 'openai_compatible' for live mode "
            f"(got {provider!r})",
            file=sys.stderr,
        )
        sys.exit(1)
    missing = [
        name
        for name in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")
        if not os.environ.get(name)
    ]
    if missing:
        print(
            "[live-diagnosis] missing required env vars: " + ", ".join(missing),
            file=sys.stderr,
        )
        sys.exit(1)


def _resolve_repository(repo_arg: str) -> Path:
    p = Path(repo_arg)
    if not p.is_absolute():
        # Try relative to cwd, then relative to project root (samples/...)
        cwd_candidate = Path.cwd() / repo_arg
        if cwd_candidate.exists():
            p = cwd_candidate.resolve()
        else:
            project_root = Path(__file__).resolve().parent.parent
            p = (project_root / repo_arg).resolve()
    if not p.exists() or not p.is_dir():
        print(f"[live-diagnosis] repository not found or not a directory: {p}", file=sys.stderr)
        sys.exit(1)
    return p


def main() -> int:
    parser = argparse.ArgumentParser(description="SpringFix Agent live diagnosis runner")
    parser.add_argument("--repository", required=True, help="Path to the Spring Boot repository")
    parser.add_argument("--issue", required=True, help="Natural-language issue description")
    parser.add_argument(
        "--error-log-file",
        default=None,
        help="Path to a file containing the error log (optional)",
    )
    parser.add_argument(
        "--output",
        default="live_report.json",
        help="Path to write the JSON report (default: live_report.json)",
    )
    args = parser.parse_args()

    _check_llm_config()

    # Force re-evaluation of settings now that env vars are confirmed set.
    from springfix_agent.config import Settings

    settings = Settings()
    repo_path = _resolve_repository(args.repository)
    error_log = _load_error_log(args.error_log_file)

    print(f"[live-diagnosis] provider={settings.llm_provider} model={settings.llm_model}")
    print(f"[live-diagnosis] repository={repo_path}")

    from springfix_agent.llm.openai_compatible import OpenAICompatibleLLMClient
    from springfix_agent.service.task_service import TaskService
    from springfix_agent.storage.in_memory import InMemoryTaskRepository

    llm = OpenAICompatibleLLMClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        timeout=float(settings.llm_timeout_seconds),
        max_retries=settings.llm_max_retries,
        temperature=settings.llm_temperature,
        max_output_tokens=settings.llm_max_output_tokens,
    )

    repo = InMemoryTaskRepository()
    allow_root = settings.resolved_allow_root()
    if not repo_path.resolve().is_relative_to(allow_root):
        # Adjust allow_root to the repo's parent so canonicalize passes.
        allow_root = repo_path.parent.resolve()
    service = TaskService(repository=repo, allow_root=allow_root, llm=llm)

    task = service.submit_task(
        repository_path=str(repo_path),
        issue_description=args.issue,
        error_log=error_log,
        scheduler=lambda tid: None,
    )
    print(f"[live-diagnosis] task_id={task.task_id}")

    import time

    start = time.monotonic()
    service.run_task_sync(task.task_id)
    duration_ms = int((time.monotonic() - start) * 1000)

    traces = service.get_traces(task.task_id)
    llm_traces = [t for t in traces if t.kind == "llm_call"]
    tool_traces = [t for t in traces if t.kind == "tool_call"]
    node_traces = [t for t in traces if t.kind == "node_timing"]
    input_tokens = sum(
        (t.payload.get("input_tokens") or 0) for t in llm_traces
    )
    output_tokens = sum(
        (t.payload.get("output_tokens") or 0) for t in llm_traces
    )

    report = service.get_report(task.task_id)
    if report is None:
        print("[live-diagnosis] no report generated (task may have failed)", file=sys.stderr)
        return 1

    print()
    print("=" * 60)
    print(f"task_id:          {task.task_id}")
    print(f"duration_ms:      {duration_ms}")
    print(f"llm_calls:        {len(llm_traces)}")
    print(f"tool_calls:       {len(tool_traces)}")
    print(f"node_timings:     {len(node_traces)}")
    print(f"input_tokens:     {input_tokens}")
    print(f"output_tokens:    {output_tokens}")
    diagnosis_status = report.json_report.get("diagnosis_status", "unknown")
    print(f"diagnosis_status: {diagnosis_status}")
    print("=" * 60)
    print()
    print(report.markdown_report)

    out_path = Path(args.output)
    out_path.write_text(json.dumps(report.json_report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[live-diagnosis] JSON report written to: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
