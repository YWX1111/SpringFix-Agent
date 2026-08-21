# M7E-3 — Semantic Dev Closeout & Freeze

Status: **PASS**. GitHub Actions run #34 passed for closeout commit `190f022`. This closeout changes documentation/artifacts only. Starting commit: `50dbe27b5cf950621419fe69f722134593813c9a`. Runtime: `0.15.1`. Dev split: `dev_semantic_v1` (6 cases).

## Freeze decision

The current Semantic Dev Repair capability is frozen at `6/6` on the current Dev set. The latest valid fresh Dev runs remain `6/6`; this is recorded as `STABLE_6_OF_6_ON_CURRENT_DEV`, not as universal generalization.

The primary functional metric remains the existing frozen Repair Success predicate. Diagnosis does not enter Repair Success, release gating, or the Holdout pass prerequisite.

Metric roles are recorded in `metric-role-registry.json`:

- V1: historical lexical/debug metric.
- V2.0: first frozen semantic evaluator, historical experiment.
- V2.1: fairness-calibrated semantic experiment.
- V2.2: latest bounded rule-based semantic diagnostic, **SECONDARY / OBSERVATIONAL** only.

V2.2 calibration was `6/6`, Fresh-1 was `6/6`, and true unseen Fresh-2 was `3/6`. The Fresh-2 score is preserved exactly. M7E-2C2C4C RCA found `TRUE_SEMANTIC_OMISSION_COUNT=0`, `IMPLICIT_ONLY_COUNT=0`, `ACTUAL_INCORRECT_DIAGNOSIS_COUNT=0`, and `ARTIFACT_AMBIGUITY_COUNT=0`; the reviewed failures were evaluator false negatives involving s1 relation aliases, s5 concept aliases, and s6 relation clause/anchor or morphology/alias coverage. The rule-based direction is sound (EA-B primary), while continued patch-by-paraphrase iteration has diminishing returns (EA-C secondary risk). `DIAGNOSIS_RULE_BASED_ITERATION_STOPPED=true`.

## Historical Dev record

| Run | Repair | Diagnosis observation |
| --- | --- | --- |
| M7E-2A | 5/6 | historical baseline |
| M7E-2C1 | 6/6 | safety-fix run |
| M7E-2C2A | 6/6 | bounded evidence introduced; V2.2 replay 6/6 |
| M7E-2C2C2 Fresh-1 | 6/6 | V2.2 replay 6/6 |
| M7E-2C2C4B Fresh-2 | 6/6 | frozen V2.2 score 3/6; RCA says evaluator false negatives |

Diagnosis evidence remains `diagnosis-evidence-v1.0`: bounded, sanitized, versioned, and replayable. It is a quality/observability signal only and cannot override Repair Success.

## Frozen contracts and technical debt

The production component hashes, prompt path/hash freeze, evaluator hashes, Dev benchmark hashes, runtime/provider configuration, and M7F entry requirements are in `m7e-freeze-manifest.json`. Prompt content is intentionally absent. No production behavior, Agent, Prompt, Repair pipeline, evaluator, Structured Diagnosis, V2.3, Fresh-3, or Holdout execution was performed in M7E-3.

The debt register records three non-blocking items: rule-based evaluator lexical maintenance (D1), a theoretical generation-schema causal-field gap not observed in Fresh-2 (D2), and the historical Holdout v1 result of `3/7` (D3). Holdout v1 remains untouched; only integrity validation is allowed in this milestone.

## Fresh Holdout v2 pre-registration

`fresh-holdout-v2-protocol.md` freezes the M7F protocol without creating or running cases. It requires genuinely new blinded cases, a pre-run manifest, independent reference and baseline validation, one-shot Agent execution, artifact freeze before scoring, Repair Success as primary, bounded diagnosis evidence capture, observational-only V2.2, and a no-tuning rule. Any infrastructure defect must follow the pre-declared invalid-run policy.

## Quality and closure

Preflight integrity, sample, benchmark, and V2.0/V2.1/V2.2 controls all passed. The full local gates also passed: `pytest` 561 passed/1 skipped, Ruff PASS, MyPy strict PASS (97 source files), and `uv lock --check` PASS. GitHub Actions run #34 passed all four jobs. With Git clean, the recorded state is `M7E-3 = PASS`, `M7E_CLOSED = true`, and `M7F_READY = true`.

The next milestone is **M7F-0 — Fresh Holdout v2 Construction & Blind Freeze**. Do not execute Fresh Holdout v2 in M7E-3.
