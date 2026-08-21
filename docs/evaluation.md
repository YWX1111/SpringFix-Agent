# SpringFix-Agent Evaluation and Release Decision

## Final decision

**Release decision: `NO-GO_FOR_UNCONDITIONAL_PRODUCTION_RELEASE`**

**Status: `HOLD_FOR_AUTHORIZED_FOLLOW_UP`**

This is an evidence-based release decision, not a claim that the project is
unusable. The current evidence supports an engineering prototype and a
controlled demonstration, but not autonomous production repair.

## Milestone record

| Milestone | Result |
|---|---|
| M7E | `PASS` |
| M7E-3A | `PASS` |
| M7F-0 | `PASS`; freeze/readiness completed; pre-existing provenance mismatch documented |
| M7F-1 | `COMPLETED`; one-shot Fresh Holdout v2 run |
| M7F-1A | `PASS_RCA_ONLY` |
| M7F-2 | `FINAL_ANALYSIS_ONLY` |

## Primary results

| Evaluation | Repair Success | Interpretation |
|---|---:|---|
| M7E Dev | `6/6` | Stable on the current Dev set; not universal generalization |
| Fresh Holdout v2 | `5/8` | Unseen one-shot result; three cases failed |

Fresh Holdout v2 case results:

- PASS: `h03`, `h05`, `h06`, `h07`, `h08`
- FAIL: `h01`, `h02`, `h04`

## Failure interpretation

### h01 and h02

Both failures occurred at the proposal-validation boundary. Their bounded
diagnosis artifacts show complete diagnosis and no demonstrated upstream
evidence rejection. The frozen failure records do not retain proposal JSON,
generation audit, target selection, patch scope, or rejected-edit reasons.

Therefore the lower-level distinction between Agent proposal generation and a
proposal/validator contract mismatch is unresolved. The cases remain counted
as failures; they are not reclassified as infrastructure or invalid-run cases.

### h04

h04 reached verification after patch application. Maven reached the target-test
path and the bounded category is `test_failure`. This is a confirmed functional
repair failure downstream of proposal validation and patch application.

### Aggregate RCA

`MIXED_REPAIR_PIPELINE_LIMITATION_AND_AGENT_VERIFICATION_FAILURE`

No benchmark defect or artifact corruption evidence was found. The historic
PatchApplier issue was not reproduced. M7E diagnosis-evaluator limitations are
separate from Repair Success, and Diagnosis V2.2 remained observational-only.

## Quality gates

The M7F-1 result was followed by passing quality gates:

- `pytest`: 574 passed, 1 skipped;
- Ruff: PASS;
- strict MyPy: PASS for 97 source files;
- `uv lock --check`: PASS;
- `semantic_dev_integrity`: PASS;
- `holdout_integrity`: PASS;
- benchmark validation: legacy 3/3, Holdout 7/7, total 10/10;
- Fresh Holdout v2 manifest: no tracked diff; and
- CI: PASS.

The stored freeze-manifest hash mismatch is pre-existing and documented. It
does not invalidate the completed run, but it remains a provenance limitation
for future maintenance.

## What this result does and does not claim

It does claim that the frozen one-shot pipeline repaired five of eight unseen
cases under the recorded contract. It does not claim production accuracy,
universal Spring bug coverage, statistical significance, or safe autonomous
deployment.

It does claim that the evaluation was completed without a rerun or silent
tuning. It does not claim that h01/h02 can be attributed more narrowly than the
retained proposal boundary.

## Follow-up boundary

Any repair, proposal-observability change, validation-feedback change,
iterative-loop experiment, or new benchmark run requires a separately
authorized phase. No such work is performed by this documentation set.
