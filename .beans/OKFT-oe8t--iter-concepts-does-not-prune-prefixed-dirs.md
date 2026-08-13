---
# OKFT-oe8t
title: iter_concepts does not prune _-prefixed dirs
status: in-progress
type: bug
priority: normal
created_at: 2026-08-09T19:09:25Z
updated_at: 2026-08-13T12:28:25Z
parent: OKFT-wmbu
---

Measured in lean-stack/docs/okf-knowledge-lifecycle/taxonomy-and-lifecycle (R09, reproducible via `just okf-archive-exclusion`).

`iter_concepts` (cli/okf-cli.py:81) prunes only dot-dirs and `assets`, while `iter_all_md` (:2582) additionally prunes `_`-prefixed staging dirs. In-bundle `_` content is therefore retrievable via index/list/find and skipped by check — the worst combination: reachable but unverified.

Really affected today: `general-knowledge-wiki/_intake/` and `qm-wiki/_intake/`.

Independent of the archive work in docs/okf-archive-lifecycle: that archive lives at catalogue level (`_archive/<bundle>/`), where the exclusion already holds. Tracked there as T15, deliberately kept out of that scope.

Note the outward coupling: fixing this makes `just okf-archive-exclusion` in lean-stack exit 1, which is intended — the guard then reports that DESIGN section 4 needs re-reading.


## ERRATA 2026-08-13 — line number for iter_all_md

The body above cites `iter_all_md` at `okf-cli.py:2582`. That is wrong: line 2582 holds the unrelated `render_recent_lines`. `iter_all_md` is defined at **okf-cli.py:2883**, and the pruning clause this bean compares against (`not d.startswith("_")`) sits at **2888-2890**. The function name is correct and greppable; only the line reference was off. Verified 2026-08-13 by ce-verify-operationalization.

`iter_concepts` at :81 is correct as written.


## Summary

`iter_concepts` (okf-cli.py:117, this repo's line drifted from the bean's
:81 since OKFT-n8xz inserted `list_indexable_bundles` above it) now prunes
`_`-prefixed staging dirs, matching `iter_all_md`'s existing convention
(:2925, clause :2930-2932, itself drifted from the bean's :2883/2888-2890
by an unrelated insertion — confirmed both names greppable and correct,
only line numbers moved).

### D01 — call-site census and decision: shared-function fix, no opt-in

Full census of `iter_concepts(` call sites in cli/okf-cli.py (grep, all 19,
excluding the `def` line and two comment mentions at :1238/:3355):

| line | caller function | purpose |
|------|------------------|---------|
| 204 | `all_tags` | tag registry usage counts |
| 267 | `cmd_merge_tags` | frontmatter tag mutation |
| 304 | `cmd_remove_tags` | frontmatter tag mutation |
| 357 | `cmd_normalize_tags` | frontmatter tag mutation |
| 522 | `bundle_types_and_tags` | `index --full` types/tags summary |
| 533 | `render_bundle_line` | `prime` bundle listing (count) |
| 548 | `render_bundle_block` | `index --full` block |
| 575 | `_bundle_summary_json` | `index --json` summary |
| 584 | `_concepts_json` | `index --json` per-bundle concepts |
| 611 | `cmd_index` | `index <bundle>` synthesized TOC |
| 643 | `cmd_list` | `list --type/--tag` |
| 761 | `build_fts_index` | FTS index build |
| 822, 830 | `_fts_index_stale` | FTS staleness check (active + archive) |
| 889 | `cmd_build_semantic_index` | semantic/tagvec index build |
| 1244 | `_substring_ranking` | `find`'s degraded lexical arm |
| 1953 | `render_catalogue_state` | `prime` onboarding facts |
| 2039 | `bundle_graph` | wikilink graph viz |
| 2754 | `cmd_recent` | `recent` listing |

Every caller feeds index, search, list, presentation (`prime`/`index`), or
frontmatter tag-maintenance. None is an integrity/`check` path — `check`
and its siblings (reserved-file scan, wikilink gate, etc.) walk
`iter_all_md` exclusively (verified: `iter_all_md(` appears only at
:3130, :3280, :3696, :3705, :3762, :3905, all inside check-family
functions; `cmd_check` itself at :3917). So the two functions already
diverging left in-bundle `_intake/` content reachable via every one of the
18 read-path callers above, while `check` — the one function it needed to
be visible to — never saw it.

**Decision: fix `iter_concepts` directly, no opt-in parameter.** This is
the opposite situation from OKFT-n8xz's `resolve_scopes()`, where ten
callers wanted two different defaults (10 call sites, D17 census missed 3
archive branches and mis-scoped `check`/`wikilinks`) — there, narrowing
the shared function would have silently broken integrity checks, so the
fix went in as an opt-in `indexable_only` parameter at the ONE caller that
wanted the narrower behaviour. Here, all 18 read-path callers of
`iter_concepts` want the same thing (staging pruned), and the one function
that must NOT prune it (`check`) already uses the sibling function
`iter_all_md`, unaffected by this change. No caller loses visibility it
needed; no opt-in is required.

## Test-Output

RED (tests written first against the unfixed `iter_concepts`, run before
any production-code edit):

```
test_underscore_staging_dir_pruned (test_okf_cli.IterConceptsStagingPrune.test_underscore_staging_dir_pruned) ... FAIL
AssertionError: Lists differ: ['_intake/konzept'] != []

test_find_degraded_excludes_staging (test_okf_cli.StagingExcludedFromIndexListFind.test_find_degraded_excludes_staging) ... FAIL
AssertionError: '_intake' unexpectedly found in '...
path: b/_intake/konzept
...'

test_index_json_excludes_staging_keeps_regular (test_okf_cli.StagingExcludedFromIndexListFind.test_index_json_excludes_staging_keeps_regular) ... FAIL
AssertionError: '_intake/konzept' unexpectedly found in ['_intake/konzept', 'sub/regular']

test_list_excludes_staging_keeps_regular (test_okf_cli.StagingExcludedFromIndexListFind.test_list_excludes_staging_keeps_regular) ... FAIL
AssertionError: '_intake' unexpectedly found in '...
path: b/_intake/konzept
...'

Ran 6 tests in 0.007s
FAILED (failures=4)
```

GREEN (after the fix, full suite, `just test`):

```
FAIL: test_index_walk_row_present_with_rank_no_dedicated_metric (test_eval_runner.RunnerAgainstRealCatalogueTest.test_index_walk_row_present_with_rank_no_dedicated_metric)
FAIL: test_metadata_hit_and_miss_rows_scored_correct (test_eval_runner.RunnerAgainstRealCatalogueTest.test_metadata_hit_and_miss_rows_scored_correct)
FAIL: test_runner_scores_literal_s1_top1 (test_eval_runner.RunnerAgainstRealCatalogueTest.test_runner_scores_literal_s1_top1)
Ran 691 tests in 26.153s
FAILED (failures=3)
```

Exactly the three pre-existing, pre-attributed failures (baseline in
OKFT-wmbu, `RunnerAgainstRealCatalogueTest`), no fourth. 691 = 685 baseline
+ 6 new tests (`IterConceptsStagingPrune` ×3, `StagingExcludedFromIndexListFind`
×3).

**Mutation proof** (Edit → run → revert, on the guard's own repo copy):
removing the `and not d.startswith("_")` clause from `iter_concepts`
reproduces the RED single-test failure above
(`test_underscore_staging_dir_pruned`: `['_intake/konzept'] != []`); the
revert Edit restored the clause byte-identically (`git diff` before/after
identical).

## Smoke

Real catalogue, read-only (`~/Obsidian/Knowledge-Catalogue`, both
bundles are symlinks resolved transparently by `os.walk`; no write, no
Testlauf writes into the catalogue — CLAUDE.md Regel 1 honoured; count
comparison run via a standalone in-process script, not `just test`):

```
general-knowledge-wiki before: 345 after: 344 intake concepts removed: ['_intake/ingest-lessons-learned']
qm-wiki                before: 764 after: 763 intake concepts removed: ['_intake/ingest-lessons-learned']
```

Outward coupling, confirmed as designed — `just okf-archive-exclusion` in
`/Users/erik/dev/lean-stack`, run read-only, lean-stack repo untouched
(`git status --porcelain` empty before and after):

```
probe catalogue: /var/folders/1s/0zxb5ygn78l1582rpl4kx5jw0000gn/T/okf-archive-probe-5pfjlayf
command   sees <bundle>/_archive/     sees /_toplevel-`_`-dir
index     no                          no
list      no                          no
find      no                          no
check     no                          no
DRIFT — okf-cli no longer behaves as R09 records, for: find, index, list
Reread R09 and D14 in docs/okf-knowledge-lifecycle/taxonomy-and-lifecycle/.
```
exit code: 1

Matches the D01 census exactly: drift reported for find/index/list (the
three read-paths this fix changes), `check` still reports "no" (unaffected
— confirmed unchanged, as it always used `iter_all_md`).

## Deviations/ERRATA

- Bean text cited `iter_concepts` at :81 and `iter_all_md` at :2883/2888-2890
  (ERRATA-corrected from the original :2582). Both had drifted further by
  the time of implementation, to :117 and :2925/2930-2932 respectively —
  OKFT-n8xz's `list_indexable_bundles` insertion above `iter_concepts`
  moved the first, an unrelated intervening insertion moved the second.
  Function names stayed correct and greppable both times; only line
  numbers moved. No bean update needed beyond this note — greppable names
  are the load-bearing reference, not line numbers, per the bean's own
  ERRATA precedent.
- No other deviation from the bean's scope. Archive-lifecycle work
  (docs/okf-archive-lifecycle, T15) was not touched.

## Notes for T(n+1)

- The lean-stack guard `just okf-archive-exclusion` now exits 1 by design.
  Per the task's explicit instruction, lean-stack was not touched — DESIGN
  section 4 in `lean-stack/docs/okf-knowledge-lifecycle/taxonomy-and-lifecycle/`
  needs re-reading/updating there to record the new `find`/`index`/`list`
  behaviour (R09/D14 currently describe the pre-fix state). That is
  lean-stack's own follow-up, out of this bean's scope.
- `check`'s own `_`-pruning behaviour (via `iter_all_md`) was not modified
  and needed no new test — pre-existing regression coverage
  (`cli/test_okf_cli.py:6713 test_staging_subdir_target_is_not_checked`)
  already locks it down, and the full-suite GREEN run confirms no
  regression there.


## Review 2026-08-13 — CHANGES_REQUIRED (ce-specs-reviewer, reproduced)

The census counts correctly — 19 call sites, every line and function name confirmed — and `check` really does run exclusively over `iter_all_md` (`run_checks` :3875-3919, called from `cmd_check` :3927, plus the separate `check_asset_placement` walk with its own untouched `_` clause). Claim (d) of D01 holds.

### B01 (blocking) — three of the nineteen write files

D01 files `cmd_merge_tags` (:267), `cmd_remove_tags` (:304) and `cmd_normalize_tags` (:357) under "read-path callers". They are not read paths. All three call `write_file`. Reproduced in a tmpdir with `merge-tags oldtag --into newtag`, no `--apply`:

```
after the fix:   would rewrite  mybundle/sub/regular.md
before the fix:  would rewrite  mybundle/_intake/staged.md
                 would rewrite  mybundle/sub/regular.md
```

`_intake/staged.md` is no longer seen at all. A tag rename now leaves staging content carrying the old tag, and nothing reports it. That is the same shape as the first OKFT-n8xz round: a narrowing placed in a shared function reached callers nobody had classified.

`fix_crosslinks` (:3290), `fix_xml_like_tags` (:3140) and `rename` are unaffected — they walk `iter_all_md` or no bundle-wide iteration at all.

### D02 — the three tag commands keep the wide walk

Resolved conservatively rather than by consistency argument.

There is a tempting counter-argument: `fix_crosslinks` and `fix_xml_like_tags` are mutation commands that already prune `_`, so pruning the tag commands too would make mutation behaviour uniform. That argument is real but it is **not this task's to settle**. This bean's mandate is the retrieval surface — index, list, find — and the reason given for it is "reachable but unverified". Nothing here asked to change which files a writing command repairs, and a change that silently shrinks a write path is exactly the class this epic has now been bitten by three times.

So: `cmd_merge_tags`, `cmd_remove_tags` and `cmd_normalize_tags` keep the unpruned walk. Use the same shape OKFT-n8xz landed on — default wide, narrowing explicit at the caller — rather than a second bespoke mechanism.

The uniformity question is filed separately as OKFT-eyla. Do not decide it here.

### Documentation errors in D01, correct them

- **I01** — D01 says "18 read-path callers"; the table underneath lists 19.
- **I02** — D01 says two comment mentions at :1238 and :3355; there are three, at :1248, :2585 and :3365.
- **I03** — D01 says all six `iter_all_md` sites sit inside check-family functions; two of them are in `fix_xml_like_tags` (:3140) and `fix_crosslinks` (:3290), which are mutation commands. Harmless in effect — both already pruned `_` before this fix — but the statement is wrong and it is the statement a future reader would rely on.

### I04 (fix with this round) — the prune must hit directories only

No test covers that the `_` rule applies to directory names and not to file names. Verified by hand: a file `_private.md` directly in a bundle root stays reachable, which is correct — and unprotected. Pin it.

### Not findings

Behaviour confirmed experimentally: `_intake` gone from index, list and find; a regular subdirectory fully retained; `assets` and dot-dirs still pruned; `check` output byte-identical before and after. The six new tests call production functions, no re-implemented pruning logic. Reverse mutation turns exactly four of them red. Outward coupling is as the bean predicted: `just okf-archive-exclusion` in lean-stack exits 1 with DRIFT on find/index/list and `check` unaffected, lean-stack working tree clean before and after. Smoke reproduced: 345→344 and 764→763, and each `_intake/` really does hold only one `.md` — the rest are `.tsv`/`.txt` and were never concepts. `just test`: `Ran 691 tests in 25.343s`, `FAILED (failures=3)`.

**I05** — regression cover for this fix rests entirely on the six unit tests; no CLI-level test reacts to removing the clause. Noted, not required this round.
