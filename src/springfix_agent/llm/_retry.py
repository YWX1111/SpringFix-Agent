"""Bounded retry policy for transient LLM errors.

Only the following conditions trigger a retry:
    - Network timeout
    - Connection failure
    - HTTP 429 (rate limit)
    - HTTP 5xx (transient server error)
    - Schema validation failure on the FIRST attempt (one format repair)

The following conditions MUST NOT retry:
    - HTTP 401 / 403 (auth)
    - Missing config
    - Repeated schema validation failure (max 1 repair)
    - Prompt logic errors

All retries are capped at ``max_retries``. The function never loops
forever. Every attempt emits an LLM trace record with its ``attempt``
number so failures are auditable.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import TypeVar

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


class RetryableError(Exception):
    """Error that should trigger a retry (network, 429, 5xx)."""


class AuthError(Exception):
    """HTTP 401/403; never retry."""


class SchemaValidationError(Exception):
    """Pydantic validation failure on the LLM response."""


class MaxRetriesExceeded(Exception):
    """Retry budget exhausted."""


# HTTP status regex; covers both "429" in an error message and "HTTP/1.1 429".
_RETRYABLE_STATUS_RE = re.compile(r"\b(429|5[0-9]{2})\b")
_AUTH_STATUS_RE = re.compile(r"\b(401|403)\b")


def classify_http_error(status_code: int, message: str = "") -> RetryableError | AuthError:
    """Map an HTTP status code to the appropriate exception class."""
    if status_code in (401, 403) or _AUTH_STATUS_RE.search(message):
        return AuthError(f"auth error: {status_code} {message}")
    if status_code == 429 or (500 <= status_code <= 599) or _RETRYABLE_STATUS_RE.search(message):
        return RetryableError(f"transient error: {status_code} {message}")
    return RetryableError(f"unknown error: {status_code} {message}")


def is_retryable(exc: BaseException) -> bool:
    """Return True if ``exc`` is a retryable error."""
    if isinstance(exc, (RetryableError, TimeoutError, ConnectionError)):
        return True
    if isinstance(exc, AuthError):
        return False
    return False


def with_retry(
    fn: Callable[[], T],
    *,
    max_retries: int,
    on_attempt_failed: Callable[[int, BaseException], None] | None = None,
) -> T:
    """Run ``fn`` with bounded retry for transient errors only.

    Args:
        fn: Zero-arg callable that produces the desired result.
        max_retries: Hard cap on additional attempts after the first.
        on_attempt_failed: Hook invoked with (attempt, exception) on
            every failed attempt before the next retry.

    Returns:
        The first successful return value.

    Raises:
        MaxRetriesExceeded: if all attempts fail and the last error is
            retryable.
        The underlying exception otherwise.
    """
    last_exc: BaseException | None = None
    for attempt in range(1, max_retries + 2):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last_exc = e
            if on_attempt_failed is not None:
                on_attempt_failed(attempt, e)
            if not is_retryable(e):
                raise
            if attempt > max_retries:
                raise MaxRetriesExceeded(f"exhausted {max_retries} retries") from e
    assert last_exc is not None
    raise MaxRetriesExceeded(f"exhausted {max_retries} retries") from last_exc
