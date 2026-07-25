---
# okf-cli-ez6f
title: P2 — Seed hidden golden fixtures S1-S4
status: in-progress
type: task
priority: normal
created_at: 2026-07-25T18:13:09Z
updated_at: 2026-07-25T18:30:45Z
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
