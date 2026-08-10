---
# OKFT-idch
title: Decision filed outside decisions/
status: draft
type: task
priority: low
created_at: 2026-08-10T12:59:09Z
updated_at: 2026-08-10T12:59:09Z
parent: OKFT-hkze
---

## Objective (User Story)
As an agent navigating by structure, I want a concept's directory to agree with its `type`, so that the directory tree is a usable filter.

## Evidence (MODUS-B-REPORT I04)
`memory-layer-wiki/memory-analyses/2026-06-02-mem-27-sprint-plan-backend-consolidation` carries `type: Decision` while a `decisions/` directory exists in the same bundle. The agent in R4 found it only through the bundle index descriptions; the directory structure carried no signal.

## EARS Acceptance
- THE `memory-layer-wiki` bundle SHALL be checked for `type`/location divergence across all its concepts, not only this one.
- WHERE a concept is misfiled, THE move SHALL go through `okf-cli rename` so crosslinks follow.

## Success Criteria
- SC-001: divergence list produced; each entry either moved or justified in writing.
- SC-002: `okf-cli check` clean, no dangling wikilinks.

## Note
Catalogue hygiene, no tooling change. Whether the convention "directory mirrors type" holds catalogue-wide is an open question — do not enforce it beyond this bundle without deciding that first.
