"""Bounded, redacted observability models for the repair stages.

These records explain where a proposal or verification failed without
retaining prompts, model response bodies, source code, or process environments.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ProposalFailureCategory = Literal[
    "no_validated_evidence",
    "provider_failure",
    "provider_timeout",
    "empty_response",
    "invalid_json",
    "structured_parse_failure",
    "schema_validation_failure",
    "proposal_status_insufficient_evidence",
    "proposal_status_unsafe",
    "validator_no_valid_edits",
    "missing_required_import",
    "internal_error",
]


class ProposalGenerationAudit(BaseModel):
    """Redacted audit for one Patch Proposal generation attempt."""

    model_config = ConfigDict(extra="forbid")

    logical_call_started: bool = False
    logical_llm_calls: int = Field(default=0, ge=0)
    http_attempts: int = Field(default=0, ge=0)
    provider_completed: bool = False
    response_received: bool = False
    response_count: int = Field(default=0, ge=0)
    response_character_count: int = Field(default=0, ge=0)
    response_top_level_keys: list[str] = Field(default_factory=list, max_length=20)
    response_status_field_present: bool = False
    response_edit_count: int | None = Field(default=None, ge=0)
    structured_parse_attempts: int = Field(default=0, ge=0)
    structured_parse_succeeded: bool = False
    schema_validation_succeeded: bool = False
    parse_attempts: int = Field(default=0, ge=0)
    parse_success: bool = False
    schema_success: bool = False
    generator_outcome: str = "not_started"
    outcome: str = "not_started"
    failure_category: ProposalFailureCategory | None = None
    failure_detail_code: str | None = None
    failure_detail: str | None = None
    source_exception_class: str | None = None


def classify_proposal_exception(exc: BaseException) -> tuple[ProposalFailureCategory, str]:
    """Map an internal exception to a stable, bounded failure category."""
    name = type(exc).__name__
    message = str(exc).casefold()
    if name == "MaxRetriesExceeded":
        cause_message = str(exc.__cause__ or "").casefold()
        return (
            ("provider_timeout", name)
            if "timeout" in cause_message
            else ("provider_failure", name)
        )
    if "timeout" in message:
        return "provider_timeout", name
    if name in {"RetryableError", "AuthError", "ConnectionError", "TimeoutError"}:
        return "provider_failure", name
    if name == "SchemaValidationError":
        if "empty response" in message:
            return "empty_response", "empty_response"
        if "invalid json" in message:
            return "invalid_json", "invalid_json"
        if "schema mismatch" in message:
            return "schema_validation_failure", "schema_validation_failure"
        return "structured_parse_failure", "structured_parse_failure"
    return "internal_error", name


def audit_from_state(state: dict[str, object]) -> ProposalGenerationAudit:
    """Validate a mutable client audit state without retaining unknown fields."""
    allowed = set(ProposalGenerationAudit.model_fields)
    data = {key: value for key, value in state.items() if key in allowed}
    logical_started = data.get("logical_call_started") is True
    parse_attempts = data.get("structured_parse_attempts", 0)
    parse_success = data.get("structured_parse_succeeded", False)
    schema_success = data.get("schema_validation_succeeded", False)
    outcome = data.get("generator_outcome", "not_started")
    detail = data.get("failure_detail_code")
    data.update(
        {
            "logical_llm_calls": 1 if logical_started else 0,
            "parse_attempts": parse_attempts,
            "parse_success": parse_success,
            "schema_success": schema_success,
            "outcome": outcome,
            "failure_detail": detail,
        }
    )
    return ProposalGenerationAudit.model_validate(data)


def audit_snapshot(state: dict[str, object]) -> dict[str, object]:
    """Return the bounded serialized shape used by existing LLM traces."""
    return audit_from_state(state).model_dump(mode="json")


__all__ = [
    "ProposalFailureCategory",
    "ProposalGenerationAudit",
    "audit_from_state",
    "audit_snapshot",
    "classify_proposal_exception",
]
