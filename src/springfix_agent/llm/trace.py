"""LLM call trace record.

One ``LLMCall`` is emitted for every model invocation, regardless of
success or failure. The record is persisted to the task trace store
with kind="llm_call" so the API can surface it alongside tool calls
and node timings.

Constraints:
    - prompt_chars / response_chars are measured in characters, never
      contain the full prompt or response body.
    - api_key / secrets must never appear in any field.
    - error_message is truncated to MAX_ERROR_CHARS.
    - duration_ms uses a monotonic clock.
    - timestamps are ISO-8601 with timezone.
"""

from __future__ import annotations

from typing import Literal, TypedDict

MAX_LLM_ERROR_CHARS = 500


class LLMCall(TypedDict):
    """A single LLM invocation record."""

    node: str
    provider: str
    model: str
    attempt: int
    start: str
    end: str
    duration_ms: int
    status: Literal["success", "retry", "error"]
    prompt_chars: int
    response_chars: int
    input_tokens: int | None
    output_tokens: int | None
    error_type: str | None
    error_message: str | None
