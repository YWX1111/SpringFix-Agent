# Live validation artifacts

This directory holds the output of `scripts/run_m2_live_validation.py` when
real LLM configuration is present. Each Case produces:

```
case-<name>/
├── report.json      # structured diagnostic report
├── report.md        # human-readable Markdown report
└── metrics.json     # provider, model, diagnosis_status, call counts, tokens
```

The Prompt Injection Case saves only `metrics.json` (redacted) to avoid
retaining untrusted content. No artifact stores a full prompt or the raw
provider response.

## M2 validation status

The transaction, insufficient-evidence and prompt-injection Cases were run
against a real OpenAI-compatible model. This is one regression run, not an
accuracy measurement. The Prompt Injection Case validates the current guard
design and observed model behavior only; it does not prove absolute resistance
to Prompt Injection.

## Commit policy

This directory is in `.gitignore`. Files here may contain:

- local absolute paths
- model-derived report content
- task IDs tied to a specific run

Do NOT commit files from this directory unless you have manually reviewed
and redacted them. Stable, sanitized reports can be force-added with
`git add -f` if needed for documentation purposes.

## When LLM config is absent

`scripts/run_m2_live_validation.py` refuses to run and prints the list of
missing environment variables. See `scripts/run_live_diagnosis.py` for the
single-Case entrypoint.
