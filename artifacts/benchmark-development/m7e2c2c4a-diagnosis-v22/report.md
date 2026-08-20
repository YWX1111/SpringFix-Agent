# M7E-2C2C4A — Diagnosis V2.2 Evaluator Correction

Status: **PASS**

This milestone is evaluator-only. It does not run the Agent, call an LLM, modify prompts or diagnosis generation, alter evidence capture, or enter Diagnosis into Repair Success.

## Frozen boundary

- Starting commit: `8417ec28ea4e89f1191ec21d842d649308c3397f`
- Runtime: `0.15.1`
- Calibration replay source: `20260820T040110Z-20b0fcf2`
- Fresh-1 replay source: `20260820T060935Z-fb5af9c3`
- Frozen V2.0 evaluator SHA-256: `ba7306d02182c81a50b1ab3ec9ce8b59de572987edad8ccd2fcf34ded8d5a060`
- Frozen V2.1 evaluator SHA-256: `33e9fa4262ed14e4ef5e58bc4259b619839740e55234828b232a6e2bc3621403`
- Frozen V2.1 metadata SHA-256: `3ab66235ae1127290a90cf07bd40c1f48b25f1219959f9e897c19e83361404a7`
- Frozen V2.1 manifest SHA-256: `ac7f37668961f47d61039a2150db686cc1c0d926681baa0655529b028473f37d`

All frozen V1, V2.0, and V2.1 files are byte-preserved.

## Independent V2.2 contract

New files only:

- `src/springfix_agent/benchmark/diagnosis_v22.py`
- `benchmark/dev_semantic_diagnosis_v2_2.jsonl`
- `benchmark/dev_semantic_diagnosis_v2_2_manifest.json`
- `benchmark/dev_semantic_diagnosis_v2_2_regressions.jsonl`
- `scripts/replay_diagnosis_v22.py`
- `tests/unit/benchmark/test_diagnosis_v22.py`

V2.2 preserves directionality, conjunctive required dimensions, contradiction gating, bounded token windows, deterministic replay, and Agent projection isolation.

## Corrections

### S1 — `profile_gate_mismatch`

Added finite relation variants for the confirmed family:

- `restricts its activation to staging`
- `activation is restricted to staging`
- `configured only for staging`
- `dev-active file is skipped because ... staging`

The matcher still requires a profile-specific source/activation anchor, a staging target, and active-dev context. A file targeting `dev` while `dev` is active, an active staging profile, or a skipped base configuration does not satisfy the relation.

### S4 — `provider_condition_mismatch`

Added bounded configured-provider versus required-condition variants for:

- sender requires webhook
- sender enabled only for webhook
- sender condition expects webhook
- sender is conditionally disabled under email
- conditional registration only when webhook is selected

The configured value remains the left-side condition. `provider=webhook` with `sender requires webhook`, and `sender requires email` with `provider=email`, are rejected as mismatches.

### S5 — `incorrect_key_binds_successfully`

Forbidden positive relation matching is now polarity-aware. A positive relation is suppressed only when the relation span has a bounded negation or non-assertion cue, including `does not`, `never`, `cannot`, and `fails to`. This preserves the required negative relation:

`region-ttl does not match ttlByRegion` → required relation PASS, forbidden positive relation NO HIT.

Forbidden contradiction matching is restricted to diagnostic assertion fields (`root_cause_summary`, candidate title, candidate description). `recommended_fix` remains available to required concept/relation coverage, but instructions such as “rename/change X to match Y” cannot be treated as the current-state contradiction. Counterfactual, future-state, and corrected-key contexts are also rejected by bounded cues and entity direction.

## Regression and adversarial controls

- Confirmed V2.1 regressions preserved: `11`
- New confirmed RCA regressions: `4`
- V2.2 confirmed regression corpus: `15`
- V2.2 positive controls: `15/15`
- V2.2 adversarial negatives: `12/12 rejected`
- V2.2 control test suite: `29/29 PASS`
- V2.1 controls remain: `24/24 PASS`
- V2.0 controls remain: `17/17 PASS`

## Frozen replays

| Source | V1 | V2.0 | V2.1 | V2.2 | V2.2 evaluated | insufficient artifact | mean V2.2 score |
|---|---:|---:|---:|---:|---:|---:|---:|
| Calibration `20260820T040110Z-20b0fcf2` | 0/6 | 0/6 | 6/6 | **6/6** | 6 | 0 | 1.0000 |
| Fresh-1 `20260820T060935Z-fb5af9c3` | 1/6 | 1/6 | 3/6 | **6/6** | 6 | 0 | 1.0000 |

Repair remains independently `6/6`; no Repair predicate or pipeline code was changed.

## Gates and safety

Passed:

- semantic development integrity
- semantic sample verification (`6/6` baseline, `6/6` reference fixes)
- holdout integrity
- legacy/holdout benchmark validation
- full pytest (`561 passed, 1 skipped`)
- Ruff
- mypy strict
- `uv lock --check`

The artifacts contain only bounded diagnosis excerpts, normalized finite matcher inputs, aggregates, and hashes. They contain no raw LLM response, prompt, hidden reasoning, full source dump, Maven dump, reference patch, Holdout material, secrets, or machine paths.

## Decision

M7E-2C2C4A is **PASS**. V2.2 is a primary-metric candidate only; it is not declared generalized until the separate Fresh-2 validation milestone. Prompt or generation-contract changes remain deferred. This task stops here; no Fresh-2 validation is entered.
