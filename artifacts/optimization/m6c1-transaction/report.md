# M6C-1 Transaction Proposal Boundary — Live Reproduction

## Conclusion

The historical `transaction-self-invocation` Proposal failure was **not reproduced** in the fresh single-case Live run. The fresh run completed diagnosis, generated a valid `PatchProposal(status=proposed)`, passed edit validation, and repaired the target case. No parser, schema, provider-completion, exception-normalization, or validator defect was demonstrated.

Per the M6C-1 boundary, this is Outcome C: preserve the historical failure as historical evidence, make no framework change, and keep version `0.13.0`.

## Run metadata

| Field | Value |
|---|---|
| Task | M6C-1 |
| Case | `transaction-self-invocation` |
| Mode | Live |
| Run ID | `20260812T070259Z-8ab8d6b1` |
| Provider | `openai_compatible` |
| Model | `qwen3.7-plus` |
| Base URL host | `wincode.winning.com.cn` |
| Version | `0.13.0` |
| Commit / tag | `1e55b62` / `v0.13.0-m6b` |

Only the requested transaction case was run. No M5D result, diagnosis, Proposal, or historical outcome was reused.

## Diagnosis boundary

- Diagnosis completed and benchmarked PASS.
- Root-cause keyword coverage: `1.0`.
- Validated evidence count: `2`.
- Rejected evidence count: `0`.
- Evidence target recall: `1.0`.
- Retrieval expected file recall at `@1`, `@3`, and `@5`: PASS.
- Validated evidence file/range list: not retained by the bounded case result artifact; no file or line range is fabricated here.

## Proposal Safe Snapshot

| Field | Value |
|---|---:|
| Logical Proposal calls | 1 |
| HTTP attempts | 1 |
| Provider completed | `true` |
| Response received | `true` |
| Response characters | 2578 |
| Parse attempts / success | `1` / `true` |
| Schema validation | `true` |
| Status field present | `true` |
| Proposal status | `proposed` |
| Generator outcome | `proposed` |
| Normalized outcome | `proposed` |
| Edit count | 2 |
| Validator invoked | `true` |
| Validated / rejected edits | 2 / 0 |
| Rejection reasons | none |
| Failure category / detail | none |
| Source exception | none |

The response body, full prompt, and patch code are intentionally not included in this report.

## Exact failure category

The historical category was `proposal_insufficient_evidence`. It was not reproduced. The fresh Proposal crossed the generation and validation boundary successfully, so there is no exact fresh failure layer to assign.

The result is therefore not evidence of:

- a provider-completion failure;
- a missing response;
- a structured parse failure;
- a schema failure;
- an exception-normalization failure; or
- a validator rejection.

## Framework bug and code change decision

- Historical insufficient-evidence failure reproduced: **No**.
- Framework bug demonstrated: **No**.
- Code changed: **No**.
- Generic fix: **None**.
- Version change: **None**; remains `0.13.0`.
- Prompt, Diagnostic Prompt, Gold, sample, validator, retry behavior, transaction behavior, and M6C-2 behavior: unchanged.

## Before / after

Before: the M5D historical transaction run ended with insufficient evidence and did not provide the detailed Proposal audit now available from M6B.

After: the fresh M6C-1 Live run produced a valid two-edit Proposal, validated both edits, applied the patch, passed the target test, and reported repair success. This does not rewrite the historical result.

## Repair and verification

- Pipeline: 1 baseline case, 1 diagnosis, 1 Proposal, 1 patch application, 1 target-test execution, 1 repair success.
- Fresh pipeline logical LLM calls / HTTP attempts: `4` / `4`.
- Tokens: input `6440`, output `9366`, total `15806`.
- Pipeline latency: `182715 ms`.
- Fresh compile success: `true`.
- Existing baseline verification: Ruff PASS, MyPy strict PASS, `414 passed, 1 skipped`; M4C/M5A/M5B/M5C/M5D mock and retrieval checks remained PASS.

Out-of-scope observation: the baseline Maven classifier recorded a stack-frame-like token as `affected_file` and no `first_actionable_error`. This is a classifier limitation outside the M6C-1 Proposal boundary and was not changed here.

## Artifact and Git safety

- Saved artifacts: `reproduction-summary.json` and this report, plus the bounded runner metadata/results.
- No raw provider response, full prompt, API key, full URL, or full patch snapshot is retained in the M6C-1 report artifacts.
- No source files or tests were modified.
- No commit, push, or tag was created.
- Working tree change is limited to the new untracked `artifacts/optimization/m6c1-transaction/` report artifacts.

## Final classification

**Outcome C — historical Transaction Proposal failure not reproduced; no framework bug demonstrated; no code change.**
