"""issue_parser node: LLM-backed problem classification.

Inputs:  issue_description, error_log
Outputs: issue_analysis, extracted_symbols (merged), warnings, llm_calls

On LLM failure the node falls back to the M1 deterministic symbol
extraction (see ``graph/nodes/_symbol_extraction.py``) and sets the
category to ``unknown``. The node never fails the whole task on an LLM
error.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from springfix_agent.graph.nodes._symbol_extraction import (
    extract_symbols as _deterministic_extract,
)
from springfix_agent.graph.state import AgentState
from springfix_agent.llm.client import LLMClient, LLMTraceContext
from springfix_agent.llm.prompts import render_prompt
from springfix_agent.llm.schemas import IssueAnalysis
from springfix_agent.observability.tracer import Tracer

_LOGGER = logging.getLogger(__name__)

_FALLBACK_SUMMARY = "LLM unavailable; analysis fell back to deterministic extraction."


def issue_parser(
    state: AgentState,
    *,
    llm: LLMClient,
    tracer: Tracer,
) -> dict[str, Any]:
    """Run IssueParser and merge deterministic symbols."""
    task_id = state["task_id"]
    issue_description = state["issue_description"]
    error_log = state.get("error_log")

    trace_ctx: LLMTraceContext = {
        "task_id": task_id,
        "node_name": "issue_parser",
        "tracer": tracer,
    }

    deterministic_symbols = _deterministic_extract(issue_description, error_log)

    try:
        user_prompt = render_prompt(
            "issue_parser",
            issue_description=issue_description,
            error_log=error_log or "(no error log provided)",
        )
        system_prompt = (
            "You are SpringFix's IssueParser. Analyze the user report and "
            "return a single IssueAnalysis JSON object."
        )
        analysis = llm.invoke_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=IssueAnalysis,
            trace_context=trace_ctx,
        )
        merged_symbols = list(dict.fromkeys([*deterministic_symbols, *analysis.extracted_symbols]))
        merged_symbols = merged_symbols[:10]
        return {
            "issue_analysis": analysis.model_dump(),
            "extracted_symbols": merged_symbols,
            "warnings": [],
        }
    except (ValidationError, Exception) as e:  # noqa: BLE001
        _LOGGER.warning("issue_parser LLM call failed: %s", e)
        fallback = IssueAnalysis(
            issue_category="unknown",
            summary=_FALLBACK_SUMMARY,
            symptoms=[],
            exception_types=[],
            extracted_symbols=deterministic_symbols[:10],
            search_terms=deterministic_symbols[:15],
            spring_concepts=[],
        )
        return {
            "issue_analysis": fallback.model_dump(),
            "extracted_symbols": deterministic_symbols[:10],
            "warnings": [f"issue_parser LLM fallback: {type(e).__name__}: {str(e)[:200]}"],
        }
