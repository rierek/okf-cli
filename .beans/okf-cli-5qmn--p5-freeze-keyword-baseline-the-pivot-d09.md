---
# okf-cli-5qmn
title: P5 — FREEZE keyword baseline (the pivot, D09)
status: in-progress
type: task
priority: normal
created_at: 2026-07-25T18:13:10Z
updated_at: 2026-07-25T19:05:40Z
parent: okf-cli-2lpu
blocked_by:
    - okf-cli-ez6f
    - okf-cli-n9l6
    - okf-cli-o7z2
---

## Objective (User Story)
As the PO, I want the keyword-only baseline frozen and committed before any retrieval change so that WS1's maturity gain is provable as a delta.

## EARS Acceptance
- THE baseline result file SHALL be produced by `runner.py` against the seeded catalogue at a recorded git rev, then committed unchanged.
- AFTER freeze, THE baseline file SHALL never be regenerated in place; re-measurement (P12) writes a new file.

## Success Criteria
- SC-001: `cli/eval/results/baseline-<rev>.json` committed.
- SC-002: headline metrics (zero-hit literal vs paraphrase) recorded in PLAN.md.
- SC-003: catalogue left clean (fixtures torn down after capture).

## HARD GATE
Nothing in Phase 2 may land before this artifact is committed.
## Steps
seed -> run --out results/baseline-<rev>.json -> record headline -> teardown -> commit.
Consumes P2,P3,P4. Full steps: PLAN.md Task 5.
Commit: `chore(eval): freeze keyword baseline before WS1`

## Prelude 2026-07-25 — from P4 review (okf-cli-o7z2, non-blocking)

Do FIRST as own commit before freezing:
- F01 (test durability): cli/test_eval_runner.py only asserts recall_at_1 > 0; mutation proof showed the aggregation formula itself is not pinned. Add ONE pure unit test constructing a fixed per_row list and asserting exact values for all 8 metrics (independent of catalogue/golden.json). This protects the very numbers you are about to freeze.
- F02 (info): runner uses FIND_LIMIT=50 (PLAN sketch said --limit 10); documented in runner docstring, no action needed — just do not 'fix' it, the frozen baseline must use the shipped value.
