---
# okf-cli-ntc8
title: T05 FTS5 index + build-index command
status: completed
type: task
priority: high
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-26T05:46:56Z
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


## Summary

Added the persistent, optional FTS5 lexical index (D14/D15): `build_fts_index(root)`
creates `<root>/.fts/fts.sqlite` via `porter unicode61 remove_diacritics 2`, field
weights title 3 / tags 2 / body 1 (`FTS_BM25_WEIGHTS`), writes into a `.tmp` sibling
and `os.replace()`s it so an interrupted build never leaves a half-written index in
place. `_fts_index_stale(root, conn)` is a stat()-only staleness check (concept count
+ newest mtime, never reads a body); missing/unreadable `fts_meta` counts as stale.
`cmd_build_index` wires it to a new `build-index` subcommand, registered next to
`reindex` and dispatched alongside the other subcommands.

**I01 resolved (query-side vs index-side tokenization, PRELUDE):** documented as a
code comment in the new lexical-index section (`cli/okf-cli.py`, above `FTS_DIRNAME`).
Decision: two tokenization layers apply in deliberate sequence, not by accident.
1. Python `tokenize()` (word-splitting, lowercasing, underscore-as-separator) decides
   QUERY TERM BOUNDARIES before a term is quoted into an FTS5 MATCH expression — this
   is exactly what T06's plan already does literally (`terms = tokenize(query)`, then
   `'"{}"*'.format(t)` per term).
2. FTS5's own configured tokenizer (`porter unicode61 remove_diacritics 2`) is applied
   a SECOND time by SQLite itself, both to indexed title/tags/body text at build time
   AND to each quoted term inside a MATCH expression at query time.
Net effect: no parity gap. Verified empirically (not inferred) with a throwaway
in-memory FTS5 table:
- `docs MATCH '"café"*'` (unfolded query term) DOES match an indexed row containing
  "café_menü"/"cafe" — SQLite folds the quoted MATCH term through the table's own
  tokenizer before comparing.
- `docs MATCH '"qualitätsmanagement"*'` (unfolded) DOES match the porter-stemmed,
  diacritic-folded indexed token ("qualitatsmanag").
- `fts5vocab` on an indexed "build_tagvec" shows unicode61 splits it into "build" /
  "tagvec" on its own — the same split Python `tokenize()` already performs, so there
  is no divergence on the underscore dimension either, contrary to what might have
  been feared from the I01 finding (which was about Python `tokenize()` vs. the
  *measured eval script's* regex, a different comparison).
So: Python `tokenize()`'s lack of diacritic-folding never leaks into the FTS5 arm's
actual matching behaviour — SQLite closes that gap on every MATCH. T06 needs nothing
extra to keep this property; it should just keep quoting each token as `"term"*`.

**I02 (cosmetic, `flags=re.UNICODE` no-op):** not touched — plan explicitly said only
touch it if the line was touched anyway for other reasons; it wasn't.

**I03 (checkbox bookkeeping):** this bean's own step checkboxes are ticked as work
progressed (see `## Steps` above), per the reviewer's forward-guard.

## Test-Output

RED (confirms failing for the stated reason, `AttributeError` not e.g. an import error):

```
$ python3 -m unittest cli.test_okf_cli.FtsIndexBuild -v
ERROR: test_index_holds_path_type_and_tags (cli.test_okf_cli.FtsIndexBuild.test_index_holds_path_type_and_tags)
AttributeError: module 'okf_cli' has no attribute 'build_fts_index'
ERROR: test_new_concept_makes_the_index_stale (cli.test_okf_cli.FtsIndexBuild.test_new_concept_makes_the_index_stale)
AttributeError: module 'okf_cli' has no attribute 'build_fts_index'
ERROR: test_rebuild_is_idempotent (cli.test_okf_cli.FtsIndexBuild.test_rebuild_is_idempotent)
AttributeError: module 'okf_cli' has no attribute 'build_fts_index'
Ran 5 tests in 0.004s
FAILED (errors=5)
```

GREEN after implementation:

```
$ python3 -m unittest cli.test_okf_cli.FtsIndexBuild -v
test_build_creates_the_artefact_and_counts_concepts ... ok
test_fresh_index_is_not_stale ... ok
test_index_holds_path_type_and_tags ... ok
test_new_concept_makes_the_index_stale ... ok
test_rebuild_is_idempotent ... ok
Ran 5 tests in 0.013s
OK
```

Mutation probe (SC-04's staleness property is not tautological — a broken
`_fts_index_stale` actually breaks a test):

```
$ # replaced `return n != n_idx or newest > newest_idx` with `return False`
$ python3 -m unittest cli.test_okf_cli.FtsIndexBuild -v
test_new_concept_makes_the_index_stale ... FAIL
AssertionError: False is not true
Ran 5 tests in 0.014s
FAILED (failures=1)
$ # reverted byte-identically (git diff --stat confirms pure additions, no stray '-' lines)
$ python3 -m unittest cli.test_okf_cli.FtsIndexBuild -v
Ran 5 tests in 0.013s
OK
```

Full suite at commit point:

```
$ python3 -m unittest discover -s cli -p 'test_*.py'
Ran 209 tests in 14.358s
FAILED (failures=19, errors=2)
```

209 tests total (204 baseline + 5 new `FtsIndexBuild` tests), still exactly 19
failures / 2 errors — same pre-existing crosslink-suite failures as T04's baseline,
none newly introduced.

## Smoke

```
$ python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue build-index
indexed 2443 concept(s) -> /Users/erik/Obsidian/Knowledge-Catalogue/.fts/fts.sqlite
```

`.gitignore` check in the live catalogue repo (separate git repo, nothing committed
there):

```
$ grep -n "tagvec\|\.fts" ~/Obsidian/Knowledge-Catalogue/.gitignore
6:.tagvec/
```

`.fts/` is NOT ignored yet — needs a line added. Reporting per instructions, not
touching that repo: **please add `.fts/` to `~/Obsidian/Knowledge-Catalogue/.gitignore`**
(one line, next to the existing `.tagvec/` line). `git status --porcelain` in that
repo shows only `?? .fts/` — untracked, nothing staged or committed there.

## Deviations/ERRATA

- **SC-05 literal count unreachable (pre-flagged, not a fresh finding).** SC-05 says
  `indexed 2437 concept(s)`; the live run reports `indexed 2443 concept(s)`. This is
  the exact drift the parent epic already recorded as `LL-pending-02` ("plan grounded
  against a moving foreign repo" — the live catalogue grew from 2437 to 2443 between
  plan-writing and realization). The *intent* of SC-05 (a full, successful live build
  against the real catalogue, one line of confirmation output) is met; the literal
  number is not, because the number was never a stable target. No plan/code deviation
  — a pre-known environmental drift, documented instead of silently reconciled.
- No other deviations. Implementation follows the plan's literal code and tests
  verbatim (constants, `build_fts_index`, `_fts_index_stale`, `cmd_build_index`,
  subparser registration, dispatch entry, module-level test imports, `FtsIndexBuild`
  test class).

## Notes for T06

- `_fts_ranking` (T06) can rely on the FTS5-internal tokenizer to fold/stem quoted
  MATCH terms automatically — no extra folding needed on the Python side before
  quoting each `tokenize()` term as `"term"*`. See the I01 resolution above and the
  code comment above `FTS_DIRNAME` in `cli/okf-cli.py` for the empirical proof.
- `_fts_db_path(root)`, `FTS_BM25_WEIGHTS`, `build_fts_index`, `_fts_index_stale` are
  all in place and tested; T06 builds `_fts_ranking`/`_hydrate_hit` directly on top
  without needing to touch the Task 5 section.
- Live index built at `~/Obsidian/Knowledge-Catalogue/.fts/fts.sqlite` (2443 concepts)
  — available for T06's manual/smoke verification against the real catalogue, but
  that repo's `.gitignore` still needs the `.fts/` line (see Smoke section) before
  anyone runs `git status` there without noise.
- Baseline leaving T05: 209 tests, 19 failures / 2 errors, unchanged from T04's 19F/2E
  — the count went from 204 to 209 tests (5 new `FtsIndexBuild` tests), no new
  failures.
