"""Structured LLM response parser with optional one-shot format repair.

Responsibilities:

    1. Extract JSON from the model's free-form output (tolerates
       markdown code fences, preamble and postamble text).
    2. Validate against the supplied Pydantic model.
    3. On validation failure, perform a single repair attempt that
       asks the model to emit a corrected JSON object matching the
       schema. A second failure surfaces as ``SchemaValidationError``
       — we do NOT loop forever.
"""

from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from springfix_agent.llm._retry import SchemaValidationError

T = TypeVar("T", bound=BaseModel)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_JSON_OBJECT_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


def extract_json_blob(text: str) -> str:
    """Return the first JSON object substring from ``text``.

    Tries fenced code blocks first, then falls back to the outermost
    balanced brace pair. Returns ``text`` unchanged if no JSON is
    detected — the caller is expected to re-raise a clear error.
    """
    stripped = text.strip()
    fence = _JSON_FENCE_RE.search(stripped)
    if fence:
        return fence.group(1).strip()
    start = stripped.find("{")
    if start == -1:
        return stripped
    end = stripped.rfind("}")
    if end <= start:
        return stripped
    return stripped[start : end + 1]


def parse_structured(raw: str, response_model: type[T]) -> T:
    """Parse ``raw`` as JSON and validate against ``response_model``.

    Raises:
        SchemaValidationError: on JSON decode or validation failure.
    """
    blob = extract_json_blob(raw)
    try:
        data = json.loads(blob)
    except json.JSONDecodeError as e:
        raise SchemaValidationError(f"invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise SchemaValidationError(f"expected object, got {type(data).__name__}")
    try:
        return response_model.model_validate(data)
    except ValidationError as e:
        raise SchemaValidationError(f"schema mismatch: {e}") from e


def build_repair_prompt(raw: str, errors: str, response_model: type[T]) -> str:
    """Compose a one-shot repair prompt asking the model to re-emit JSON."""
    schema = response_model.model_json_schema()
    return (
        "Your previous response failed schema validation. "
        "Emit a corrected JSON object that conforms to the schema below. "
        "Output ONLY the JSON object; no prose, no fences, no commentary.\n\n"
        f"Schema: {json.dumps(schema)}\n\n"
        f"Validation errors: {errors}\n\n"
        f"Your previous response (truncated): {raw[:2000]}\n"
    )
