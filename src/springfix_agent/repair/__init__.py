"""Repair proposal generation and deterministic validation.

M5A deliberately stops at a validated, human-reviewable proposal.  Nothing
in this package writes repository files or executes a proposed change.
"""

from springfix_agent.repair.generator import (
    PatchGenerationResult,
    PatchProposalGenerator,
    PatchProposalService,
)
from springfix_agent.repair.models import (
    EvidenceSnippet,
    PatchEdit,
    PatchProposal,
    PatchValidationResult,
    RejectedPatchEdit,
)
from springfix_agent.repair.validator import (
    PatchProposalValidator,
    collect_validated_evidence,
    validate_patch_proposal,
)

__all__ = [
    "EvidenceSnippet",
    "PatchEdit",
    "PatchGenerationResult",
    "PatchProposal",
    "PatchProposalGenerator",
    "PatchProposalService",
    "PatchProposalValidator",
    "PatchValidationResult",
    "RejectedPatchEdit",
    "collect_validated_evidence",
    "validate_patch_proposal",
]
