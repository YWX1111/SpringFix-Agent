"""Mock LLM client for tests and offline CI.

``MockLLMClient`` returns pre-configured structured outputs per node,
without any network IO. It can also simulate failure modes (timeout,
429, invalid JSON, missing fields) so tests can verify the retry and
degradation paths of the real clients.

Usage:
    mock = MockLLMClient()
    mock.set_response(IssueAnalysis(...))   # next call returns this
    mock.set_behavior("timeout", n=1)       # first call raises, then OK

When no behavior is configured the mock returns a safe default instance
of the requested model so tests stay deterministic.
"""

from __future__ import annotations

import time
from collections import deque
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel

from springfix_agent.llm._retry import (
    AuthError,
    RetryableError,
    SchemaValidationError,
)
from springfix_agent.llm.client import LLMTraceContext
from springfix_agent.llm.schemas import (
    InvestigationPlan,
    InvestigationStep,
    IssueAnalysis,
    RootCauseAnalysis,
)
from springfix_agent.llm.trace import LLMCall
from springfix_agent.repair.models import PatchProposal
from springfix_agent.repair.observability import audit_snapshot, classify_proposal_exception

Behavior = Literal["ok", "timeout", "connection", "rate_limit", "auth", "invalid_json", "schema_error"]

_SAFE_DEFAULTS: dict[type[BaseModel], BaseModel] = {
    IssueAnalysis: IssueAnalysis(
        issue_category="unknown",
        summary="Mock default — no LLM response configured.",
    ),
    InvestigationPlan: InvestigationPlan(
        steps=[
            InvestigationStep(step_id=1, objective="Browse repository tree", rationale="mock"),
            InvestigationStep(step_id=2, objective="Search for key symbols", rationale="mock"),
            InvestigationStep(step_id=3, objective="Read top candidate files", rationale="mock"),
        ]
    ),
    RootCauseAnalysis: RootCauseAnalysis(
        diagnosis_status="insufficient_evidence",
        summary="Mock default — no evidence configured.",
    ),
}


_SAFE_DEFAULTS[PatchProposal] = PatchProposal(
    status="insufficient_evidence",
    summary="Mock default - no patch response configured.",
    root_cause_reference="none",
)


class MockLLMClient:
    """Deterministic LLM client for tests."""

    def __init__(self) -> None:
        self._responses: dict[type[BaseModel], BaseModel] = {}
        self._behaviors: dict[type[BaseModel], deque[Behavior]] = {}
        self._call_count = 0
        self._profile: str | None = None

    def set_response(self, model_instance: BaseModel) -> None:
        """Configure the next return value for the instance's type."""
        self._responses[type(model_instance)] = model_instance

    def use_profile(self, profile: str) -> None:
        """Activate a named Profile from ``llm.profiles``.

        When a Profile is active, ``invoke_structured`` returns the
        Profile's pre-configured instance unless ``set_response`` or
        ``set_behavior`` has overridden the model type.
        """
        from springfix_agent.llm.profiles import SUPPORTED_PROFILES

        if profile not in SUPPORTED_PROFILES:
            raise ValueError(f"unknown profile: {profile}")
        self._profile = profile

    def set_behavior(self, behavior: Behavior, *, for_model: type[BaseModel] | None = None, n: int = 1) -> None:
        """Queue a failure behavior for the next ``n`` calls of ``for_model``.

        If ``for_model`` is None, applies to all models (useful for
        testing global degradation paths).
        """
        targets = [for_model] if for_model is not None else list(_SAFE_DEFAULTS.keys())
        for target in targets:
            q = self._behaviors.setdefault(target, deque())
            for _ in range(n):
                q.append(behavior)

    @property
    def provider(self) -> str:
        return "mock"

    @property
    def model(self) -> str:
        return "mock-fixed"

    def sanitize_for_trace(self, text: str) -> str:
        """Mock client has no secrets; return text truncated for trace size."""
        return text[:200]

    def record_llm_call(self, call: LLMCall, trace_context: LLMTraceContext) -> None:
        trace_context["tracer"].record_llm_call(trace_context["task_id"], call)

    def invoke_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[Any],
        trace_context: LLMTraceContext,
    ) -> Any:
        """Return a configured response or simulate a failure."""
        self._call_count += 1
        start_perf = time.monotonic()
        start_iso = datetime.now(tz=UTC).isoformat()
        prompt_chars = len(system_prompt) + len(user_prompt)
        audit = trace_context.get("audit")
        if audit is not None:
            audit["logical_call_started"] = True

        behavior = self._next_behavior(response_model)
        if behavior != "ok":
            exc = self._build_behavior_exception(behavior)
            if audit is not None:
                audit["response_received"] = behavior in {"invalid_json", "schema_error"}
                audit["response_count"] = 1 if audit["response_received"] else 0
                audit["response_character_count"] = 0
                audit["structured_parse_attempts"] = 1 if audit["response_received"] else 0
                category, detail = classify_proposal_exception(exc)
                audit["failure_category"] = category
                audit["failure_detail_code"] = detail
                audit["source_exception_class"] = type(exc).__name__
                audit["generator_outcome"] = category
            end_iso = datetime.now(tz=UTC).isoformat()
            duration_ms = int((time.monotonic() - start_perf) * 1000)
            call = LLMCall(
                node=trace_context["node_name"],
                provider=self.provider,
                model=self.model,
                attempt=self._call_count,
                start=start_iso,
                end=end_iso,
                duration_ms=duration_ms,
                status="error",
                prompt_chars=prompt_chars,
                response_chars=0,
                input_tokens=None,
                output_tokens=None,
                error_type=type(exc).__name__,
                error_message=str(exc)[:500],
            )
            if audit is not None:
                call["proposal_audit"] = audit_snapshot(audit)
            self.record_llm_call(call, trace_context)
            raise exc

        instance = self._responses.get(response_model)
        if instance is None and self._profile is not None:
            from springfix_agent.llm.profiles import (
                build_failure_exception,
                build_failure_trace,
                get_profile_response,
                is_failure_profile,
            )

            if is_failure_profile(self._profile):
                exc = build_failure_exception(self._profile)
                failure_call = build_failure_trace(
                    self._profile,
                    node_name=trace_context["node_name"],
                    prompt_chars=prompt_chars,
                )
                if audit is not None:
                    category, detail = classify_proposal_exception(exc)
                    audit["provider_completed"] = False
                    audit["response_received"] = False
                    audit["failure_category"] = category
                    audit["failure_detail_code"] = detail
                    audit["source_exception_class"] = type(exc).__name__
                    audit["generator_outcome"] = "exception_normalized_insufficient_evidence"
                    failure_call["proposal_audit"] = audit_snapshot(audit)
                self.record_llm_call(failure_call, trace_context)
                raise exc
            profile_instance = get_profile_response(self._profile, response_model)
            if profile_instance is not None:
                instance = profile_instance

        if instance is None:
            instance = _SAFE_DEFAULTS.get(response_model)

        if instance is None:
            exc = SchemaValidationError(f"no mock response for {response_model.__name__}")
            if audit is not None:
                category, detail = classify_proposal_exception(exc)
                audit["failure_category"] = category
                audit["failure_detail_code"] = detail
                audit["source_exception_class"] = type(exc).__name__
            end_iso = datetime.now(tz=UTC).isoformat()
            duration_ms = int((time.monotonic() - start_perf) * 1000)
            call = LLMCall(
                node=trace_context["node_name"],
                provider=self.provider,
                model=self.model,
                attempt=self._call_count,
                start=start_iso,
                end=end_iso,
                duration_ms=duration_ms,
                status="error",
                prompt_chars=prompt_chars,
                response_chars=0,
                input_tokens=None,
                output_tokens=None,
                error_type="SchemaValidationError",
                error_message=str(exc)[:500],
            )
            if audit is not None:
                call["proposal_audit"] = audit_snapshot(audit)
            self.record_llm_call(call, trace_context)
            raise exc

        end_iso = datetime.now(tz=UTC).isoformat()
        duration_ms = int((time.monotonic() - start_perf) * 1000)
        if audit is not None:
            data = instance.model_dump(mode="json")
            audit["provider_completed"] = True
            audit["response_received"] = True
            audit["response_count"] = 1
            audit["response_character_count"] = len(instance.model_dump_json())
            audit["structured_parse_attempts"] = 1
            audit["structured_parse_succeeded"] = True
            audit["schema_validation_succeeded"] = True
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
        call = LLMCall(
            node=trace_context["node_name"],
            provider=self.provider,
            model=self.model,
            attempt=self._call_count,
            start=start_iso,
            end=end_iso,
            duration_ms=duration_ms,
            status="success",
            prompt_chars=prompt_chars,
            response_chars=len(instance.model_dump_json()),
            input_tokens=None,
            output_tokens=None,
            error_type=None,
            error_message=None,
        )
        if audit is not None:
            call["proposal_audit"] = audit_snapshot(audit)
        self.record_llm_call(call, trace_context)
        return instance

    def _next_behavior(self, model: type[BaseModel]) -> Behavior:
        q = self._behaviors.get(model)
        if q:
            return q.popleft()
        for other in self._behaviors.values():
            if other:
                return other.popleft()
        return "ok"

    @staticmethod
    def _build_behavior_exception(behavior: Behavior) -> BaseException:
        if behavior == "timeout":
            return RetryableError("mock timeout")
        if behavior == "connection":
            return RetryableError("mock connection error")
        if behavior == "rate_limit":
            return RetryableError("mock HTTP 429")
        if behavior == "auth":
            return AuthError("mock HTTP 401")
        if behavior == "invalid_json":
            return SchemaValidationError("mock invalid JSON")
        if behavior == "schema_error":
            return SchemaValidationError("mock schema mismatch")
        return RetryableError("mock unknown behavior")
