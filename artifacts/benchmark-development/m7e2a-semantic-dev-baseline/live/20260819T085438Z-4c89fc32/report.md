# SpringFix Dev_Semantic_V1 End-to-End Repair Benchmark

- mode: `live`
- run_id: `20260819T085438Z-4c89fc32`
- split: `dev_semantic_v1`
- sample_size: `6`
- M5D is a single-shot end-to-end benchmark; failed repairs are not retried.
- Results are limited to the current controlled Legacy benchmark and are not a production accuracy rate.

## End-to-End Funnel

| Stage | Passed | Total |
|---|---:|---:|
| Baseline Reproduced | 6/6 | 6 |
| Diagnosis Completed | 6/6 | 6 |
| Diagnosis Benchmark Passed | 0/6 | 6 |
| Proposal Generated | 6/6 | 6 |
| Proposal Validated | 6/6 | 6 |
| Patch Applied | 5/6 | 6 |
| Target Test Executed | 5/6 | 6 |
| Repair Successful | 5/6 | 6 |

## Cases

| Case | Diagnosis | Proposal | Apply | Test | Repair | Failed stage |
|---|---|---|---|---|---|---|
| `dev-s1-profile-config-source` | PASSED | PASSED | FAILED | FALSE | FALSE | `application` |
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
  "duration_ms": 960328,
  "git_commit": "13c5505a5f45dddf0c14623221141336fa4fea0b",
  "git_tag": "v0.15.1-m7d2-1-g13c5505",
  "include_tests": false,
  "java_version": 17,
  "maven_version": "3.9.4",
  "max_output_tokens": 2000,
  "max_retries": 2,
  "mode": "live",
  "model": "qwen3.7-plus",
  "provider": "openai_compatible",
  "run_id": "20260819T085438Z-4c89fc32",
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
  "diagnosis_benchmark_pass_rate": 0.0,
  "diagnosis_completed_count": 6,
  "diagnosis_completion_rate": 1.0,
  "diagnosis_pass_count": 0,
  "max_pipeline_duration_ms": 188390,
  "mean_evidence_target_recall": 1.0,
  "mean_pipeline_duration_ms": 159893.0,
  "mean_root_cause_keyword_coverage": 0.4389,
  "p50_pipeline_duration_ms": 153616.5,
  "patch_application_rate": 0.8333,
  "patch_applied_count": 5,
  "proposal_generated_count": 6,
  "proposal_generation_rate": 1.0,
  "proposal_valid_count": 6,
  "proposal_validation_rate": 1.0,
  "repair_success_count": 5,
  "repair_success_rate": 0.8333,
  "sample_size": 6,
  "target_test_executed_count": 5,
  "target_test_execution_rate": 0.8333,
  "total_http_attempts": 26,
  "total_input_tokens": 38125,
  "total_logical_llm_calls": 24,
  "total_model_evidence": 15,
  "total_output_tokens": 48952,
  "total_rejected_evidence": 0,
  "total_tokens": 87077,
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
