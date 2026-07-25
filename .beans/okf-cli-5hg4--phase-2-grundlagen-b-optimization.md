---
# okf-cli-5hg4
title: 'Phase 2 — Grundlagen-B: optimization'
status: in-progress
type: epic
priority: normal
tags:
    - accepted
created_at: 2026-07-25T18:13:09Z
updated_at: 2026-07-25T21:42:04Z
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

## Review 2026-07-25

US-04 · Embedding-Producer reproduzierbar im Repo (build_tagvec.py + README) · r: "wann werden neue Tags embedded? => das muss automatisch erfolgen sonst haben wir das dilemma, dass dann xxx tags nicht embedded sind. Also rework erforderlich." → okf-cli-3geg (reopened)

US-05 · Semantischer Backstop springt bei Zero-Hit/Paraphrase ein (P8), P12-Gate misst Zero-Hit-Rate 1.000→0.500, sauberer Fallback ohne Cache · a (Q03 = separate Rollout-Entscheidung, kein Defekt an US-05)

US-06 · Keyword-Top-1 strukturell auf Rang 1 gepinnt, Backstop kann korrekten Literal-Treffer nie verdraengen; Gate zeigt 0 Literal-Regressionen · a

US-07 · --type/--tag Filter grenzen Suche ein, --breakdown zeigt Score-Komponente je Treffer (title/tags/body + provenance:semantic) · a

US-08 · MCP okf_tags als eigenes Tool registriert, gleichberechtigt neben den anderen 9 Tools (P10) · a
US-09 · Root-Safety: kein stiller Fallback auf Skript-Verzeichnis mehr -- hard-fail oder Auto-Detect aus Repo-Unterordner (P11) · a

## Rework closure 2026-07-25

US-04 rework done inline (okf-cli-3geg, commit cc2696e): tags --register now auto-embeds new tags (bge-m3), best-effort, mutation-proven (2/2 caught). US-04 re-evaluated: a (was r, fix verified). All 8 stories of this epic now accepted (US-04..US-09) -> epic re-tagged accepted.
