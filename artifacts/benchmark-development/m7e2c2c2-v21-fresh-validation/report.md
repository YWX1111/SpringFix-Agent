# M7E-2C2C2 — Diagnosis V2.1 Fresh-Output Generalization Validation

## Outcome

Status: **NEEDS_RCA**. The single authorized fresh dev_semantic_v1 live run
completed normally on all six cases with valid bounded diagnosis evidence.
Repair Success remained **6/6**, but the fresh-output Diagnosis V2.1 score was
**3/6** (6/6 evaluated, insufficient artifact 0/6), below the required 6/6
generalization threshold. This is a real semantic generalization result, not
an evidence-capture or infrastructure failure.

No evaluator, metadata, prompt, Agent, diagnosis-generation, retrieval,
proposal, validator, PatchApplier, Maven, Repair predicate, evidence-capture,
sample, Gold, holdout, model, provider, or runtime setting was changed. No
second live run, semantic rerun, case exception, cherry-pick, or evaluator
tuning was performed. The milestone stops here for RCA.

## Frozen execution

- Starting commit / origin/main: 9ce8747f5d39412480cb34e0e365fde706f1ef3e
- Runtime: 0.15.1
- Split: dev_semantic_v1, sample size 6/6
- Fresh run id: 20260820T060935Z-fb5af9c3
- Mode/provider/model: live / openai_compatible / qwen3.7-plus
- Temperature: 0.0
- Timeout / retries / max output: 60s / 2 / 2000
- Exactly one fresh run; no Holdout Agent/Mock/Live execution

The raw run was frozen before scoring in fresh-live-artifact-hashes.json:
15/15 files and byte lengths verified, with zero post-scoring mismatches.
Replay was deterministic and made zero Agent or LLM calls.

## Joint results

| Metric | Result |
|---|---:|
| Repair Success | **6/6** |
| Diagnosis V1 | 1/6 |
| Diagnosis V2.0 | 1/6 |
| V2.0 evaluated / insufficient artifact | 6/6 / 0/6 |
| Diagnosis V2.1 | **3/6** |
| V2.1 evaluated / insufficient artifact | 6/6 / 0/6 |
| V2.1 mean semantic score | 0.9558 |

All six cases had diagnosis-evidence-v1.0, bounded and sanitized text,
truncated=false, evaluation_ready=true, and the two frozen V2 compatibility
keys. The evidence capture therefore did not suppress or distort the semantic
score.

## Per-case results

| Case | Repair | V1 | V2.0 | V2.1 | V2.1 issue |
|---|---:|---:|---:|---:|---|
| dev-s1-profile-config-source | PASS | FAIL | FAIL | FAIL | missing profile_gate_mismatch |
| dev-s2-code-property-override | PASS | FAIL | FAIL | PASS | — |
| dev-s3-storage-validation | PASS | FAIL | FAIL | PASS | — |
| dev-s4-conditional-notification | PASS | PASS | FAIL | FAIL | missing provider_condition_mismatch |
| dev-s5-cache-binding-key | PASS | FAIL | PASS | FAIL | contradiction incorrect_key_binds_successfully |
| dev-s6-local-precedence-conflict | PASS | FAIL | FAIL | PASS | — |

The three V2.1 misses are semantic output failures: two missing directional
relations and one contradiction. There is no insufficient-artifact case and no
provider/network outage.

## Frozen evaluator and control integrity

V2.0 and V2.1 remained byte-identical to the pre-live freeze:

- V2.0 evaluator: ba7306d02182c81a50b1ab3ec9ce8b59de572987edad8ccd2fcf34ded8d5a060
- V2.1 evaluator: 33e9fa4262ed14e4ef5e58bc4259b619839740e55234828b232a6e2bc3621403
- V2.1 metadata: 3ab66235ae1127290a90cf07bd40c1f48b25f1219959f9e897c19e83361404a7
- V2.1 manifest: ac7f37668961f47d61039a2150db686cc1c0d926681baa0655529b028473f37d
- V2.1 regression corpus: 11 confirmed positives, hash
  1e87d32941da83d4797df0c7bcd778e544b8bd1d8624ff54acfbaacae0048bbc

Pre-live controls passed: V2.0 17/17, V2.1 24/24, confirmed-FN
regressions 11/11, adversarial negatives 12/12. Post-run controls and hash
rechecks are recorded in summary.json after completion.

## Gates and safety

Preflight passed: semantic-dev integrity; semantic sample baseline/reference
fixes 6/6; holdout integrity; structural and sample validation; full pytest
532 passed, 1 skipped; Ruff; strict mypy (96 source files); and uv lock check.
The fresh report/replay projection contains no provider response, prompt,
hidden reasoning, full source dump, full Maven output, reference patch,
holdout answer material, secret, API key, or machine-absolute path.

## Decision

V2.1 is **not promoted** as the primary Semantic Dev metric from this
validation. Preserve the calibrated evaluator and regression corpus unchanged.
The result requires RCA before any separately authorized follow-up; do not
enter generation-contract improvement, and do not treat Diagnosis as a Repair
gate.

## Artifacts

- Machine-readable summary: summary.json
- Frozen fresh raw-artifact hashes: fresh-live-artifact-hashes.json
- Offline V1/V2.0/V2.1 replay: fresh-live-diagnosis-replay.json
- Frozen raw live run: live/20260820T060935Z-fb5af9c3/
