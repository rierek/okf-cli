---
# okf-cli-5qmn
title: P5 — FREEZE keyword baseline (the pivot, D09)
status: in-progress
type: task
priority: normal
tags:
    - to-review
created_at: 2026-07-25T18:13:10Z
updated_at: 2026-07-25T19:10:57Z
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


## Summary

Prelude F01 done first as its own commit: extracted the inline aggregation block
in `run()` into a pure `aggregate_metrics(per_row)` function and added
`AggregateMetricsPureUnitTest` — a hand-built 10-row `per_row` fixture (covering
literal/paraphrase/location/metadata/index-walk) asserting exact values for all
eight metrics, no subprocess/catalogue/golden.json involved. This pins the exact
formula before the numbers it produces get frozen.

Task 5 freeze executed per the plan recipe (seed -> run -> teardown), plus two
extra independent cycles to prove determinism before writing the committed file,
and one more cycle after the commit to prove the committed file still matches a
fresh measurement. `catalogue_rev` is unchanged at `f0714b2` (same as Task 4's
last recorded run) so no rev bump was needed in the baseline filename.
`cli/eval/results/baseline-f0714b2.json` is now committed and, per the milestone's
"baseline immutability" constraint, will never be regenerated in place — Task 12
writes a new file.

## Test-Output

Full suite (pre-existing 19F/2E baseline, unrelated to this task's files):
- BASELINE (start of task): `Ran 125 tests ... FAILED (failures=19, errors=2)`
- AFTER (end of task): `Ran 126 tests ... FAILED (failures=19, errors=2)`
- Delta: +1 test (the new F01 pure unit test), 0 new failures/errors.

`cli.test_eval_runner` alone: `Ran 10 tests ... OK` (was 9 before F01).

## Smoke

Two-lap determinism proof (pre-commit): `seed -> run --out run1.json -> teardown`,
then `seed -> run --out run2.json -> teardown` — `diff run1.json run2.json` ->
identical. Third capture written directly to
`cli/eval/results/baseline-f0714b2.json` (`seed -> run -> teardown`) ->
`diff run1.json baseline-f0714b2.json` -> identical -> committed.
Fourth capture, post-commit (`seed -> run -> teardown`) diffed against the
now-committed `baseline-f0714b2.json` -> identical.
Catalogue (`~/Obsidian/Knowledge-Catalogue`) `git status --short` clean
(only pre-existing unrelated `?? .claude/`) after every teardown, both before
and after the freeze commit.

Headline metrics (SC-002), all four captures identical:

| Metric | Value |
|---|---|
| recall_at_1 | 0.750 |
| recall_at_5 | 1.000 |
| mrr | 0.812 |
| zero_hit_rate_literal | 0.000 |
| zero_hit_rate_paraphrase | 1.000 |
| mean_score_ratio | 0.396 |
| location_correct_rate | 1.000 |
| metadata_hit_rate | 1.000 |
| catalogue_rev | f0714b2 |

## Deviations/ERRATA

- None from the bean's EARS acceptance or the plan recipe. F02 (FIND_LIMIT=50 vs
  PLAN sketch's `--limit 10`) was explicitly "no action needed" per the prelude
  and was left untouched, as instructed — the frozen baseline uses the shipped
  FIND_LIMIT=50.
- Minor addition beyond the literal step list: refactored `run()`'s inline
  aggregation block into a standalone `aggregate_metrics(per_row)` function.
  This was required to satisfy F01 ("pure unit test ... independent of
  catalogue/golden.json") since the formula previously only existed inline
  inside `run()`, which always needs a catalogue + golden.json to reach it.
  Verified behavior-preserving: full suite delta is 0 new failures/errors and
  `run()`'s own tests (`RunnerAgainstRealCatalogueTest`, `MainCliTest`) still
  pass unchanged.
- Two extra determinism cycles run beyond the plan's literal "seed -> run once"
  step, per the supervisor's FREEZE-BEWEIS requirement (two independent runs
  pre-commit + one post-commit re-run diffed against the committed file). No
  scope creep — same recipe, repeated for proof, all transient/torn down.

## Notes for T(n+1)

- HARD GATE cleared: `cli/eval/results/baseline-f0714b2.json` is committed and
  immutable. Phase 2 (WS1 hybrid retrieval) may now land.
- Task 12 (re-measurement) must write a NEW file
  (`cli/eval/results/baseline-<new-rev>.json` or an explicitly distinct
  post-WS1 filename) — never touch `baseline-f0714b2.json` in place.
- The primary optimization signal WS1 must move: `zero_hit_rate_paraphrase`
  1.000 -> lower, ideally without regressing `zero_hit_rate_literal` (0.000)
  or `recall_at_1`/`recall_at_5`.
- `aggregate_metrics(per_row)` is now a stable, independently-tested seam —
  any future metric change should update `AggregateMetricsPureUnitTest`'s
  hand-computed expectations first (TDD), not just the real-catalogue
  integration tests.
