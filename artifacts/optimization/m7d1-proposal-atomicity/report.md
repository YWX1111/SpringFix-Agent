# M7D-1 Proposal Atomic Validation Gate

- start commit: `94e48ba88e0ff0592b33d17f135577d3e8f22934`
- development started from runtime version: `0.14.0`
- final solidified runtime version: `0.15.0`
- scope: fail-closed proposal atomicity only

## Contract

`PatchValidationResult.passed` is true only when all of the following hold:

```text
proposal.status == proposed
original_edit_count > 0
accepted_edit_count == original_edit_count
rejected_edit_count == 0
```

The sanitized accepted-edit subset is never reinterpreted as a new valid
proposal. Any deterministic rejection of an original edit blocks application.
This applies equally to `missing_required_import`, old-code mismatch, unsafe
path, invalid evidence, and other deterministic rejection reasons.

The validator accounting invariant is also explicit in regression tests:
`original_edit_count == accepted_edit_count + rejected_edit_count`.

Failure taxonomy is deterministic: partial acceptance is reported as
`proposal_partial_rejection`; other proposal validation rejection is reported
as `proposal_validation_rejected`. These cases are not provider,
infrastructure, application, or verification failures.

## Deterministic before / after

| Shape | Before | After |
|---|---|---|
| 2 original, 1 accepted, 1 rejected | `validation.passed=true`; proposal application reachable | `validation.passed=false`; `PatchApplier` unreachable |
| 0 original, 0 accepted, 0 rejected | fails because `accepted_edit_count > 0` is false | fails because `original_edit_count > 0` is explicit |
| 1 original, 1 accepted, 0 rejected | pass | pass |
| 2 original, 2 accepted, 0 rejected | pass | pass |

## Regression coverage

The deterministic test file `tests/unit/repair/test_m7d1_proposal_atomicity.py`
adds eight tests covering:

- partial rejection with a non-import reason;
- partial rejection caused by `missing_required_import`;
- zero-edit, single-edit, and fully accepted multi-edit proposals;
- the synthetic M7C failure shape (`2 → 1 accepted + 1 rejected`);
- E2E gate behavior with a PatchApplier spy, proving apply call count is zero.

Result: `8 passed`. Related proposal, observability, Java import, and E2E tests: `49 passed`.
Full suite: `446 passed, 1 skipped`.

## Quality results

- `uv lock --check`: PASS
- `uv run ruff check src/ tests/ scripts/`: PASS
- `uv run mypy --strict src/`: PASS
- `uv run python scripts/holdout_integrity.py`: PASS
- `uv run python scripts/verify_benchmark_samples.py`: PASS
- `uv run python scripts/validate_agent_benchmark.py`: Legacy `3/3`, Holdout `7/7`, total `10/10`
- `uv run python scripts/verify_m4a_sqlite.py`: PASS
- `uv run python scripts/run_end_to_end_repair_benchmark.py --mode mock`: Legacy Mock `3/3`

The frozen M7B Holdout v1 Agent baseline remains `3/7`; no Holdout Live or
Holdout Mock run was performed for M7D-1.

## Scope and compatibility

`PatchApplier` application semantics were not changed. Existing fully valid
single- and multi-edit proposals continue to pass. Prompt, retrieval, Gold,
Samples and Holdout were not changed. The runtime version was bumped from
`0.14.0` to `0.15.0` as part of this solidification. Commit, push, and tag
operations are recorded by the final Git audit.
