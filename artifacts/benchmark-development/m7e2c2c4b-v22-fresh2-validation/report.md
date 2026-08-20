# M7E-2C2C4B — Diagnosis V2.2 Fresh-2 Generalization Validation

## Decision

**M7E-2C2C4B = NEEDS_RCA.** The one authorized Fresh-2 live run completed all six cases with valid bounded diagnosis evidence, but frozen Diagnosis V2.2 scored **3/6**. Because `cases_evaluated=6` and `cases_insufficient_artifact=0`, this is a real semantic generalization failure, not an evidence-capture failure. No rerun, tuning, evaluator change, prompt change, Agent change, or Repair change was performed.

Repair remained **6/6**, so no repair regression was observed.

## Frozen run

| Field | Value |
|---|---|
| Starting commit / origin | `2ad03aee7d54ab40e543802b1dbc2eb437ef9c8b` |
| Runtime | `0.15.1` |
| Split / mode | `dev_semantic_v1` / `live` |
| Run ID | `20260820T075619Z-3bb64f39` |
| Provider / model | `openai_compatible` / `qwen3.7-plus` |
| Temperature | `0.0` |
| Timeout / retries / output | `60s` / `2` / `2000` |
| Evidence schema | `diagnosis-evidence-v1.0` |
| Authorized live runs | 1 (no rerun) |

The exact runner used the existing `EndToEndRepairBenchmarkRunner` with the frozen Dev manifest and Repair Gold manifest, writing only under this milestone's artifact directory.

## Live and Repair outcome

| Measure | Result |
|---|---:|
| Cases completed | 6/6 |
| Evidence-ready | 6/6 |
| Truncated evidence | 0/6 |
| Insufficient artifact | 0/6 |
| Repair success | **6/6** |

| Case | Repair |
|---|---|
| `dev-s1-profile-config-source` | PASS |
| `dev-s2-code-property-override` | PASS |
| `dev-s3-storage-validation` | PASS |
| `dev-s4-conditional-notification` | PASS |
| `dev-s5-cache-binding-key` | PASS |
| `dev-s6-local-precedence-conflict` | PASS |

## Frozen diagnosis replay

The replay made zero new LLM calls and consumed the frozen top-level compatibility projection. V1, V2.0, V2.1, and V2.2 were scored independently.

| Evaluator | Passed | Evaluated | Insufficient | Mean score |
|---|---:|---:|---:|---:|
| V1 | 0/6 | 6 | n/a | keyword coverage only |
| V2.0 | 0/6 | 6 | 0 | 0.8580 |
| V2.1 | 3/6 | 6 | 0 | 0.9453 |
| V2.2 | **3/6** | 6 | 0 | 0.9453 |

| Case | V1 coverage | V2.0 | V2.1 | V2.2 | V2.2 failure reason |
|---|---:|---:|---:|---:|---|
| `dev-s1-profile-config-source` | 0.6000 | FAIL (0.8333) | FAIL (0.9167) | FAIL (0.9167) | missing `profile_gate_mismatch` |
| `dev-s2-code-property-override` | 0.4000 | FAIL (0.9091) | PASS (1.0000) | PASS (1.0000) | — |
| `dev-s3-storage-validation` | 0.5000 | FAIL (0.8182) | PASS (1.0000) | PASS (1.0000) | — |
| `dev-s4-conditional-notification` | 0.6000 | FAIL (0.9091) | PASS (1.0000) | PASS (1.0000) | — |
| `dev-s5-cache-binding-key` | 0.3333 | FAIL (0.9091) | FAIL (0.9091) | FAIL (0.9091) | missing `observed_default` |
| `dev-s6-local-precedence-conflict` | 0.2000 | FAIL (0.7692) | FAIL (0.8462) | FAIL (0.8462) | missing `local_source_overrides_base`; missing `local_value_violates_validation` |

The failures are semantic omissions despite complete, sanitized evidence. They are not caused by V2.2 artifact insufficiency or by Repair execution.

## Integrity and safety

- Preflight passed: semantic Dev integrity; Dev samples baseline/reference `6/6`; Holdout integrity; structural benchmark validation; Legacy/Holdout samples `3/3`, `7/7`; V2.0 `17/17`; V2.1 `24/24`; V2.2 `29/29`.
- V2.2 controls include confirmed regressions `15/15` and adversarial negatives `12/12` rejected.
- Post-run full test suite: **561 passed, 1 skipped**.
- The 15 raw run files were hashed before replay; post-replay verification found zero mismatches.
- V2.0, V2.1, V2.2 evaluator files, V2.2 metadata, manifest, and regression corpus hashes remained unchanged.
- Artifact audit contains only bounded sanitized evidence and aggregate/structural metrics; no credentials, raw provider response, prompt, reasoning transcript, full build log, machine absolute path, reference patch, or Holdout material is persisted.
- Holdout was not executed or modified. No tuning or next milestone was entered.

## Stop condition

Per the Fresh-2 contract, the result is `NEEDS_RCA`; do not promote V2.2 as the primary metric and do not enter M7E-3/M7F or a Diagnosis Repair/generation-contract improvement gate from this task. The next action is a separately authorized RCA for the three failing Fresh-2 cases.

## Artifacts

- [bounded summary](summary.json)
- [pre-live freeze](pre-live-freeze.json)
- [frozen live artifact hashes](fresh2-live-artifact-hashes.json)
- [joint V1/V2.0/V2.1/V2.2 replay](fresh2-live-diagnosis-replay.json)
- [raw live summary](live/20260820T075619Z-3bb64f39/summary.json)
- [raw live report](live/20260820T075619Z-3bb64f39/report.md)
