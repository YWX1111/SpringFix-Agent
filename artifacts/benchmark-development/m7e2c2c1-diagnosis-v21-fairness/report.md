# M7E-2C2C1 — Diagnosis V2.1 Fairness Calibration

Status: **PASS** (evaluator-only; validated on Semantic Dev v1). The frozen
Diagnosis V2.0 contract remains reproducible at 0/6. V2.1 is an independent
versioned evaluator and does not alter Agent, diagnosis generation, repair, or
historical reports.

## Frozen scope

- Starting commit: `408f15f26b930e3d63ef063814b0b5c3b52ac550`
- Runtime: `0.15.1`
- Frozen live source: `20260820T040110Z-20b0fcf2`
- Frozen Repair Success: 6/6; V1: 0/6; V2.0: 0/6, evaluated 6/6, insufficient artifact 0/6.
- No Agent execution, no LLM calls, no holdout Agent/Mock/Live execution.
- Frozen live artifact hash manifest was not changed; all 15/15 raw files remain byte-identical.

## V2.0 preservation and V2.1 contract

V2.0 evaluator, metadata, and manifest bytes are preserved exactly:

| Item | SHA-256 |
|---|---|
| `src/springfix_agent/benchmark/diagnosis_v2.py` | `ba7306d02182c81a50b1ab3ec9ce8b59de572987edad8ccd2fcf34ded8d5a060` |
| `benchmark/dev_semantic_diagnosis_v2.jsonl` | `7663a5ab72280bb60c368a793189434f845e833af7baa4fee516e32da97ef2d7` |
| `benchmark/dev_semantic_diagnosis_v2_manifest.json` | `bb7baee19383ad632d03846fc24ca7be941a9036acfe9a4119eec1ef64716007` |

V2.1 is `diagnosis-semantic-v2.1`, with independent metadata, manifest, and
replay output. It uses no case-ID conditionals in evaluator code and remains
post-output/evaluator-only.

## Calibration changes

1. Normalization converts Markdown punctuation and file/property punctuation to
   token separators, segments CamelCase (`StorageProperties`), and applies a
   finite allowlisted morphology table for plural and bounded relation
   inflections (`properties`, `overrides`, `overriding`, `takes`, `binding`,
   and similar forms). It is not an unrestricted stemmer.
2. Relations remain directional: left entity → relation → right entity/value/
   constraint. Matching is restricted to one clause and a bounded token window
   (24 tokens by default; 28–32 only for the explicitly longer calibrated
   variants).
3. Numeric variants require a bounded value span (8 tokens), reject an
   intervening numeric token, and therefore do not turn an unrelated `0` into
   an invalid-value relation. Valid values and reversed relations remain
   rejected.
4. Clause splitting continues to protect dotted filenames and Markdown while
   treating sentence punctuation, semicolons, and newlines as boundaries.

## Confirmed-false-negative regression corpus

The bounded 11-item corpus is in
`benchmark/dev_semantic_diagnosis_v2_1_regressions.jsonl`. Every item records
its component ID, bounded paraphrase, V2.0 result (`matched=false`), and V2.1
expected result (`matched=true`).

| Case | Component(s) | V2.0 | V2.1 |
|---|---|---:|---:|
| s1 | `active_profile`, `profile_gate_mismatch` | 0 | 2/2 |
| s2 | `code_source_overrides_configuration` | 0 | 1/1 |
| s3 | `binding_target`, `configured_capacity_violates_validation` | 0 | 2/2 |
| s4 | `provider_condition_mismatch` | 0 | 1/1 |
| s5 | `observed_default`, `configuration_key_binding_mismatch` | 0 | 2/2 |
| s6 | `invalid_retry_value`, `local_source_overrides_base`, `local_value_violates_validation` | 0 | 3/3 |
| **Total** | **11 confirmed paraphrases** | **0/11** | **11/11** |

The full frozen live replay passes all six cases with V2.1. Structural
conditions remain conjunctive and all six cases score 1.0.

## Controls

- Existing V2.0 controls: 17/17 PASS.
- V2.1 controls: 24 tests PASS.
- Confirmed paraphrase positives: 11/11.
- Existing positives: all retained and pass under V2.0; V2.1 live positives: 6/6.
- Expanded adversarial negatives: 12/12 rejected, covering pluralized and
  inflected reversed precedence, wrong CamelCase source, same- and
  different-clause unrelated numbers, missing override, valid value,
  correct binding, contradictory relation, punctuation stuffing, plural
  stuffing, and wrong source.
- No evaluator false positives were observed.

## Frozen replay

`frozen-live-v21-replay.json` reports:

- Diagnosis V1: 0/6
- Diagnosis V2.0: 0/6, evaluated 6/6, insufficient artifact 0/6
- Diagnosis V2.1: **6/6**, evaluated 6/6, insufficient artifact 0/6,
  mean semantic score 1.0
- Deterministic replay hash: `6f0c12079b391d8b6476bb021ce1054a0d034da223a7a42e97e15cd019ca7cdc`

Replay was run twice with identical bytes. V2.1 does not read patch diffs,
Maven results, Repair Success, reference fixes, hidden reasoning, prompts, or
provider responses.

## Metric decision

V2.1 is recommended as a **primary diagnosis-metric candidate**, validated only
on Semantic Dev v1. V1 remains the historical lexical/debug metric and V2.0
remains the frozen experimental metric. V2.1 is not added to the Repair Success
predicate and is not a Repair gate.

The generation-contract gap identified in M7E-2C2B remains intentionally
unchanged. This milestone stops after evaluator fairness calibration; it does
not enter generation-contract improvement.

## Gates and artifacts

Preflight and post-change gates all passed: semantic development integrity
(including V2.0/V2.1 schema/hash/isolation), semantic samples 6/6 and reference
fixes 6/6, holdout integrity, benchmark validation, V2.0 controls, V2.1
controls, full pytest (`532 passed, 1 skipped`), ruff, strict mypy, and
`uv lock --check`.

Artifacts:

- `artifacts/benchmark-development/m7e2c2c1-diagnosis-v21-fairness/report.md`
- `artifacts/benchmark-development/m7e2c2c1-diagnosis-v21-fairness/summary.json`
- `artifacts/benchmark-development/m7e2c2c1-diagnosis-v21-fairness/frozen-live-v21-replay.json`
- `src/springfix_agent/benchmark/diagnosis_v21.py`
- `benchmark/dev_semantic_diagnosis_v2_1.jsonl`
- `benchmark/dev_semantic_diagnosis_v2_1_manifest.json`
- `benchmark/dev_semantic_diagnosis_v2_1_regressions.jsonl`

Artifact safety audit: no secrets, API keys, machine-absolute paths, raw model
responses, prompt dumps, hidden reasoning, full source, full Maven output,
reference patch, or holdout answer material.

Commit/push/CI status is recorded in `summary.json` and the final handoff.
