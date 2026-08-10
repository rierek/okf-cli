---
# OKFT-cfgj
title: P15 — (optional, Q04) partial --help-derived verb tables
status: scrapped
type: task
priority: normal
created_at: 2026-07-25T18:13:10Z
updated_at: 2026-07-25T22:16:14Z
parent: OKFT-oka0
blocked_by:
    - OKFT-sjqu
---

## Objective (User Story)
As a maintainer, I want the verb tables in the overview generated from argparse --help so that they stop drifting, while narrative prose stays hand-authored.

## EARS Acceptance
- WHEN run, THE generator SHALL emit the verb/flag table from argparse metadata; the narrative sections SHALL remain hand-authored (not overwritten).

## Success Criteria
- SC-001: generator walks argparse subparsers, emits a markdown table spliced between markers.
- SC-002: prose sections untouched.

## Note
OPTIONAL — PO-gated on Q04. If PO downscopes to de-stale-only (P14), scrap this bean. Full steps: PLAN.md Task 15.
Commit: `feat(docs): generate verb tables from argparse --help`

## Scrapped 2026-07-26 (D04, PO-Grilling)

Gestrichen -- P14 ist akzeptierter Endstand (20/20 Verben in der Overview), kein Beleg fuer wiederkehrende Verb-Drift. Siehe OKFT-wuiv D04.
