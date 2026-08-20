# M7E-2C2C3 — Diagnosis V2.1 Fresh Generalization Failure RCA

## Outcome

Status: **PASS_RCA_ONLY**. This milestone analyzed the one frozen C2C2 fresh
run offline. No Agent rerun, LLM call, evaluator edit, prompt edit, tuning,
holdout execution, or generation-contract implementation occurred.

The fresh run was valid: Repair Success 6/6, V2.1 evaluated 6/6 with
insufficient artifact 0/6, and mean semantic score 0.9558. The three V2.1
failures are not true diagnosis omissions:

- s1 and s4 are explicit semantic diagnoses expressed with relation wording
  outside the calibrated alias set.
- s5 states the required negative binding relation, but the contradiction
  matcher reads a positive relation from the same negated clause and from the
  recommended-fix context.

The aggregate primary RCA is **mixed evaluator defects**: relation-alias
generalization gaps plus a contradiction negation/context false positive.

## Frozen run and integrity

- Starting commit and origin/main: c7428a967a34ea1f5a8917ce8367459fe61d056c
- Runtime: 0.15.1
- Fresh source: 20260820T060935Z-fb5af9c3
- Exactly one fresh run; invalid run false
- Repair Success: 6/6
- Diagnosis V1: 1/6
- Diagnosis V2.0: 1/6
- Diagnosis V2.1: 3/6, evaluated 6/6, insufficient artifact 0/6
- V2.1 mean semantic score: 0.9558
- Agent rerun: false; LLM calls during RCA: 0

The C2C2 raw artifact hash manifest rechecked 15/15 files with zero
mismatches. Frozen evaluator and metadata hashes remain unchanged:

- V2.0 evaluator: ba7306d02182c81a50b1ab3ec9ce8b59de572987edad8ccd2fcf34ded8d5a060
- V2.1 evaluator: 33e9fa4262ed14e4ef5e58bc4259b619839740e55234828b232a6e2bc3621403
- V2.1 metadata: 3ab66235ae1127290a90cf07bd40c1f48b25f1219959f9e897c19e83361404a7
- V2.1 manifest: ac7f37668961f47d61039a2150db686cc1c0d926681baa0655529b028473f37d

## Bounded evidence review

Only diagnosis-evidence-v1.0 fields were read: root-cause summary, candidate
title, description, and recommended fix. All three cases were sanitized,
bounded, untruncated, and evaluation-ready. Hidden reasoning, chain of
thought, raw provider responses, prompts, source dumps, and Maven output were
not used.

## S1 — profile_gate_mismatch

Fresh score: 0.9167; all four required concepts pass; contradiction none.

The calibration run used the exact relation wording “incorrectly specifies
on-profile: staging”; V2.1 normalizes specifies to specify and matches the
application-dev.yml → specify → on-profile staging witness.

The fresh bounded diagnosis says the file “incorrectly restricts its activation
to the staging profile” and that the dev file is skipped when dev is active.
This is an explicit gate mismatch, but the matcher has no relation alias for
restricts its activation to, skipped, or the resulting mismatch. Left and
right anchors are present; the relation span is absent. No token-distance,
clause-boundary, or morphology failure is involved.

Classification: **R3_EXPLICIT_NEW_PARAPHRASE /
NEW_PARAPHRASE_FALSE_NEGATIVE**. Primary RCA: evaluator relation-alias
coverage gap. Confidence: high. This is not a real diagnosis-quality failure.

## S4 — provider_condition_mismatch

Fresh score: 0.9091; all three required concepts pass; contradiction none.

The calibration diagnosis says the sender is “conditionally registered only
when alerts.provider is webhook”, which is a direct V2.1 relation witness.

The fresh diagnosis says the WebhookNotificationSender is “conditionally
disabled” and requires webhook while the configured provider is email. That is
an explicit provider/condition mismatch, but the relation matcher only knows
phrases such as conditionally registered only when, activates only for, and
is disabled for. It does not match requires or conditionally disabled in this
direction. No token-window or clause-boundary failure is present.

Classification: **R3_EXPLICIT_NEW_PARAPHRASE /
NEW_PARAPHRASE_FALSE_NEGATIVE**. Primary RCA: evaluator relation-alias
coverage gap. Confidence: high. This is not a real diagnosis-quality failure.

## S5 — configuration_key_binding_mismatch

Fresh score: 0.9091; all three concepts pass and the required relation passes.

The required witness is:

    cache region ttl | do not match | ttl by region

This correctly expresses that the configured key does not bind to the target.
The contradiction witness is:

    cache region ttl | match | ttl by region

from the same normalized clause:

    the configuration property cache region ttl ... do not match the field name ttl by region

V2.1’s finite morphology table maps matches to match. The contradiction
variant contains matches as a positive relation alias. Because relation
matching does not model negation scope, the match substring inside do not match
satisfies the forbidden positive relation. A second witness comes from the
recommended-fix text, where a positive instruction to match the key to the
target is treated as current diagnosis semantics. V2.0 passes this case because
its normalization does not map matches to match; this is the precise V2.0 to
V2.1 delta.

Classification: **C2_NEGATION_SCOPE_FALSE_POSITIVE**, with
C3_REFERENCE_CONTEXT_FALSE_POSITIVE as a secondary contributor. Primary RCA:
contradiction matcher correctness defect, amplified by untagged recommendation
context. Confidence: high. There is no real contradiction in the diagnosis.

## Fresh failure taxonomy

| Category | Cases | Count | Finding |
|---|---|---:|---|
| true semantic omission | — | 0 | none observed |
| implicit relation | — | 0 | all three are explicit |
| new paraphrase false negative | s1, s4 | 2 | alias coverage gap |
| matcher implementation bug | s5 | 1 | contradiction matcher |
| clause boundary failure | — | 0 | not observed |
| token window failure | — | 0 | not observed |
| negation scope | s5 | 1 | positive relation inside negated clause |
| contradiction false positive | s5 | 1 | V2.0 PASS to V2.1 FAIL |
| real contradiction | — | 0 | not observed |
| generation variance | s1, s4 | 2 | wording variance exposed the gap |
| artifact ambiguity | — | 0 | evidence was complete |

## V2.1 architecture judgment

Judgment: **D — mixed evaluator defects**. V2.1 is not fundamentally
invalid, and its structural/concept gates and directional required relations
work. However, this fresh sample establishes both insufficient bounded
paraphrase coverage and a contradiction polarity/context defect. The calibrated
V2.1 result should not be promoted as the primary Semantic Dev metric yet.
Diagnosis remains separate from Repair Success and is not a Repair gate.

## Ranked next-stage candidates (not implemented)

1. Versioned V2.2 matcher generalization: add bounded s1/s4 relation variants
   and polarity-aware contradiction handling while preserving V2.1 replay.
2. Versioned contradiction semantics fix: distinguish negated required
   relations from positive forbidden relations and tag recommendation context.
3. Diagnosis generation-contract improvement only if a separately authorized
   RCA finds true semantic omissions; this RCA does not justify it.

Do not modify V2.1 in place. Any future evaluator change must be a new
versioned contract; V1, V2.0, and V2.1 remain replayable.

## Gates and safety

Preflight and post-RCA checks pass: semantic development integrity; semantic
sample baseline/reference fixes 6/6; holdout integrity; structural benchmark
validation; benchmark samples legacy 3/3 and holdout 7/7; V2.0 controls
17/17; V2.1 controls 24/24; confirmed paraphrases 11/11; adversarial
negatives 12/12; full pytest 532 passed and 1 skipped; Ruff; strict mypy for
96 source files; and uv lock check.

The RCA artifact contains only bounded evidence and deterministic matcher
spans. It contains no raw model response, prompt, hidden reasoning, full
source, full Maven output, reference patch, holdout answer material, secrets,
or machine-absolute paths.

## Artifacts

- Machine-readable RCA summary: summary.json
- Bounded matcher trace: bounded-matcher-trace.json
- Frozen source hash manifest: ../m7e2c2c2-v21-fresh-validation/fresh-live-artifact-hashes.json
- Frozen joint replay: ../m7e2c2c2-v21-fresh-validation/fresh-live-diagnosis-replay.json

M7E-2C2C3 is complete and stops here. No V2.2 or generation-contract
implementation is entered in this milestone.
