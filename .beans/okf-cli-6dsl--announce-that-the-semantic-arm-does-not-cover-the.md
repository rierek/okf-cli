---
# okf-cli-6dsl
title: announce that the semantic arm does not cover the archive
status: completed
type: task
priority: normal
created_at: 2026-08-09T19:15:04Z
updated_at: 2026-08-09T22:34:57Z
parent: okf-cli-scd5
blocked_by:
    - okf-cli-pn72
---

The embedding build (`cli/embeddings/build_tagvec.py:174`) stays on the active catalogue: embeddings cost API calls for material that is hidden by default. That is a deliberate limit, and an unannounced limit is a trap — the user would search an archive the answering arm never saw and read the empty result as an answer. One note per arm per invocation, following the existing degradation notes (PF-4).

### Requirement 1: A named limit instead of a silent one

**Objective:** As a searcher, I want to be told when my archive flag did not reach the arm that answered, so that an empty result is not mistaken for an absence.

#### Acceptance Criteria

1. WHEN `--include-archive` is set AND the semantic arm contributes hits THE okf-cli SHALL write exactly one note to stderr stating that the flag covers the lexical arm only.
2. WHILE `--include-archive` is not set THE okf-cli SHALL write no such note.
3. THE okf-cli SHALL write the note at most once per invocation.

#### Success Criteria

- SC-01: A `find --include-archive` whose answer contains semantic hits carries the note on stderr.
- SC-02: The same query without the flag carries no note.

_Requirements: R-13_

## Recommended Skills

- `superpowers:test-driven-development`


## Summary

`cmd_find` (`cli/okf-cli.py:1471`) gained one gated stderr note (`cli/okf-cli.py:1526-1535`): `if filters.include_archive and semantic_hits:` prints `"note: --include-archive covers the lexical arm only; embeddings stay on the active catalogue"` once. `filters.include_archive` is the `FindFilters` field set from `args.include_archive` at line 1488 (already present, from `okf-cli-pn72`); `semantic_hits` is the local list `_semantic_hit_dicts(...)` returns (line 1519-1524), non-empty only when the semantic arm actually ran and produced hits. Placed after `semantic_hits` is computed and before `fuse_conditional`, so it fires exactly once per `cmd_find` invocation by construction — no loop wraps it.

## Deviation from the Andock-Notiz (verified, documented)

The predecessor bean's note cited the existing "semantic arm owns this ranking" print at `cli/okf-cli.py:1483` and `cmd_find` at `:1426`. Verified against the actual current file: `cmd_find` starts at `:1471`, the cited print is at `:1528`(pre-change)/`:1543`(post-change) — both ~52-55 lines later than the note's numbers. Cause not investigated further (irrelevant to the task); the *names and shapes* the note pointed at (`filters.include_archive`, local `semantic_hits`, the print right before `fuse_conditional`) were all correct and used as given. No design deviation, only a stale line-number citation.

## RED output (verbatim, before production change)

```
test_ac1_conjunction_flag_set_but_no_semantic_hits_writes_no_note ... ok
test_ac3_note_appears_at_most_once_with_multiple_semantic_hits ... FAIL
test_sc01_flag_set_and_semantic_hits_present_notes_once ... FAIL
test_sc02_flag_not_set_writes_no_note ... ok

FAIL: test_sc01_flag_set_and_semantic_hits_present_notes_once
AssertionError: Lists differ: [] != ['note: --include-archive covers the lexic[49 chars]gue']
FAIL: test_ac3_note_appears_at_most_once_with_multiple_semantic_hits
AssertionError: 0 != 1

Ran 4 tests in 0.008s
FAILED (failures=2)
```
(`test_sc02_...` and `test_ac1_conjunction_...` pass trivially pre-implementation — they assert absence of a note that does not yet exist; both are exercised as mutation targets below to prove they carry real enforcement, not just vacuous truth.)

## Test-per-criterion

| AC/SC | Test |
|---|---|
| AC1 (conjunction: flag set AND semantic hits present) | `test_sc01_flag_set_and_semantic_hits_present_notes_once` (positive) + `test_ac1_conjunction_flag_set_but_no_semantic_hits_writes_no_note` (flag alone insufficient) |
| AC2 (flag unset -> no note) | `test_sc02_flag_not_set_writes_no_note` |
| AC3 (at most once per invocation) | `test_ac3_note_appears_at_most_once_with_multiple_semantic_hits` |
| SC-01 | `test_sc01_flag_set_and_semantic_hits_present_notes_once` |
| SC-02 | `test_sc02_flag_not_set_writes_no_note` |

All four in `cli/test_okf_cli.py`, class `SemanticArmArchiveNote` (`cli/test_okf_cli.py:2882`).

## Mutation table

| Kriterium | Mutation | Roter Test | Warum |
|---|---|---|---|
| AC2 (flag guards the note) | `if filters.include_archive and semantic_hits:` -> `if True and semantic_hits:` | `test_sc02_flag_not_set_writes_no_note` | note fires even with the flag unset, proving `filters.include_archive` is what AC2 actually depends on |
| AC1 (conjunction, not flag alone) | `if filters.include_archive and semantic_hits:` -> `if filters.include_archive:` | `test_ac1_conjunction_flag_set_but_no_semantic_hits_writes_no_note` | note now fires with zero semantic hits, proving the `semantic_hits` conjunct is load-bearing, not redundant |
| AC3 (at most once) | print wrapped in `for _sh in semantic_hits:` | `test_ac3_note_appears_at_most_once_with_multiple_semantic_hits` | 2 semantic hits -> 2 notes instead of 1 |

All three mutations run, observed red for the stated reason, reverted via targeted `Edit`. `git diff cli/okf-cli.py` after all three cycles showed only the intended net +10 lines (verified: no residue).

## Full suite

`just test` -> `Ran 607 tests … OK` (baseline 603 + 4 new tests in this bean).

## Gate evidence

Commit `e73dd36` (`feat(cli): announce include-archive misses semantic arm (R-13)`).
