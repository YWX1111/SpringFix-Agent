"""OpenAICompatibleLLMClient tests.

Uses httpx.MockTransport to intercept outgoing requests. No real
network IO is performed. Covers:

    2. Invalid JSON response
    3. Schema validation failure
    7. Format repair success
    8. Format repair still fails
"""

from __future__ import annotations

import json

import httpx
import pytest

from springfix_agent.llm._retry import AuthError, RetryableError, SchemaValidationError
from springfix_agent.llm.openai_compatible import OpenAICompatibleLLMClient
from springfix_agent.llm.schemas import IssueAnalysis
from springfix_agent.observability.in_memory_tracer import InMemoryTracer
from springfix_agent.storage.in_memory import InMemoryTaskRepository


def _make_client(handler) -> OpenAICompatibleLLMClient:
    client = OpenAICompatibleLLMClient(
        base_url="https://mock.api.example",
        api_key="sk-test-do-not-use",
        model="mock-model",
        max_retries=0,
    )
    # Replace the internal httpx client with one that uses a mock transport.
    client._client = httpx.Client(transport=httpx.MockTransport(handler))  # type: ignore[attr-defined]
    return client


def _tracer_ctx():
    repo = InMemoryTaskRepository()
    task = repo.create_task(
        repository_path="/tmp/x",
        issue_description="test issue description",
        error_log=None,
    )
    tracer = InMemoryTracer(repo)
    return repo, tracer, task.task_id


def test_openai_success_structured_output() -> None:
    """Case 1: normal structured output via chat/completions."""
    repo, tracer, task_id = _tracer_ctx()

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://mock.api.example/v1/chat/completions"
        body = {
            "choices": [{"message": {"content": json.dumps({
                "issue_category": "transaction",
                "summary": "self-invocation bypass",
            })}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 10},
        }
        return httpx.Response(200, json=body)

    client = _make_client(handler)
    ctx = {"task_id": task_id, "node_name": "issue_parser", "tracer": tracer}
    result = client.invoke_structured(
        system_prompt="sys",
        user_prompt="user",
        response_model=IssueAnalysis,
        trace_context=ctx,
    )
    assert result.issue_category == "transaction"
    # Trace must be recorded
    traces = repo.get_traces(task_id)
    llm_traces = [t for t in traces if t.kind == "llm_call"]
    assert len(llm_traces) >= 1
    last = llm_traces[-1]
    assert last.payload["input_tokens"] == 50
    assert last.payload["output_tokens"] == 10
    assert "sk-test-do-not-use" not in json.dumps(last.payload)


def test_openai_invalid_json_raises() -> None:
    """Case 2: model returns garbage → SchemaValidationError."""
    repo, tracer, task_id = _tracer_ctx()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})

    client = _make_client(handler)
    ctx = {"task_id": task_id, "node_name": "issue_parser", "tracer": tracer}
    with pytest.raises(SchemaValidationError):
        client.invoke_structured(
            system_prompt="sys",
            user_prompt="user",
            response_model=IssueAnalysis,
            trace_context=ctx,
        )


def test_openai_missing_required_field_raises() -> None:
    """Case 3: JSON object missing required field → SchemaValidationError."""
    repo, tracer, task_id = _tracer_ctx()

    def handler(request: httpx.Request) -> httpx.Response:
        body = {"choices": [{"message": {"content": json.dumps({"summary": "only this"})}}]}
        return httpx.Response(200, json=body)

    client = _make_client(handler)
    ctx = {"task_id": task_id, "node_name": "issue_parser", "tracer": tracer}
    with pytest.raises(SchemaValidationError):
        client.invoke_structured(
            system_prompt="sys",
            user_prompt="user",
            response_model=IssueAnalysis,
            trace_context=ctx,
        )


def test_openai_429_raises_retryable() -> None:
    """429 response is retryable; with max_retries=0 it surfaces as MaxRetriesExceeded."""
    from springfix_agent.llm._retry import MaxRetriesExceeded

    repo, tracer, task_id = _tracer_ctx()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="rate limited")

    client = _make_client(handler)
    ctx = {"task_id": task_id, "node_name": "issue_parser", "tracer": tracer}
    with pytest.raises((RetryableError, MaxRetriesExceeded)):
        client.invoke_structured(
            system_prompt="sys",
            user_prompt="user",
            response_model=IssueAnalysis,
            trace_context=ctx,
        )


def test_openai_existing_v1_is_not_duplicated() -> None:
    """An explicit /v1 base URL is used as-is."""
    repo, tracer, task_id = _tracer_ctx()

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://mock.api.example/v1/chat/completions"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"issue_category": "unknown", "summary": "ok"}
                            )
                        }
                    }
                ]
            },
        )

    client = OpenAICompatibleLLMClient(
        base_url="https://mock.api.example/v1/",
        api_key="test-key",
        model="mock-model",
        max_retries=0,
    )
    client._client = httpx.Client(transport=httpx.MockTransport(handler))  # type: ignore[attr-defined]
    result = client.invoke_structured(
        system_prompt="sys",
        user_prompt="user",
        response_model=IssueAnalysis,
        trace_context={"task_id": task_id, "node_name": "issue_parser", "tracer": tracer},
    )
    assert result.summary == "ok"


def test_openai_auth_error_is_not_retried() -> None:
    """401/403 are non-retryable even when a retry budget is configured."""
    repo, tracer, task_id = _tracer_ctx()
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(401, text="unauthorized")

    client = OpenAICompatibleLLMClient(
        base_url="https://mock.api.example",
        api_key="test-key",
        model="mock-model",
        max_retries=2,
    )
    client._client = httpx.Client(transport=httpx.MockTransport(handler))  # type: ignore[attr-defined]
    with pytest.raises(AuthError):
        client.invoke_structured(
            system_prompt="sys",
            user_prompt="user",
            response_model=IssueAnalysis,
            trace_context={"task_id": task_id, "node_name": "issue_parser", "tracer": tracer},
        )
    assert call_count == 1


def test_openai_format_repair_success() -> None:
    """Case 7: first call returns invalid JSON, repair call succeeds."""
    repo, tracer, task_id = _tracer_ctx()

    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(200, json={"choices": [{"message": {"content": "oops"}}]})
        body = {
            "choices": [{"message": {"content": json.dumps({
                "issue_category": "transaction",
                "summary": "repaired",
            })}}]
        }
        return httpx.Response(200, json=body)

    client = _make_client(handler)
    ctx = {"task_id": task_id, "node_name": "issue_parser", "tracer": tracer}
    result = client.invoke_structured(
        system_prompt="sys",
        user_prompt="user",
        response_model=IssueAnalysis,
        trace_context=ctx,
    )
    assert result.issue_category == "transaction"
    assert call_count["n"] == 2  # initial + repair


def test_openai_format_repair_still_fails() -> None:
    """Case 8: both initial and repair call fail → SchemaValidationError."""
    repo, tracer, task_id = _tracer_ctx()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})

    client = _make_client(handler)
    ctx = {"task_id": task_id, "node_name": "issue_parser", "tracer": tracer}
    with pytest.raises(SchemaValidationError):
        client.invoke_structured(
            system_prompt="sys",
            user_prompt="user",
            response_model=IssueAnalysis,
            trace_context=ctx,
        )


def test_openai_sanitize_redacts_api_key() -> None:
    """API key must never appear in trace output."""
    client = OpenAICompatibleLLMClient(
        base_url="https://mock",
        api_key="sk-super-secret-123",
        model="m",
    )
    out = client.sanitize_for_trace("Bearer sk-super-secret-123 is used")
    assert "sk-super-secret-123" not in out


def test_openai_missing_config_raises() -> None:
    """Missing base_url/api_key/model raises on construction."""
    with pytest.raises(ValueError):
        OpenAICompatibleLLMClient(base_url="", api_key="k", model="m")
    with pytest.raises(ValueError):
        OpenAICompatibleLLMClient(base_url="https://x", api_key="", model="m")
    with pytest.raises(ValueError):
        OpenAICompatibleLLMClient(base_url="https://x", api_key="k", model="")
