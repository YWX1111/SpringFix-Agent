"""LLM layer: clients, schemas, prompts, retry and trace.

M2 introduces three LLM reasoning nodes: IssueParser, TaskPlanner,
RootCauseAnalyzer. All other nodes remain deterministic (M1 tools +
code retrieval + report rendering).

The layer is organized around four responsibilities:

    1. **Protocol** (``client.py``): ``LLMClient.invoke_structured``
       is the single entry point for all LLM calls. Implementations
       include a deterministic ``MockLLMClient`` (for tests / CI) and
       an OpenAI-compatible client.
    2. **Schemas** (``schemas.py``): Pydantic models for every
       structured LLM output. Node code never touches raw JSON or
       plain dicts from the model.
    3. **Parser + retry** (``parser.py``, ``_retry.py``): JSON
       extraction, schema validation, one-shot format repair and
       bounded retry for transient errors.
    4. **Trace** (``trace.py``): ``LLMCall`` TypedDict that feeds the
       observability pipeline alongside ``ToolCall`` and ``NodeTiming``.
"""

from springfix_agent.llm.client import LLMClient, LLMTraceContext
from springfix_agent.llm.mock import MockLLMClient
from springfix_agent.llm.openai_compatible import OpenAICompatibleLLMClient
from springfix_agent.llm.schemas import (
    EvidenceReference,
    InvestigationPlan,
    InvestigationStep,
    IssueAnalysis,
    RootCauseAnalysis,
    RootCauseCandidate,
)
from springfix_agent.llm.trace import LLMCall

__all__ = [
    "LLMClient",
    "LLMTraceContext",
    "LLMCall",
    "MockLLMClient",
    "OpenAICompatibleLLMClient",
    "IssueAnalysis",
    "InvestigationStep",
    "InvestigationPlan",
    "EvidenceReference",
    "RootCauseCandidate",
    "RootCauseAnalysis",
]
