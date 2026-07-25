---
# okf-cli-5hg4
title: 'Phase 2 — Grundlagen-B: optimization'
status: in-progress
type: epic
priority: normal
created_at: 2026-07-25T18:13:09Z
updated_at: 2026-07-25T19:20:36Z
parent: okf-cli-wuiv
---

The work to be measured. Hybrid retrieval + targeted MCP parity + root-safety, all landing AFTER the frozen baseline so each change is a delta.

## Shared context for children
- Hybrid = keyword primary (unchanged first pass) + semantic backstop firing only on weak/zero keyword results (D04).
- `.tagvec` provenance must be pulled in-repo first (gates the hybrid design: tag-only vs body embeddings).
- MCP already exposes check/refs/index/list/... (okf_mcp.py:65-115); the only agent-relevant gap is `tags` (D05).
- Root default falls back to the script dir (okf-cli.py:72-73) — unsafe.

## DoD
Hybrid `find` (backstop + filters + score breakdown) shipped; `okf_tags` registered; root-safety in place; all under the frozen baseline.
Plan detail: `docs/okf-revision/PLAN.md` Phase 2 (Tasks 7,8,10,11).
BLOCKED until Phase 1 baseline freeze is committed.
