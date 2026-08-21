# M7F-1 Fresh Holdout v2 One-shot Evaluation

- status: `COMPLETED`
- starting commit: `409e1f8621fa3077c1565655a4b7d358467101f2`
- ending commit: `409e1f8621fa3077c1565655a4b7d358467101f2`
- runtime: `0.15.1`
- Fresh Holdout version: `fresh_holdout_v2`
- case count: `8`
- live Agent executions: `1` (one benchmark run; eight case executions)
- LLM calls: `32`
- Repair Success: `5/8`
- Diagnosis V2.2: observational-only; not used to invalidate Repair Success.

## Per-case results

| Case | Result | Failure stage | Failure category |
|---|---|---|---|
| `fresh-v2-h01` | `FAIL` | `proposal` | `proposal_validation_rejected` |
| `fresh-v2-h02` | `FAIL` | `proposal` | `proposal_validation_rejected` |
| `fresh-v2-h03` | `PASS` | `none` | `none` |
| `fresh-v2-h04` | `FAIL` | `verification` | `test_failure` |
| `fresh-v2-h05` | `PASS` | `none` | `none` |
| `fresh-v2-h06` | `PASS` | `none` | `none` |
| `fresh-v2-h07` | `PASS` | `none` | `none` |
| `fresh-v2-h08` | `PASS` | `none` | `none` |

## Artifact safety

The frozen live artifacts contain only bounded, sanitized Agent-facing results. They contain no secret, raw model output, hidden reasoning, Fresh v2 Gold, or reference patch.

Quality-gate results are recorded separately after the live artifact freeze.

## Quality gates

| Gate | Result |
|---|---|
| pytest | PASS — 574 passed, 1 skipped |
| Ruff | PASS |
| MyPy strict | PASS — 97 source files |
| uv lock --check | PASS |
| semantic_dev_integrity | PASS |
| holdout_integrity | PASS |
| benchmark validation | PASS — legacy 3/3, Holdout 7/7, total 10/10 |
| Fresh Holdout v2 manifest unchanged | PASS — no tracked diff |

The stored freeze-manifest file hashes show a pre-existing checkout mismatch; the frozen benchmark files were not modified during this run.
