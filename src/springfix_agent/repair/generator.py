"""LLM-backed Patch Proposal generation and service orchestration."""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from springfix_agent.llm.client import LLMClient, LLMTraceContext
from springfix_agent.observability.tracer import Tracer
from springfix_agent.repair.models import (
    EvidenceSnippet,
    PatchProposal,
    PatchValidationResult,
)
from springfix_agent.repair.validator import (
    collect_validated_evidence,
    validate_patch_proposal,
)


class _NullTracer:
    """Fallback trace sink for direct unit-level Generator usage."""

    def record_tool_call(self, task_id: str, call: Any) -> None:
        del task_id, call

    def record_node_timing(self, task_id: str, timing: Any) -> None:
        del task_id, timing

    def record_llm_call(self, task_id: str, call: Any) -> None:
        del task_id, call


def _render_patch_prompt(root_cause: dict[str, object], evidence: list[EvidenceSnippet]) -> str:
    with resources.files("springfix_agent.repair.prompts").joinpath("patch_proposal.md").open(
        "r", encoding="utf-8"
    ) as prompt_file:
        template = prompt_file.read()
    evidence_text = "\n\n".join(
        f"--- {item.file} (lines {item.start_line}-{item.end_line}) ---\n"
        f"{item.content}\nEvidence note: {item.explanation[:300]}"
        for item in evidence[:12]
    )
    return template.replace(
        "{{root_cause_analysis}}",
        json.dumps(root_cause, ensure_ascii=False, sort_keys=True),
    ).replace("{{evidence_snippets}}", evidence_text)


def _insufficient(summary: str) -> PatchProposal:
    return PatchProposal(
        status="insufficient_evidence",
        summary=summary,
        root_cause_reference="none",
        edits=[],
        verification_steps=[],
        risks=["No patch is proposed without validated evidence."],
        assumptions=[],
    )


@dataclass(frozen=True)
class PatchGenerationResult:
    """Internal result containing the generated proposal and validation audit."""

    validation: PatchValidationResult
    evidence: tuple[EvidenceSnippet, ...]
    generation_error: str | None
    patch_llm_calls: int
    patch_generation_duration_ms: int = 0
    patch_validation_duration_ms: int = 0

    @property
    def proposal(self) -> PatchProposal:
        """Return the sanitized proposal."""
        return self.validation.proposal


class PatchProposalGenerator:
    """Generate one structured proposal from validated diagnostic context."""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def generate(
        self,
        *,
        root_cause_analysis: dict[str, object] | Any,
        validated_evidence: list[EvidenceSnippet] | tuple[EvidenceSnippet, ...],
        task_id: str = "patch-proposal",
        tracer: Tracer | None = None,
    ) -> PatchProposal:
        """Call the Patch LLM once, unless the evidence set is empty."""
        evidence = list(validated_evidence)
        if not evidence:
            return _insufficient("Validated evidence is required before proposing a patch.")
        if hasattr(root_cause_analysis, "model_dump"):
            root_cause = dict(root_cause_analysis.model_dump(exclude={"rejected_evidence"}))
        elif isinstance(root_cause_analysis, dict):
            root_cause = dict(root_cause_analysis)
            root_cause.pop("rejected_evidence", None)
        else:
            return _insufficient("The root-cause analysis is not a valid structured result.")
        context_tracer: Tracer = tracer if tracer is not None else _NullTracer()
        trace_context: LLMTraceContext = {
            "task_id": task_id,
            "node_name": "patch_proposal",
            "tracer": context_tracer,
        }
        prompt = _render_patch_prompt(root_cause, evidence)
        try:
            result = self._llm.invoke_structured(
                system_prompt=(
                    "You are SpringFix's Patch Proposal Generator. "
                    "Return a PatchProposal JSON object. You propose only; "
                    "you never apply or verify a patch."
                ),
                user_prompt=prompt,
                response_model=PatchProposal,
                trace_context=trace_context,
            )
        except Exception:  # noqa: BLE001
            return _insufficient("Patch proposal generation failed; no patch was proposed.")
        return result


class PatchProposalService:
    """Build validated evidence, generate one proposal, then validate it."""

    def __init__(self, llm: LLMClient) -> None:
        self._generator = PatchProposalGenerator(llm)

    def propose(
        self,
        *,
        repository_root: Path,
        root_cause_analysis: dict[str, object] | Any,
        retrieved_snippets: Sequence[dict[str, object] | EvidenceSnippet],
        task_id: str = "patch-proposal",
        tracer: Tracer | None = None,
    ) -> PatchGenerationResult:
        """Generate and deterministically validate a proposal without mutation."""
        evidence = collect_validated_evidence(
            repository_root,
            root_cause_analysis,
            retrieved_snippets,
        )
        generation_started = time.monotonic()
        proposal = self._generator.generate(
            root_cause_analysis=root_cause_analysis,
            validated_evidence=evidence,
            task_id=task_id,
            tracer=tracer,
        )
        generation_duration_ms = max(0, int((time.monotonic() - generation_started) * 1000))
        validation_started = time.monotonic()
        validation = validate_patch_proposal(proposal, repository_root, evidence)
        validation_duration_ms = max(0, int((time.monotonic() - validation_started) * 1000))
        patch_calls = 1 if evidence else 0
        return PatchGenerationResult(
            validation=validation,
            evidence=tuple(evidence),
            generation_error=None if proposal.status != "insufficient_evidence" else proposal.summary,
            patch_llm_calls=patch_calls,
            patch_generation_duration_ms=generation_duration_ms,
            patch_validation_duration_ms=validation_duration_ms,
        )

    generate = propose
