# M7E-2B Semantic Dev Failure RCA

## Conclusion

The frozen baseline remains 5/6. The primary repair failure is an application-layer false positive, not a Maven or confirmed semantic failure: the current PatchApplier rejects the s1 diff as `unsafe_diff` because its absolute-path alternative `[a-z]:[\\/]` also matches the `s:/` substring inside `https://` in the URL-bearing configuration diff. A deterministic isolated probe reproduced Validator PASS followed by PatchApplier rejection with zero writes and no Maven execution.

The mechanism is HIGH confidence. The exact historical s1 edit is not fully recoverable: the M7E-2A e2e result records counts and stage fields, but not the edit file, line range, old text, new text, or PatchApplier rejection detail; no s1 patch diff was emitted. Attribution of the reproduced mechanism to the historical payload is therefore MEDIUM confidence, and this evidence limit is preserved rather than filled by inference.

Diagnosis benchmark 0/6 has a separate cause. All six cases completed, matched expected category and status, hit expected evidence targets, and had no rejected evidence. Every case failed only the deterministic root-cause keyword coverage gate of 0.66: s1 0.6, s2 0.4, s3 0.5, s4 0.6, s5 0.3333, s6 0.2. The metric is independent of the current Repair Success predicate, so s2-s6 can repair successfully while all six miss the diagnosis metric.

## Frozen scope and evidence chain

- Starting commit: `a5ec9ec296c50da51dd2d952b30733b2a2632b8b`
- Runtime: `0.15.1`
- Split: `dev_semantic_v1`
- Baseline run: `20260819T085438Z-4c89fc32`
- No new Agent run and no new LLM call occurred in M7E-2B.
- Holdout Agent, Mock, and Live execution were not performed.
- The examined chain was: Agent evidence → diagnosis metrics → proposal audit/validation → PatchApplier → Maven gate → repair result.

The saved M7E-2A result proves for s1: baseline PASS, diagnosis completed, one proposal edit, Validator PASS, application failure, zero applied edits, one rejected application edit, no changed files, original source unchanged, and Maven not executed. The saved artifact does not prove the exact Agent file/value representation.

## RCA-1: s1

### Semantic target and desired fix

The canonical s1 semantics are: the active `dev` profile must make the profile-specific shipping configuration source effective. The canonical sample fix changes the profile activation value in `src/main/resources/application-dev.yml` from the non-active profile to `dev`; the target test then passes. The s1 evidence metrics support the same semantic area: category match, expected-file hit, evidence-target recall 1.0, and zero rejected evidence. The historical Agent target file and old/new values were not serialized, so the exact Agent proposal is not claimed as directly observed.

### Why Validator passed

`src/springfix_agent/repair/validator.py` checks repository-relative allowed paths, proposal status, evidence-backed file/range, file existence, line range, old-text equality using its newline-tolerant comparator, non-empty changed replacement, dangerous new-code patterns, duplicate/conflicting edits, and Java import consistency where applicable. It does not render the final unified diff, run PatchApplier's sensitive-diff scan, write the workspace, or execute Maven. In the saved s1 metrics, one original edit was accepted and zero edits were rejected; therefore the validation result was atomically `passed`.

### Why PatchApplier failed

`src/springfix_agent/repair/applier.py` first preflights the edit, builds a unified diff, then scans that diff with `_SENSITIVE_DIFF_PATTERN`. The pattern includes `[a-z]:[\\/]`, intended to catch drive-style absolute paths. A URL in the changed configuration context contains `https://`; the substring `s:/` satisfies that alternative. The isolated reference-edit probe returned:

```text
Validator: PASS; accepted edits: 1; rejected edits: 0
PatchApplier: REJECTED; application_error: unsafe_diff; rejected reason: unsafe_diff
Changed files: 0; original source unchanged: true
```

Because the safety check runs before atomic writes, the observed result is exactly the M7E-2A shape: one requested edit, zero applied, one rejected, empty changed-file list, and no Maven verifier invocation. A second isolated probe showed a separate representation gap: Validator accepts an old text with two extra boundary newlines while PatchApplier rejects it as `stale_patch`. That secondary probe is not attributed to the historical s1 payload.

### Semantic versus application classification

The confirmed primary class is `patch_application` / `patch_representation`, specifically an unsafe-diff false positive. There is no direct evidence that the s1 semantic reasoning itself was wrong. The canonical semantic fix is valid, and the application-layer probe rejects it before build verification. Historical exact-payload identity remains MEDIUM confidence because the old/new text and target path were not persisted.

## RCA-2: diagnosis versus repair

The evaluator rule in `src/springfix_agent/benchmark/evaluator.py` requires completed execution, matching diagnosis status, keyword coverage at least 0.66, at least one expected file, at least one evidence target hit, and no invalid rejected evidence. The six saved results satisfy every condition except keyword coverage. This is a deterministic metric miss, not an evaluator crash and not evidence that all six diagnoses were semantically wrong.

| Case | Class | Saved diagnosis evidence | Proposal / repair evidence |
|---|---|---|---|
| `dev-s1-profile-config-source` | D2: partially correct | category/status match, file hit, evidence recall 1.0, keyword coverage 0.6 | application rejected; exact proposal payload absent |
| `dev-s2-code-property-override` | D4: diagnosis incomplete but proposal correct | keyword coverage 0.4; all other diagnosis gate fields pass | applied change in `Application.java`; target test PASS |
| `dev-s3-storage-validation` | D4: diagnosis incomplete but proposal correct | keyword coverage 0.5; all other diagnosis gate fields pass | applied storage configuration change; target test PASS |
| `dev-s4-conditional-notification` | D4: diagnosis incomplete but proposal correct | keyword coverage 0.6; all other diagnosis gate fields pass | applied provider configuration change; target test PASS |
| `dev-s5-cache-binding-key` | D4: diagnosis incomplete but proposal correct | keyword coverage 0.3333; all other diagnosis gate fields pass | applied nested binding-key change; target test PASS |
| `dev-s6-local-precedence-conflict` | D4: diagnosis incomplete but proposal correct | keyword coverage 0.2; all other diagnosis gate fields pass | applied local configuration change; target test PASS |

D1 is not supported by the saved evidence. D3 is not claimed because the actual diagnosis text is absent, so semantic correctness cannot be proven independently of the metric. D5 is not observed because no incompatible diagnosis/proposal field mapping is retained. D6 is not claimed because the evaluator rule is deterministic and consistently explains all six misses; the evidence supports a metric-alignment issue, not an evaluator implementation bug.

Diagnosis benchmark is therefore an independent debugging-quality / observational metric in the current pipeline, not a necessary precondition for Repair Success. It should not be tuned in isolation to turn 0/6 into 6/6 if that does not improve actual repair behavior.

## Failure taxonomy

| Category | Observation | Repair effect | Severity | Improvement surface |
|---|---|---|---|---|
| `semantic_understanding` | No confirmed semantic failure; s2-s6 produce test-passing repairs; s1 payload is absent | s1 attribution limited | medium | application boundary first |
| `source_precedence_reasoning` | Benchmark subject in s1, s2, s6; s2 and s6 repair | no confirmed failure | low | diagnosis assertions |
| `target_selection` | All expected-file-hit flags true; s1 exact changed file not saved | no confirmed selection failure | low | bounded forensics |
| `proposal_generation` | 6/6 generated; structured/schema audit succeeded | none observed | low | none immediate |
| `proposal_validation` | 6/6 passed; current validator does not exercise final diff safety | s1 proceeded to apply gate | medium | shared normalization/parity |
| `patch_representation` | Extra-boundary-newline probe gives Validator PASS / PatchApplier `stale_patch` | not attributed to s1 | medium | canonical edit normalization |
| `patch_application` | s1 `unsafe_diff` reproduced; zero writes | direct cause of 5/6 | high | diff safety classifier |
| `build_verification` | s2-s6 pass; s1 correctly skipped after apply rejection | no independent build failure | low | none |
| `diagnosis_evaluation` | all six fail coverage threshold despite other gate fields passing | metric miss only | high for interpretation | semantic concept scoring |
| `benchmark_evaluation` | 0/6 diagnosis versus 5/6 repair is code-consistent but poorly aligned | no direct repair block | medium | metric design/reporting |

## M7E-2C candidates (not implemented)

1. **P0 — PatchApplier safety classification.** Replace the ambiguous drive-path alternative with a boundary-aware path check and add URL/path regression cases. Evidence is the deterministic s1 `unsafe_diff` reproduction. Expected benefit is direct Repair Success improvement for the observed 5/6 failure. Risk is weakening safety checks if the replacement is too broad; blast radius is every changed diff; Holdout impact requires protected validation.

2. **P1 — Diagnosis semantic scoring.** Score structured concept groups plus source/evidence assertions and report lexical coverage separately. Evidence is 0/6 despite category/status/evidence success and 5/6 repair. Expected benefit is Diagnosis metric improvement; direct Repair Success benefit is unproven. Risk is historical metric comparability and over-crediting vague text.

3. **P1 — Bounded patch forensics.** Persist sanitized file/line identifiers, old/new hashes, and a finite PatchApplier rejection category, without model answers or complete responses. This improves RCA and regression detection, not direct repair behavior. Risk is accidental source leakage; blast radius is artifact schema and tooling.

4. **P2 — Proposal concept matching.** Normalize concept matching across summary, rationale, and applied behavior. All six `acceptable_change_concept_hit` values are false even though s2-s6 repair. This is a metric improvement candidate, not a direct repair fix, with risk of judge variance or answer leakage.

Recommended priority is PatchApplier safety classification first, because it is the only confirmed direct Repair Success failure. Diagnosis scoring and proposal metrics follow as independent measurement work.

## Integrity and safety

- `semantic_dev_integrity`: PASS.
- `verify_semantic_dev_samples`: PASS; baseline 6/6 and canonical fixes 6/6.
- `holdout_integrity`: PASS.
- Dev samples, Dev Gold, Holdout membership/hashes, prompts, runtime, Validator, Retrieval, PatchApplier, and Maven verifier were not modified.
- Artifact files: `artifacts/benchmark-development/m7e2b-semantic-dev-rca/report.md` and `artifacts/benchmark-development/m7e2b-semantic-dev-rca/summary.json`.
- Safety review: no credentials or keys, machine-specific paths, scratch paths, unprocessed model responses, complete build transcripts, complete prompts, Holdout answer key, or sample solution dump are included.

## Status

M7E-2B is recorded as **PASS** for RCA completion with MEDIUM confidence on exact historical s1 payload attribution and HIGH confidence on the reproduced PatchApplier mechanism. No production behavior was changed. M7E-2C has not been entered; the candidates above are proposals only.
