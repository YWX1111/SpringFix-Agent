"""root_cause_analyzer node: LLM-backed root-cause inference.

Inputs:  issue_description, issue_analysis, investigation_plan,
         project_tree_summary, retrieved_snippets, error_log
Outputs: root_cause_analysis, warnings

The node:
    1. Renders a structured prompt with the retrieval evidence.
    2. Calls the LLM for a RootCauseAnalysis.
    3. Applies a secondary business check: every evidence file must be
       present in ``retrieved_snippets`` and line ranges must fall
       within the snippet's real ``line_range``.
    4. Invalid references are stripped; if any candidate ends up with
       empty evidence, the candidate is dropped.
    5. If the model output still fails validation after repair, the
       node emits ``diagnosis_status="insufficient_evidence"`` with a
       summary explaining why.

The node never fails the whole task.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import ValidationError

from springfix_agent.graph.state import AgentState, RetrievedSnippet
from springfix_agent.llm.client import LLMClient, LLMTraceContext
from springfix_agent.llm.prompts import render_prompt
from springfix_agent.llm.schemas import (
    EvidenceReference,
    RootCauseAnalysis,
    RootCauseCandidate,
)
from springfix_agent.observability.tracer import Tracer

_LOGGER = logging.getLogger(__name__)

_MAX_SNIPPETS_IN_PROMPT = 8
_MAX_SNIPPET_CHARS = 2000

_INSUFFICIENT = RootCauseAnalysis(
    diagnosis_status="insufficient_evidence",
    summary="Not enough evidence was retrieved to propose a root cause.",
    candidates=[],
    missing_information=["Additional code context is required."],
)


def root_cause_analyzer(
    state: AgentState,
    *,
    llm: LLMClient,
    tracer: Tracer,
) -> dict[str, Any]:
    """Run RootCauseAnalyzer with secondary business validation."""
    task_id = state["task_id"]
    snippets: list[RetrievedSnippet] = list(state.get("retrieved_snippets", []) or [])
    issue_analysis_raw = state.get("issue_analysis", {}) or {}
    plan_raw = state.get("investigation_plan", {}) or {}

    trace_ctx: LLMTraceContext = {
        "task_id": task_id,
        "node_name": "root_cause_analyzer",
        "tracer": tracer,
    }

    snippet_index = {s["file"]: s for s in snippets}

    if not snippets:
        return {
            "root_cause_analysis": _INSUFFICIENT.model_dump(),
            "warnings": ["root_cause_analyzer: no snippets available"],
        }

    try:
        snippet_block = _render_snippets_block(snippets)
        user_prompt = render_prompt(
            "root_cause_analyzer",
            issue_description=state["issue_description"],
            issue_category=issue_analysis_raw.get("issue_category", "unknown"),
            symptoms=json.dumps(issue_analysis_raw.get("symptoms", []), ensure_ascii=False),
            exception_types=json.dumps(issue_analysis_raw.get("exception_types", []), ensure_ascii=False),
            investigation_plan=json.dumps(plan_raw, ensure_ascii=False),
            project_tree_summary=state.get("project_tree_summary", "")[:2000],
            retrieved_snippets=snippet_block,
        )
        system_prompt = (
            "You are SpringFix's RootCauseAnalyzer. Use only the provided "
            "retrieved snippets as evidence. Return a single "
            "RootCauseAnalysis JSON object."
        )
        analysis = llm.invoke_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=RootCauseAnalysis,
            trace_context=trace_ctx,
        )
        validated, dropped, rejections = _validate_evidence(analysis, snippet_index)
        warnings: list[str] = []
        if dropped:
            warnings.append(
                f"root_cause_analyzer dropped {dropped} invalid evidence "
                f"reference(s); see rejected_evidence in root_cause_analysis"
            )
        rejected_evidence = [
            {
                "candidate_index": r.get("candidate_index"),
                "evidence_index": r.get("evidence_index"),
                "rejection_reason": r.get("rejection_reason"),
                "referenced_file": r.get("referenced_file"),
                "referenced_line_range": r.get("referenced_line_range"),
            }
            for r in rejections
        ]
        rca_with_audit = validated.model_copy(
            update={"rejected_evidence": rejected_evidence}
        )
        return {
            "root_cause_analysis": rca_with_audit.model_dump(),
            "warnings": warnings,
        }
    except (ValidationError, Exception) as e:  # noqa: BLE001
        _LOGGER.warning("root_cause_analyzer LLM call failed: %s", e)
        return {
            "root_cause_analysis": _INSUFFICIENT.model_dump(),
            "warnings": [
                f"root_cause_analyzer LLM fallback: {type(e).__name__}: {str(e)[:200]}"
            ],
        }


def _render_snippets_block(snippets: list[RetrievedSnippet]) -> str:
    """Compose a compact text block of retrieval evidence for the prompt."""
    out: list[str] = []
    for s in snippets[:_MAX_SNIPPETS_IN_PROMPT]:
        content = s["content"]
        if len(content) > _MAX_SNIPPET_CHARS:
            content = content[:_MAX_SNIPPET_CHARS] + "..."
        start, end = s["line_range"]
        out.append(
            f"--- {s['file']} (lines {start}-{end}, score {s['score']:.2f}) ---\n{content}"
        )
    return "\n\n".join(out)


def _validate_evidence(
    analysis: RootCauseAnalysis,
    snippet_index: dict[str, RetrievedSnippet],
) -> tuple[RootCauseAnalysis, int, list[dict[str, object]]]:
    """Strip invalid evidence references; return (cleaned, dropped_count, rejections).

    Each rejection record carries:
        - candidate_index
        - evidence_index
        - rejection_reason
        - referenced_file
        - referenced_line_range
    """
    dropped_total = 0
    rejections: list[dict[str, object]] = []
    cleaned: list[RootCauseCandidate] = []

    for c_idx, candidate in enumerate(analysis.candidates[:3]):
        kept: list[EvidenceReference] = []
        for e_idx, ref in enumerate(candidate.evidence):
            snippet = snippet_index.get(ref.file)
            if snippet is None:
                dropped_total += 1
                rejections.append({
                    "candidate_index": c_idx,
                    "evidence_index": e_idx,
                    "rejection_reason": "file_not_in_retrieved_snippets",
                    "referenced_file": ref.file,
                    "referenced_line_range": [ref.start_line, ref.end_line],
                })
                continue
            start, end = snippet["line_range"]
            if ref.start_line > ref.end_line:
                dropped_total += 1
                rejections.append({
                    "candidate_index": c_idx,
                    "evidence_index": e_idx,
                    "rejection_reason": "start_line_greater_than_end_line",
                    "referenced_file": ref.file,
                    "referenced_line_range": [ref.start_line, ref.end_line],
                })
                continue
            if ref.start_line < start or ref.end_line > end:
                dropped_total += 1
                rejections.append({
                    "candidate_index": c_idx,
                    "evidence_index": e_idx,
                    "rejection_reason": "line_range_outside_snippet",
                    "referenced_file": ref.file,
                    "referenced_line_range": [ref.start_line, ref.end_line],
                    "snippet_line_range": [start, end],
                })
                continue
            kept.append(ref)
        if not kept:
            dropped_total += 1
            rejections.append({
                "candidate_index": c_idx,
                "evidence_index": -1,
                "rejection_reason": "candidate_no_valid_evidence",
                "referenced_file": "",
                "referenced_line_range": [],
            })
            continue
        cleaned.append(candidate.model_copy(update={"evidence": kept}))

    return analysis.model_copy(update={"candidates": cleaned}), dropped_total, rejections
