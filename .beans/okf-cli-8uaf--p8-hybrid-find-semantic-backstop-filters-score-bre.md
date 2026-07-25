---
# okf-cli-8uaf
title: 'P8 — Hybrid find: semantic backstop + filters + score breakdown'
status: todo
type: task
priority: normal
created_at: 2026-07-25T18:13:10Z
updated_at: 2026-07-25T18:13:10Z
parent: okf-cli-5hg4
blocked_by:
    - okf-cli-3geg
---

## Objective (User Story)
As an agent, I want `find` to rescue paraphrase queries semantically, be scopeable by type/tag/bundle, and expose a score breakdown so that retrieval is precise and trustworthy — while staying keyword-first and degrading gracefully.

## EARS Acceptance
- WHEN `find <q> --type T --tag G --scope B` runs, THE CLI SHALL keyword-rank only concepts matching the exact type/tag within scope B (resolve_scopes okf-cli.py:514, extract_tags :519); WITHOUT filters, behavior unchanged.
- WHEN `find <q> --breakdown` runs, THE CLI SHALL emit per-hit contributing field(s)/term(s); WITHOUT it, output byte-identical to today (okf-cli.py:568).
- WHEN a paraphrase query (keyword zero-hit per baseline) for S3 is issued AND an embedding backend is available, THE CLI SHALL surface the expected concept within top-5.
- WHEN the `.tagvec` cache OR embedding backend is absent, THE CLI SHALL return keyword-only results without error.
- THE semantic pass SHALL run only as a backstop (below-threshold/zero keyword), never replacing a strong keyword top-hit (S1 literal stays Top-1).

## Success Criteria
- SC-001: scoped find excludes non-matching types (unit test).
- SC-002: --breakdown lists contributing fields; default output unchanged.
- SC-003: semantic fallback rescues S3 paraphrase (backend-guarded/xfail); graceful keyword-only when cache removed.
- SC-004: `okf_find` MCP tool exposes type/tag/scope/bundle; `_FLAGS` (okf_mcp.py:19) registers scope/bundle so build_argv marshals them (subprocess test).

## Affected code
- `cli/okf-cli.py:538-574` cmd_find + argparse `pf` (:1894-1896)
- `mcp/okf_mcp.py:67-69` okf_find tool + `:18-19` _FLAGS (`"scope":"--scope","bundle":"--bundle"`)
- sqlite3 (stdlib) reader for `.tagvec`; threshold const `SEMANTIC_FALLBACK_RATIO`
- Tests: `cli/test_okf_cli.py`, `cli/test_okf_mcp.py`
Design keyed on P7's tags-vs-body finding. Full 8a/8b/8c steps: PLAN.md Task 8.
Commit: `feat(cli): hybrid find — semantic backstop, filters, score breakdown`
