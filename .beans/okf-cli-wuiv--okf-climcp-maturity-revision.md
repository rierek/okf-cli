---
# okf-cli-wuiv
title: okf-cli/mcp maturity revision
status: in-progress
type: milestone
created_at: 2026-07-25T18:13:09Z
updated_at: 2026-07-25T18:13:09Z
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
