---
# okf-cli-snxj
title: T10 Informative zero-hit for agent consumers
status: completed
type: task
priority: normal
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-26T08:30:10Z
parent: okf-cli-cskz
blocked_by:
    - okf-cli-uagv
---

Plan: `docs/okf-retrieval-architecture/PLAN.md` → **Task 10**. Follow it step by step; it carries the literal code and tests.

The consumer of `find` is usually an agent over MCP, and an agent can reformulate if it learns *why* nothing matched (Q13). Only the zero-hit branch changes (`cli/okf-cli.py:881-883`) — a query with hits prints exactly as before.

### Requirement 1: A zero hit hands back something to reformulate with

**Objective:** As an agent whose query returned nothing, I want the nearest registered tags, so that I can reformulate instead of giving up.

#### Acceptance Criteria

1. WHEN a query yields no hits THE CLI SHALL print the registered tag slugs closest to the query's terms, and a concrete retry suggestion.
2. IF no tag is close enough THEN THE CLI SHALL print the plain no-match line without suggestions.
3. THE suggestion lookup SHALL use fuzzy string matching only, so that it also works on the fully degraded path with no index, no cache and no network.
4. THE output for a query WITH hits SHALL be unchanged.

#### Success Criteria

- SC-01: `_zero_hit_suggestions(root, "tailscal")` contains `tailscale`.
- SC-02: `_zero_hit_suggestions(root, "zzzzqqqq")` returns `[]`.
- SC-03: `find tailscal` prints `(no matches for: tailscal)` and names `tailscale`.
- SC-04: the fixture gate still prints `GATE: PASS` — `cli/eval/runner.py:64` only parses `score:`/`path:` lines, so the extra lines cannot confuse it. Verify, do not assume.
- SC-05: `python3 -m unittest discover -s cli -p 'test_*.py'` stays at exactly 19 failures / 2 errors.

_Requirements: PLAN.md Task 10 · QUESTIONS Q13 · TASKS.md T07_

## Steps

- [ ] Write the failing `ZeroHitSuggestions` tests
- [ ] Run them, confirm they fail for the stated reason
- [ ] Add `_zero_hit_suggestions()` using `difflib`; extend the zero-hit branch
- [ ] Tests pass; suite still 19F/2E
- [ ] Re-run the gate command from the measurement task, confirm `GATE: PASS`
- [ ] Commit `feat(cli): suggest nearest tags on zero hit`

## Recommended Skills

- `superpowers:test-driven-development`



## PRELUDE 2026-07-26 — carried over from T09 (measured facts, not estimates)

**The residual zero-hit set you are writing output for: 8 of 48 queries (0.1667 combined)** —
7 of 40 in `queries_v2.json`, 1 of 8 in `queries_real.json`. Down from 0.979. Identify the
exact rows via `docs/okf-retrieval-architecture/eval/remeasure.py` and
`docs/okf-retrieval-architecture/eval/shipped_v2.json`.

**Do NOT assume your `(no matches ...)` branch covers the `okf-cli-uumj` squeeze-out cases.**
It does not, by construction: in those cases the target IS a hit — it is merely truncated out
of the output window. A zero-hit message will never fire for them. Measured by T09 and
independently reproduced by the reviewer: 5 of 48 queries (10.4%) reach the mechanism at all,
and of those **5 of 5 (100%)** lose their target from the window if that one concept has no
`concept_emb` row. Affected concepts: tailscale-subnet-routing, data-ui-convention,
replikations-playbook, ai-operating-system, immich.

Gate state entering T10 (all four criteria passed, no retune, reviewer-reconfirmed):
zero-hit 0.1667 (<= 0.30) · MRR 0.4519 (>= 0.35) · real-query zero-hit 0.125 (<= 0.25) ·
p50 0.621 s (<= 2.0 s). Baseline: 248 tests, exactly 19 failures / 2 errors BOTH with
`VOYAGE_API_KEY` set and with `env -u VOYAGE_API_KEY`.


## Summary

Implemented `_zero_hit_suggestions(root, query, limit=5)` (cli/okf-cli.py) and wired it into `cmd_find`'s zero-hit branch: on `(no matches for: <query>)` the CLI now also prints `nearest registered tags: <a, b, ...>` and `try: okf-cli find "<a> <b>"` when `difflib.get_close_matches` (cutoff 0.7) finds any registered tag close to a query term; prints nothing extra when it does not. A query with hits is byte-identical to before — only the zero-hit branch changed. Also added a PF-4 adversarial test proving the zero-hit branch adds no stderr note of its own when it coincides with degraded arms (2 notes total, not 3). Full gate re-run against the live catalogue: `GATE: PASS` (fixtures seeded, embedded, scored, gated, torn down, `.tagvec`/`.fts` cleaned — catalogue left with 0 stray `_okfeval-*` files/rows, confirmed by count).

Commits: `edc2347` feat(cli): suggest nearest tags on zero hit (cli/okf-cli.py, cli/test_okf_cli.py, cli/eval/results/architecture-0d20b07.json — the gate-run evidence for this task, generated at HEAD=0d20b07 before this commit).

## Test-Output

Full suite, both env directions, before AND after this change:

Before (HEAD=0d20b07, VOYAGE_API_KEY set):
```
Ran 248 tests in 17.248s
FAILED (failures=19, errors=2)
```
Before (env -u VOYAGE_API_KEY):
```
Ran 248 tests in 14.007s
FAILED (failures=19, errors=2)
```

After (HEAD=edc2347, VOYAGE_API_KEY set):
```
Ran 252 tests in 17.095s
FAILED (failures=19, errors=2)
```
After (env -u VOYAGE_API_KEY):
```
Ran 252 tests in 13.730s
FAILED (failures=19, errors=2)
```

New-class-only run (GREEN):
```
$ python3 -m unittest cli.test_okf_cli.ZeroHitSuggestions cli.test_okf_cli.ZeroHitSuggestionsPF4 -v
test_near_miss_term_suggests_the_registered_tag ... ok
test_output_names_the_suggestions ... ok
test_unrelated_query_may_return_nothing ... ok
test_exactly_one_note_per_degraded_arm_no_third_for_zero_hit ... ok
Ran 4 tests in 0.003s
OK
```

Mutation probe (cutoff 0.7 -> 0.95 in `_zero_hit_suggestions`): 3 of 4 tests failed for the right reason (fuzzy match no longer found at the tightened cutoff — `AssertionError: 'tailscale' not found in ...`); `test_unrelated_query_may_return_nothing` stayed green (already an empty-list case, correctly insensitive to the mutation). Reverted the one-line change; `md5 cli/okf-cli.py` matched before/after mutation: `f45b0ddecaeb1e992a6d4d32c243262e`.

Live-catalogue gate (Task 9 Step 4, re-run against `~/Obsidian/Knowledge-Catalogue`):
```
GATE: PASS
```
Cleanup verified: `find $ROOT -name "_okfeval-*" | wc -l` -> `0`; `SELECT COUNT(*) FROM concept_emb WHERE path LIKE '%/_okfeval-%'` -> `0`. `git status --short` in that repo: empty (no commit made there, per constraint).

## Smoke

Real subprocess CLI run (not the in-process test harness) against a throwaway fixture catalogue, degraded on both arms (no `.fts`, no `.tagvec`), showing the actual command-line output:

```
$ python3 cli/okf-cli.py --root <tmp>/smoke_root find "tailscael"
note: lexical index absent — falling back to substring scan; run `okf-cli build-index` for BM25 ranking
note: semantic arm skipped (.tagvec cache/concept embeddings absent) — lexical results only
(no matches for: tailscael)
nearest registered tags: tailscale
try: okf-cli find "tailscale"
```

Two stderr notes (one per degraded arm, PF-4-compliant), stdout carries the zero-hit line plus the new suggestion lines — matches the PF-4 unit test exactly. Fixture removed after the run.

## Deviations/ERRATA

None against the shipped Task 10 code — `_zero_hit_suggestions()` and the `cmd_find` zero-hit branch are verbatim from PLAN.md Task 10 Step 3 (post-fix-commit 0d20b07). Two process notes, not code deviations:

1. **Line numbers.** PLAN.md cites `cli/okf-cli.py:881-883` for the zero-hit branch; by the time this leaf ran it was at line ~1154-1156 (T13's FTS work and other intervening tasks shifted the file). Located it by content (`(no matches for:`), not by line number — no functional deviation.
2. **Fixture-query defect, already resolved upstream.** I found (verified live, not assumed) that PLAN.md's original Task 10 fixture query `"tailscal"` is a literal substring of the registered tag `"tailscale"`, so the degraded substring-scan lexical arm scores a real hit (2/6) on the tags field and the zero-hit branch never fires — `test_output_names_the_suggestions` failed on the `assertIn`, not on the intended `AttributeError`. Flagged via `herdr pane run w2B:pG`. The plan author fixed PLAN.md itself in commit `0d20b07` (query -> `"tailscael"`, a transposition typo, not a truncation) before I continued; I re-read the corrected plan and implemented against it, so my test fixtures are the plan's literal text as of `0d20b07` — no local invention left in the repo.

## Notes for T11

**Feature-bounding finding (plan-author-mandated note, carries forward into T13 documentation):** `_zero_hit_suggestions()` reaches typos and synonyms ONLY. A truncated or partially-typed query term can never reach this branch by construction — both the substring-scan lexical arm and the FTS5 arm (`"term"*` prefix query) match any prefix of a registered tag before the zero-hit branch is ever entered, so `_zero_hit_suggestions` never gets a chance to run for a truncation. Only a query whose edit-distance from the target is NOT a pure-prefix relationship (typo, transposition, synonym) can produce a genuine zero-hit that this feature then rescues. A reader who does not know this will wonder why suggestions stay silent on a half-typed query — this is that answer.

T11 (`okf-cli-ftri`, `--expand-tags`) reads `all_tags(root)`, `tokenize()`, `difflib` and `_query_vector`/`_expand_query_tags` per PLAN.md Task 11 — none of those interfaces were touched by this task; `_zero_hit_suggestions()` is a new, independent helper that does not intersect T11's expansion path. The zero-hit branch in `cmd_find` (now ending in `return` after printing suggestions) is unchanged in control flow otherwise — T11 modifies the CONFIDENT-lexical-arm gate and `semantic_ranking()`, both upstream of where this branch fires, so no interface collision expected.
