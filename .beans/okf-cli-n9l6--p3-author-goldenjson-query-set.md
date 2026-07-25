---
# okf-cli-n9l6
title: P3 — Author golden.json query set
status: todo
type: task
priority: normal
created_at: 2026-07-25T18:13:09Z
updated_at: 2026-07-25T18:40:55Z
parent: okf-cli-2lpu
blocked_by:
    - okf-cli-ez6f
---

## Objective (User Story)
As the eval runner, I want a golden file mapping queries to expected concept paths + thresholds so that retrieval can be scored deterministically per scenario and query class.

## EARS Acceptance
- THE golden file SHALL contain >=2 rows per fixture (one `literal`, one `paraphrase`) plus the S4 index-walk and S1/S4 `list`-metadata rows (EVAL-DESIGN.md:27-32).
- THE golden file SHALL contain an explicit S2 location row: `list --scope=<correct-bundle>` expected to MISS the S2 fixture (EVAL-DESIGN.md:12,16-17), with an `expect` (hit/miss) field on `list` rows.
- EACH row SHALL name the verb (find/list/index) and the expected concept path.

## Success Criteria
- SC-001: >=2 rows/fixture with literal+paraphrase classes.
- SC-002: explicit S2 `list --scope` miss row present with `expect:miss`.
- SC-003: JSON (stdlib), no PyYAML dependency.

## Affected code
- Create `cli/eval/golden.json`: rows `{id, verb, query, class, expected_path, min_rank, min_score_ratio, expect}`. `expected_path` matches `bundle/concept-id` (okf-cli.py:560,571).
Consumes `FIXTURES` (P2). Full steps: PLAN.md Task 3.
Commit: `feat(eval): add golden.json query set for S1-S4`

## Prelude 2026-07-25 (from P2 completion, okf-cli-ez6f)

- EVAL-DESIGN.md EXISTS at ~/Obsidian/Vault/okf-revision/EVAL-DESIGN.md (P2 bean's original deviation note claiming otherwise was wrong; corrected). PLAN.md Task 3 line-refs resolve against it.
- S1 and S2 fixtures carry an extra 'tags: [eval-fixture]' (P2 deviation, deliberate) so Task 3 can build a list(type,tag) hit/miss row (S1 hit / S4 miss).
- Fixtures are TRANSIENT: wrap any golden-query validation runs in cli/eval/fixtures.py seed()/teardown() — catalogue must end clean.
