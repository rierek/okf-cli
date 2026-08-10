---
# OKFT-fu7o
title: index the archive and split the staleness counters
status: completed
type: task
priority: normal
created_at: 2026-08-09T19:15:04Z
updated_at: 2026-08-09T22:20:55Z
parent: OKFT-scd5
blocked_by:
    - OKFT-pn72
---

Without the archive in the FTS index the flag is a decoration: FTS is the default arm, and no predicate can surface what the index never saw. The counter split is not style. If the index counts both sets and `_fts_index_stale` (cli/okf-cli.py:717) counts only the active one, the index is permanently stale. If both are counted as one sum, that sum stays constant across an archive move and `git mv` preserves the file mtime, so the move goes unnoticed, the index keeps serving the concept under its active path, and `find` shows archived material by default.

### Requirement 1: An index that knows the archive

**Objective:** As a searcher, I want the archive present in the lexical index and its movements detected, so that `--include-archive` returns real results and the default view never leaks archived material.

#### Acceptance Criteria

1. WHEN building the FTS index THE okf-cli SHALL index every concept under `_archive/<bundle>/` at that path.
2. THE okf-cli SHALL record separate counts of active and archived concepts in `fts_meta`.
3. THE okf-cli SHALL compare both counts in the staleness decision.
4. THE okf-cli SHALL keep the staleness check free of concept-body reads, using file metadata only.

#### Success Criteria

- SC-01: After archiving one concept, the staleness check reports the index as stale.
- SC-02: Immediately after a build, the staleness check reports the index as current, with archived concepts present.

_Requirements: R-11_

## Recommended Skills

- `superpowers:test-driven-development`


## 2026-08-09 — Prelude: incoming `cmd_index` guard from a parallel branch

A parallel session added a bundle-existence guard to `cmd_index` and `cmd_visualize` on branch `fix/b01-b02-bundle-validation` (commit `b5a9f1d`, based on `3310656`). It is **not on `main` yet** — it rebases onto this chain afterwards, so you implement against `main` without it. Know it anyway, because it lands on top of your work:

- The guard is a helper `require_bundle_dir(root, bundle)` placed directly below `is_bundle_dir` in `cli/okf-cli.py`. It checks `os.path.isdir` only, deliberately **not** `is_bundle_dir()` — the latter rejects `_`-prefixed names and would have broken `index _archive`. A `_archive/` directory that exists on disk passes the guard.
- That property is pinned by their test `test_the_gate_is_existence_not_bundle_eligibility`, verified by mutation. Anyone tightening the guard later gets a red test rather than silently breaking this leaf.

What this means for you: if your indexing path needs to accept a path that does **not** exist as a directory (for instance indexing an archive before any concept has been archived into it), the parallel assumption is wrong and their helper needs an exception. Record that in `## Notes` and report it — the supervisor relays it to the other session. If your path only ever indexes an archive directory that exists, nothing to do.



## 2026-08-09 — incoming guard from the parallel Rust-rewrite session (final)

That session has closed. Its branch `fix/b01-b02-bundle-validation` @ `b5a9f1d` (base `3310656`, suite 559 green) is the only one of theirs that touches `cli/` and will need a rebase onto whatever `main` looks like after this chain. It is not merged yet — the merge gate is mutual and the PO decides.

What it adds, verbatim from their handover:

- Helper `require_bundle_dir(root, bundle)`, placed under `is_bundle_dir`.
- Called in `cmd_index` and `cmd_visualize`.
- It checks `os.path.isdir` and deliberately **not** `is_bundle_dir()` — precisely so that `_archive/` paths pass through it.
- Test class `BundleArgumentIsValidated`.

Consequence for this task: the guard is archive-compatible by design, so indexing `_archive/<bundle>/**` does not have to fight it. But this task and that branch both edit `cmd_index`, in the same file, from different bases. Whoever rebases second resolves the conflict. Keep the edit here as small and as local as it can be, and do not restructure `cmd_index` beyond what R-11 requires — a large refactor here turns their rebase into a rewrite.

They also report that `cmd_archive` (cli/okf-cli.py:4163) already implements `--apply` exactly the way their cross-cutting rules COM-29/COM-30 require, and cite it as precedent in their `log.md`.



## Summary

`build_fts_index` (`cli/okf-cli.py:677`) now indexes `_archive/<bundle>/<cid>` at that exact path, in addition to the active bundles it already indexed — an `os.path.isdir(archive_root)` guard mirroring `resolve_scopes`'s existing archive-discovery pattern, so a catalogue that has never archived anything (no `_archive/` dir on disk) is unaffected. `fts_meta` now carries `n_concepts` (active count, name kept for backward compatibility) and a new `n_archived` key (archived count), instead of one combined counter. `_fts_index_stale` (`:742`) reads and compares both counters independently — `n_active != n_active_idx or n_archived != n_archived_idx or newest > newest_idx` — rather than comparing a sum, which is the actual mechanism SC-01 exercises: archiving one concept decrements the active count and increments the archived count by the same amount, so a summed comparison would stay unchanged and the move would go undetected (mtime is preserved by the move, so the mtime signal doesn't catch it either). A small internal `_index_bundle(b, bp, path_prefix)` closure inside `build_fts_index` de-duplicates the insert/count/newest-tracking logic between the active loop and the new archive loop — contained entirely inside the function, no signature or call-site change outside it.

`cmd_index` (`cli/okf-cli.py:544`, the human-readable bundle-description command) and `cmd_visualize` were **not touched** — R-11's AC/SC text and SPEC §4.1 both name `build_fts_index`/`_fts_index_stale` specifically, and that function takes no bundle argument at all (it walks the whole catalogue root unconditionally). The parallel session's incoming `require_bundle_dir` guard is scoped to `cmd_index`/`cmd_visualize` only (per the bean's own prelude) and this leaf never calls it, never routes through it, and never touches those two functions — see "Guard exception" below.

## RED output (verbatim, before any production change)

```
test_archived_concept_is_indexed_at_its_archive_path ... FAIL
  AssertionError: {'b/one': 'Runbook'} != {'b/one': 'Runbook', '_archive/b/two': 'Konzept'}
test_meta_records_separate_active_and_archived_counts ... ERROR
  KeyError: 'n_archived'
test_pre_split_index_is_treated_as_stale_not_crashed ... ok
test_sc01_archiving_with_preserved_mtime_makes_index_stale ... ok
test_sc02_fresh_build_with_archive_present_is_current ... FAIL
  AssertionError: '_archive/b/two' not found in ['b/one']
test_staleness_check_never_reads_a_concept_body ... ok

Ran 6 tests in 0.018s
FAILED (failures=2, errors=1)
```

Three of the six pass trivially pre-change, documented, not concealed: SC-01 (the split doesn't even matter yet — pre-change the archived file was never in the index at all, so removing it from the active tree alone already changes the single old-style counter) and the migration/AC4 tests exercise behaviour that predates this bean (an absent-key crash-vs-stale question, and a body-read question) and only become *meaningful* regression guards once the split logic they pin actually exists — proven by the mutation table below, same pattern as `OKFT-pn72`'s SC-02/SC-04 precedent.

## Test-per-criterion

| AC/SC | Test | Codestelle |
|---|---|---|
| AC1 (index the archive at its path) | `FtsIndexArchive.test_archived_concept_is_indexed_at_its_archive_path` | `cli/test_okf_cli.py:3096` |
| AC2 (separate counters in fts_meta) | `FtsIndexArchive.test_meta_records_separate_active_and_archived_counts` | `cli/test_okf_cli.py:3106` |
| AC3 (both counts compared in the staleness decision) + SC-01 (move detected, mtime preserved) | `FtsIndexArchive.test_sc01_archiving_with_preserved_mtime_makes_index_stale` | `cli/test_okf_cli.py:3125` |
| AC4 (staleness check free of body reads) | `FtsIndexArchive.test_staleness_check_never_reads_a_concept_body` | `cli/test_okf_cli.py:3150` |
| SC-02 (fresh build is current, archive present) | `FtsIndexArchive.test_sc02_fresh_build_with_archive_present_is_current` | `cli/test_okf_cli.py:3116` |
| Migration (pre-R-11 index schema) | `FtsIndexArchive.test_pre_split_index_is_treated_as_stale_not_crashed` | `cli/test_okf_cli.py:3170` |

## Mutation table (the SC-01 summed-counter proof is the core evidence)

| Kriterium | Mutation | Roter Test | Warum |
|---|---|---|---|
| AC1 (archive gets indexed) | `build_fts_index`'s `if os.path.isdir(archive_root):` guarded behind `if False and ...` | `test_archived_concept_is_indexed_at_its_archive_path`, `test_meta_records_separate_active_and_archived_counts`, `test_sc02_fresh_build_with_archive_present_is_current` (3 tests) | archive loop never runs, `_archive/b/two` never lands in `docs`, `n_archived` stays 0, and the "archived concepts present" half of SC-02 fails |
| **AC3/SC-01 (two counters, not their sum) — the task's core proof** | `_fts_index_stale`'s return line changed from `n_active != n_active_idx or n_archived != n_archived_idx` to `(n_active + n_archived) != (n_active_idx + n_archived_idx)` | `test_sc01_archiving_with_preserved_mtime_makes_index_stale` | archiving one concept decrements active by 1 and increments archived by 1 in the same call; the **sum** stays constant, mtime is preserved by the move (`os.rename`, same as `git mv`), so a summed comparison reports "not stale" — the exact silent-regression class R-11 exists to close |
| AC4 (stat-only, no body reads) | Added `read_file(ap)` inside the archive-scanning loop of `_fts_index_stale` | `test_staleness_check_never_reads_a_concept_body` | the monkeypatched `read_file` (raises `AssertionError` unconditionally) is now reachable from the staleness path, proving the test would catch a body read if one were ever (re)introduced |

## Umkehrmutation (guard-hat-einen-guard probe, migration decision)

`_fts_index_stale`'s `except (sqlite3.DatabaseError, KeyError, ValueError, TypeError):` had `KeyError` removed, leaving the rest of the mechanism (the two-key read, the comparison) untouched. Result: `test_pre_split_index_is_treated_as_stale_not_crashed` went from `ok` to **ERROR** — an uncaught `KeyError: 'n_archived'` at `cli/okf-cli.py:760` — proving it is specifically the `KeyError` branch of that except-tuple, not merely "the function has a try/except", that turns a legacy (pre-R-11) index into a clean "stale, please rebuild" instead of a crash. Confirmed live against the real, pre-existing index at `~/Obsidian/Knowledge-Catalogue/.fts/fts.sqlite` (built before this bean, old schema) — see smoke section below.

All four mutation/reverse-mutation cycles run, observed red/error for the stated reason, reverted via targeted `Edit` back to the exact original text. `git diff --stat cli/okf-cli.py` after every cycle: only the net intended change (`64 insertions(+), 19 deletions(-)`), no residue.

## Migration decision (Bestandsindizes)

An index built before this bean lands has `fts_meta` rows for `n_concepts`/`newest_mtime` only — no `n_archived` key. Decision: **treat it as stale, not a crash.** `_fts_index_stale`'s existing `except (..., KeyError, ...)` tuple already catches the missing-key read (same branch that already handled a missing/corrupt meta table before this bean), so a legacy index is reported stale on the very next `find`/`build-index --if-stale` call, triggers a clean rebuild, and the new two-counter schema is written from then on — no user-visible error, no manual migration step. Verified two ways: (1) `test_pre_split_index_is_treated_as_stale_not_crashed`, a synthetic legacy-schema fixture, passes without raising; (2) a live read-only run of `find` against the real, pre-existing (old-schema) index at `~/Obsidian/Knowledge-Catalogue/.fts/fts.sqlite` printed `note: lexical index is stale (catalogue changed since build) — run \`okf-cli build-index\`` to stderr and did not crash — see smoke section.

## Guard exception check (parallel session's `require_bundle_dir`)

**No exception needed.** `require_bundle_dir(root, bundle)` is scoped to `cmd_index` and `cmd_visualize` per the bean's own prelude — both take a single `bundle` argument from argparse. R-11's indexing path is `build_fts_index`/`cmd_build_index`, which takes **no bundle argument at all**: it walks `list_bundles(root)` for the active side and, new in this bean, unconditionally checks `os.path.isdir(os.path.join(root, "_archive"))` for the archived side — the same existence-check shape `resolve_scopes` already established for R-12, not a bundle-argument validation gate. This leaf never calls `require_bundle_dir`, never touches `cmd_index`/`cmd_visualize`, and doesn't need to accept a bundle path that fails `os.path.isdir` through anyone else's guard — the "index an archive that doesn't exist yet" case here is handled by a plain `if os.path.isdir(...)`, not a call into their helper. Nothing to relay to the other session for this leaf.

## Kept the intervention local (point 3)

`cmd_index` (`:544`) is completely unmodified by this bean — confirmed by `git diff cli/okf-cli.py` touching only `build_fts_index` and `_fts_index_stale` (lines 677–796). The other session's rebase of `require_bundle_dir` onto `cmd_index`/`cmd_visualize` is unaffected by anything in this commit.

## Prüfung auf veraltete Tests (Gate item 4)

Two pre-existing test classes staged archived FTS rows by hand (`_insert_fts_row`, direct `INSERT INTO docs`) because, at the time they were written (`OKFT-pn72`), `build_fts_index` did not yet index `_archive/`. Now that it does, those manual inserts would duplicate the row `build_fts_index` creates for real from the same fixture files on disk — same path, same content, just a second row. Fixed:

- `FindIncludeArchive` (`cli/test_okf_cli.py:1987`) — removed both `_insert_fts_row` calls and the now-unused helper method; docstring rewritten to state build_fts_index indexes the archive for real since this bean, not "R-11/OKFT-iwx4's sibling scope, not this bean's" (stale cross-reference — R-11 is this bean, `OKFT-iwx4` was R-12/traversal, a different scope entirely; the original docstring conflated the two).
- `FindScopeLikeEscaping` (`cli/test_okf_cli.py:2088`) — same removal; the comment explaining why `Xarchive/my_bundle/hidden2.md` needed no manual row ("ordinary bundle, build_fts_index indexes it on its own... unlike the `_archive/...` fixtures above") was inaccurate the moment the `_archive/...` fixtures also became self-indexing — reworded to say all fixtures in that class are self-indexing now.
- `PathInScopeArchiveRule` (`cli/test_okf_cli.py:2060`) — its docstring claimed "the FTS arm above proves it end to end because SC-01/02/03 stage archived rows directly in the docs table," which stopped being true the moment `FindIncludeArchive` stopped staging rows manually; reworded to describe the real mechanism (a real `build_fts_index()` build over real fixture files).

All three edits are docstring/fixture-setUp only — no assertion in any of the affected tests changed, and `just test` confirms all three classes stay green after the edit (verified below). No test was weakened or had its checked property changed; the manual-insert removal is exactly what the arrival of the real mechanism it was standing in for calls for.

## Full suite

`just test` → baseline `Ran 597 tests … OK` → after this task `Ran 603 tests in 52-57s` → `OK` (597 + 6 new `FtsIndexArchive` tests).

## Read-only smoke against the real catalogue

`python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue find "retry" --limit 2` — no `--apply`, no `build-index` invoked. Output included `note: lexical index is stale (catalogue changed since build) — run \`okf-cli build-index\`` on stderr, confirming the migration decision live against the real, pre-existing (old-schema, pre-R-11) index — reported stale cleanly, no crash, no write. `git -C ~/Obsidian/Knowledge-Catalogue status --short` empty before and after. No index rebuild was run against the real catalogue, per the task's explicit prohibition.

## Deviations / ERRATA

None from the bean/SPEC text. One clarification worth recording: this bean does **not** touch `cmd_index` (`cli/okf-cli.py:544`, the bundle-description CLI command) at all, despite the bean title's surface-level "index" wording and the two dated prelude sections about an incoming `cmd_index` guard — R-11's own AC/SC text and SPEC §4.1 are unambiguous that "the FTS index" (`build_fts_index`/`_fts_index_stale`) is the subject, a different function with a different call shape (no bundle argument) from `cmd_index`. Flagging this explicitly since the prelude discussion could otherwise be misread as directing me to touch `cmd_index`.

## Notes for T(n+1)

No outstanding follow-up specific to this leaf — R-11 is the last requirement in this SPEC's coverage table that involves the FTS build/staleness path. `cmd_prime`'s "fts index: present/absent" line (`cli/okf-cli.py` render_catalogue_state area) only checks `os.path.isfile`, not staleness or the meta schema — unaffected by this bean, not in scope for R-11.

For whoever next touches `fts_meta`'s schema: the two counters are named `n_concepts` (active, kept for backward compatibility with pre-R-11 readers/writers) and `n_archived` (new). A third dimension, if one is ever needed, should follow the same pattern — its own named key, compared independently in `_fts_index_stale`'s final boolean, never folded into an existing counter's arithmetic — that fold-into-a-sum failure mode is exactly what this bean's core mutation proof (SC-01 going red) demonstrates.

## Gate evidence

`just test` → `Ran 603 tests … OK`. Four mutation cycles (AC1, AC3/SC-01 — the required summed-counter proof —, AC4, and the migration-decision Umkehrmutation), each correctly reddened (or errored, for the Umkehrmutation) the intended test(s) for the stated reason, each reverted via targeted `Edit`; `git diff --stat cli/okf-cli.py` confirmed no residue after every cycle. Read-only smoke against the real catalogue confirmed the migration decision live, `git status --short` clean, no `--apply`, no index rebuild on the real catalogue. Commit `5d03cb1` (`feat(cli): index the archive, split staleness counters (R-11)`).
