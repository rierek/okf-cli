---
# OKFT-rx72
title: Eval harness ranks are not deterministic at tie-break
status: draft
type: bug
priority: low
created_at: 2026-08-10T14:39:43Z
updated_at: 2026-08-10T14:39:43Z
parent: OKFT-wuiv
---

## Objective (User Story)
As the owner of the P12 gate metric, I want two runs of the same query set against unchanged code and an unchanged catalogue to produce the same ranks, so that a metric delta means a real change.

## Evidence (OKFT-3rb6, 2026-08-10)
While proving that the `rank:` presentation change moved nothing, the before/after remeasure showed one query flipping between rank 8 and rank 9 — `"Kollegen Mannschaft Abgrenzung Kriterien"` from `queries_v2.json` — which moved `mrr` by 0.0005 (0.43228 against 0.43179). The implementer did not smooth it over: running the SAME post-change code twice in a row reproduces the identical 8/9 flip and two different mrr values (0.41194444444444445 against 0.4115972222222222). The noise is therefore pre-existing and independent of that change.

The flip sits at a rank position that the default output does not even print, so it never reaches a reader — but it does reach the metric, and the P12 gate is a delta discipline.

## EARS Acceptance
- THE source of the tie-break non-determinism SHALL be located before anything is changed — candidates are equal BM25 scores with an unstable sort key, equal cosine values, or set/dict iteration order feeding the fusion.
- WHERE a tie exists, THE order SHALL be broken by a stable, documented key (concept path is the obvious candidate).

## Success Criteria
- SC-001: two consecutive `remeasure.py` runs against unchanged code and an unchanged catalogue produce byte-identical rank lists; asserted, not observed once.
- SC-002: the fix does not move any rank that was not already ambiguous — before/after on the canonical 48-query set.

## Note
Low priority on purpose: the effect is a fifth decimal place on one metric. It matters because it sets the floor for what a gate delta can prove, not because the retrieval is wrong.
