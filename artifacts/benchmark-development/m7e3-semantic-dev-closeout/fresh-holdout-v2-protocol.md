# Fresh Holdout v2 Protocol (M7F pre-registration)

Status: **FROZEN PROTOCOL — NOT EXECUTED IN M7E-3**

This document is a registration for M7F-0. M7E-3 creates no new cases, does not run an Agent, and does not score a Holdout.

## Construction and blinding

1. Cases must be genuinely new and absent from `dev_semantic_v1` and all prior tuning material.
2. Prompt, evaluator, retrieval, proposal, validator, PatchApplier, sample, and Gold decisions must not be tuned from case content.
3. The case set and manifest are blinded until execution and the manifest is frozen before the Agent run.
4. Reference solutions and baseline failures are independently validated before execution.

## One-shot execution and scoring

1. Execute the Agent once per case; do not rerun a semantic failure.
2. Freeze artifacts before any scoring.
3. **Repair Success rate is the primary metric**, using the existing frozen predicate.
4. Capture bounded, sanitized, versioned, replayable `diagnosis-evidence-v1.0` for observability.
5. Report Diagnosis V2.2 only as a secondary observational metric. A V2.2 result cannot invalidate a successful Repair.
6. Secondary observations may include evidence availability, V2.2 score, failure taxonomy, patch safety, and target-test completion.
7. Preserve any pre-existing frozen Holdout threshold. If none exists, report the raw fraction and confidence interval only; do not invent a threshold after seeing results.

## Anti-tuning and invalid runs

After the Fresh Holdout v2 manifest is frozen, no Prompt, Agent, Retrieval, Proposal, Validator, PatchApplier, evaluator, sample, or Gold change is allowed until the one-shot evaluation is complete. Only a pre-declared infrastructure-defect invalid-run policy may interrupt execution; an invalid run is quarantined and never silently replaced or scored as a semantic failure.

No Holdout-based V2.3 tuning is allowed during final evaluation.

## M7F entry condition

M7F may begin only after the M7E freeze manifest, Git state, CI, runtime/config, Repair pipeline, Prompt set, Dev benchmark, evaluator versions, debt register, this protocol, and historical Holdout v1 are all frozen and verified. Fresh Holdout v2 construction and blind freeze belong to M7F-0.
