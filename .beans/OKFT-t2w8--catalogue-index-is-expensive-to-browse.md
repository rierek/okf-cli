---
# OKFT-t2w8
title: Catalogue index is expensive to browse
status: draft
type: task
priority: low
created_at: 2026-08-10T12:59:09Z
updated_at: 2026-08-10T12:59:09Z
parent: OKFT-hkze
---

## Objective (User Story)
As an agent with a small tool budget, I want the catalogue-level index to cost one cheap call, so that navigating is a viable path next to searching.

## Evidence (MODUS-B-REPORT I03)
`okf_index` at catalogue level returns 22 bundles with full descriptions. In run R4 exactly one of those lines carried the answer; a wrong bundle guess (both `home-lab-wiki/decisions` and `general-knowledge-wiki/home-lab-and-hosting` were plausible) would have left almost no budget for a second index call.

## EARS Acceptance
- THE catalogue-level index SHALL default to a compact form — bundle name plus a one-line description.
- THE full description SHALL remain reachable on explicit request.

## Success Criteria
- SC-001: default output shrinks measurably (assert on line count or bytes for the real catalogue), full form still available behind a flag.
- SC-002: MCP surface exposes the same distinction; `just test` green.
