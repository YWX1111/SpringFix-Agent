# M7D-2：Maven Verification Observability Hardening

## Scope

- Baseline: `main` at `0600052d7e90eb22b5f34592f7289ed7a39ed746`, tag `v0.15.0-m7d1`.
- Start runtime: `0.15.0`; final solidified runtime: `0.15.1`.
- This is an observability/classification hardening only. No Holdout repair, Prompt/Retrieval change, Proposal atomicity change, or repair-success claim was made.
- Holdout Live and Holdout Mock were not run.

## Call graph

`_execute_maven` captures bounded process state and raw stdout/stderr → `_result_from_process` parses workspace-local Surefire XML → `classify_maven_failure` determines lifecycle, root category, first actionable error, affected file/symbol, and Surefire start state → `MavenTestResult` stores the structured result → `MavenRepairVerifier._patched_failure_reason` prefers a trusted upstream category → Repair/E2E map that reason into verification failure fields → existing artifact writers serialize the nested Maven result.

## Contract

The primary category is the root Maven outcome: `main_compile_failure`, `test_compile_failure`, `test_failure`, `timeout`, `maven_execution_failure`, `success`, or an existing more-specific category/`unknown`. Surefire report presence, target-test presence, and test counters remain downstream observations. A missing Surefire report cannot overwrite a trusted upstream compiler or process classification.

The classifier now validates every affected path against the supplied repository root and emits only repository-relative existing files. Compiler diagnostics have precedence over user/test stack frames. Framework and runtime frames such as `java.lang.reflect.Method.invoke`, `java.util.ArrayList.forEach`, `org.junit.*`, `org.springframework.*`, and Maven internals are rejected unless a repository-backed source mapping proves they are user code.

## M7C missing-Surefire synthetic fixture

Fixture: `tests/fixtures/observability/maven/m7c-main-compile-missing-surefire.txt`

Observed result:

```json
{
  "lifecycle_phase": "compile",
  "failure_category": "main_compile_failure",
  "surefire_started": false,
  "surefire_report_found": false,
  "affected_file": "src/main/java/com/example/AuditClient.java",
  "affected_symbol": "AuditClient",
  "first_actionable_error": "duplicate class: AuditClient"
}
```

The primary reason remains `main_compile_failure`; Surefire absence is a secondary observation. The framework stack frames in the fixture do not become `affected_file`.

## Before / after examples

Before:

```text
failure_category = main_compile_failure
verification_failure_reason = surefire_report_missing
affected_file = java.lang.reflect.Method.invoke(Method.java
```

After:

```text
primary failure_category = main_compile_failure
verification_failure_reason = main_compile_failure
surefire_started = false
surefire_report_found = false
affected_file = src/main/java/com/example/AuditClient.java
```

For an unmappable or framework-only stack, `affected_file` is now `null` rather than an absolute path or a framework token.

## Compatibility and scope audit

- Existing `MavenFailureClassification` and `MavenTestResult` fields remain the artifact contract.
- `maven_execution_failure` is an additive formal category for a process that could not start; the existing early `maven_not_found`/`java_not_compatible` guards remain unchanged.
- Repair Success remains defined by baseline reproduction, validated complete application, integrity checks, target execution, Maven exit code 0, and zero failures/errors/skips.
- M7D-1 Proposal atomic validation and its tests are unchanged.
- Gold, Samples, Holdout manifests, Prompt, Retrieval, Validator, PatchApplier, and runtime configuration were not modified.

## Validation

- `uv lock --check` — PASS
- `uv run ruff check src/ tests/ scripts/` — PASS
- `uv run mypy --strict src/` — PASS
- `uv run pytest tests/ -q` — PASS: 455 passed, 1 skipped
- `uv run pytest tests/unit/repair/test_m7d1_proposal_atomicity.py -q` — PASS: 8 passed
- `uv run python scripts/holdout_integrity.py` — PASS
- `uv run python scripts/verify_benchmark_samples.py` — PASS: legacy 3/3, holdout sample verification 7/7
- `uv run python scripts/validate_agent_benchmark.py` — PASS
- `uv run python scripts/verify_m4a_sqlite.py` — PASS
- `uv run python scripts/run_end_to_end_repair_benchmark.py --mode mock` — PASS: Legacy 3/3
- Holdout Mock — not run
- Holdout Live — not run

This Solidification round creates commit `fix: harden Maven failure observability`, pushes it after staged-diff review, waits for green CI, and then creates tag `v0.15.1-m7d2`. The next phase remains explicitly out of scope.
