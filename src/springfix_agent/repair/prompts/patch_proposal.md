# Patch Proposal Generator

You are proposing a patch, not applying or verifying it.

Use only the validated root-cause analysis, validated evidence snippets, and
the real production-code segments supplied below.  Do not use benchmark Gold,
README or Markdown content, test source, build output, or any information not
present in these inputs.

Rules:

1. Propose only edits supported by a supplied evidence file and overlapping
   its validated line range.
2. Do not edit tests, README files, benchmark data, build output, metadata, or
   dependency files.
3. Do not execute commands, modify files, download data, or claim that a fix
   was applied or verified.
4. Keep the change minimal and preserve existing business behavior.
5. `old_code` must be copied from the supplied real code segment, including
   its meaningful whitespace.  `new_code` must be non-empty and different.
6. If the evidence does not support a safe edit, return status
   `insufficient_evidence` with an empty edits list.
7. If a proposed change would introduce command execution, process control,
   deletion, network download, credentials, secrets, or hardcoded keys, return
   status `unsafe_to_propose` and an empty edits list.

Return only one JSON object matching this shape:

```json
{
  "status": "proposed" | "insufficient_evidence" | "unsafe_to_propose",
  "summary": "short explanation",
  "root_cause_reference": "candidate:0",
  "edits": [
    {
      "file": "relative/path",
      "start_line": 1,
      "end_line": 1,
      "old_code": "exact supplied code",
      "new_code": "minimal replacement",
      "rationale": "why this edit addresses the validated cause"
    }
  ],
  "verification_steps": ["manual checks for a later milestone"],
  "risks": ["review risks"],
  "assumptions": ["explicit assumptions"]
}
```

## Validated root cause

{{root_cause_analysis}}

## Validated evidence and real code

{{evidence_snippets}}
