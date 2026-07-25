---
# okf-cli-wuiv
title: okf-cli/mcp maturity revision
status: in-progress
type: milestone
priority: normal
created_at: 2026-07-25T18:13:09Z
updated_at: 2026-07-25T18:23:36Z
---

Raise okf-cli + okf-mcp maturity at its three weak edges — retrieval semantics, MCP->subprocess correctness, root-safety — with every retrieval change measured as a delta against a keyword baseline frozen BEFORE any optimization.

## Definition of Done (what ships together)
- Keyword baseline frozen (Phase 1) then re-measured after hybrid retrieval; regression gate green.
- B01 fixed + integration-test layer at the MCP->subprocess boundary.
- Hybrid `find` (semantic backstop + filter composition + score breakdown), MCP `okf_tags` parity, root-safety.
- Canonical overview doc de-staled to 20 verbs.

## Plan (source of truth)
`docs/okf-revision/PLAN.md` (ce-plan-reviewer GREEN, PO-approved 2026-07-25).
Think collection: `~/Obsidian/Vault/okf-revision/{DESIGN,EVAL-DESIGN,DECISIONS}.md`.

## Global constraints
- No new runtime deps in `cli/okf-cli.py` (stdlib only; sqlite3 for tagvec reads; embedding production stays offline).
- `find` degrades gracefully to keyword-only when `.tagvec` / embedding backend absent — never hard-fail.
- Conventional Commits, title <=50 chars, no Co-Authored-By.
- Baseline immutability: re-measurement writes a NEW result file.
- Fixtures seeded into the real catalogue (D11), each with reliable teardown.

## Parallelization guidance (added 2026-07-25)

Dispatch ce-implementer agents in waves per the blocked_by graph. Parallel agents MUST run in isolated git worktrees (tools/CLAUDE.md: git checkout/switch in the main workdir is forbidden; concurrent commits to shared HEAD collide). One worktree per concurrent task, then serialize the merges back.

Safe parallel waves:
- Wave A: P1 (okf-cli-83vq) || P2 (okf-cli-ez6f) - okf-cli.py vs new fixtures.py
- Wave B: P6 (okf-cli-asky) || P3 (okf-cli-n9l6) - new test file vs new golden.json
- Wave C: P4 (okf-cli-o7z2) - solo (needs P2+P3)
- BARRIER: P5 (okf-cli-5qmn) FREEZE - solo, blocks all Phase 2 (D09, non-negotiable)
- Wave D: P7 (okf-cli-3geg) || P10 (okf-cli-x0l7) || P11 (okf-cli-1617) - distinct files/regions
- Wave E: P8 (okf-cli-8uaf) - long pole; edits okf-cli.py cmd_find + okf_mcp.py. Dispatch AFTER Wave D lands (P10/P11 small, different regions of the same files) even though its only hard blocked_by is P7.
- Wave F: P12 (okf-cli-6gq6) - solo
- Wave G: P13 (okf-cli-e9hm) || P14 (okf-cli-sjqu) - new md vs catalogue-repo doc

Hard limits (not a cut defect): (1) P5 baseline freeze is a deliberate global barrier. (2) okf-cli.py (P1/P8/P11) and okf_mcp.py (P8/P10) are shared files - worktree isolation is mandatory for concurrent edits.
