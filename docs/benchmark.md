# SpringFix-Agent Benchmark Design

## Purpose

The benchmark separates engineering validation from unseen generalization. It
measures whether the complete diagnosis-to-patch-to-verification pipeline can
repair a case under a fixed contract.

The primary metric is **Repair Success**. Diagnosis metrics are diagnostic
signals and do not change Repair Success.

## M7E Dev Benchmark

M7E closed the current Semantic Dev evaluation with **Repair Success 6/6**.
This is recorded as stable performance on the current six-case Dev set, not as
a universal Spring bug repair rate.

Diagnosis V2.2 is frozen as `SECONDARY / OBSERVATIONAL`. Its Fresh-2 failures
were reviewed as evaluator false negatives rather than true semantic omissions;
the diagnosis metric is not a release gate.

## M7F-0 Fresh Holdout v2 freeze

Fresh Holdout v2 contains eight fresh cases across eight semantic families,
including compositional/generalization cases. Before any live Agent execution,
M7F-0 checked:

- baseline reproduction and repeatability;
- reference validation and repeatability;
- sample restoration;
- Agent projection isolation;
- novelty and test-leak audits;
- manifest loadability and unique case IDs;
- Maven target resolvability;
- invalid-run policy; and
- anti-tuning lock.

The freeze was usable for M7F-1 and its pre-existing M7E provenance hash
mismatch was preserved as an explicit finding. No frozen benchmark asset was
silently changed to remove that finding.

## Gold isolation

The live Agent receives only an Agent-facing projection containing issue/context
information and permitted repository evidence. Repair Gold, expected fixes, and
reference patches are sealed outside that projection. They are used only by
authorized offline validation/scoring paths and are not reproduced in project
documentation.

## One-shot protocol

Fresh Holdout v2 permits exactly one live Agent execution across all eight
cases. The run performs:

1. load Agent projection;
2. diagnose the case;
3. retrieve and validate evidence;
4. generate a repair proposal;
5. validate and apply the patch in an isolated workspace;
6. run fixed Maven/Surefire verification; and
7. freeze bounded artifacts before post-run analysis.

Whole-run retries, failed-case retries, selective reruns, prompt tuning, model
switching, and production changes are prohibited. Provider outage, runner
crash, or artifact corruption must be quarantined under the frozen invalid-run
policy rather than hidden by a rerun.

## Observed Fresh Holdout v2 result

The completed run used one live Agent execution and produced:

| Case | Result | Stage/category when failed |
|---|---|---|
| `h01` | FAIL | proposal / `proposal_validation_rejected` |
| `h02` | FAIL | proposal / `proposal_validation_rejected` |
| `h03` | PASS | — |
| `h04` | FAIL | verification / `test_failure` |
| `h05` | PASS | — |
| `h06` | PASS | — |
| `h07` | PASS | — |
| `h08` | PASS | — |

**Repair Success: 5/8.** The result is valid and completed, not an invalid-run
quarantine. Post-run tests, static checks, integrity checks, benchmark
validation, and CI passed.

## Artifact contract

Evaluation artifacts are bounded, sanitized, and hash-audited. They contain no
secrets, raw model output, hidden reasoning, or Fresh Holdout solution content.
Failure records retain only the minimum stage/category/reference information
needed for safe reporting.
