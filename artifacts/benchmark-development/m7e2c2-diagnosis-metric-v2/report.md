# M7E-2C2 — Diagnosis Metric Alignment

## Outcome

Diagnosis Metric V2 was implemented as a deterministic, versioned,
post-output evaluator. Its positive and negative controls pass, including
paraphrase acceptance, vague-diagnosis rejection, wrong-source rejection,
directional-precedence rejection, keyword-stuffing rejection, contradiction
rejection, and evidence-source enforcement.

The frozen M7E-2A and M7E-2C1 E2E artifacts do not contain the bounded
diagnosis summary or candidate text required for semantic replay. Both replays
therefore classify all six cases as `insufficient_artifact`; they do not count
those cases as semantic failures. A truthful `DIAGNOSIS_V2 = X/6` cannot be
reported from the archived evidence.

Stage status: **M7E-2C2 BLOCKED — frozen semantic payload unavailable**.

## Diagnosis V1 contract

The historical V1 pass predicate is:

```text
agent_completed
AND diagnosis_status_match
AND root_cause_keyword_coverage >= 0.66
AND expected_file_hit
AND evidence_target_hit_count > 0
AND no invalid rejected evidence
```

`issue_category_match` and `structurally_valid` are recorded metrics but are
not direct terms in the historical `case_pass` predicate. V1 is unchanged and
remains reproducible.

For frozen run `20260819T085438Z-4c89fc32`, all six cases passed every V1 gate
except keyword coverage:

| Case | V1 coverage | V1 pass | Repair outcome |
|---|---:|---:|---:|
| dev-s1 | 0.6000 | FAIL | FAIL at PatchApplier in that historical run |
| dev-s2 | 0.4000 | FAIL | PASS |
| dev-s3 | 0.5000 | FAIL | PASS |
| dev-s4 | 0.6000 | FAIL | PASS |
| dev-s5 | 0.3333 | FAIL | PASS |
| dev-s6 | 0.2000 | FAIL | PASS |

Historical result: `DIAGNOSIS_V1 = 0/6`.

## Diagnosis V2 contract

V2 requires all of the following dimensions rather than a lowered lexical
threshold:

1. Agent completion and expected diagnosis status.
2. Expected failure category.
3. Expected source/file and evidence-target support.
4. All case-required semantic concept groups.
5. All case-required directional root-cause relations.
6. No invalid rejected evidence and no contradictory directional relation.

The diagnostic score is the fraction of satisfied structural, concept,
relation, and contradiction-free components. PASS is conjunctive: every
required component must pass. The score is diagnostic only and is not a
threshold substitute.

Direction is evaluated within bounded clauses using versioned relation
variants. Reversed precedence is separately represented as a forbidden
relation, so a response containing all expected words but asserting the wrong
direction fails.

## Versioned evaluator metadata

- Schema: `diagnosis-semantic-v2.0`.
- Storage: separate Dev-only evaluator metadata and hash manifest.
- V1 manifest and V1 keyword fields remain unchanged.
- Metadata is loaded only by the post-output evaluator/replay path.
- `semantic_dev_integrity` validates schema, case order, hashes, and Agent
  projection isolation.
- No metadata enters issue input, retrieval, Prompt, diagnosis generation, or
  repair generation.

## Controls

Positive controls:

- Strong semantic diagnosis for each of the six Dev contracts: PASS 6/6.
- Correct paraphrase without an exact Gold phrase: PASS.
- Correct directional relationship with expected evidence/source: PASS.

Negative controls:

- Incomplete vague diagnosis: rejected.
- Wrong source: rejected.
- Reversed precedence: rejected.
- V1 keyword stuffing with the wrong relationship: rejected.
- Correct and contradictory relationships together: rejected.
- Correct text without expected source/evidence support: rejected.

V1 backward compatibility and strict V2 schema/version handling also pass.

## Frozen evaluator-only replay

No Agent was rerun and no LLM call was made.

| Frozen run | Repair | V1 | V2 evaluated | V2 insufficient artifact |
|---|---:|---:|---:|---:|
| `20260819T085438Z-4c89fc32` | 5/6 historical | 0/6 | 0/6 | 6/6 |
| `20260820T015242Z-fdaa73fd` | 6/6 frozen | 0/6 | 0/6 | 6/6 |

The archived E2E case records retain structural metrics, keyword coverage,
evidence hit counts, and repair outcomes, but omit the semantic text consumed
by V2. Patch diffs and Repair Success were not used as substitutes for
diagnosis content.

## Recommendations

1. Preserve V1 permanently for historical reproduction.
2. Treat V1 as a lexical/debug metric once V2 is empirically validated.
3. Treat V2 as a candidate primary diagnosis metric, not the primary metric
   yet, because no frozen real diagnosis output can be scored.
4. The deterministic contract demonstrates semantic validity, negative
   discrimination, and reproducibility on controls; frozen-run validity remains
   unestablished because of the artifact limitation.
5. Do not add Diagnosis V2 to Repair Success. Diagnosis remains an independent
   quality metric until separate evidence justifies coupling.

## Scope and integrity

- Runtime remains `0.15.1`.
- Frozen post-fix Repair Success remains `6/6` at run
  `20260820T015242Z-fdaa73fd`.
- Agent rerun: false; new LLM calls: 0.
- Prompt, Agent workflow, Retrieval, Validator, PatchApplier, Maven verifier,
  proposal generation, and Repair Success predicate: unchanged.
- Dev sample source/tests and reference fixes: unchanged.
- Holdout Agent/Mock/Live: not executed; Holdout content unchanged.
- `semantic_dev_integrity`: PASS.
- `verify_semantic_dev_samples`: baseline 6/6; reference fixes 6/6.
- `holdout_integrity`: PASS.
- Benchmark validation: legacy 3/3; Holdout 7/7; total 10/10.
- pytest: 487 passed, 1 skipped.
- Ruff, MyPy strict, and `uv lock --check`: PASS.

## Artifact safety

Artifacts contain aggregate outcomes, finite component names, hashes, and
evidence-limitation categories only. They contain no credentials,
machine-specific paths, temporary paths, unprocessed model output, complete
build logs, complete instruction payloads, answer-bearing frozen-split content, or
reference-solution patch dump.

## Artifacts

- `summary.json`
- `replay-m7e2a.json`
- `replay-m7e2c1.json`
- `report.md`

No next milestone was entered.
