# M7E-1 Semantic Repair Development Benchmark Expansion

This artifact records construction-time validation only. No Agent, Mock Holdout, or Live LLM run was performed.

- Split: `dev_semantic_v1`
- Runtime: `0.15.1` (unchanged)
- New Dev cases: 6/6 deterministic baselines reproduced
- Reference fixes: 6/6 isolated-copy validations passed
- Frozen Holdout v1: 7 cases; historical repair result remains 3/7

## Case audit

| Case | Category | Effective source | Higher-precedence source | Baseline | Reference fix |
| --- | --- | --- | --- | --- | --- |
| `dev-s1-profile-config-source` | `configuration` | profile-specific config document | active profile document over base config | 1 test / 1 failure | PASS |
| `dev-s2-code-property-override` | `configuration` | application property binding | System property set in visible application code | 1 test / 1 failure | PASS |
| `dev-s3-storage-validation` | `configuration` | storage ConfigurationProperties binding | validated storage value from application config | 1 test / 1 failure | PASS |
| `dev-s4-conditional-notification` | `dependency_injection` | conditional notification Bean | alerts.provider condition | 1 test / 1 failure | PASS |
| `dev-s5-cache-binding-key` | `configuration` | cache ConfigurationProperties map | cache binding path | 1 test / 1 failure | PASS |
| `dev-s6-local-precedence-conflict` | `configuration` | active local profile config | application-local.yml over application.yml | 1 test / 1 failure | PASS |

## Integrity and scope

- Target tests contain no hidden property/profile override; all configuration evidence is in Agent-visible source.
- Gold is post-output verification data and is not included in the Agent projection.
- Frozen Holdout v1 membership and hashes are checked separately by `scripts/holdout_integrity.py`.
- No reference patch is stored in this artifact; fixes were applied only to isolated validation copies.
