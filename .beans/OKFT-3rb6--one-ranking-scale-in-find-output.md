---
# OKFT-3rb6
title: One ranking scale in find output
status: draft
type: task
priority: normal
created_at: 2026-08-10T12:59:09Z
updated_at: 2026-08-10T12:59:26Z
parent: OKFT-hkze
blocked_by:
    - OKFT-wvgb
---

## Objective (User Story)
As an agent skimming `find` results, I want a single comparable ranking number per line, so that the numeric order of the list matches its actual order.

## Evidence (MODUS-B-REPORT I02)
A mixed list prints `score: cosine 0.63` next to `score: 100/100`, with the numerically larger BM25 values BELOW the semantic hits. Three of five agents (R1, R2, R5) named this independently as the hardest part of reading the output.

## EARS Acceptance
- THE result list SHALL carry one comparable ranking value per line on a single scale.
- THE per-arm raw value SHALL remain available in the score breakdown, not in the headline number.

## Success Criteria
- SC-001: no result list mixes two scales; asserted by a test over a mixed-arm query.
- SC-002: `docs/okf-retrieval-architecture/eval/remeasure.py` still parses results, and the shipped metrics are re-measured to prove the change is presentation-only (no rank movement).

## Note
Blocked by OKFT-wvgb in practice — both touch the same emission site in `cmd_find`; land the provenance line first, then the scale.
