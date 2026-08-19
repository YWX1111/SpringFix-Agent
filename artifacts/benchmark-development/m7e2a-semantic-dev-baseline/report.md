# M7E-2A Semantic Dev Agent Baseline

## Scope

- Starting commit: `13c5505a5f45dddf0c14623221141336fa4fea0b`
- Runtime: `0.15.1`
- Split: `dev_semantic_v1`
- Cases: 6/6, one complete run, no case-level rerun
- Run ID: `20260819T085438Z-4c89fc32`
- Mode: `live`
- Provider/model: `openai_compatible / qwen3.7-plus`
- Java/Maven: `17 / 3.9.4`
- Frozen timeout/retry/output settings: `60s / 2 / 2000`; temperature `0.0`

The run used the existing `EndToEndRepairBenchmarkRunner` with the frozen Dev
case and Repair Gold manifests supplied as evaluator inputs. Agent views were
isolated from Gold and reference material before execution. Gold was used only
for deterministic post-output evaluation.

## Exact execution

```text
@'
from pathlib import Path
from springfix_agent.repair.e2e_runner import EndToEndRepairBenchmarkRunner
root = Path('.').resolve()
runner = EndToEndRepairBenchmarkRunner(project_root=root, manifest_path=root / 'benchmark' / 'dev_semantic_cases.jsonl', repair_gold_path=root / 'benchmark' / 'dev_semantic_repair_gold.jsonl', output_dir=root / 'artifacts' / 'benchmark-development' / 'm7e2a-semantic-dev-baseline', mode='live', benchmark_split='dev_semantic_v1')
result = runner.run()
print(result.run_id, result.aggregate.repair_success_count, result.aggregate.sample_size)
'@ | uv run python -c "import sys; exec(sys.stdin.buffer.read().decode('utf-8-sig'))"
```

## Aggregate result

| Stage | Result |
|---|---:|
| Baseline failure reproduced | 6/6 |
| Diagnosis completed | 6/6 |
| Diagnosis benchmark pass | 0/6 |
| Proposal generated | 6/6 |
| Proposal validated | 6/6 |
| Patch applied | 5/6 |
| Target test executed | 5/6 |
| CURRENT_SEMANTIC_DEV_REPAIR_SUCCESS | **5/6** |

The run recorded 24 logical LLM calls, 26 provider HTTP attempts, 38,125
input tokens, 48,952 output tokens, and 87,077 total tokens. Mean/p50/max
pipeline duration was 159,893 / 153,616.5 / 188,390 ms.

## Per-case evidence

| Case | Category | Baseline | Diagnosis | Proposal | Patch | Maven/test | Repair Success | Failure stage |
|---|---|---|---|---|---|---|---|---|
| `dev-s1-profile-config-source` | configuration | PASS | completed | validated | failed | not run | FAIL | application: `patch_application_failed` |
| `dev-s2-code-property-override` | configuration | PASS | completed | validated | applied | 1 test, 0/0/0/0 | PASS | — |
| `dev-s3-storage-validation` | configuration | PASS | completed | validated | applied | 1 test, 0/0/0/0 | PASS | — |
| `dev-s4-conditional-notification` | dependency_injection | PASS | completed | validated | applied | 1 test, 0/0/0/0 | PASS | — |
| `dev-s5-cache-binding-key` | configuration | PASS | completed | validated | applied | 1 test, 0/0/0/0 | PASS | — |
| `dev-s6-local-precedence-conflict` | configuration | PASS | completed | validated | applied | 1 test, 0/0/0/0 | PASS | — |

Here `0/0/0/0` is `failures/errors/skipped` with one executed test. The failed
case is recorded as a normal semantic baseline outcome, not an invalid run.
There were no benchmark retries and no invalidation reason. Provider-level
attempts remain recorded separately in the aggregate.

## Integrity and isolation

- Preflight: HEAD matched `origin/main`, working tree clean.
- Agent projection / Gold isolation: PASS for all six Dev views.
- `semantic_dev_integrity`: PASS.
- `verify_semantic_dev_samples`: baseline 6/6; reference fixes 6/6.
- `holdout_integrity`: PASS; Holdout Agent/Mock/Live not executed.
- Legacy/Holdout benchmark validation: 3/3, 7/7, total 10/10.
- Dev samples, Dev Gold, Holdout membership/hashes, and runtime behavior were unchanged.
- No Prompt, Runtime, Validator, Retrieval, PatchApplier, or Maven verifier changes were made.

## Artifact safety

PASS: no credentials, machine-specific paths, scratch paths, unprocessed model
output, complete build logs, or answer-key material are present.

## Artifacts

- Raw run: `live/20260819T085438Z-4c89fc32/`
- Structured summary: `summary.json`
- This report: `report.md`

## M7E-2A conclusion

M7E-2A PASS: the current Semantic Dev Agent baseline is measured and frozen as
`5/6`. This report records measurement only. No RCA, tuning, retry, Holdout
rerun, M7E-2B, M7E-2C, or M7F work was started.
