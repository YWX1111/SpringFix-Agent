# M6D Fresh Full Live End-to-End Comparison

## Conclusion

On the frozen `v0.14.0-m6c2` baseline, the one permitted fresh full Live
three-case single-shot run repaired **3/3** cases. The historical M5D result
was **1/3**, so the controlled benchmark delta is **+2 repaired cases** and
**+66.67 percentage points** (33.33% to 100.00%). This is a result on the
current controlled three-case benchmark, not a production repair-accuracy
claim.

All three cases reached terminal outcomes in the same run. No prompt,
validator, retrieval, Gold, sample, test, model, retry policy, or repair
success definition was changed during M6D. No repair retry or reflection was
used.

## 1. Scope and frozen baseline

| Field | Value |
|---|---|
| Branch | `main` |
| Commit / tag | `39a341a` / `v0.14.0-m6c2` |
| Version | `0.14.0` |
| M6D run ID | `20260813T044423Z-f44023c0` |
| Mode | `live` |
| Sample size | `3` |
| Cases | `transaction-self-invocation`, `no-unique-bean-definition`, `configuration-properties-prefix-mismatch` |
| Provider / model | `openai_compatible` / `qwen3.7-plus` |
| Temperature / timeout | `0.0` / `60s` |
| Max retries / output tokens | `2` / `2000` |
| API key recording | boolean configured flag only |

The run used one provider, one model, one configuration, and one Run ID for
all three cases. It was a fresh execution; no M5D, M6C-1, or M6C-2 Live
diagnosis, Proposal, patch, or Maven result was reused.

## 2. M5D versus M6D aggregate

| Metric | M5D historical baseline | M6D fresh Live |
|---|---:|---:|
| Sample size | 3 | 3 |
| Baseline reproduced | 3/3 | 3/3 |
| Diagnosis completed | 3/3 | 3/3 |
| Diagnosis benchmark passed | 3/3 | 3/3 |
| Proposal generated | 2/3 | 3/3 |
| Proposal validated | 2/3 | 3/3 |
| Patch applied | 2/3 | 3/3 |
| Target test executed | 1/3 | 3/3 |
| Repair Success | 1/3 | 3/3 |
| Total tokens | 44,363 | 43,570 |
| Mean pipeline latency | 107.470s | 152.733s |
| P50 pipeline latency | 104.964s | 153.353s |
| Max pipeline latency | 114.797s | 160.488s |

M5D source: Run `20260812T040246Z-b5818c80`. M6D is the fresh Run
`20260813T044423Z-f44023c0`.

The fresh M6D run improved controlled Repair Success while using slightly
fewer total tokens, but pipeline latency increased materially: mean latency
rose by `+45.264s` (107.470s to 152.733s), while total tokens changed by
`-793` (44,363 to 43,570). Performance did not improve in every dimension.

## 3. Per-case funnel

| Case | Diagnosis | Proposal | Import | Apply | Maven / Test | Repair | Failed stage |
|---|---|---|---|---|---|---|---|
| `transaction-self-invocation` | PASS | proposed / valid | PASS | PASS | compile PASS; 1/1 test PASS | TRUE | none |
| `no-unique-bean-definition` | PASS | proposed / valid | PASS | PASS | compile PASS; 1/1 test PASS | TRUE | none |
| `configuration-properties-prefix-mismatch` | PASS | proposed / valid | not_run (non-Java edit) | PASS | compile PASS; 1/1 test PASS | TRUE | none |

### Transaction

- Baseline verified: `true`; Diagnosis completed and benchmark passed.
- Proposal: `proposed`, valid; 2 edits requested, 2 validated, 0 rejected.
- Import validation: `pass`; unresolved symbols: none.
- Patch applied: `true`; original repository unchanged: `true`.
- Maven exit code: `0`; compile success: `true`; target test found: `true`.
- Test counts: 1 test, 0 failures, 0 errors, 0 skipped.
- Repair Success: `true`.
- Calls: 3 diagnostic + 1 patch logical call; 4 HTTP attempts.
- Tokens: 6,665 input, 8,467 output, 15,132 total.
- Pipeline latency: 160,488ms.

### Bean

- Baseline verified: `true`; Diagnosis completed and benchmark passed.
- Proposal: `proposed`, valid; 1 edit requested, 1 validated, 0 rejected.
- Import validation: `pass`; unresolved symbols: none.
- Patch applied: `true`; original repository unchanged: `true`.
- Maven exit code: `0`; compile success: `true`; target test found: `true`.
- Test counts: 1 test, 0 failures, 0 errors, 0 skipped.
- Repair Success: `true`.
- Calls: 3 diagnostic + 1 patch logical call; 4 HTTP attempts.
- Tokens: 6,359 input, 8,317 output, 14,676 total.
- Pipeline latency: 153,353ms.

### Configuration

- Baseline verified: `true`; Diagnosis completed and benchmark passed.
- Proposal: `proposed`, valid; 1 edit requested, 1 validated, 0 rejected.
- Import validation: `not_run` because the edit was a non-Java configuration
  edit; unresolved symbols: none.
- Patch applied: `true`; original repository unchanged: `true`.
- Maven exit code: `0`; compile success: `true`; target test found: `true`.
- Test counts: 1 test, 0 failures, 0 errors, 0 skipped.
- Repair Success: `true`.
- Calls: 3 diagnostic + 1 patch logical call; 4 HTTP attempts.
- Tokens: 6,179 input, 7,583 output, 13,762 total.
- Pipeline latency: 144,359ms.

## 4. Funnel and observability

The M6D aggregate funnel is:

```text
Baseline Reproduced       3/3
Diagnosis Completed       3/3
Diagnosis Benchmark Pass  3/3
Proposal Generated        3/3
Proposal Validated        3/3
Import Validation         2/2 Java cases PASS; 1 non-Java case not_run
Patch Applied             3/3
Target Test Executed      3/3
Repair Successful         3/3
```

M6B observability was active for all three cases. Each Proposal completed
with provider response, parse and schema success, `proposal_status=proposed`,
validator invocation, validated edit count, rejected edit count, and no
failure category. The two Java cases recorded import status `pass`, no
unresolved symbols, and no rejected edits. The non-Java control recorded
`import_check_status=not_run`.

Maven/Surefire observability recorded exit code `0`, successful compile/test
verification, target test found, one test executed, zero failures, zero
errors, and zero skipped for every case.

## 5. Attribution boundaries

### Transaction

The Transaction case succeeded in the fresh M6D run. M6C-1 made no framework
code change and its historical Proposal abstention was not reproduced, so
this result is not described as “M6C-1 fixed Transaction.”

### Bean

The Bean result is consistent with the previously observed targeted M6C-2
import-aware correctness success: Proposal import validation passed and Maven
verified the target test. Because Live model behavior is stochastic, M6C-2 is
not claimed as the sole cause of the full-run result.

### Configuration

The Configuration case remains the control case in the full three-case
comparison. Its import stage was correctly not run because the repair was not
a Java edit.

## 6. Usage and latency

M6D totals were 12 logical LLM calls and 12 HTTP attempts: three diagnostic
calls and one Patch Proposal call per case. Provider usage reported 19,203
input tokens and 24,367 output tokens, for 43,570 total tokens. Mean, P50,
and maximum pipeline latencies were 152,733ms, 153,353ms, and 160,488ms.
No estimated or null token values were used.

## 7. Artifact safety

The complete Live runner directory remains local and ignored under the
existing end-to-end artifact policy. This comparison directory retains only
the bounded `report.md` and `comparison-summary.json`.

The retained comparison artifacts contain no API key value, Authorization or
Bearer value, `.env` contents, full Base URL, raw provider response, full
Prompt, absolute local path, temporary workspace path, full Maven environment,
or full patch diff.

## 8. Regression and source integrity

After the Live run, the existing mock gate was rerun and remained `3/3`.
M6D did not modify source code, Prompt, Import validator, Evidence Gate,
retrieval, Gold, samples, tests, the Repair Success definition, retry policy,
model, or version. No commit, push, or tag was created for M6D.

## Final classification

**Fresh full M6D Live comparison complete: Repair Success increased from 1/3
to 3/3 on the current controlled three-case benchmark on `v0.14.0`.**
