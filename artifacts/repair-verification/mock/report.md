# SpringFix M5C Repair Verification

- mode: `mock`
- sample_size: `3`
- Repair Success Rate is measured only on the current 3-case controlled benchmark.
- M5C restricts command type, cwd, environment, timeout, and artifact handling.
- M5C does not provide OS/container/network sandbox isolation.

## Cases

| Case | Baseline | Patch | Maven | Target | Tests | F | E | S | Repair | Reason | Duration (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| `transaction-self-invocation` | true | true | true | true | 1 | 0 | 0 | 0 | true | `none` | 14890 |
| `no-unique-bean-definition` | true | true | true | true | 1 | 0 | 0 | 0 | true | `none` | 8885 |
| `configuration-properties-prefix-mismatch` | true | true | true | true | 1 | 0 | 0 | 0 | true | `none` | 12731 |

## Aggregate Metrics

```json
{
  "baseline_reproduction_rate": 1.0,
  "maven_execution_rate": 1.0,
  "max_verification_duration_ms": 14890,
  "mean_verification_duration_ms": 12168.667,
  "p50_verification_duration_ms": 12731.0,
  "patch_application_rate": 1.0,
  "repair_success_rate": 1.0,
  "sample_size": 3,
  "target_test_execution_rate": 1.0,
  "workspace_cleanup_rate": 1.0,
  "workspace_integrity_rate": 1.0
}
```

## Repair Success Definition

Baseline bug reproduced, validated patch applied, original/test/pom integrity preserved, target test executed, Maven exit code 0, and no failures/errors/skips.
