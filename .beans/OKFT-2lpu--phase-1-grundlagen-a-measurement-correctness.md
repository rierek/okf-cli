---
# OKFT-2lpu
title: 'Phase 1 — Grundlagen-A: measurement & correctness'
status: in-progress
type: epic
priority: normal
tags:
    - accepted
created_at: 2026-07-25T18:13:09Z
updated_at: 2026-07-25T21:36:42Z
parent: OKFT-wuiv
---

Build the measurement + correctness fundament that MUST stand before any retrieval optimization. Eval-first (D09): the keyword-only baseline is frozen while `find` is still pure substring matching, so WS1's effect is a measurable delta.

## Shared context for children
- `find` today = pure keyword/substring, no semantic path (okf-cli.py:538-574). `.tagvec` embeddings exist but are dead code.
- B01: MCP appends `--json` for index/list (okf_mcp.py:11-12 supports_json), but CLI argparse for index/list has no `--json` (okf-cli.py:1884-1893) -> RuntimeError.
- Existing tests call Python funcs directly (test_okf_cli.py:6-13), never the subprocess -> cannot catch B01.
- Fixtures seeded into the REAL catalogue (D11): `_`-prefixed fake concepts, reachable by `find`, each with teardown. Catalogue root: `~/Obsidian/Knowledge-Catalogue/`.

## DoD
B01 fixed; subprocess integration tests green; eval runner + golden fixtures S1-S4 built; keyword baseline frozen + committed.
Plan detail: `docs/okf-revision/PLAN.md` Phase 1 (Tasks 1-6).

## Review 2026-07-25

US-01 · MCP okf_index/okf_list liefern via --json sauberes JSON statt RuntimeError (B01-Fix, abgesichert durch Subprocess-Boundary-Tests) · a
US-02 · Eval-Runner seedet S1–S4 transient in den echten Katalog, misst 12 golden Queries mit 8 Metriken, idempotenter Teardown lässt den Katalog clean · a
US-03 · Keyword-Baseline als immutable baseline-f0714b2.json eingefroren; P12-Gate misst Hybrid als Delta dagegen (PASS) · a
