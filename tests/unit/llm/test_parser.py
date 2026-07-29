"""Parser and retry tests."""

from __future__ import annotations

import pytest

from springfix_agent.llm._retry import (
    AuthError,
    MaxRetriesExceeded,
    RetryableError,
    SchemaValidationError,
    classify_http_error,
    is_retryable,
    with_retry,
)
from springfix_agent.llm.parser import build_repair_prompt, extract_json_blob, parse_structured
from springfix_agent.llm.schemas import IssueAnalysis


def test_extract_json_blob_handles_fences() -> None:
    raw = "preamble\n```json\n{\"issue_category\":\"unknown\",\"summary\":\"s\"}\n```"
    assert extract_json_blob(raw).startswith("{")


def test_extract_json_blob_handles_plain_object() -> None:
    raw = '{"issue_category":"unknown","summary":"s"}'
    assert extract_json_blob(raw) == raw


def test_parse_structured_valid() -> None:
    raw = '{"issue_category":"transaction","summary":"ok"}'
    result = parse_structured(raw, IssueAnalysis)
    assert result.issue_category == "transaction"


def test_parse_structured_invalid_json_raises() -> None:
    with pytest.raises(SchemaValidationError):
        parse_structured("not json", IssueAnalysis)


def test_parse_structured_missing_field_raises() -> None:
    with pytest.raises(SchemaValidationError):
        parse_structured('{"summary":"only this"}', IssueAnalysis)


def test_build_repair_prompt_includes_schema() -> None:
    prompt = build_repair_prompt("prev", "missing field", IssueAnalysis)
    assert "IssueAnalysis" in prompt or "issue_category" in prompt
    assert "missing field" in prompt


def test_classify_http_error_retryable() -> None:
    assert isinstance(classify_http_error(429), RetryableError)
    assert isinstance(classify_http_error(500), RetryableError)
    assert isinstance(classify_http_error(503), RetryableError)


def test_classify_http_error_auth() -> None:
    assert isinstance(classify_http_error(401), AuthError)
    assert isinstance(classify_http_error(403), AuthError)


def test_is_retryable_true_for_timeout() -> None:
    assert is_retryable(TimeoutError("t")) is True
    assert is_retryable(ConnectionError("c")) is True
    assert is_retryable(RetryableError("r")) is True


def test_is_retryable_false_for_auth() -> None:
    assert is_retryable(AuthError("a")) is False


def test_with_retry_succeeds_first_try() -> None:
    result = with_retry(lambda: 42, max_retries=3)
    assert result == 42


def test_with_retry_succeeds_after_retry() -> None:
    calls: list[int] = []

    def attempt() -> int:
        calls.append(1)
        if len(calls) < 3:
            raise RetryableError("transient")
        return 99

    result = with_retry(attempt, max_retries=3)
    assert result == 99
    assert len(calls) == 3


def test_with_retry_gives_up_after_max() -> None:
    def attempt() -> int:
        raise RetryableError("always fail")

    with pytest.raises(MaxRetriesExceeded):
        with_retry(attempt, max_retries=2)


def test_with_retry_does_not_retry_auth() -> None:
    def attempt() -> int:
        raise AuthError("no retry")

    with pytest.raises(AuthError):
        with_retry(attempt, max_retries=3)


def test_with_retry_does_not_retry_schema_error() -> None:
    def attempt() -> int:
        raise SchemaValidationError("bad schema")

    with pytest.raises(SchemaValidationError):
        with_retry(attempt, max_retries=3)
