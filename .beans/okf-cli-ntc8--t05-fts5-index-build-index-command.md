---
# okf-cli-ntc8
title: T05 FTS5 index + build-index command
status: in-progress
type: task
priority: high
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-26T05:41:35Z
parent: okf-cli-cskz
blocked_by:
    - okf-cli-48qk
---

Plan: `docs/okf-retrieval-architecture/PLAN.md` → **Task 5**. Follow it step by step; it carries the literal code and tests.

The lexical arm of the measured architecture is FTS5 + BM25 (`DESIGN.md`), with `porter unicode61 remove_diacritics 2` and prefix matching — the best measured variant (R32). This task builds and persists the index; Task 6 queries it.

### Requirement 1: A persistent, optional lexical index

**Objective:** As a user of the CLI, I want a search index I can rebuild with one command, so that lexical retrieval is fast and reproducible without becoming a precondition for using the catalogue.

#### Acceptance Criteria

1. THE CLI SHALL expose a `build-index` command that writes `<root>/.fts/fts.sqlite`.
2. THE index SHALL hold, per concept, its path, its frontmatter type, its title, its tags and its body.
3. THE builder SHALL write into a temporary sibling file and atomically replace the target, so that an interrupted build never leaves a half-written index in place of a working one.
4. THE builder SHALL be idempotent — rebuilding SHALL NOT duplicate rows.
5. THE builder SHALL make no network call.
6. THE staleness check SHALL report stale WHEN the catalogue's concept count differs from the indexed count OR any concept file is newer than the newest file seen at build time, and SHALL do so using file metadata only, never by reading concept bodies.
7. IF the index metadata is missing or unreadable THEN THE staleness check SHALL report stale.

#### Success Criteria

- SC-01: `build_fts_index(root)` on a two-concept fixture returns `(2, "<root>/.fts/fts.sqlite")` and the file exists.
- SC-02: the `docs` table maps `b/one -> Runbook` and `b/two -> Konzept`.
- SC-03: a second build still yields 2 rows total.
- SC-04: a freshly built index is not stale; adding one concept file makes it stale.
- SC-05: `okf-cli --root ~/Obsidian/Knowledge-Catalogue build-index` reports `indexed 2437 concept(s)`.
- SC-06: `python3 -m unittest discover -s cli -p 'test_*.py'` stays at exactly 19 failures / 2 errors.

_Requirements: PLAN.md Task 5 · DECISIONS D14, D15 · TASKS.md T13 · REFERENCES R32_

## Steps

- [x] Add the five module-level test imports (deliberate departure from the file's local-import style — see the plan)
- [x] Write the failing `FtsIndexBuild` tests
- [x] Run them, confirm they fail for the stated reason
- [x] Add the lexical-index section: constants, `_fts_db_path`, `build_fts_index`, `_fts_index_stale`, `cmd_build_index`
- [x] Register the `build-index` subparser and its dispatch entry (`cli/okf-cli.py:2321-2328`)
- [x] Tests pass; suite still 19F/2E
- [x] Build the live index; check whether the catalogue's `.gitignore` needs a `.fts/` line — report it, do NOT commit in that repo
- [x] Commit `feat(cli): add fts5 lexical index + build-index`

## Recommended Skills

- `superpowers:test-driven-development`



## PRELUDE 2026-07-26 — carried over from the T04 review (ce-specs-reviewer on okf-cli-48qk)

Handle these BEFORE the T05 work proper; the first one is substantive for your task.

**I01 (low, but it lands exactly on your seam).** The shipped `tokenize()` is NOT fully
equivalent to the measured tokenizer, and T04's bean summary slightly overstates parity
("matches the FTS arm tokenization measured in eval/fts_arm.py:56").

- Shipped: `re.split(r"[\W_]+", s.lower())` at `cli/okf-cli.py:598-602` — splits on underscore.
- Measured: `[^\wäöüÄÖÜß]+` at `docs/okf-retrieval-architecture/eval/fts_arm.py:56` — does NOT
  split on underscore. Note the `äöüÄÖÜß` clause there is INERT: `\w` already covers those
  characters under Python 3, so the measured regex reduces to plain `\W+`.
- Verified divergence: `tokenize("build_tagvec")` -> `['build','tagvec']` vs measured
  `['build_tagvec']`; same for `café_menü`. Across German words, ß, digits, CJK and accented
  non-German Latin the two agree — underscore is the only disagreement dimension.
- Why it does not invalidate D14: the reviewer checked all three measured query sets
  (`queries_generated.json`, `queries_v2.json`, `queries_real.json`, 98 queries) and none
  contains an underscore, so R43's 0.437 is unaffected. Underscore-splitting is also mandated
  by T04's own AC2/SC-02 and matches the previous behaviour for identifiers.

**What you must do with it:** decide and document explicitly how the QUERY side tokenizes
relative to what goes into the FTS index, instead of leaving parity implied. Keep in mind the
layering already noted by T04: the Python-level `tokenize()` does NOT fold (ä stays ä), while
FTS5's own `unicode61` tokenizer inside SQLite folds (ä -> a, per REFERENCES R41). Two layers,
different rules — be deliberate about which one you are in at each call site.

**I02 (low, cosmetic, optional).** `flags=re.UNICODE` at `cli/okf-cli.py:601` is a no-op in
Python 3 (proven: dropping it left all 7 `TokenizeUnicode` tests green). Not wrong, just
misleading about why the fix works. If you touch that line anyway, drop the flag or fix the
docstring; do not make a separate commit for it.

**I03 (cosmetic).** T04's bean still shows its 5 step checkboxes unticked despite
`status: completed`. Bookkeeping only, mentioned so the pattern is not repeated: tick your own
boxes as you go.

**Verified context you can build on:** `tokenize()` has exactly two callers,
`cli/okf-cli.py:772` (`_semantic_hit_dicts`) and `cli/okf-cli.py:792` (`cmd_find`), both
introduced by this plan — no pre-existing caller relies on the old ASCII-only splitting.
Baseline entering T05: 204 tests, 19 failures / 2 errors.

Source: ce-specs-reviewer APPROVED verdict on okf-cli-48qk, 2026-07-26 (commits 4ee120d, b721cf4).
