"""Repair proposal generation, validation, and isolated patch application.

M5A proposes and validates.  M5B applies only to a disposable repository copy;
it never writes the source repository or executes Maven.
"""

from springfix_agent.repair.application_models import (
    AppliedEdit,
    PatchApplicationAggregateMetrics,
    PatchApplicationCaseMetrics,
    PatchApplicationResult,
    PatchApplicationRunResult,
    RejectedApplicationEdit,
)
from springfix_agent.repair.applier import PatchApplier
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
from springfix_agent.repair.workspace import (
    IsolatedPatchWorkspace,
    compute_sha256_manifest,
    create_isolated_patch_workspace,
)

__all__ = [
    "EvidenceSnippet",
    "AppliedEdit",
    "IsolatedPatchWorkspace",
    "PatchEdit",
    "PatchGenerationResult",
    "PatchProposal",
    "PatchProposalGenerator",
    "PatchProposalService",
    "PatchProposalValidator",
    "PatchApplier",
    "PatchApplicationAggregateMetrics",
    "PatchApplicationCaseMetrics",
    "PatchApplicationResult",
    "PatchApplicationRunResult",
    "PatchValidationResult",
    "RejectedApplicationEdit",
    "RejectedPatchEdit",
    "collect_validated_evidence",
    "compute_sha256_manifest",
    "create_isolated_patch_workspace",
    "validate_patch_proposal",
]
