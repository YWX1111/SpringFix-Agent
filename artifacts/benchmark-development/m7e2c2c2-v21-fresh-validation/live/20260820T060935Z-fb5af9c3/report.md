# SpringFix Dev_Semantic_V1 End-to-End Repair Benchmark

- mode: `live`
- run_id: `20260820T060935Z-fb5af9c3`
- split: `dev_semantic_v1`
- sample_size: `6`
- M5D is a single-shot end-to-end benchmark; failed repairs are not retried.
- Results are limited to the current controlled Legacy benchmark and are not a production accuracy rate.

## End-to-End Funnel

| Stage | Passed | Total |
|---|---:|---:|
| Baseline Reproduced | 6/6 | 6 |
| Diagnosis Completed | 6/6 | 6 |
| Diagnosis Benchmark Passed | 1/6 | 6 |
| Proposal Generated | 6/6 | 6 |
| Proposal Validated | 6/6 | 6 |
| Patch Applied | 6/6 | 6 |
| Target Test Executed | 6/6 | 6 |
| Repair Successful | 6/6 | 6 |

## Cases

| Case | Diagnosis | Proposal | Apply | Test | Repair | Failed stage |
|---|---|---|---|---|---|---|
| `dev-s1-profile-config-source` | PASSED | PASSED | PASSED | TRUE | TRUE | `none` |
| `dev-s2-code-property-override` | PASSED | PASSED | PASSED | TRUE | TRUE | `none` |
| `dev-s3-storage-validation` | PASSED | PASSED | PASSED | TRUE | TRUE | `none` |
| `dev-s4-conditional-notification` | PASSED | PASSED | PASSED | TRUE | TRUE | `none` |
| `dev-s5-cache-binding-key` | PASSED | PASSED | PASSED | TRUE | TRUE | `none` |
| `dev-s6-local-precedence-conflict` | PASSED | PASSED | PASSED | TRUE | TRUE | `none` |

## Run Metadata

```json
{
  "api_key_configured": true,
  "base_url_host": "wincode.winning.com.cn",
  "duration_ms": 923594,
  "git_commit": "9ce8747f5d39412480cb34e0e365fde706f1ef3e",
  "git_tag": "v0.15.1-m7d2-10-g9ce8747",
  "include_tests": false,
  "java_version": 17,
  "maven_version": "3.9.4",
  "max_output_tokens": 2000,
  "max_retries": 2,
  "mode": "live",
  "model": "qwen3.7-plus",
  "provider": "openai_compatible",
  "run_id": "20260820T060935Z-fb5af9c3",
  "sample_size": 6,
  "split": "dev_semantic_v1",
  "temperature": 0.0,
  "timeout": 60,
  "version": "0.15.1"
}
```

## Aggregate Metrics

```json
{
  "baseline_reproduction_rate": 1.0,
  "baseline_verified_count": 6,
  "cases_completed": 6,
  "cases_total": 6,
  "diagnosis_benchmark_pass_rate": 0.1667,
  "diagnosis_completed_count": 6,
  "diagnosis_completion_rate": 1.0,
  "diagnosis_pass_count": 1,
  "max_pipeline_duration_ms": 198532,
  "mean_evidence_target_recall": 1.0,
  "mean_pipeline_duration_ms": 153770.5,
  "mean_root_cause_keyword_coverage": 0.5,
  "p50_pipeline_duration_ms": 151390.0,
  "patch_application_rate": 1.0,
  "patch_applied_count": 6,
  "proposal_generated_count": 6,
  "proposal_generation_rate": 1.0,
  "proposal_valid_count": 6,
  "proposal_validation_rate": 1.0,
  "repair_success_count": 6,
  "repair_success_rate": 1.0,
  "sample_size": 6,
  "target_test_executed_count": 6,
  "target_test_execution_rate": 1.0,
  "total_http_attempts": 24,
  "total_input_tokens": 38554,
  "total_logical_llm_calls": 24,
  "total_model_evidence": 15,
  "total_output_tokens": 46888,
  "total_rejected_evidence": 0,
  "total_tokens": 85442,
  "total_validated_evidence": 15
}
```

## Limitations

- sample_size is 6 and the bug categories are limited to the selected frozen split.
- Live results depend on the selected model version and frozen provider configuration.
- The benchmark has no statistical significance claim and no iterative repair loop.
- Maven verification is restricted by command shape, cwd, environment, and timeout, but is not an OS/container/network sandbox.
- Maven may access normal dependency repositories required by the sample projects.
- `compile_success` is true only when Surefire confirms the target test executed; otherwise it remains null unless a verifier provides a definitive compilation classification.
