# M7E-2C2B — Real Diagnosis Semantic Failure RCA

## Outcome

M7E-2C2B is complete as an RCA-only milestone. The frozen live run was reviewed without rerunning the Agent or making any runtime, prompt, evaluator, metadata, sample, or holdout change.

Source run: `20260820T040110Z-20b0fcf2`  \
Frozen starting commit: `d3900482cb7495dac1f949559bec1ed436a298dc`  \
Runtime: `0.15.1`  \
Repair Success: **6/6**  \
Diagnosis V1: **0/6**  \
Diagnosis V2: **0/6**, evaluated **6/6**, insufficient artifact **0/6**

The bounded artifact is valid. Every case has `diagnosis-evidence-v1.0`, complete bounded text, and the frozen adapter’s compatibility projection. The 0/6 result is therefore not an artifact-loss diagnosis.

## Preflight and frozen controls

`HEAD == origin/main == d3900482cb7495dac1f949559bec1ed436a298dc`; the worktree was clean. Integrity and benchmark gates passed: semantic-dev integrity; semantic-dev samples (`6/6` baseline and `6/6` reference fixes, using `--no-artifact`); holdout integrity; benchmark manifest validation; benchmark samples (`3/3` legacy and `7/7` holdout); and frozen V2 controls (`17/17`).

The frozen SHA-256 values remain unchanged:

| Frozen file | SHA-256 |
|---|---|
| `src/springfix_agent/benchmark/diagnosis_v2.py` | `ba7306d02182c81a50b1ab3ec9ce8b59de572987edad8ccd2fcf34ded8d5a060` |
| `benchmark/dev_semantic_diagnosis_v2.jsonl` | `7663a5ab72280bb60c368a793189434f845e833af7baa4fee516e32da97ef2d7` |
| `benchmark/dev_semantic_diagnosis_v2_manifest.json` | `bb7baee19383ad632d03846fc24ca7be941a9036acfe9a4119eec1ef64716007` |

The 15-file M7E-2C2A live hash manifest was also verified against both the working tree and committed bytes.

## RCA-A — Did the Agent understand the root cause?

**Yes.** The six bounded summaries and candidate descriptions are causal explanations, not symptom/location-only notes:

| Case | Bounded semantic explanation | Applied behavior |
|---|---|---|
| `dev-s1` | profile-specific file is gated for staging while dev is active, so the default endpoint is used | changed the profile gate to dev |
| `dev-s2` | code-supplied system property takes precedence over `application.yml` | removed the static property initializer |
| `dev-s3` | zero max entries violates the storage validation minimum | changed the configured value to 1 |
| `dev-s4` | email configuration does not activate the webhook-only sender, leaving the dependency missing | changed provider to webhook |
| `dev-s5` | the regional key does not bind to the map and the map remains empty/default | renamed the YAML key to the binding name |
| `dev-s6` | local configuration overrides base configuration with retry-limit zero, violating validation | changed local retry-limit to 1 |

All six expected source files were hit, all six evidence targets were hit, and all 11 V2 misses are represented in the bounded text in explicit natural-language form. The issue is not absence of the underlying facts.

## RCA-B — Did diagnosis stop at symptom/location/fix?

**No as the primary live cause.** The current diagnosis prompt and schema do have a structural gap: they require a root-cause summary, candidate description, evidence, and recommended fix, but they do not require a dedicated causal relation or an explicit source-A → relation → source/value-B → effect statement.

That gap is a future-generation risk, not the dominant explanation for this run. The six observed outputs already state the relevant precedence, condition, binding, or validation relationships in prose. No prompt or generation change is made here.

## RCA-C — Are these evaluator false negatives?

**Yes, confirmed for all 11 missing concept/relation components.** The frozen V2 matcher normalizes whitespace and case, then requires exact alias spans in directional order within one sentence clause. It does not cover the live forms below:

| Missing component | Observed explicit form | Frozen matching gap |
|---|---|---|
| `s1.active_profile` | ``dev`` profile is active | backtick punctuation splits the `dev profile` alias |
| `s1.profile_gate_mismatch` | staging gate + active dev + ignored file | `specifies`/`not applied` and sentence boundaries are outside variants |
| `s2.code_source_overrides_configuration` | system properties take precedence | plural `properties` misses singular alias |
| `s3.binding_target` | `StorageProperties` | CamelCase does not match spaced alias |
| `s3.configured_capacity_violates_validation` | max-entries set to 0 violates `@Min(1)` | numeric value is not adjacent to the alias |
| `s4.provider_condition_mismatch` | sender is registered only when provider is webhook | conditional-registration wording is outside variants |
| `s5.observed_default` | map retains an empty default value | wording is outside empty-map/map-default aliases |
| `s5.configuration_key_binding_mismatch` | regional key is not binding to the map because of a name mismatch | left/right aliases and relation wording differ |
| `s6.invalid_retry_value` | retry-limit is set to/with 0 | numeric value is not adjacent to the alias |
| `s6.local_source_overrides_base` | local file is overriding the base file | inflected `overriding` and lexical variants miss |
| `s6.local_value_violates_validation` | retry-limit value 0 violates `@Min(1)` | non-adjacent value misses the alias |

The V2 component audit is `36/36` structural conditions, `16/20` concepts, `0/7` relations, and zero contradictions. The conjunctive gate turns one or more lexical misses in every case into a case-level 0/6, despite the high per-case scores (`0.7692`–`0.9091`).

Fairness judgment: **TOO_STRICT for these observed paraphrases at the lexical matcher layer**. This is a read-only finding; the frozen evaluator and metadata remain unchanged.

## RCA-D — Why Repair is 6/6 while Diagnosis V2 is 0/6

Diagnosis and repair use different representations and inputs. The diagnosis stage emits bounded free text plus evidence references. The proposal stage receives the validated root-cause object, validated evidence snippets, and real production-code segments, then produces a concrete `PatchProposal` that is independently validated and applied. Each live case produced one valid edit, passed its target test, and ended with `repair_success=true`.

The applied diffs agree with the bounded recommended fixes in all six cases. That proves the action path can use concrete source/config evidence; it does not backfill missing diagnosis semantics. The raw proposal response is intentionally not persisted, so this RCA makes no claim about hidden reasoning or unarchived proposal prose.

Conclusion: the pipeline exhibits **action-level diagnosis → proposal semantic enrichment**, while the frozen V2 metric judges only the diagnosis text. Repair correctness is not evidence that the diagnosis text satisfied the V2 relation contract.

## Overall architecture judgment

The Agent is **C: it understood the relation, but the evaluator did not recognize the paraphrase**, with a secondary **B-level generation-contract gap** because causal relations are not structurally required. This is not an A (semantic absence), not an R1/R2 artifact or implicit-only failure, and not a Repair pipeline failure.

## Failure taxonomy

| Taxonomy | Frequency | Severity | Repair impact | Diagnosis impact |
|---|---:|---|---|---|
| evaluator paraphrase matching | 11 components / 6 cases | high | none; Repair 6/6 | primary cause of 0/6 |
| generation contract gap | systemic | medium | none observed | future risk of symptom/fix-only output |
| diagnosis → proposal representation delta | 6/6 | medium | none observed | proposal action cannot backfill diagnosis metric |
| conjunctive gate amplification | 6/6 | high metric impact | none observed | one missed component fails the case |

Source identification, evidence retrieval, contradiction handling, and repair application were not the failure classes in this run.

## M7E-2C2C candidates (not implemented)

1. **P0 — Explicit causal generation contract.** Require source A, relation/precedence/condition, source or value B, and observed consequence in diagnosis output. This prioritizes explanation quality over score tuning.
2. **P1 — Structured relation fields.** Add bounded `cause_source`, `affected_source_or_value`, `relation_type`, and `observed_effect` alongside prose so causal direction is auditable.
3. **P2 — Separately versioned V2 fairness expansion.** Only after this confirmed audit, consider controlled variants for pluralization, CamelCase, punctuation, inflection, and non-adjacent numeric expressions. This is not a change permitted in M7E-2C2B.
4. **P3 — Non-gating Diagnosis-to-Proposal consistency audit.** Record whether the applied edit addresses the diagnosed relation without making Diagnosis a Repair Success gate.

All candidates are recommendations only. No implementation, tuning, evaluator change, gold change, or rerun is made in M7E-2C2B.

## Artifact and stop conditions

- [Machine-readable RCA summary](summary.json)
- [M7E-2C2A source report](../m7e2c2a-bounded-diagnosis-evidence/report.md)
- [Frozen live V2 replay](../m7e2c2a-bounded-diagnosis-evidence/live-20260820T040110Z-20b0fcf2-diagnosis-replay.json)
- [Frozen live artifact hash manifest](../m7e2c2a-bounded-diagnosis-evidence/live-20260820T040110Z-20b0fcf2-artifact-hashes.json)

This report stores bounded paraphrases and aggregate judgments only. It does not dump full model output, raw provider responses, prompts, hidden reasoning, tool transcripts, source file contents, secrets, or machine paths. Holdout remained untouched. M7E-2C2B is **PASS**; stop here and do not enter M7E-2C2C in this turn.
