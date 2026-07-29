"""LLM client Protocol and trace context.

The protocol is intentionally minimal: one method, ``invoke_structured``,
that takes system/user prompts and a Pydantic response model and
returns a validated instance. Implementations (``MockLLMClient``,
``OpenAICompatibleLLMClient``) are responsible for model IO, parsing
and retry.

The ``LLMTraceContext`` is injected by the calling node and carries
everything the implementation needs to emit an LLM trace record:

- task_id (to persist the record)
- node_name (the node making the call)
- tracer (observability sink)

API keys must NEVER appear in any trace, log or exception message.
The client implementations strip them on the way out.
"""

from __future__ import annotations

from typing import Protocol, TypedDict, TypeVar

from pydantic import BaseModel

from springfix_agent.llm.trace import LLMCall
from springfix_agent.observability.tracer import Tracer

T = TypeVar("T", bound=BaseModel)


class LLMTraceContext(TypedDict):
    """Context the client uses to persist an LLM call record."""

    task_id: str
    node_name: str
    tracer: Tracer


class LLMClient(Protocol):
    """Contract for all LLM clients."""

    def invoke_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        trace_context: LLMTraceContext,
    ) -> T:
        """Invoke the model and return a validated Pydantic instance."""
        ...

    @property
    def provider(self) -> str:
        """Stable identifier for the provider (e.g. 'mock', 'openai_compatible')."""
        ...

    @property
    def model(self) -> str:
        """Stable identifier for the model (e.g. 'mock-fixed', 'gpt-4o-mini')."""
        ...

    def sanitize_for_trace(self, text: str) -> str:
        """Strip any accidental secret material before persisting."""
        ...

    def record_llm_call(self, call: LLMCall, trace_context: LLMTraceContext) -> None:
        """Persist an LLM call record through the tracer."""
        ...
