---
# okf-cli-6gq6
title: P12 — Re-measure + regression gate
status: todo
type: task
priority: normal
created_at: 2026-07-25T18:13:10Z
updated_at: 2026-07-25T19:19:12Z
parent: okf-cli-s3ee
blocked_by:
    - okf-cli-5qmn
    - okf-cli-8uaf
---

## Objective (User Story)
As the PO, I want the hybrid retrieval re-measured against the frozen baseline with a gate so that the maturity gain is proven and regressions are blocked.

## EARS Acceptance
- THE gate SHALL compute per-metric delta (baseline vs hybrid) across all eight metrics — including location_correct_rate (S2) and metadata_hit_rate (Ziel-3) — and per-scenario delta (S1-S4 x literal/paraphrase).
- THE gate SHALL FAIL (exit non-zero) if paraphrase zero-hit-rate did not decrease OR if any literal S1 recall regressed.
- THE re-measurement SHALL write a NEW result file (baseline immutability).

## Success Criteria
- SC-001: `cli/eval/results/hybrid-<rev>.json` written (new file).
- SC-002: `cli/eval/gate.py` prints per-metric + per-scenario delta table.
- SC-003: gate exits non-zero on paraphrase-zero-hit-not-down or S1-literal regression.

## Steps
seed -> runner --out hybrid-<rev>.json -> gate.py (delta table, assert direction) -> teardown -> commit -> report delta to PO.
Consumes P5 (baseline), P8 (hybrid), P4 run()-shape. Own bean (Test-Coordinator). Full steps: PLAN.md Task 12.
Commit: `feat(eval): regression gate — hybrid vs frozen baseline`

## Prelude 2026-07-25 — from P5 review (okf-cli-5qmn, non-blocking F01, do FIRST)

AggregateMetricsPureUnitTest fixture (cli/test_eval_runner.py:78-95) has 50/50 splits for recall_at_1 (2 literal rows) and location_correct_rate (2 location rows) — inverting those predicates is mean-invariant, mutations pass undetected. Before re-measuring: widen fixture to asymmetric splits (e.g. 3 literal rows 2/1, 3 location rows 2/1) so all 8 metric predicates are mutation-caught. Own commit. Frozen baseline itself is unaffected (independently verified byte-identical).
