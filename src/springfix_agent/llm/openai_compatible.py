"""OpenAI-compatible LLM client.

Works with any endpoint that exposes ``POST /chat/completions`` with a
JSON schema in the ``response_format`` field (OpenAI itself, DeepSeek,
local Ollama, LiteLLM, etc.).

The implementation uses ``httpx`` directly instead of the OpenAI SDK so
that ``openai`` stays an optional runtime dependency.

Security:
    - api_key is passed in Authorization but never persisted.
    - sanitize_for_trace redacts the Authorization header.
    - error messages never include the API key.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from springfix_agent.llm._retry import (
    AuthError,
    RetryableError,
    SchemaValidationError,
    with_retry,
)
from springfix_agent.llm.client import LLMTraceContext
from springfix_agent.llm.parser import build_repair_prompt, parse_structured
from springfix_agent.llm.trace import LLMCall
from springfix_agent.repair.observability import audit_snapshot, classify_proposal_exception

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_TEMPERATURE = 0.0
DEFAULT_MAX_OUTPUT_TOKENS = 2000


class OpenAICompatibleLLMClient:
    """OpenAI-compatible chat/completions client using httpx."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        temperature: float = DEFAULT_TEMPERATURE,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    ) -> None:
        if not base_url:
            raise ValueError("LLM_BASE_URL is required for live mode")
        if not api_key:
            raise ValueError("LLM_API_KEY is required for live mode")
        if not model:
            raise ValueError("LLM_MODEL is required for live mode")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._max_retries = max(0, max_retries)
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._client = httpx.Client(timeout=timeout)

    @property
    def provider(self) -> str:
        return "openai_compatible"

    @property
    def model(self) -> str:
        return self._model

    def sanitize_for_trace(self, text: str) -> str:
        """Redact API key and Authorization values from ``text``."""
        if not text:
            return ""
        redacted = text.replace(self._api_key, "***REDACTED***")
        if len(self._api_key) >= 8:
            redacted = redacted.replace(self._api_key[:8], "***REDACTED***")
        return redacted

    def record_llm_call(self, call: LLMCall, trace_context: LLMTraceContext) -> None:
        trace_context["tracer"].record_llm_call(trace_context["task_id"], call)

    def invoke_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        trace_context: LLMTraceContext,
    ) -> T:
        """Invoke the model with bounded retry and one-shot format repair."""
        schema = response_model.model_json_schema()
        base_user_prompt = (
            f"{user_prompt}\n\n"
            "Return a single JSON object that conforms to this schema "
            "(no prose, no fences):\n"
            f"{json.dumps(schema)}"
        )

        attempt_number = 0
        last_usage: dict[str, int | None] = {"input_tokens": None, "output_tokens": None}
        prompt_chars = len(system_prompt) + len(base_user_prompt)
        audit = trace_context.get("audit")
        if audit is not None:
            audit["logical_call_started"] = True

        def attempt() -> T:
            nonlocal attempt_number
            attempt_number += 1
            raw, usage = self._raw_completion(system_prompt, base_user_prompt, audit=audit)
            last_usage.update(usage)
            if audit is not None:
                audit["structured_parse_attempts"] = _audit_int(audit, "structured_parse_attempts") + 1
                audit["response_character_count"] = len(raw)
                audit["response_received"] = True
                if not raw.strip():
                    audit["failure_category"] = "empty_response"
            try:
                result = parse_structured(raw, response_model)
            except SchemaValidationError as exc:
                if audit is not None and audit.get("failure_category") != "empty_response":
                    message = str(exc).casefold()
                    audit["failure_category"] = (
                        "invalid_json" if "invalid json" in message else "schema_validation_failure"
                    )
                raise
            if audit is not None:
                audit["structured_parse_succeeded"] = True
                audit["schema_validation_succeeded"] = True
                _record_response_shape(audit, result)
            return result

        start_perf = time.monotonic()
        start_iso = datetime.now(tz=UTC).isoformat()

        try:
            result = with_retry(attempt, max_retries=self._max_retries)
        except SchemaValidationError as first_error:
            # One-shot format repair.
            repair_prompt = build_repair_prompt(
                raw="", errors=str(first_error), response_model=response_model
            )
            combined_user = f"{base_user_prompt}\n\n---\n{repair_prompt}"
            raw, usage = self._raw_completion(system_prompt, combined_user, audit=audit)
            last_usage.update(usage)
            if audit is not None:
                audit["structured_parse_attempts"] = _audit_int(audit, "structured_parse_attempts") + 1
                audit["response_character_count"] = len(raw)
                audit["response_received"] = True
            try:
                result = parse_structured(raw, response_model)
            except SchemaValidationError as second_error:
                if audit is not None:
                    if raw.strip():
                        _record_parse_failure(audit, second_error)
                    else:
                        audit["failure_category"] = "empty_response"
                        audit["failure_detail_code"] = "empty_response"
                        audit["source_exception_class"] = type(second_error).__name__
                        audit["generator_outcome"] = "empty_response"
                end_iso = datetime.now(tz=UTC).isoformat()
                duration_ms = int((time.monotonic() - start_perf) * 1000)
                call = LLMCall(
                    node=trace_context["node_name"],
                    provider=self.provider,
                    model=self.model,
                    attempt=attempt_number + 1,
                    start=start_iso,
                    end=end_iso,
                    duration_ms=duration_ms,
                    status="error",
                    prompt_chars=len(system_prompt) + len(combined_user),
                    response_chars=len(raw),
                    input_tokens=last_usage.get("input_tokens"),
                    output_tokens=last_usage.get("output_tokens"),
                    error_type="SchemaValidationError",
                    error_message=self.sanitize_for_trace(str(second_error))[:500],
                )
                _attach_audit(call, audit)
                self.record_llm_call(call, trace_context)
                raise second_error
        except Exception as exc:  # noqa: BLE001 - preserve bounded provider failures
            if audit is not None:
                category, detail = classify_proposal_exception(exc)
                if category == "internal_error":
                    category = "provider_failure"
                audit["failure_category"] = category
                audit["failure_detail_code"] = detail
                audit["source_exception_class"] = type(exc).__name__
            end_iso = datetime.now(tz=UTC).isoformat()
            duration_ms = int((time.monotonic() - start_perf) * 1000)
            call = LLMCall(
                node=trace_context["node_name"],
                provider=self.provider,
                model=self.model,
                attempt=max(1, attempt_number),
                start=start_iso,
                end=end_iso,
                duration_ms=duration_ms,
                status="error",
                prompt_chars=prompt_chars,
                response_chars=0,
                input_tokens=last_usage.get("input_tokens"),
                output_tokens=last_usage.get("output_tokens"),
                error_type=type(exc).__name__,
                error_message=self.sanitize_for_trace(str(exc))[:500],
            )
            _attach_audit(call, audit)
            self.record_llm_call(call, trace_context)
            raise

        # Success path: record one trace for the overall invocation.
        end_iso = datetime.now(tz=UTC).isoformat()
        duration_ms = int((time.monotonic() - start_perf) * 1000)
        response_chars = len(result.model_dump_json())
        call = LLMCall(
            node=trace_context["node_name"],
            provider=self.provider,
            model=self.model,
            attempt=attempt_number,
            start=start_iso,
            end=end_iso,
            duration_ms=duration_ms,
            status="success",
            prompt_chars=prompt_chars,
            response_chars=response_chars,
            input_tokens=last_usage.get("input_tokens"),
            output_tokens=last_usage.get("output_tokens"),
            error_type=None,
            error_message=None,
        )
        _attach_audit(call, audit)
        self.record_llm_call(call, trace_context)
        return result

    def _raw_completion(
        self, system_prompt: str, user_prompt: str, *, audit: dict[str, object] | None = None
    ) -> tuple[str, dict[str, int | None]]:
        """POST /chat/completions and return (content, usage_dict)."""
        # Many OpenAI-compatible endpoints expect the /v1 prefix. If the
        # configured base_url doesn't already end with /v1, append it so
        # users can configure either https://host/ai or https://host/ai/v1.
        base = self._base_url.rstrip("/")
        if not base.endswith("/v1"):
            base = f"{base}/v1"
        url = f"{base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "model": self._model,
            "temperature": self._temperature,
            "max_tokens": self._max_output_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        try:
            if audit is not None:
                audit["http_attempts"] = _audit_int(audit, "http_attempts") + 1
            response = self._client.post(url, headers=headers, json=body)
        except httpx.TimeoutException as e:
            raise RetryableError(f"timeout: {e}") from e
        except httpx.RequestError as e:
            raise RetryableError(f"connection error: {e}") from e

        response_detail = self.sanitize_for_trace(response.text[:200])
        if response.status_code == 429 or 500 <= response.status_code < 600:
            raise RetryableError(f"HTTP {response.status_code}: {response_detail}")
        if response.status_code in (401, 403):
            raise AuthError(f"auth HTTP {response.status_code}")
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code}: {response_detail}")

        try:
            payload = response.json()
        except ValueError as e:
            raise RetryableError(f"invalid JSON response: {e}") from e

        content = ""
        if audit is not None:
            audit["provider_completed"] = True
            audit["response_count"] = _audit_int(audit, "response_count") + 1
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    content = str(message.get("content", "") or "")

        usage_raw = payload.get("usage") if isinstance(payload, dict) else None
        input_tokens: int | None = None
        output_tokens: int | None = None
        if isinstance(usage_raw, dict):
            it = usage_raw.get("prompt_tokens")
            ot = usage_raw.get("completion_tokens")
            if isinstance(it, int):
                input_tokens = it
            if isinstance(ot, int):
                output_tokens = ot

        return content, {"input_tokens": input_tokens, "output_tokens": output_tokens}


def _record_response_shape(audit: dict[str, object], result: BaseModel) -> None:
    """Record bounded structured-output shape, never its content."""
    data = result.model_dump(mode="json")
    audit["response_top_level_keys"] = sorted(str(key) for key in data)
    audit["response_status_field_present"] = "status" in data
    status = data.get("status")
    if status == "insufficient_evidence":
        audit["failure_category"] = "proposal_status_insufficient_evidence"
        audit["generator_outcome"] = status
    elif status == "unsafe_to_propose":
        audit["failure_category"] = "proposal_status_unsafe"
        audit["generator_outcome"] = status
    elif status == "proposed":
        audit["generator_outcome"] = status
    if isinstance(data.get("edits"), list):
        audit["response_edit_count"] = len(data["edits"])


def _audit_int(audit: dict[str, object], key: str) -> int:
    value = audit.get(key)
    return value if isinstance(value, int) else 0


def _attach_audit(call: LLMCall, audit: dict[str, object] | None) -> None:
    if audit is not None:
        call["proposal_audit"] = audit_snapshot(audit)


def _record_parse_failure(audit: dict[str, object], exc: SchemaValidationError) -> None:
    """Record only a stable parse category, never response content."""
    message = str(exc).casefold()
    audit["failure_category"] = (
        "empty_response"
        if "empty response" in message
        else "invalid_json"
        if "invalid json" in message
        else "schema_validation_failure"
        if "schema mismatch" in message
        else "structured_parse_failure"
    )
    audit["failure_detail_code"] = str(audit["failure_category"])
    audit["source_exception_class"] = type(exc).__name__
    audit["generator_outcome"] = str(audit["failure_category"])
