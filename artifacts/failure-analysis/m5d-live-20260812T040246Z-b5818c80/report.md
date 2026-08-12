# M5D Live Repair Failure RCA

## Scope

Evidence-only RCA for the two failed cases in existing M5D Live Run `20260812T040246Z-b5818c80`. No Agent, Prompt, Gold, Sample, test, Validator, Retrieval, Repair Success logic, or Patch was changed. No Live LLM call, patch regeneration, retry, commit, push, or tag was performed.

The retained redacted artifact contains run metadata, aggregate/per-case results, and diffs for cases that reached application. It does not contain the raw LLM response, full trace, proposal parser error, rejected-edit audit, or structured Maven phase/first-error record. Conclusions below distinguish observed facts from unsupported hypotheses.

## Baseline

Current repository baseline:

```text
HEAD: e4e87320804a6cdf23a2956eb5505751bb98b3ab
tag: v0.12.0-m5d
branch: main
working tree: clean
.env: ignored by .gitignore; not read
```

Live Run provenance recorded in its own metadata:

```text
commit: 7bfaea3be5dbddff80faa58a568f898ef2cf6412
tag: v0.11.0-m5c
version: 0.12.0
provider/model: openai_compatible / qwen3.7-plus
sample_size: 3
```

These are preserved as two separate provenance facts.

## Funnel

| Stage | Passed | Total |
|---|---:|---:|
| Baseline Reproduced | 3/3 | 3 |
| Diagnosis Completed | 3/3 | 3 |
| Diagnosis Benchmark Passed | 3/3 | 3 |
| Proposal Generated | 2/3 | 3 |
| Proposal Validated | 2/3 | 3 |
| Patch Applied | 2/3 | 3 |
| Target Test Executed | 1/3 | 3 |
| Repair Successful | 1/3 | 3 |

Diagnosis is `3/3`; repair is `1/3`. Losses occur after diagnosis: one at proposal outcome and one at verification after patch application.

## Failure 1 - Transaction Proposal

### Observed

Case: `transaction-self-invocation`.

Baseline reproduction passed: Maven exit `1`, one test failure, zero errors, and Surefire found the target test. The retained assertion says the inserted row remained persisted and explicitly identifies self-invocation bypassing the Spring AOP proxy.

Diagnosis passed:

```text
diagnosis_status: passed
diagnosis_benchmark_pass: true
root_cause_keyword_coverage: 1.0
expected_file_recall: 1.0
evidence_target_recall: 1.0
model_evidence_count: 2
validated_evidence_count: 2
rejected_evidence_count: 0
valid_evidence_rate: 1.0
```

Proposal outcome:

```text
proposal_status: failed
proposal_result_status: insufficient_evidence
proposal_generated: false
proposal_valid: false
failed_stage: proposal
failure_reason: proposal_invalid
edit_count: 0
validated_edit_count: 0
rejected_edit_count: 0
patch_logical_llm_calls: 1
patch_http_attempts: 1
```

### Evidence

Current source corroborates the diagnosed defect at `samples/sample-springboot-bug-transaction-self-invocation/src/main/java/com/springfix/sample/transaction/service/OrderService.java`:

- lines 31-34: `createOrder()` directly calls `createOrderInTransaction()`;
- line 36: `createOrderInTransaction()` is annotated `@Transactional`;
- lines 38-42: the insert is followed by the simulated `RuntimeException`.

The Run retains evidence counts and recall, but not candidate references, evidence file/range list, retrieved snippets, or the root-cause payload. It is not possible to reconstruct exactly which two evidence items the Patch Proposal Generator received.

### Primary Root Cause

**Primary failure layer: Patch Proposal Generator / structured-proposal boundary; exact lower-level subcategory is not recoverable from retained evidence.**

The exact supported category is the normalized `proposal_insufficient_evidence` outcome (`proposal_result_status=insufficient_evidence`), classified by the pipeline as `proposal_invalid`.

The artifact does not distinguish among:

- the model deliberately returning a valid `insufficient_evidence` object;
- structured-output parse/schema failure normalized to that status; or
- an exception inside proposal generation normalized to that status.

The implementation maps proposal-generation exceptions to an insufficient-evidence proposal, while the Run does not retain the exception class or final parser error. Therefore this RCA does not claim `proposal_invalid_json`, `proposal_schema_validation_failed`, `proposal_provider_failure`, or `proposal_unsafe_to_propose`.

### Contributing Factors

- No proposal edit existed, so no edit-level rejection reason can be observed.
- `validated_evidence_count=2` and target recall `1.0`; the Run does not support a Retrieval or diagnosis Evidence Gate failure claim.
- A separate transactional service/bean is a plausible repair shape, but no proposal attempting it was retained. A capability boundary is not proven.

### Ruled Out

The retained result does not support diagnosis failure, baseline reproduction failure, rejected edit, patch application failure, or Maven verification failure as the primary cause. It also does not support the claim that the model proposed a new Bean/file and M5A rejected it.

### Instrumentation Gaps

- final proposal status plus separate `generation_error_category`;
- structured parse attempts, retry count, parser error class, and provider outcome;
- sanitized proposal payload or safe proposal summary when no edit is accepted;
- validated evidence file/ranges delivered to the generator;
- rejected proposal/edit audit.

### Recommended Next Experiment

**P0 - offline proposal-boundary fixture replay:** preserve a sanitized transaction RCA/evidence payload and run known valid single-file and two-file/separate-service proposal fixtures through the existing parser/validator. Classify accepted, `file_not_in_validated_evidence`, `new_file_not_supported`, and parser/schema outcomes. Do not call Live LLM or change the validator.

## Failure 2 - Bean Verification

### Observed

Case: `no-unique-bean-definition`.

Diagnosis, proposal, and application passed:

```text
proposal_status: passed
proposal_result_status: proposed
proposal_valid: true
validated_edit_count: 1
evidence_supported_edit_rate: 1.0
patch_applied: true
all_edits_applied: true
changed_files: [src/main/java/com/springfix/sample/beans/gateway/StripePaymentGateway.java]
```

Maven exited `1` with no Surefire report and no target test result:

```text
maven_executed: true
maven_exit_code: 1
compile_success: false
surefire_report_found: false
target_test_found: false
tests: 0
failures: 0
errors: 0
verification_failure_reason: surefire_report_missing
```

### Patch Diff

Actual retained diff, not Gold:

```diff
--- a/src/main/java/com/springfix/sample/beans/gateway/StripePaymentGateway.java
+++ b/src/main/java/com/springfix/sample/beans/gateway/StripePaymentGateway.java
@@ -4,6 +4,7 @@

 /** First PaymentGateway bean. */
 @Component
+@Primary
 public class StripePaymentGateway implements PaymentGateway {
```

One existing file was touched and one annotation was added. No import was added; `CheckoutService`, either interface, and `@Qualifier` were not changed. The intended fix was to select `StripePaymentGateway` among the two `PaymentGateway` beans.

Project source confirms that `StripePaymentGateway.java` imports only `org.springframework.stereotype.Component`; it does not import `org.springframework.context.annotation.Primary`. The actual patch therefore references an unresolved symbol.

### Maven Phase

**Exact phase: main-source compilation.** The sanitized tail contains:

```text
[ERROR] COMPILATION ERROR
Failed to execute goal org.apache.maven.plugins:maven-compiler-plugin:3.11.0:compile (default-compile)
Compilation failure
cannot find symbol ... symbol: class Primary
```

### First Actionable Error

First actionable error:

```text
first_actionable_error: cannot find symbol: class Primary
error_phase: maven-compiler-plugin:compile / main compile
affected_file: src/main/java/com/springfix/sample/beans/gateway/StripePaymentGateway.java
affected_symbol: Primary
```

The path/line fragment is encoding-damaged, but the added annotation at patch line 7 and unresolved symbol are unambiguous. This is not dependency resolution, test compilation, Surefire plugin failure, or runtime startup. Maven stopped before test execution; Surefire never started.

### Primary Root Cause

The actual patch added `@Primary` without importing `org.springframework.context.annotation.Primary`, so main compilation failed before Surefire could start.

### Patch Behavior

The `@Primary` idea is relevant to the ambiguous-bean defect, but the applied Java patch is incomplete because it omitted the required annotation import. This is a compile/semantic correctness failure after deterministic proposal validation, not an M5A evidence/path failure.

### Why Earlier Validators Passed

M5A checks path policy, evidence overlap, line range, `old_code` matching, dangerous-code patterns, duplicates, and conflicts. It does not compile Java or resolve Spring annotation symbols.

M5B safely applied the edit in an isolated workspace and preserved test/POM integrity. Application success means the edit was written safely, not that Java/Spring semantics are correct.

```text
M5A deterministic proposal validation passed,
but Java compile correctness failed at M5C main compilation.
```

### Instrumentation Gaps

- Maven lifecycle phase is not a structured result field.
- `first_actionable_error`, affected file, and affected symbol are not structured fields.
- `surefire_report_missing` is coarse even when the tail contains a definitive compiler error.
- Main compile, test compile, plugin execution, and runtime startup are not first-class classifications.
- Patch artifacts do not include annotation/import semantic-check results.

### Recommended Next Experiment

**P1 - offline accepted-patch verification fixture:** classify saved accepted diffs and Maven tails into main compile versus test compile and extract the first actionable symbol/file before generic Surefire-missing fallback. Do not change repair behavior or invoke Live LLM.

## Successful Control - Configuration Prefix

Case: `configuration-properties-prefix-mismatch`.

Actual patch:

```diff
-@ConfigurationProperties(prefix = "springfix.mail")
+@ConfigurationProperties(prefix = "springfix.email")
```

The Run records proposal pass, application pass, Maven exit `0`, Surefire report found, target test found, one test, zero failures/errors/skips, and `repair_success=true`.

This is a minimal one-file metadata edit directly covered by validated evidence. It requires no new file, new import/symbol, or structural refactor, and the target test passes.

## Cross-Case Comparison

| Case | Patch type | Files touched | New file required? | New import/symbol? | Structural refactor? | Proposal valid? | Compile/test reached? | Repair success? |
|---|---|---|---|---|---|---|---|---|
| transaction-self-invocation | unknown; no proposal/diff retained | none | unknown | unknown | unknown | no | no | no |
| no-unique-bean-definition | add `@Primary` annotation | `StripePaymentGateway.java` | no | new `Primary` symbol; import absent | no | yes | main compile reached; target test not reached | no |
| configuration-properties-prefix-mismatch | one-line annotation-value edit | `MailProperties.java` | no | no | no | yes | compile and target test reached | yes |

`unknown` is intentional for Transaction: no proposal was generated and the retained artifact cannot establish the intended edit shape.

## Current Repair Capability Boundary

This Run demonstrates:

- baseline reproduction and diagnosis for these cases: `3/3`;
- successful repair of a minimal, existing-file, evidence-local edit: `1/3` overall;
- safe application of one validated existing-file edit even when later compilation fails.

It does not establish that the pipeline cannot perform multi-file or new-bean repairs, because the Transaction proposal failure lacks the raw proposal/evidence audit needed to prove that boundary. It does establish that deterministic proposal validation and application are not Java/Spring compile or semantic validation, as shown by the missing `Primary` import.

## Prioritized Follow-up Experiments

1. **P0 - Transaction proposal boundary:** offline fixture replay with proposal status, parser error category, evidence ranges, and two-file candidate; determine exact rejection/generation layer.
2. **P1 - Bean compile diagnostics:** offline classification of accepted diffs and Maven tails into dependency, main compile, test compile, plugin, runtime, or unknown, with first actionable error extraction.
3. **P2 - Benchmark expansion:** add offline import-sensitive and multi-file structural cases and measure proposal and verification separately from diagnosis.

No experiment in this list was executed during M6A.

## Limitations

- Sample size is three and has no statistical significance claim.
- The Live artifact is redacted and lacks raw LLM output, full trace, proposal parser error, proposal evidence ranges, rejected-edit audit, and structured Maven phase/error.
- Transaction is complete only at normalized `insufficient_evidence`; its lower-level generator/parser/provider/capability cause remains unresolved.
- Bean's tail is partly encoding-damaged, but compiler goal and unresolved `Primary` symbol are clear enough to classify main compilation.
- Current source corroborates the actual diff and source semantics; it is not a replay of the historical Live workspace.

## Verification and Change Policy

No project source, prompt, Gold, sample, test, Agent, Validator, Retrieval, or Repair Success logic was modified. No Live LLM was called. No patch was generated or retried. The only new files are this RCA report and structured summary under `artifacts/failure-analysis/`.
