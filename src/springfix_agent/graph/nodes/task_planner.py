"""task_planner node: LLM-backed investigation planning.

Inputs:  issue_analysis, issue_description, error_log
Outputs: investigation_plan, warnings

On LLM failure the node falls back to a small deterministic plan
(browse tree, search symbols, read candidates, gather evidence) and
records a warning. It never fails the whole task.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import ValidationError

from springfix_agent.graph.state import AgentState
from springfix_agent.llm.client import LLMClient, LLMTraceContext
from springfix_agent.llm.prompts import render_prompt
from springfix_agent.llm.schemas import InvestigationPlan, InvestigationStep
from springfix_agent.observability.tracer import Tracer

_LOGGER = logging.getLogger(__name__)

_FALLBACK_PLAN = InvestigationPlan(
    steps=[
        InvestigationStep(
            step_id=1,
            objective="Browse repository structure",
            rationale="Understand package layout and identify likely source directories.",
        ),
        InvestigationStep(
            step_id=2,
            objective="Search for extracted symbols",
            rationale="Locate class and method definitions mentioned in the issue.",
        ),
        InvestigationStep(
            step_id=3,
            objective="Read top candidate files",
            rationale="Collect bounded code evidence for root-cause analysis.",
        ),
    ]
)


def task_planner(
    state: AgentState,
    *,
    llm: LLMClient,
    tracer: Tracer,
) -> dict[str, Any]:
    """Run TaskPlanner or fall back to a deterministic minimal plan."""
    task_id = state["task_id"]
    issue_description = state["issue_description"]
    error_log = state.get("error_log")
    issue_analysis_raw = state.get("issue_analysis", {}) or {}

    trace_ctx: LLMTraceContext = {
        "task_id": task_id,
        "node_name": "task_planner",
        "tracer": tracer,
    }

    try:
        user_prompt = render_prompt(
            "task_planner",
            issue_description=issue_description,
            issue_category=issue_analysis_raw.get("issue_category", "unknown"),
            extracted_symbols=json.dumps(issue_analysis_raw.get("extracted_symbols", []), ensure_ascii=False),
            search_terms=json.dumps(issue_analysis_raw.get("search_terms", []), ensure_ascii=False),
        )
        system_prompt = (
            "You are SpringFix's TaskPlanner. Build a short investigation "
            "plan and return a single InvestigationPlan JSON object."
        )
        if error_log:
            user_prompt = f"{user_prompt}\n\nError log (for context only):\n{error_log[:2000]}"

        plan = llm.invoke_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=InvestigationPlan,
            trace_context=trace_ctx,
        )
        return {"investigation_plan": plan.model_dump(), "warnings": []}
    except (ValidationError, Exception) as e:  # noqa: BLE001
        _LOGGER.warning("task_planner LLM call failed: %s", e)
        return {
            "investigation_plan": _FALLBACK_PLAN.model_dump(),
            "warnings": [f"task_planner LLM fallback: {type(e).__name__}: {str(e)[:200]}"],
        }
