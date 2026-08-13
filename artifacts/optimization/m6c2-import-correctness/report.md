# M6C-2 Import-aware Patch Correctness

## Final conclusion

M6C-2 is complete. The implementation adds a generic import-completeness
contract to the Patch Prompt and a conservative deterministic Java import
validator. The one permitted fresh Bean Live experiment produced Outcome A:
the Proposal included the new annotation usage and its import, import check
passed, Maven compile/test passed, and Repair Success was `true`.

This does not rewrite the historical M5D aggregate (`Repair Success = 1/3`)
or the M6C-1 Transaction conclusion. No full three-case Live benchmark was
run, and no further Live attempt was made after this run.

## 1. M6C-1 evidence preservation

M6C-1 remains under `artifacts/optimization/m6c1-transaction/` with its
sanitized `report.md`, `reproduction-summary.json`, and bounded Live runner
artifacts. Its conclusion remains: the historical Transaction
`proposal_insufficient_evidence` failure was not reproduced and no framework
change was justified.

## 2. M6C-2 changed files

- `pyproject.toml`
- `uv.lock`
- `src/springfix_agent/__init__.py`
- `src/springfix_agent/repair/models.py`
- `src/springfix_agent/repair/java_import_validator.py`
- `src/springfix_agent/repair/validator.py`
- `src/springfix_agent/repair/generator.py`
- `src/springfix_agent/repair/observability.py`
- `src/springfix_agent/repair/e2e_models.py`
- `src/springfix_agent/repair/e2e_runner.py`
- `src/springfix_agent/repair/__init__.py`
- `src/springfix_agent/repair/prompts/patch_proposal.md`
- `tests/test_health.py`
- `tests/unit/repair/test_java_import_validator.py`
- `README.md`, `CLAUDE.md`, and M6C-2 architecture/evaluation/roadmap documentation

Version is `0.14.0`; the Health API returns the package version and therefore
returns status `ok` with version `0.14.0`.

## 3. Prompt contract

The production Patch Prompt now generically requires that a new Java type,
annotation, class, interface, enum, record, or other non-fully-qualified symbol
has the necessary import in the same Java file. It says not to assume imports
already exist, not to emit unresolved simple type names, to prefer minimal
imports, and not to use wildcard imports merely to satisfy the rule. It also
states that the Proposal is not yet compiled and Maven remains authoritative.

There is no Bean-specific example or mapping in the production Prompt. The
implementation does not mention any benchmark case, framework annotation, or
known concrete class.

## 4. Validator architecture

`repair/java_import_validator.py` is a pure, bounded heuristic. It receives the
existing full Java file, the composed proposed Java file, and the edit
segments. It returns `JavaImportCheckResult` with:

- `introduced_symbols`
- `already_resolved_symbols`
- `unresolved_symbols`
- `status = pass | fail | unknown`

It recognizes only high-confidence Java annotation/type contexts. It excludes
Java keywords, common `java.lang` types, existing non-wildcard imports,
same-file declarations, and fully-qualified names. It does not implement Java
name resolution, guess a FQN, use Tree-sitter, invoke javac, or replace Maven.

The existing M5A path, evidence, dangerous-code, old-code, duplicate, and
conflicting-edit rules remain active. Import validation is an additional layer
after those checks; it never edits a Proposal.

## 5. Import handling behavior

- Missing required import: high-confidence unresolved simple symbol is rejected
  with `failure_category = missing_required_import` and `affected_symbol`.
- Existing import: a matching non-wildcard import resolves the symbol and passes.
- Added import: a supporting import edit is allowed only in the same validated
  evidence file, under `src/main/java/**`, in the Java import section, changing
  only import declarations, and importing a symbol used by a validated primary
  edit in that file.
- Fully-qualified symbol: passes without requiring an import.
- Same-file declaration: class/interface/enum/record/annotation declarations
  resolve the symbol and pass.
- Unknown: ambiguous identifiers return `unknown` and remain non-fatal.
- Wrong/unrelated import: rejected; the import validator does not turn an
  unrelated import into a pass.

The stable failure category is `missing_required_import`. The affected symbol
is a simple symbol name only; no absolute path or guessed FQN is recorded.

## 6. Evidence Gate and supporting edit

The primary Evidence Gate was not globally widened. A primary edit must still
overlap validated evidence. Supporting import edits are a derived, narrow
exception only for the exact same evidence-supported Java file and the strict
conditions above. An import-only edit without a validated primary edit, an
unrelated import, a package edit, an arbitrary file-header edit, or an import
edit outside the Java import section is rejected.

This is necessary because imports normally precede the constructor or method
range that diagnoses a bug, but it does not authorize arbitrary edits outside
evidence.

## 7. Deterministic fixtures

`fixture-summary.json` records generic fixtures for missing, existing, added,
fully-qualified, same-file, unknown, and wrong/unrelated imports. The fixtures
do not read Gold or acceptable concepts. The fixture tests cover both the
standalone helper and the integrated Proposal validator.

## 8. Verification

- `uv sync --extra dev`: PASS
- `uv lock --check`: PASS
- Ruff: PASS
- MyPy strict: PASS
- Pytest: `422 passed, 1 skipped`
- M4C benchmark sample verification: PASS (`3/3`)
- Agent benchmark Mock: PASS (`3/3`)
- Patch Proposal Mock: PASS (`3/3`)
- Patch Application Mock: PASS (`3/3`)
- Repair Verification Mock: PASS (`3/3`)
- End-to-End Repair Mock: PASS (`3/3`)
- Retrieval evaluation, manifest validation, and M4A SQLite verification: PASS

No Gold, benchmark sample, or existing test was modified to make the new
validator pass. The new tests are generic fixture-backed tests.

## 9. Bean post-fix Live experiment

| Field | Value |
|---|---|
| Run ID | `20260813T022513Z-4280ae48` |
| Provider / model | `openai_compatible` / `qwen3.7-plus` |
| Case | `no-unique-bean-definition` |
| Diagnosis | completed and benchmark PASS |
| Proposal | `proposed`, valid |
| Import check | `pass` |
| Introduced / unresolved symbols | `Primary` / none |
| Edits | 1 proposed, 1 validated, 0 rejected |
| Changed file | `src/main/java/com/springfix/sample/beans/gateway/StripePaymentGateway.java` |
| Apply | PASS |
| Compile | PASS |
| Maven lifecycle/category | `test_runtime` / `success` |
| Surefire / target test | started / found |
| Test counts | 1 test, 0 failures, 0 errors, 0 skipped |
| Repair Success | `true` |

The Proposal audit recorded one provider-completed response, one parse attempt
with parse/schema success, one Patch logical call, and no normalized failure.
No response body or patch body is included here.

## 10. Before / after

Before (historical M5D Bean result): Proposal PASS and Apply PASS, then Maven
main compilation failed because the new Java annotation import was omitted;
Surefire did not produce the target report and Repair Success was false.

After (fresh M6C-2 Bean result): Proposal included the import-aware change,
validator PASS, isolated Apply PASS, compile PASS, target test PASS, and Repair
Success true. The historical M5D aggregate remains `1/3` and is not replaced by
this single targeted experiment.

## 11. Calls, tokens, and latency

- Diagnostic logical LLM calls: 3
- Patch logical LLM calls: 1
- Total logical LLM calls: 4
- HTTP attempts: 4
- Input tokens: 7061
- Output tokens: 7903
- Total tokens: 14964
- Total pipeline latency: 189280 ms
- Diagnosis latency: 151728 ms
- Patch Proposal latency: 28982 ms
- Maven verification latency: 4238 ms

No automatic repair retry was added. The Live run used one single-shot
Proposal attempt and stopped after completion.

## 12. Safety and Git state

- No API key, Authorization value, `.env`, raw LLM response, full Prompt,
  absolute machine path, or temporary workspace path is in the M6C-2 report
  artifacts.
- The runner-generated complete `patch.diff` was removed; only bounded scalar
  audit fields and repository-relative changed-file names remain.
- No Gold or sample data was modified.
- No production code contains a case-specific import mapping.
- No Reflection, Multi-Agent, Tree-sitter, Docker, or automatic repair retry was
  introduced.
- No commit, push, or tag was created.
- Source/test/doc changes are present in the working tree as the requested
  M6C-2 implementation; generated artifacts are untracked under the two
  optimization report directories.

## Final classification

**Outcome A — generic import-aware Proposal correctness is implemented and the
single permitted Bean Live experiment produced import check PASS, Maven PASS,
and Repair Success=true. Historical M5D/M6C-1 results remain preserved.**
