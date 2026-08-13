"""Repair proposal generation, isolated application, and M5C verification.

M5A proposes and validates. M5B applies only to a disposable repository copy.
M5C runs one fixed Maven target test in that patched copy and never invokes a
live LLM or accepts an arbitrary command.
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
from springfix_agent.repair.e2e_models import (
    EndToEndAggregateMetrics,
    EndToEndCaseResult,
    EndToEndRunResult,
)
from springfix_agent.repair.generator import (
    PatchGenerationResult,
    PatchProposalGenerator,
    PatchProposalService,
)
from springfix_agent.repair.maven_verifier import MavenRepairVerifier
from springfix_agent.repair.models import (
    EvidenceSnippet,
    JavaImportCheckResult,
    PatchEdit,
    PatchProposal,
    PatchValidationResult,
    RejectedPatchEdit,
)
from springfix_agent.repair.observability import ProposalGenerationAudit
from springfix_agent.repair.validator import (
    PatchProposalValidator,
    collect_validated_evidence,
    validate_patch_proposal,
)
from springfix_agent.repair.verification_models import (
    BaselineVerificationResult,
    MavenFailureClassification,
    MavenTestResult,
    RepairAggregateMetrics,
    RepairCaseMetrics,
    RepairVerificationResult,
    RepairVerificationRunResult,
)
from springfix_agent.repair.workspace import (
    IsolatedPatchWorkspace,
    compute_repository_manifest,
    compute_sha256_manifest,
    create_isolated_patch_workspace,
)

__all__ = [
    "EvidenceSnippet",
    "JavaImportCheckResult",
    "AppliedEdit",
    "IsolatedPatchWorkspace",
    "PatchEdit",
    "PatchGenerationResult",
    "PatchProposal",
    "PatchProposalGenerator",
    "PatchProposalService",
    "PatchProposalValidator",
    "PatchApplier",
    "MavenRepairVerifier",
    "ProposalGenerationAudit",
    "PatchApplicationAggregateMetrics",
    "PatchApplicationCaseMetrics",
    "PatchApplicationResult",
    "PatchApplicationRunResult",
    "PatchValidationResult",
    "RejectedApplicationEdit",
    "RejectedPatchEdit",
    "BaselineVerificationResult",
    "MavenTestResult",
    "MavenFailureClassification",
    "RepairAggregateMetrics",
    "RepairCaseMetrics",
    "RepairVerificationResult",
    "RepairVerificationRunResult",
    "collect_validated_evidence",
    "compute_sha256_manifest",
    "compute_repository_manifest",
    "create_isolated_patch_workspace",
    "validate_patch_proposal",
    "EndToEndAggregateMetrics",
    "EndToEndCaseResult",
    "EndToEndRunResult",
]
