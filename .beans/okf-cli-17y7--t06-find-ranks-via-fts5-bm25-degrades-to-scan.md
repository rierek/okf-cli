---
# okf-cli-17y7
title: T06 find ranks via FTS5 BM25, degrades to scan
status: in-progress
type: task
priority: high
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-26T05:55:53Z
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

- [ ] Define the module-level `_run_find(root, query, **kw)` test helper (new — mirrors the per-class pattern at `cli/test_okf_cli.py:1376-1387`)
- [ ] Write the failing `FtsRanking` and `FindDegradesWithoutIndex` tests
- [ ] Run them, confirm they fail for the stated reason
- [ ] Add `_fts_ranking()` and `_hydrate_hit()`
- [ ] Extract today's scan verbatim into `_substring_ranking()`
- [ ] Add `_rank_lexically()` returning `(hits, max_score)`; call it from `cmd_find`
- [ ] Add the `--breakdown` branch for FTS hits
- [ ] Tests pass; suite still 19F/2E
- [ ] Verify on the live catalogue (literal query + timing)
- [ ] Commit `feat(cli): rank lexically via fts5 bm25`, with the score-scale note in the body

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
