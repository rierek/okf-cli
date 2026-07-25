---
# okf-cli-6gq6
title: P12 — Re-measure + regression gate
status: completed
type: task
priority: normal
created_at: 2026-07-25T18:13:10Z
updated_at: 2026-07-25T20:55:21Z
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

## Prelude 2026-07-25 — from P11 review (non-blocking I09, optional)

Eval test suite writes fixtures into the real unsandboxed KC; stray state from an aborted run caused 3 spurious errors until cleaned. If cheap during P12: add pre-flight teardown() call at runner/suite start (idempotent since P2). Full sandboxing is out of scope.

## Summary (2026-07-25, INLINE per PF-1 — no subagents)

Both preludes done first (asymmetric metric-fixture splits 2eb59b5; seed() pre-clean I09 8674cd6). gate.py delivered TDD (8 tests, RED FileNotFoundError quoted in session; both guards mutation-proven in isolation: paraphrase-guard inversion -> 4 failures, S1-guard inversion -> 2 failures, byte-identical reverts). Re-measurement run per P8 pattern: pristine cache backed up (md5 0ad92871cfc0a13cdb5baadefdc21ce2), 4 fixture concept_emb rows produced via local Ollama bge-m3 into a scratch copy, swapped in, runner wrote cli/eval/results/hybrid-39d6c0a.json (NEW file, baseline untouched), gate.py PASS, cache restored md5-identical, catalogue clean.

## Test-Output

Full suite after close: 189 tests, exactly 19F/2E pre-existing (0 new). New: cli/test_eval_gate.py 8/8, noise-floor tests 2/2 (RED quoted: 'path: b/wanted' not found pre-fix).

## Smoke (gate verdict, real run)

zero_hit_rate_paraphrase 1.000 -> 0.500 (-0.500). Scenario ranks: s1-paraphrase inf->2, s3-paraphrase inf->3 (8c EARS S3 top-5 SATISFIED), all literals unchanged rank 1, s4-index-walk/list rows unchanged. GATE: PASS exit 0. catalogue_rev baseline=f0714b2 hybrid=39d6c0a (KC drifted during session — foreign agent-memory commits, zqxeval token-space unaffected).

## Deviations/ERRATA

1. MEASUREMENT-DRIVEN FIX in cmd_find (0235eb8): first measurement exposed that the P8 margin gate never fires on real-catalogue NOISE (S3-paraphrase top1 3/24=0.125 with 'clear' 0.667 margin over 1/24 runner-up) — S3 rescue impossible, 8c EARS violated. Added SEMANTIC_NOISE_RATIO=0.25 absolute floor (fires backstop regardless of margin/hit-count; rank-1 pin unchanged). Substantively P8 material, fixed under P12 because only the re-measurement could reveal it; ERRATA pointer appended to bean okf-cli-8uaf.
2. hybrid result file named for the rev at measurement time (39d6c0a), not milestone-start rev.
3. Stale-bytecode pitfall hit during mutation proofs: same-size same-second edits kept a stale __pycache__ .pyc alive — all proofs re-run with cache clearing (see LESSONS-LEARNED LL-07).

## Notes for T(n+1) / P13 (Modus B, SEPARATE session)

- s2/s4-paraphrase remain inf even with backstop firing and their concept_emb present — cosine of those paraphrases against title+body vectors too weak to enter top-limit, or crowded by keyword noise. Candidate question for the agentic realism check.
- cli/test_eval_runner.py RunnerAgainstRealCatalogueTest pins 'all paraphrase rows rank inf' — TRUE only while the LIVE cache has no concept_emb rows. The moment concept_emb is produced for the live catalogue, that pin flips (old-behavior pin, LL-risk). Update it together with any decision to populate concept_emb productively (open PO question Q03).
- Q01 (index.md vs --json surface) still open with PO.
