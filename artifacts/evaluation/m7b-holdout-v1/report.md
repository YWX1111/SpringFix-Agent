# M7B — Fresh Unseen Holdout v1 Live E2E Evaluation

## Conclusion

The first fresh single-shot Live evaluation repaired **3/7 cases** in the
frozen unseen Holdout v1 benchmark. This is a controlled benchmark result,
not a production repair-accuracy claim.

- Run ID: `20260819T040252Z-9aa5957d`
- Start commit: `df2d63c433cdc1b50c38a22255b2e76dbf7b4ad1`
- Runtime version: `0.14.0`
- Split: `holdout`
- Sample size: `7`
- Provider / model: `openai_compatible` / `qwen3.7-plus`
- One provider, one model, one frozen configuration, one Run ID
- No iterative repair loop, repair retry, reflection, or case rerun

## Frozen configuration

| Field | Value |
|---|---|
| Provider | `openai_compatible` |
| Model | `qwen3.7-plus` |
| Temperature | `0.0` |
| Timeout | `60` seconds |
| Max retries | `2` |
| Max output tokens | `2000` |
| API key recording | configured boolean only |

## Funnel

| Stage | Result |
|---|---:|
| Baseline Reproduced | 7/7 |
| Diagnosis Completed | 7/7 |
| Diagnosis Benchmark Passed | 5/7 |
| Proposal Generated | 6/7 |
| Proposal Validated | 6/7 |
| Patch Applied | 6/7 |
| Target Test Executed | 5/7 |
| Repair Successful | 3/7 |

**Holdout Repair Success = 3/7 (42.86%)**

## Case outcomes

| Case | Diagnosis | Proposal | Import | Patch | Verification | Repair | Failure |
|---|---|---|---|---|---|---|---|
| `missing-constructor-bean` | completed / benchmark fail | generated / valid | fail | applied | compile failed; Surefire not started | false | verification / `main_compile_failure` |
| `constructor-circular-dependency` | completed / benchmark fail | generated / valid | pass | applied | compile and target test passed | true | none |
| `invalid-config-property-value` | completed / benchmark pass | generated / valid | not_run | applied | compile succeeded; target test failed | false | verification / `test_failure` |
| `wrong-active-profile` | completed / benchmark pass | generated / valid | not_run | applied | compile succeeded; target test failed | false | verification / `test_failure` |
| `component-scan-boundary` | completed / benchmark pass | generated / valid | unknown | applied | compile and target test passed | true | none |
| `transaction-proxy-visibility` | completed / benchmark pass | generated / valid | unknown | applied | compile and target test passed | true | none |
| `ambiguous-request-mapping` | completed / benchmark pass | not generated / insufficient evidence | not_run | not applied | not run | false | proposal / `proposal_status_insufficient_evidence` |

### Failed cases retained

- `missing-constructor-bean`: proposal generated, proposal validated, patch
  applied, Maven compile failed, Surefire did not start;
  `failure_category=main_compile_failure`.
- `invalid-config-property-value`: proposal valid, patch applied, compile
  succeeded, target test executed and remained failing;
  `failure_category=test_failure`.
- `wrong-active-profile`: proposal valid, patch applied, compile succeeded,
  target test executed and remained failing;
  `failure_category=test_failure`.
- `ambiguous-request-mapping`: diagnosis completed and evidence was present;
  the provider completed a structured proposal response with
  `proposal_status=insufficient_evidence`; no patch or Maven verification was
  performed.

### Successful cases retained

- `constructor-circular-dependency`
- `component-scan-boundary`
- `transaction-proxy-visibility`

## Diagnosis and repair metric boundary

Diagnosis Benchmark Pass and Repair Success are independent deterministic
metrics. The final results are **Diagnosis Benchmark = 5/7** and
**Repair Success = 3/7**. The `constructor-circular-dependency` case is an
observed Repair Success even though its diagnosis benchmark metric did not
pass. This evidence does not claim that diagnosis accuracy directly predicts
repair success and does not alter Diagnosis Gold.

The four failed repairs consist of three verification-stage failures and one
proposal-stage abstention. The observed failures are concentrated after
diagnosis, especially in patch correctness / verification, with one proposal
abstention. This is a result summary only; failure RCA and fixes are outside
M7B and belong to a later M7C scope.

## Usage and latency

- Logical LLM calls: `28`
- HTTP attempts: `28`
- Input tokens: `42,825`
- Output tokens: `56,321`
- Total tokens: `99,146`
- Mean pipeline latency: `149077.714 ms`
- P50 pipeline latency: `149906 ms`
- Maximum pipeline latency: `169014 ms`
- Total Run duration: `1044452 ms`

## Post-run gates

- Holdout Integrity: PASS
- Pytest: `438 passed, 1 skipped`
- Ruff: PASS
- MyPy strict: PASS
- Legacy baseline: `3/3`
- Holdout baseline: `7/7`
- Total benchmark baseline: `10/10`
- Legacy Mock E2E: `3/3`

## Artifact provenance and safety

The detailed source artifact remains local and ignored under the existing
end-to-end artifact policy. This curated report is derived from the original
Run `20260819T040252Z-9aa5957d`; it does not rerun the Agent, LLM, repair
pipeline, or metric computation.

The retained curated evidence contains only bounded metrics and redacted
metadata. It does not contain an API key, Authorization or Bearer value,
`.env` contents, a full Base URL, raw provider response, full Prompt, full
Maven stdout/stderr, absolute local paths, temporary workspace paths, or a
full patch diff.

The original detailed runner report contains one stale template sentence
labelled `M5D`. That is an artifact-label issue only. The curated evidence is
correctly labelled M7B, and the original Live artifact was not modified.

## Source integrity and scope boundary

- Source, runtime configuration, Prompt, Validator, Retrieval, Gold, Samples,
  and Tests were not modified for this evidence solidification.
- No Holdout Live, Holdout Mock, Legacy Live, case rerun, repair fix, M7C RCA,
  or version upgrade was performed.
- Runtime remains `0.14.0`.
- No runtime SemVer tag is created by this evidence record.
