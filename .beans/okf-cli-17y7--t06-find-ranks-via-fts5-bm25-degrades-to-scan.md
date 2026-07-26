---
# okf-cli-17y7
title: T06 find ranks via FTS5 BM25, degrades to scan
status: completed
type: task
priority: high
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-26T06:25:17Z
parent: okf-cli-cskz
blocked_by:
    - okf-cli-ntc8
---

Plan: `docs/okf-retrieval-architecture/PLAN.md` → **Task 6**. Follow it step by step; it carries the literal code and tests.

Replaces the substring full scan (`cli/okf-cli.py:801-837`, R01/R02) as the *ranking* arm, while keeping it in the tool as the degradation target (D15). Also removes the scan's cost: only the `limit` concepts that actually rank get read from disk.

**Output contract change.** When the FTS arm serves the query, `max_score` becomes `100` and each hit's score is `round(100 * s / top_s)`. The substring fallback keeps `6 * len(terms)` byte-for-byte. `cli/eval/gate.py:56-81` gates only on paraphrase zero-hit and literal S1 ranks — `mean_score_ratio` shifts but is not gated. Say so in the commit body.

### Requirement 1: Rank lexically via BM25, degrade to the scan

**Objective:** As a user, I want lexical ranking to use BM25 over the index when it exists and the old scan when it does not, so that I get better ranking without the tool ever becoming unusable.

#### Acceptance Criteria

1. WHEN a usable index exists THE lexical arm SHALL rank via `bm25()` with column weights title 3 / tags 2 / body 1, using prefix matching over the query terms.
2. IF the index file is absent or corrupt THEN THE lexical arm SHALL fall back to the substring scan and SHALL print one stderr note, and SHALL NOT raise.
3. THE `--type`, `--tag` and `--scope` filters SHALL narrow the indexed query without re-reading concept files.
4. THE `--tag` filter SHALL match whole tags only — a query for `tail` SHALL NOT match the tag `tailscale`.
5. WHEN the index is stale THE CLI SHALL print one stderr note and SHALL still return results.
6. THE substring fallback SHALL keep its scoring, its `contrib` breakdown and its `6 * len(terms)` scale unchanged, because the frozen eval baseline was recorded against it.
7. WHEN `--breakdown` is passed for an FTS-ranked hit THE CLI SHALL state that no field-level breakdown is available rather than printing an empty one.

#### Success Criteria

- SC-01: `_fts_ranking()` returns `None` without an index and `None` after the index file is overwritten with garbage.
- SC-02: with an index, a title match outranks a body-only match.
- SC-03: `type_filter="Runbook"` narrows to the Runbook concept; `tag_filter="tail"` returns `[]`; `scope="zz"` returns `[]`.
- SC-04: `find` without any index still prints `path: b/one` and `score: 3/6` — unchanged pre-plan output.
- SC-05: on the live catalogue a literal query still answers, and the timed run is not slower than before the change.
- SC-06: `python3 -m unittest discover -s cli -p 'test_*.py'` stays at exactly 19 failures / 2 errors.

_Requirements: PLAN.md Task 6 · DECISIONS D14, D15 · TASKS.md T13 · REFERENCES R01, R02, R32_

## Steps

- [x] Define the module-level `_run_find(root, query, **kw)` test helper (new — mirrors the per-class pattern at `cli/test_okf_cli.py:1376-1387`)
- [x] Write the failing `FtsRanking` and `FindDegradesWithoutIndex` tests (plus adversarial extras: absent-note count, unreadable-index D15 case, BM25-weights-applied)
- [x] Run them, confirm they fail for the stated reason
- [x] Add `_fts_ranking()` and `_hydrate_hit()`
- [x] Extract today's scan verbatim into `_substring_ranking()`
- [x] Add `_rank_lexically()` returning `(hits, max_score)`; call it from `cmd_find`
- [x] Add the `--breakdown` branch for FTS hits
- [x] Tests pass; suite still 19F/2E (225 tests total)
- [x] Verify on the live catalogue (literal query + timing)
- [x] Commit `feat(cli): rank lexically via fts5 bm25` (3c3c026), with the score-scale note in the body

## Recommended Skills

- `superpowers:test-driven-development`



## PRELUDE 2026-07-26 — carried over from the T05 review (ce-specs-reviewer on okf-cli-ntc8)

Handle these FIRST, as their own commit, before the T06 work proper. Both are coverage gaps
inherited from the plan's own test list — neither is a functional defect in T05, and both land
naturally in your task because T06 is where `MATCH` queries first appear.

**I01 (low).** The FTS5 tokenizer config is unprotected by any regression test. Proven: the
reviewer reduced `FTS_TOKENIZER` (`cli/okf-cli.py:685`) from `porter unicode61
remove_diacritics 2` to bare `"unicode61"` — dropping porter stemming AND diacritic folding —
and all 5 `FtsIndexBuild` tests stayed green, full suite unchanged at 19F/2E. Anyone can
silently break stemming/folding.
*Asked-for test:* query the REAL `build_fts_index` output and assert a match that only works
with the full tokenizer — e.g. unfolded `"café"*` against an indexed `cafe` token, or a
porter-stemming pair. Put it next to your `_fts_ranking` tests.

**I02 (low).** Bean AC7 of T05 ("IF index metadata is missing or unreadable THEN the staleness
check SHALL report stale") has no committed test. `_fts_index_stale`'s except-branch
(`cli/okf-cli.py:740-753`) was verified correct only by a live reviewer probe.
*Asked-for test:* open a garbage-byte or schema-less sqlite file and assert `_fts_index_stale`
returns `True` without raising.

**D15 IS YOURS — this is the substantive one.** The reviewer established that T05 correctly
does NOT implement the degradation path: no T05 code connects to a path that could be missing,
corrupt, or unreadable. The whole "missing/corrupt/unreadable -> substring scan with ONE
stderr note, never a hard fail" behaviour lives in your `_fts_ranking` (PLAN.md:917
`os.path.isfile` check, 940-952 `try/except sqlite3.DatabaseError` around the `connect()`).
Useful confirmation from the review: `sqlite3.OperationalError` IS a subclass of
`DatabaseError` (checked via `__mro__`), so the planned catch does cover permission-denied and
corrupt files — but you must SHOW it. Commit tests for all three cases: index absent, index
present but garbage bytes, index present but unreadable. Each must degrade with exactly one
stderr note and a normal exit, never an exception.

**Verified ground you can build on (reviewer-confirmed, not implementer-claimed):**
- `FTS_BM25_WEIGHTS = "0.0, 0.0, 3.0, 2.0, 1.0"` maps to path/ctype/title/tags/body =
  title 3 / tags 2 / body 1 as mandated. It is DEFINED but not yet consumed anywhere —
  applying it in the ranking call is your job, and "defined" is not "applied".
- `_fts_db_path`, `build_fts_index`, `_fts_index_stale` are in place and tested; build them on,
  no need to touch the Task 5 section.
- Staleness works for modified AND deleted concepts, not just additions (independently probed).
  Known, spec-mandated edge case (AC6): a body modified with a backdated mtime is NOT detected —
  metadata-only tradeoff, disclosed, not a defect.
- Tokenizer parity is settled empirically through the shipped index: unfolded `"café"*` hits
  an indexed `cafe`, unfolded `"qualitätsmanagement"*` hits via the porter-stemmed token, and
  `fts5vocab` shows `build_tagvec` split into `build`/`tagvec` exactly like Python
  `tokenize()`. You need NO extra folding logic on the query side.
- Live index available for manual checks: `~/Obsidian/Knowledge-Catalogue/.fts/fts.sqlite`
  (13.2 MB, 2443 concepts). That is a SEPARATE git repo — read it, never commit in it.
- Baseline entering T06: 209 tests, 19 failures / 2 errors.

Source: ce-specs-reviewer APPROVED verdict on okf-cli-ntc8, 2026-07-26 (commits 67a8bbb, a678008).


## Summary

Ships T13 part 2 (PLAN.md Task 6): `cmd_find`'s lexical arm now ranks via FTS5
BM25 (title 3 / tags 2 / body 1, prefix matching) when the persistent
`<root>/.fts/fts.sqlite` index exists and is usable, and degrades to the
pre-existing substring scan — extracted verbatim into `_substring_ranking()`
— when it does not. `--type`/`--tag`/`--scope` narrow inside the SQL query
(no file re-reads); `--tag` matches whole tags only. FTS hits report on a
0..100 scale (`round(100 * s / top_s)`); the substring fallback keeps its
`6 * len(terms)` scale, `contrib` breakdown, and scoring byte-identical
(frozen eval baseline). `--breakdown` on an FTS hit now states no
field-level breakdown is available instead of KeyError-ing on a missing
`contrib`. `FTS_BM25_WEIGHTS` (defined since T05, consumed nowhere) is now
the weight vector actually passed into `bm25()` — proven, not assumed, by a
dedicated adversarial test (see Test-Output).

PRELUDE (own commit, `0d5f717`, before Task 6 proper): I01/I02 gap-closing
regression tests carried over from the T05 review — FTS_TOKENIZER
(porter+unicode61+diacritics) and `_fts_index_stale`'s except-branch were
previously correct-but-unproven.

D15 degradation (the substantive part of this task, per PRELUDE): all three
failure modes — index absent, index present but garbage bytes, index
present but unreadable (permission denied) — degrade to the substring scan
with **exactly one** stderr note and a normal (non-raising) exit. Verified
by dedicated tests per case, not inferred from the corrupt-file case alone.

## Test-Output

**PRELUDE (I01/I02) — RED via mutation, not via TDD-red** (the guarded
behaviour already existed and was correct; these are regression locks, so
"RED" means "the test catches an induced regression," proven then
reverted):

```
$ mutate FTS_TOKENIZER -> "unicode61" (drops porter+diacritics)
FAIL: test_porter_stem_bridges_study_query_to_studies_token
AssertionError: Lists differ: [] != ['b/one']
$ git checkout -- cli/okf-cli.py   # byte-identical revert
OK (3 tests)

$ mutate _fts_index_stale except clause -> drop sqlite3.DatabaseError
ERROR: test_garbage_byte_file_reports_stale_without_raising
  sqlite3.DatabaseError: file is not a database
ERROR: test_schemaless_db_reports_stale_without_raising
  sqlite3.OperationalError: no such table: fts_meta
$ git checkout -- cli/okf-cli.py   # byte-identical revert
OK (3 tests)
```

**Task 6 — true RED first** (`_fts_ranking` did not exist yet):

```
$ python3 -m unittest cli.test_okf_cli.FtsRanking cli.test_okf_cli.FindDegradesWithoutIndex cli.test_okf_cli.FtsBm25WeightsApplied -v
ERROR: test_type_filter_narrows ... AttributeError: module 'okf_cli' has no attribute '_fts_ranking'
ERROR: test_unreadable_index_degrades_to_none_with_one_note ... AttributeError: ...
ERROR: test_title_weight_outranks_denser_body_match ... AttributeError: ...
FAIL: test_find_without_index_prints_exactly_one_stderr_note ... AssertionError: 0 != 1
Ran 12 tests in 0.020s
FAILED (failures=1, errors=10)
```

GREEN after Steps 3-5:

```
$ python3 -m unittest cli.test_okf_cli.FtsRanking cli.test_okf_cli.FindDegradesWithoutIndex cli.test_okf_cli.FtsBm25WeightsApplied cli.test_okf_cli.FtsTokenizerRegression cli.test_okf_cli.FtsIndexStaleDegrades -v
Ran 16 tests in 0.026s
OK
```

**Mutation probe 1 — FTS_BM25_WEIGHTS actually consumed** (bean's second
substantive point: "defined is not applied"):

```
$ mutate: sql = "SELECT path, bm25(docs) AS r FROM docs WHERE docs MATCH ?"  # weights dropped
FAIL: test_title_weight_outranks_denser_body_match
AssertionError: 'b/bodyhit' != 'b/titlehit'
$ revert via Edit (byte-identical)
OK (2 tests)
```

Fixture note: the crossover (3 body occurrences) was measured, not guessed
— at 1-3 reps unweighted bm25 already favours the denser body match while
weighted (title=3/body=1) still favours the single title hit; above ~4
reps even the weighted score flips. `test_unweighted_bm25_would_rank_body_first`
is a control probe against raw `bm25(docs)` confirming the fixture's
premise so the main test cannot be a fluke of this specific corpus.

**Mutation probe 2 — double-stderr-note bug found by adversarial testing,
not in the original plan.** `_fts_index_stale()`'s own except-branch
swallows `sqlite3.DatabaseError` and reports "stale" (T05 AC7, correct and
locked). Calling it BEFORE the real query (as the plan's literal Step 3
code did) meant a corrupt/garbage index printed the "stale" note first
(from `_fts_index_stale`'s defensive True) and then the "unusable" note
(from `_fts_ranking`'s own except) — two notes for one degradation event,
violating "exactly one stderr note":

```
$ revert the reorder (stale-check before execute, matching original plan literal code)
FAIL: test_corrupt_index_prints_exactly_one_stderr_note
AssertionError: 2 != 1
$ re-apply the fix (execute first, then stale-check) via Edit (byte-identical)
OK
```

Fix: run the real query first (raises DatabaseError on a corrupt file,
caught once by the existing except); check staleness only after a
successful query. `_fts_index_stale()` itself is untouched — its own
contract (I02, locked) is unaffected.

**Full-suite gate, before -> after:**

```
before (T04/T05 baseline): 209 tests, 19 failures / 2 errors
after PRELUDE commit (0d5f717): 212 tests, 19 failures / 2 errors
after Task 6 commit (3c3c026): 225 tests, 19 failures / 2 errors
```

Command: `python3 -m unittest discover -s cli -p 'test_*.py'`

## Smoke

Live catalogue: `~/Obsidian/Knowledge-Catalogue` (2443 concepts,
`.fts/fts.sqlite` present, 13.2 MB).

Literal query, FTS-ranked (0..100 scale, confirms weights + prefix
matching against real data):

```
$ python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue find "data-ui konvention namensschema" --limit 5
score: 100/100  title: Data-UI-Pflicht in Storybook und Live-Code
score: 94/100   title: Baustein data-ui Konvention
score: 81/100   title: Baustein Hover-Label und Indicator
...
```

Timing (SC-05, "not slower than before" — the 2581-file scan is gone, only
`limit` files are hydrated):

```
$ time python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue find "tailscale" --limit 5 >/dev/null
0.07s user 0.02s system 98% cpu 0.091 total
```

Live degradation (index parked via `mv`, restored via `mv` back —
`os.rename`/`mv` never copies bytes, so this is a structural move, not a
byte-copy-and-compare; `ls -la` size match after the fact is a sanity
check that the same file came back, not proof of content integrity):

```
$ mv .fts/fts.sqlite .fts/fts.sqlite.smoketest-park
$ python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue find "tailscale" --limit 3
note: lexical index absent — falling back to substring scan; run `okf-cli build-index` for BM25 ranking
score: 4/6  title: Portal Remote Review via tailscale serve
... (6*len(terms) scale, substring scan working)
exit: 0
$ mv .fts/fts.sqlite.smoketest-park .fts/fts.sqlite   # restored
```

`--breakdown` on an FTS hit (AC7):

```
$ python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue find "tailscale" --limit 2 --breakdown
contrib: bm25 (fts5 index; field-level breakdown not available)
```

`--tag tail` does not match `tailscale` on the live corpus (AC4):

```
$ python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue find "tailscale" --tag tail --limit 3
(no matches for: tailscale)
```

## Deviations/ERRATA

1. **Plan-code fix landed upstream, not by me (no deviation on my part).**
   The plan's original `_fts_ranking()` (PLAN.md Step 3, pre-`daac681`)
   printed no stderr note for the absent-index case, contradicting D15
   ("absent/stale -> degradation with an stderr note"). Raised via
   `herdr pane run w2B:pG "FRAGE okf-cli-17y7: ..."` before implementing;
   the plan author fixed PLAN.md directly (commit `daac681`) and instructed
   me to follow the corrected plan as-is. Implemented as corrected.

2. **Double-stderr-note bug, fixed in my own new code (real deviation from
   the plan's literal Step 3 code, not from D15).** Found by my own
   adversarial test for the corrupt-index case (mandated by the PRELUDE:
   "each must degrade with exactly ONE stderr note"). The plan's literal
   code checked `_fts_index_stale()` before running the real query; a
   corrupt/garbage index file makes `_fts_index_stale()`'s own except-branch
   fire (by design, T05 AC7/I02) and report "stale" BEFORE the real query
   raises `DatabaseError` and prints "unusable" — two notes for one
   degradation. Reordered: run the query first, check staleness only after
   a successful query. Mutation-probed both directions (see Test-Output).
   `_fts_index_stale()` itself is unchanged.

3. **`test_eval_runner.py::RunnerAgainstRealCatalogueTest` updated (file
   outside this task's stated `Test:` scope, fixed anyway to hold the
   19F/2E gate).** This pre-existing integration test seeds fixture
   concepts directly into the live catalogue and immediately expects them
   findable at rank 1. Once FTS ranking prefers the live catalogue's real,
   persistent `.fts/fts.sqlite` (built in an earlier task), a
   freshly-seeded fixture concept that postdates that index build is
   invisible to the FTS arm — not a bug, an inherent property of "stale
   index still returns results FROM the index" (D15/AC5). This is not
   something any correct T06 implementation could avoid without either
   rebuilding the index on every `find` call (defeats the performance goal)
   or ignoring the index entirely for the live root. Fix: the test now
   parks `.fts/fts.sqlite` out of the way for its own duration and restores
   it byte-identically in `tearDown` regardless of pass/fail, so `find`
   degrades cleanly to the substring scan (which always reads fixtures
   fresh) for this specific integration test. **Correction (T06 review
   round 1, I01):** the original wording here — "restored byte-identically,
   verified by size match" — was imprecise on two counts.
   `os.rename`/`mv` never copies bytes at all, so "byte-identical" is a
   structural property of a rename, not something a size check verifies;
   and the size match after manual smoke tests said nothing about whether
   the parking window was exception-safe. It was not: `setUp` renamed the
   index and called `runner.run()` with no `try/finally`, and unittest
   never calls `tearDown` when `setUp` itself raises, so any exception
   inside `runner.run()` would have stranded the live artefact under a
   `.parked-by-test-eval-runner` name with no automatic recovery. Fixed in
   Fix round 1 below: `_park_fts_index()` is now a context manager with its
   own `try/finally`, tested in isolation (including a forced-exception
   case) against a throwaway temp directory, never the live path.

4. **Extra tests beyond the plan's literal Step 1 list, per the PRELUDE's
   explicit demand for three D15 cases and a real weights-applied proof.**
   The plan's literal `FtsRanking`/`FindDegradesWithoutIndex` classes cover
   absent and corrupt but not the third D15 case (unreadable/permission-
   denied), and contain no test that would fail if `FTS_BM25_WEIGHTS`
   stopped being passed. Added: `test_unreadable_index_degrades_to_none_with_one_note`,
   `test_absent_index_prints_exactly_one_stderr_note`,
   `test_corrupt_index_prints_exactly_one_stderr_note`,
   `test_find_without_index_prints_exactly_one_stderr_note`, and the whole
   `FtsBm25WeightsApplied` class. All requested explicitly in this task's
   dispatch prompt, not scope creep.

## Notes for T07

- `_rank_lexically(root, query, terms, limit, type_filter, tag_filter, scope) -> (hits, max_score)`
  is the entry point Task 7/8 (semantic arm, conditional handover fusion)
  will call to get the lexical side of the fusion decision. `hits` are
  dicts with `score`/`path`/`title`/`type`/`desc`/`snip`/`provenance`
  (`"lexical"`), optionally `contrib` (substring path only) or `cosine`
  (semantic path, not yet produced). `max_score` is `100` on the FTS path,
  `6 * len(terms)` on the substring path — T07/T08's fusion math needs to
  read this return value rather than assume a fixed scale, since the two
  lexical sub-arms are NOT on the same scale as each other, let alone as
  the semantic arm.
- The existing `cmd_find` semantic-backstop block (bge-m3, `_keyword_top1_is_confident`,
  `_semantic_hit_dicts`) is UNTOUCHED and still runs after `_rank_lexically`
  — it only reads `hits[0]["score"]`/`hits` length, which stayed compatible.
  Tasks 7/8 replace this block per the plan; it is not yet gone.
- `_hydrate_hit()` only reads a concept file for paths that actually ranked
  — reuse it rather than re-implementing hydration for semantic hits if the
  shape fits (it already accepts an optional `cosine` kwarg).
- The `--breakdown` on FTS hits prints a fixed "field-level breakdown not
  available" message; if T07/T08 introduce a semantic contrib-equivalent,
  that branch ordering (`semantic` -> `contrib` in dict -> fallback bm25
  message) is the pattern to extend, not replace.
- Live catalogue currently has `.fts/fts.sqlite` (2443 concepts) but NO
  `.tagvec` cache yet ("semantic backstop skipped (.tagvec cache/concept
  embeddings absent)" fires on every live smoke run) — T07/T08 will need to
  build that artefact before any live semantic verification is possible.
- The double-stderr-note class of bug (two degradation paths firing for one
  root cause) is worth checking again once the semantic arm adds its own
  degradation note — same risk shape if two "something is wrong" checks can
  both fire off the same underlying failure.



## REVIEW ROUND 1 — APPROVED with one finding, fixed inline 2026-07-26

Verdict was APPROVED (no blocking findings). Full evidence: all three D15 cases live-probed
(absent / corrupt / unreadable -> exactly ONE stderr note each, exit 0), plus combinations
(absent+tag filter, unreadable+--breakdown, stale-but-not-corrupt) each with exactly one note;
SC-04 stdout byte-identical against `git show 7a0557f:cli/okf-cli.py`; BM25 weights proven
APPLIED by an independent mutation (title==body flips the ranking test red); the double-note
fix reproduced by reverting to the plan's literal ordering (`2 != 1`); the 21-line
FAIL/ERROR name list byte-identical to the pre-task baseline (`diff` exit 0, nothing silenced).

**I01 (medium) — being fixed now rather than deferred.**
`RunnerAgainstRealCatalogueTest.setUp` (`cli/test_eval_runner.py:169-186`) renames the LIVE
`~/Obsidian/Knowledge-Catalogue/.fts/fts.sqlite` aside and then calls `runner.run(...)`
without `try/finally`. unittest does NOT run `tearDown` when `setUp` raises (reviewer verified
live), so any exception inside `runner.run()` — subprocess, JSON, disk I/O — strands a 13.2 MB
live artefact of a SEPARATE repo as `.fts.sqlite.parked-by-test-eval-runner` and silently
breaks `find` on the live catalogue until someone restores it by hand.

Also corrected: the bean's phrase "restored byte-identically, verified by size match" is
imprecise. `os.rename` never copies bytes, so byte-identity is structural, not something the
size check verifies. The real exposure was never content corruption — it is exception-safety
of the parking window.

The park itself is NOT scope creep: the reviewer reverted `cli/test_eval_runner.py` to the
pre-park version and `test_runner_scores_literal_s1_top1` fails (`rank inf != 1`), so the
change is substantively required by the FTS arm's stale-preference behaviour.

**Why this is not deferred:** the full suite runs at every gate point, and seven leaves remain.
The parking window would open dozens more times before anyone came back to it.


## Fix round 1

**I01 (T06 review, 2026-07-26) — `RunnerAgainstRealCatalogueTest.setUp` had
no exception-safety around the live `.fts/fts.sqlite` parking window.**

Root cause: `setUp` renamed the live index aside, then called
`runner.run(...)` with no `try/finally`. unittest does not call `tearDown`
when `setUp` itself raises, so any exception inside `runner.run()`
(subprocess failure, JSON error, disk I/O) would have permanently stranded
a 13.2 MB artefact of a SEPARATE repo under a `.parked-by-test-eval-runner`
name, silently breaking `find` on the live catalogue until a human noticed
and restored it by hand.

Fix: extracted the parking logic into `_park_fts_index(root)`, a
`@contextlib.contextmanager` with its own internal `try/finally`. A
generator-based context manager's `finally` runs on every exit from the
`with` block — clean return or an exception propagating through it —
independent of whatever unittest does with `setUp`/`tearDown`. Wired into
`RunnerAgainstRealCatalogueTest.setUp` as
`with _park_fts_index(CATALOGUE_ROOT): self.result = runner.run(...)`.
Tested in isolation (`ParkFtsIndexTest`) against a disposable temp
directory, never the live catalogue — per the review's own suggested
restructuring.

**RED** (mutated `_park_fts_index` back to the pre-fix pattern — rename,
bare `yield`, rename-back with no `try`/`finally` — to prove the new test
actually catches the exact failure mode the reviewer described):

```
$ python3 -m unittest cli.test_eval_runner.ParkFtsIndexTest -v
test_absent_index_is_a_silent_no_op ... ok
test_index_is_absent_inside_the_with_block ... ok
test_restores_the_index_after_a_clean_exit ... ok
test_restores_the_index_when_the_body_raises ... FAIL

======================================================================
FAIL: test_restores_the_index_when_the_body_raises
----------------------------------------------------------------------
AssertionError: False is not true

Ran 4 tests in 0.002s
FAILED (failures=1)
```

**GREEN** (`try`/`finally` restored via targeted `Edit`, byte-identical to
the fix):

```
$ python3 -m unittest cli.test_eval_runner.ParkFtsIndexTest -v
test_absent_index_is_a_silent_no_op ... ok
test_index_is_absent_inside_the_with_block ... ok
test_restores_the_index_after_a_clean_exit ... ok
test_restores_the_index_when_the_body_raises ... ok

Ran 4 tests in 0.002s
OK
```

**Live integration re-verified** (real `RunnerAgainstRealCatalogueTest`
class against `~/Obsidian/Knowledge-Catalogue`, real `.fts/fts.sqlite`):

```
$ python3 -m unittest cli.test_eval_runner -v
Ran 14 tests in 12.453s
OK
```

Live index confirmed present and unchanged after: `ls -la
~/Obsidian/Knowledge-Catalogue/.fts/` -> `13164544` bytes (identical to the
size recorded before this fix round and before the original T06 commit).

**Full-suite gate:**

```
$ python3 -m unittest discover -s cli -p 'test_*.py'
Ran 229 tests in 13.561s
FAILED (failures=19, errors=2)
```

225 (T06 close) + 4 new `ParkFtsIndexTest` tests = 229. 19F/2E unchanged —
no new failure, none silenced (same FAIL/ERROR name list as before).

**Correction to the T06 close entry:** the original `## Deviations/ERRATA`
wording "restored byte-identically, verified by size match" was imprecise
on two counts — `os.rename`/`mv` never copies bytes at all (byte-identity
is structural, not something a size check "verifies"), and the size match
said nothing about exception-safety, which was the actual gap. Both
instances of that wording (Smoke section, Deviations entry 3) have been
rewritten in place above to state what was actually true.
