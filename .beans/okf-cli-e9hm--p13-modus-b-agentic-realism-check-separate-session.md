---
# okf-cli-e9hm
title: 'P13 — Modus B: agentic realism check (SEPARATE session)'
status: todo
type: task
priority: normal
created_at: 2026-07-25T18:13:10Z
updated_at: 2026-07-25T18:13:10Z
parent: okf-cli-s3ee
blocked_by:
    - okf-cli-6gq6
---

## Objective (User Story)
As the PO, I want an agentic realism check of the whole retrieval loop, run by a separate agent session, so that real query-formulation success is sanity-checked beyond the mechanical metric.

## EARS Acceptance
- THE bean SHALL be executed in a SEPARATE agentic session (NOT ce-implementer) — D12.
- THE task set SHALL cover >=1 paraphrase-style retrieval per scenario S1-S4 and record agent success/failure as qualitative sanity, explicitly excluded from the gate metric.

## Success Criteria
- SC-001: `cli/eval/modus-b-tasks.md` authored (task prompts + rubric).
- SC-002: outcomes recorded, marked non-gating sanity.

## Note
Author the task set (this bean); the agentic run happens in a separate session with only okf MCP tools. Full steps: PLAN.md Task 13.
Commit: `docs(eval): Modus B agentic realism task set`
