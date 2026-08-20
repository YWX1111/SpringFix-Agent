# M7E-2C2A — Bounded Diagnosis Evidence Capture & Real-Output Validation

## Outcome

M7E-2C2A passes its capture and replay-validation objective. One live `dev_semantic_v1` run completed with valid, bounded, sanitized diagnosis evidence for all six cases. Frozen V2 replay evaluated all six cases (`insufficient_artifact=0`). The real semantic diagnosis result is **0/6**, so the result is a diagnosis-quality failure classification, not an evidence-capture failure. The unchanged Repair Success result is **6/6**.

Run: `20260820T040110Z-20b0fcf2`  \
Starting commit: `bd334e3e84508d5bfec288a0f6b9d7d08649b488`  \
Implementation commit: `4d2594de70b2aa845cb105ecb904bcdc531f4d07`  \
Runtime: `0.15.1`  \
Frozen contract: `diagnosis-semantic-v2.0`

## Scope and evidence boundary

The only production behavior changed is the observability copy from the already-sanitized M4C `CaseResult` into `EndToEndCaseResult`, followed by artifact serialization. Agent workflow, prompts, diagnosis generation, retrieval, validation, PatchApplier, Maven execution, Repair Success, V1, V2 evaluator code, V2 metadata, samples, and holdout behavior were not changed.

The persisted schema is `diagnosis-evidence-v1.0`: summary ≤400 characters; at most three candidates; each candidate has title ≤200, description ≤600, and recommended fix ≤600. Text is allowlisted, sanitized before Unicode-code-point truncation, and marked when truncated. Reasoning, prompt, raw provider output, tool transcript, Maven output, and holdout/reference data are discarded. Complete evidence is projected to the frozen adapter’s top-level `root_cause_summary` and `diagnosis_candidates`; missing or truncated evidence omits those keys and remains fail-closed.

## Frozen controls and historical compatibility

Post-live `tests/unit/benchmark/test_diagnosis_v2.py` passed **17/17**, including vague, wrong-source, reversed-precedence/keyword-stuffing, contradiction, missing-source/evidence, strict schema, and insufficient-artifact controls. The evaluator, metadata JSONL, and manifest SHA-256 values matched the pre-live freeze exactly:

| File | SHA-256 |
|---|---|
| `src/springfix_agent/benchmark/diagnosis_v2.py` | `ba7306d02182c81a50b1ab3ec9ce8b59de572987edad8ccd2fcf34ded8d5a060` |
| `benchmark/dev_semantic_diagnosis_v2.jsonl` | `7663a5ab72280bb60c368a793189434f845e833af7baa4fee516e32da97ef2d7` |
| `benchmark/dev_semantic_diagnosis_v2_manifest.json` | `bb7baee19383ad632d03846fc24ca7be941a9036acfe9a4119eec1ef64716007` |

Historical replays were byte-identical to their frozen outputs: M7E-2A remained V2 `0/6`, evaluated `0/6`, insufficient `6/6`; M7E-2C1 remained the same. Historical artifacts were not retrofilled.

## Quality gates

Pre-live gates all passed: full pytest `508 passed, 1 skipped`; Ruff; strict mypy (`95` source files); lock check; semantic-dev integrity; semantic sample verification (`6/6` baseline and `6/6` reference fixes, no artifact write); holdout integrity; benchmark structural validation; benchmark sample verification (`3/3` legacy and `7/7` holdout); and the frozen V2 controls (`17/17`). The post-live V2 controls also passed `17/17`.

## Real live metrics

| Metric | Result |
|---|---:|
| Repair Success | **6/6** |
| Diagnosis V1 | **0/6** |
| Diagnosis V2 semantic | **0/6** |
| V2 evaluated | **6/6** |
| V2 insufficient artifact | **0/6** |
| V2 mean semantic score | `0.8428` |

All six cases had `diagnosis-evidence-v1.0`, nonblank bounded text, no truncation, and the flat compatibility projection. The raw artifact was frozen before scoring; the 15-file hash manifest was rechecked after scoring with zero mismatches. A recursive safety audit found zero credential/secret, machine-absolute-path, or forbidden-key findings.

## Read-only V2 failure classification

The six evaluated failures are semantic omissions in the model output, not capture loss:

| Case | Missing concepts/relations |
|---|---|
| `dev-s1-profile-config-source` | `active_profile`; `profile_gate_mismatch` |
| `dev-s2-code-property-override` | `code_source_overrides_configuration` |
| `dev-s3-storage-validation` | `binding_target`; `configured_capacity_violates_validation` |
| `dev-s4-conditional-notification` | `provider_condition_mismatch` |
| `dev-s5-cache-binding-key` | `observed_default`; `configuration_key_binding_mismatch` |
| `dev-s6-local-precedence-conflict` | `invalid_retry_value`; `local_source_overrides_base`; `local_value_violates_validation` |

Per the milestone rule, no rerun was made and no evaluator, metadata, gold, concept group, relation, contradiction, or sample change was made. The next step is **M7E-2C2B RCA**.

## Artifact index

- [Machine-readable milestone summary](summary.json)
- [Pre-live freeze record](pre-live-freeze.json)
- [M7E-2A historical replay](replay-m7e2a.json)
- [M7E-2C1 historical replay](replay-m7e2c1.json)
- [Live artifact hash manifest](live-20260820T040110Z-20b0fcf2-artifact-hashes.json)
- [Frozen V2 replay of live output](live-20260820T040110Z-20b0fcf2-diagnosis-replay.json)
- [Raw live artifact directory](live/20260820T040110Z-20b0fcf2/)

Holdout was not executed or modified. The live run was exactly once, with the frozen configuration (`openai_compatible`, `qwen3.7-plus`, temperature `0`, timeout `60s`, max retries `2`, max output tokens `2000`).
