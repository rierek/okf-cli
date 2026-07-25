---
# okf-cli-sjqu
title: P14 — De-stale canonical cli/mcp overview
status: completed
type: task
priority: normal
created_at: 2026-07-25T18:13:10Z
updated_at: 2026-07-25T20:59:40Z
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

## Summary (2026-07-25, INLINE per PF-1)

Canonical reference de-staled surgically via /okf loop (D07 prose preserved): 20-verb CLI table (prime + remove-tags added), find row rewritten for hybrid surface (filters, --breakdown, semantic backstop -> §6.1 new subsection with noise floor/margin gate/rank-1 pin/graceful degradation + measured P12 numbers), MCP table now 10 tools (okf_tags added, okf_find params extended, positional-collision guard documented), B01 flipped to fixed (commit 7570642, P6 boundary tests), root-safety hard-fail documented, source-repo move note added, timestamp bumped.

## Verification (SC proof)

- SC-001: 20/20 verbs listed. The '100%' claim named in PLAN Task 14 did NOT exist in the document (grep '100%' = 0 hits) — recorded as already-satisfied, nothing removed.
- SC-002: okf_tags + find filters/breakdown/backstop documented (§1 find row, §2 table, §6.1).
- SC-003: edited via /okf skill loop; conformance proof 'OK — 0 violations' (okf-meta-wiki scan), concept parses + top-hit in find.
- Commit (catalogue repo): afe0bf7 'docs(okf): de-stale cli/mcp overview to 20 verbs', rationale in body.
