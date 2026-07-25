---
# okf-cli-ez6f
title: P2 — Seed hidden golden fixtures S1-S4
status: in-progress
type: task
priority: normal
tags:
    - to-review
created_at: 2026-07-25T18:13:09Z
updated_at: 2026-07-25T18:36:35Z
parent: okf-cli-2lpu
---

## Objective (User Story)
As the eval harness, I want reproducible hidden fixtures seeded into the real catalogue so that retrieval quality can be measured against known ground-truth without polluting real data permanently.

## EARS Acceptance
- WHEN `seed(root)` runs, THE module SHALL write exactly one `.md` per fixture (S1-S4) under real bundles, each reachable by `iter_concepts` (okf-cli.py:89-98).
- WHEN `teardown(root)` runs after any partial seed, THE module SHALL remove every `_`-prefixed fixture file it owns (idempotent, no residue).
- WHEN invoked as `python3 fixtures.py --root <cat> --seed|--teardown`, THE module SHALL run the matching function and print affected paths.
- THE seed token SHALL NOT appear in any real catalogue concept (pre-seed `find` returns zero hits).

## Success Criteria
- SC-001: token has 0 `find` hits before seed.
- SC-002: 4 fixture files exist after seed, 0 after teardown.
- SC-003: `__main__` CLI dispatches --seed/--teardown.

## Fixture placement (EVAL-DESIGN.md:7-17)
S1 token in Title+H2+Body correct bundle; S2 as S1 in WRONG bundle; S3 correct bundle, generic title, no tags, token body-only; S4 correct bundle, type/tag wrong/missing.
## Affected code
- Create `cli/eval/fixtures.py`: `SEED_TOKEN`, `FIXTURES`, `seed()`, `teardown()`, `__main__` argparse.
- Test: `cli/test_eval_fixtures.py`
Produces `SEED_TOKEN`/`FIXTURES`/`seed`/`teardown` consumed by P3,P4,P5,P12. Full steps: PLAN.md Task 2.
Commit: `feat(eval): seed/teardown hidden golden fixtures S1-S4`


## Summary

Implemented `cli/eval/fixtures.py` (SEED_TOKEN=`zqxeval`, FIXTURE_PREFIX=`_okfeval-`,
4 `Fixture` namedtuples S1-S4, `seed()`, `teardown()`, `__main__` argparse
`--root/--seed|--teardown`) plus `cli/test_eval_fixtures.py` (6 tests, TDD RED
proven by temporarily removing fixtures.py before implementing). Target
bundles are picked deterministically via `_pick_bundles()`: first two
non-symlink real bundles from `list_bundles()` (currently `agent-memory`
correct, `ai-wiki` wrong) — symlinked bundles (e.g. `lean-stack-okf`) are
skipped so seeding never writes through a symlink into an unrelated repo.
`teardown()` is ownership-by-filename-prefix (walks every real bundle,
removes any `_okfeval-*.md`), not bundle-tracked, so it stays idempotent
across partial seeds even if bundle ordering later drifts.

## Test-Output

Baseline (`cli/test_okf_cli.py`, unchanged by this task — no edits to
`cli/okf-cli.py`):
```
Ran 98 tests in 0.056s
FAILED (failures=19, errors=2)
```
After (identical, confirming no regression):
```
Ran 98 tests in 0.061s
FAILED (failures=19, errors=2)
```

New test module (`cli/test_eval_fixtures.py`, TDD RED->GREEN):
RED (fixtures.py temporarily removed): `FileNotFoundError` on import.
GREEN:
```
Ran 6 tests in 0.193s
OK
```
6 tests: token-absent-before-seed (SC-001), seed-writes-4-teardown-removes-them
+ every fixture reachable via `iter_concepts` (SC-002), teardown-after-partial-seed
idempotent, seed-flag prints paths (SC-003), teardown-flag prints paths (SC-003),
--seed/--teardown mutually exclusive.

## Smoke

Direct CLI invocation against the real catalogue
(`/Users/erik/Obsidian/Knowledge-Catalogue`, rev `f0714b2`):
```
== pre-seed find (must be zero hits) ==
(no matches for: zqxeval)
== seed ==
.../agent-memory/_okfeval-s1.md
.../ai-wiki/_okfeval-s2.md
.../agent-memory/_okfeval-s3.md
.../agent-memory/_okfeval-s4.md
== verify: find post-seed ==
score: 4/6 title: "Zqxeval Sanity Concept"        path: agent-memory/_okfeval-s1
score: 4/6 title: "Zqxeval Metadata-Gap Concept"  path: agent-memory/_okfeval-s4  (type: <empty>)
score: 4/6 title: "Zqxeval Sanity Concept (S2)"   path: ai-wiki/_okfeval-s2       (wrong bundle, same rank as S1)
score: 1/6 title: "Generic Fixture Concept"       path: agent-memory/_okfeval-s3  (body-only)
== teardown ==
(same 4 paths printed)
== verify clean: find post-teardown ==
(no matches for: zqxeval)
== verify: files on disk (should be empty) ==
(empty)
```
`git status --short` in the catalogue repo after teardown: clean (only
pre-existing untracked `.claude/`, not touched by this task).

## Deviations/ERRATA

- `EVAL-DESIGN.md` (referenced by line numbers throughout PLAN.md Task 2) does
  not exist anywhere in the repo or elsewhere on disk — searched, zero hits.
  Not a blocker: the full S1-S4 placement table is reproduced verbatim in both
  the bean body and PLAN.md Task 2, so it was sufficient ground truth. Flagging
  for whoever owns Task 3/4 (golden.json/runner also cite EVAL-DESIGN.md line
  numbers) — that file may need to be authored or the plan's citations
  corrected to point at PLAN.md's own table instead.
- Fixture tags: S1/S2 carry `tags: [eval-fixture]` (not mentioned in the
  placement table, which is silent on tags for S1/S2) so a later Task 3
  `list(type=Concept, tag=eval-fixture)` row can hit S1 and miss S4 (S4 has
  `tags: []` and no `type`) — this directly supports the "Ziel-3 list rows"
  Task 3 needs (S1 hit / S4 miss) without pre-empting Task 3's own file.

## Notes for T(n+1)

- `fixtures.SEED_TOKEN` = `zqxeval`, `fixtures.FIXTURE_PREFIX` = `_okfeval-`.
- `fixtures.DEFAULT_ROOT` = `~/Obsidian/Knowledge-Catalogue` (used as the
  argparse `--root` default only; every function takes an explicit root).
- Correct bundle = `agent-memory` (S1/S3/S4), wrong bundle = `ai-wiki` (S2) —
  but Task 3/4 should call `fixtures._pick_bundles(root)` (or read
  `Fixture.rel_path`/`correct_bundle` off `fixtures._fixture_spec(root)`)
  rather than hardcoding these names, since the pick is catalogue-state-
  dependent (first two non-symlink bundles in `list_bundles()` order).
- `seed(root)`/`teardown(root)` both return lists of abs paths written/removed
  — Task 5's/Task 12's baseline-freeze/re-measure scripts should call
  `teardown()` in a `finally` around their `run()` invocation, same pattern
  used in `test_eval_fixtures.py`.
