# M7F-0 Fresh Holdout v2 Construction & Blind Freeze

Status: **BLOCKED_BY_PREEXISTING_M7E_HASH_MISMATCH**

This report contains aggregate construction and isolation results only. Reference patches, exact expected edits, and case Gold are sealed separately.

- Starting commit: `35f8bbebcafded22397e53a5a2f2a148dab0c890`
- Freeze commit: `16ecd46fea9801c598a1b4e6faf718a1224584f6`
- Runtime: `0.15.1`
- Cases: `8` (fresh-v2-h01, fresh-v2-h02, fresh-v2-h03, fresh-v2-h04, fresh-v2-h05, fresh-v2-h06, fresh-v2-h07, fresh-v2-h08)
- Semantic families: `8`
- Compositional/generalization cases: `2`
- Baseline validation: `8/8`; repeat `2/2 per case`
- Reference validation: `8/8`; repeat `2/2 per case`
- Baseline restoration: `8/8`
- Gold isolation: `PASS`
- Novelty audit: `PASS`
- M7E freeze intact: `False`
- M7E recheck note: pre-existing frozen manifest mismatch in `src/springfix_agent/repair/evaluator.py`; no frozen asset was changed.
- Agent executions: `0`; Fresh Holdout executed: `False`
- Invalid-run policy frozen: `True`
- Anti-tuning lock: `True`
- M7F1 execution readiness: `True`

## Artifact safety

The Agent-facing manifest contains only neutral issue/context fields. Gold and reference patches are excluded from the Agent projection and are stored only under the sealed benchmark paths recorded in the freeze manifest.
