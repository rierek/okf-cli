---
# okf-cli-sjqu
title: P14 — De-stale canonical cli/mcp overview
status: todo
type: task
priority: normal
created_at: 2026-07-25T18:13:10Z
updated_at: 2026-07-25T18:13:10Z
parent: okf-cli-oka0
blocked_by:
    - okf-cli-8uaf
    - okf-cli-x0l7
    - okf-cli-1617
---

## Objective (User Story)
As an agent reading the canonical reference, I want it to reflect the real 20-verb surface and the new capabilities so that the doc stops misleading me.

## EARS Acceptance
- THE overview SHALL list all 20 verbs (add `prime`, `remove-tags`), remove the "100%" claim, and reflect the new MCP surface (`okf_tags`) + `find` filters/breakdown/semantic backstop.
- Hand-written prose/narrative SHALL be preserved (D07).

## Success Criteria
- SC-001: 20/20 verbs listed, "100%" gone.
- SC-002: `okf_tags` + new `find` capabilities documented.
- SC-003: edited via `/okf`, not by hand.

## Affected file
`Knowledge-Catalogue/okf-meta-wiki/okf-cli-mcp-overview.md` (Stand 2026-07-12, 18/20 verbs). Via `/okf`.
Consumes P8,P10,P11 (shipped surface). Full steps: PLAN.md Task 14.
Commit (catalogue repo): `docs(okf): de-stale cli/mcp overview to 20 verbs`
