# M7E-2C2C4C — Diagnosis V2.2 Fresh-2 Generalization Failure RCA

## Decision

**M7E-2C2C4C = PASS_RCA_ONLY.** This is a read-only RCA. No V2.2 modification, V2.3 implementation, Prompt change, Agent change, diagnosis-generation change, Agent rerun, runtime LLM call, Repair change, or Holdout evaluation was performed.

The three Fresh-2 semantic failures are evaluator false negatives against complete bounded evidence. No true semantic omission, implicit-only diagnosis, artifact ambiguity, or matcher implementation bug was found.

## Frozen input and result

| Field | Value |
|---|---|
| Starting commit | `a7f116fbb112f417c8ac81190ea807b8db24f698` |
| Runtime | `0.15.1` |
| Fresh-2 run | `20260820T075619Z-3bb64f39` |
| Configuration | live / dev_semantic_v1 / openai_compatible / qwen3.7-plus |
| Temperature / timeout / retries / output | `0.0` / `60s` / `2` / `2000` |
| Fresh-2 executions | exactly 1 |
| Agent reruns / LLM calls in RCA | 0 / 0 |
| Repair Success | 6/6 |
| V1 | 0/6 |
| V2.0 | 0/6, mean 0.8580 |
| V2.1 | 3/6, mean 0.9453 |
| V2.2 | 3/6 evaluated, insufficient artifact 0, mean 0.9453 |

The source run had six valid `diagnosis-evidence-v1.0` captures. Its 15 raw artifact files were frozen before scoring and rechecked with zero hash mismatches. Only bounded `root_cause_summary`, candidate title, description, and recommended fix fields were used.

## Three-output comparison

| Case | Calibration V2.2 | Fresh-1 V2.2 | Fresh-2 V2.2 | Fresh-2 classification |
|---|---:|---:|---:|---|
| `dev-s1-profile-config-source` | PASS | PASS | FAIL | relation false negative; explicit new paraphrase |
| `dev-s5-cache-binding-key` | PASS | PASS | FAIL | concept false negative; explicit new paraphrase |
| `dev-s6-local-precedence-conflict` | PASS | PASS | FAIL | two independent relation false negatives |

Calibration `20260820T040110Z-20b0fcf2` and Fresh-1 `20260820T060935Z-fb5af9c3` both score V2.2 6/6. The complete bounded wording comparison and deterministic spans are in [bounded-matcher-trace.json](bounded-matcher-trace.json).

## s1 RCA — `profile_gate_mismatch`

All four required concepts pass. The Fresh-2 summary explicitly says that `application-dev.yml` contains a staging activation condition instead of dev, that the active dev profile ignores the file, and that the endpoint falls back. This is not a vague or incorrect diagnosis.

The frozen V2.2 relation variants require a directional witness such as `application-dev.yml` → an allowed relation phrase → `staging`, with active-dev context. Fresh-2 uses “contains a profile activation condition for staging instead of dev”; the observed relational wording is not one of the frozen relation aliases, so no relation span/witness is produced. Calibration and Fresh-1 use recognized relation wording and pass.

**Classification:** `NEW_PARAPHRASE_FALSE_NEGATIVE`.

**S1_PRIMARY_RCA:** `RELATION_ALIAS_COVERAGE_GAP` (high confidence).

## s5 RCA — `observed_default`

The configuration-key/binding-target relation passes. The missing concept is only `observed_default`. Fresh-2 explicitly states that the field “retains its default empty LinkedHashMap” after the mismatch. That is a concrete final-state observation, not an implicit guess.

The frozen concept aliases cover `empty map`, `map default`, `pt0s`, `zero duration`, and `empty default`, but not the semantically equivalent `default empty LinkedHashMap` wording. This is a concept alias coverage false negative, not a relation matcher failure.

**Classification:** `CONCEPT_FALSE_NEGATIVE` / `NEW_PARAPHRASE_FALSE_NEGATIVE`.

**S5_PRIMARY_RCA:** `CONCEPT_ALIAS_COVERAGE_GAP` (high confidence).

The three-run comparison shows that calibration and Fresh-1 use recognized empty/default wording and pass; Fresh-2 introduces a new explicit default-map paraphrase and fails.

## s6 RCA — two independent relations

All four required concepts pass. The two relations must remain independent.

### Relation A — `local_source_overrides_base`

Fresh-2 explicitly states that the local profile overrides the base warehouse retry limit, with `application-local.yml` setting 0 and `application.yml` providing 3. The meaning is present.

The deterministic trace shows why the frozen matcher does not witness it: the first clause has `local profile` and the relation `overrides` but lacks the exact frozen left anchor `local profile configuration`; the later clause has `application-local.yml` and `application.yml` but uses a cross-clause “this file … overriding …” structure. V2.2 requires a bounded same-clause left → relation → right witness. This is a clause/anchor coverage gap, not a directionality algorithm failure.

**Classification:** `NEW_PARAPHRASE_FALSE_NEGATIVE`.

**S6 relation-A RCA:** `RELATION_CLAUSE_AND_ANCHOR_GAP` (high confidence).

### Relation B — `local_value_violates_validation`

Fresh-2 explicitly states that value 0 is violating the `@Min(1)` constraint and causes `BindException`. The causal relation is written, not merely implied by Repair success.

The frozen relation aliases include `violates`, but finite normalization does not map the observed `violating` form to it. The bounded trace therefore finds the left/value/right anchors in nearby clauses but no allowed relation span/witness.

**Classification:** `NEW_PARAPHRASE_FALSE_NEGATIVE`.

**S6 relation-B RCA:** `RELATION_ALIAS_COVERAGE_GAP` (high confidence).

Repair 6/6 is not used to infer diagnosis completeness; it only confirms that the action path succeeded. Diagnosis evidence and evaluator spans are the basis of this RCA.

## Counts

Counts are reported separately at case and missed-component level; s6 contributes two independent relation components.

| Classification | Count |
|---|---:|
| True semantic omission cases | 0 |
| Implicit-only cases | 0 |
| New-paraphrase false-negative cases | 3 |
| Concept false-negative components | 1 |
| Relation false-negative components | 3 |
| Matcher implementation bug components | 0 |
| Actually incorrect diagnosis cases | 0 |
| Artifact ambiguity cases | 0 |

**FRESH2_PRIMARY_RCA:** `EVALUATOR_FALSE_NEGATIVE`.

**RCA confidence:** high. Every failed component has explicit bounded semantic text, and each miss is reproduced by the frozen deterministic matcher trace without any new model call.

## Generation contract and architecture judgment

**Generation-contract gap observed? No.** Fresh-2 did not omit the required semantics and did not rely only on reader inference. The observed failure is evaluator lexical/clause coverage.

**Architecture judgment: EA-B (primary).** V2.2 is sound, but lexical coverage will continue requiring maintenance. The evidence is the 6/6 calibration and Fresh-1 passes followed by three explicit Fresh-2 paraphrase misses. EA-C is a secondary risk: if this pattern repeats, a rule-based relation evaluator may approach diminishing returns. This RCA does not justify an LLM judge.

## Ranked candidates (not implemented)

1. Separately review a bounded V2.3 correction only for confirmed, generalizable evaluator false negatives; do not patch V2.2 in place and do not run Fresh-3 automatically.
2. Evaluate structured diagnosis output (`cause_source`, `relation_type`, `affected_source_or_value`, `observed_effect`) in a separately authorized architecture milestone if repeated natural-language coverage gaps justify the contract cost.
3. Consider diagnosis-generation contract improvement only if a future RCA finds true omission or implicit-only explanation. This RCA does not provide that evidence.

Therefore: no immediate V2.3 recommendation, no Prompt change, no generation-contract implementation, no Fresh-3, and no entry into M7E-3 or M7F.

## Gates and frozen hashes

- Dev integrity: PASS; Dev baseline/reference samples 6/6; Holdout integrity PASS (integrity only).
- Benchmark validation: legacy 3/3, Holdout 7/7, total 10/10.
- V2.0 controls 17/17; V2.1 controls 24/24; V2.2 controls 29/29.
- V2.2 confirmed regressions 15/15; adversarial negatives 12/12 rejected.
- Post-RCA full pytest: **561 passed, 1 skipped**; Ruff PASS; strict mypy PASS for 97 source files; uv lock check PASS.
- Frozen V2.0/V2.1/V2.2 evaluator and V2.2 metadata/manifest/regression hashes are unchanged from the starting commit.
- Holdout Agent, Mock, Live, semantic scoring, and Gold inspection were not run.

## Artifacts and safety

- [RCA summary](summary.json)
- [bounded matcher trace](bounded-matcher-trace.json)
- [Fresh-2 source hash manifest](../m7e2c2c4b-v22-fresh2-validation/fresh2-live-artifact-hashes.json)
- [Fresh-2 frozen replay](../m7e2c2c4b-v22-fresh2-validation/fresh2-live-diagnosis-replay.json)

The RCA artifacts contain bounded evidence, normalized spans, near-miss classifications, aggregate counts, and hashes only. They contain no raw provider output, Prompt, hidden reasoning, full source, Maven dump, reference patch, or Holdout material.

M7E-2C2C4C ends here with `PASS_RCA_ONLY`.
