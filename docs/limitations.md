# SpringFix-Agent Limitations and Future Work

## Current limitations

### Not production autonomous repair yet

Fresh Holdout v2 achieved Repair Success `5/8` in one valid one-shot run. This
is useful engineering evidence, but three failures remain and the result does
not justify unconditional production release.

### Proposal observability debt

h01 and h02 stopped at `proposal_validation_rejected`. Their safe failure
artifacts intentionally omit raw proposal content and detailed rejection
reasons. This protects secrets and hidden reasoning, but it limits RCA below
the proposal boundary: Agent output and validator-contract causes cannot always
be separated after the run.

### Verification feedback loop limitation

h04 reached Maven verification and failed its target test. The current workflow
is single-shot: it records the failure and stops. It does not automatically
interpret the failure, generate a second proposal, or retry the case.

### Generalization boundary

M7E Dev performance is `6/6` on the current six-case set. Fresh Holdout v2 is
the stronger unseen evidence and is `5/8`. Neither sample is large enough to
estimate production-scale accuracy or statistical significance.

### Diagnosis metric boundary

Diagnosis V2.2 is a bounded rule-based diagnostic evaluator with limited
paraphrase generalization. It is secondary and observational only; it cannot
invalidate a successful repair or compensate for a failed repair.

### Verification and sandbox boundary

Maven execution is restricted to a disposable workspace with a fixed target
test, restricted environment, timeout, and Surefire parsing. This is not a
complete OS/container/network sandbox and does not provide supply-chain
isolation.

### No product UI

The repository exposes API/CLI-oriented workflows rather than a finished
product interface. No screenshot is included because there is no UI to show;
future demonstrations should use real interface captures or terminal/API
examples, never fabricated screenshots.

## Future work

Future work must be separately authorized and measured against the frozen
baseline:

1. **Proposal audit improvement:** retain more bounded, non-sensitive stage
   metadata so proposal failures can be attributed without storing raw model
   output or hidden reasoning.
2. **Better validation feedback:** expose deterministic rejection categories and
   actionable summaries at the artifact boundary.
3. **Iterative repair loop:** evaluate bounded retry and verification-feedback
   policies with explicit budgets, stop conditions, and no silent reruns.
4. **Human-in-the-loop approval:** require review before applying a patch to a
   user repository, especially when verification is incomplete or ambiguous.
5. **Release-quality evaluation:** use a separately frozen, independently
   reviewed benchmark and a pre-declared acceptance threshold before making a
   future production release decision.

## Non-goals of this document

This document does not change the Agent, Prompt, Runtime, Model, Retrieval,
Proposal, Validator, PatchApplier, Maven verifier, evaluator, Benchmark,
Holdout, Gold, or reference patches. It does not authorize a benchmark rerun
or an LLM call.
