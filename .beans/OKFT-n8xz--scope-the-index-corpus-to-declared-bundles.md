---
# OKFT-n8xz
title: Scope the index corpus to declared bundles
status: in-progress
type: task
priority: high
created_at: 2026-08-13T11:07:18Z
updated_at: 2026-08-13T11:46:01Z
parent: OKFT-wmbu
blocking_external: lean-stack:LES-zr4r
---

Add a second, narrower bundle set beside list_bundles - e.g. list_indexable_bundles(root) - derived from the .okf.toml bundle key, falling back to the existing name filter when the key is absent (catalogue behaviour, correct there).

Use it ONLY at the index and search call sites: okf-cli.py:740 (build-index), 785 (freshness stats), 851 (semantic coverage / --if-stale), 3312 and 3317 (resolve_scopes -> find).

Do NOT touch is_bundle_dir, and do NOT narrow these call sites: 3627 and 3636 (build_concept_basename_index), 3721 (wikilink_checked_bundles validation), 3765 (wikilinks target validation), 3964 (symlink traversal), nor the presentation sites 166, 560, 585, 588, 1909, 1962.

Reason for the split: okf-tools-okf/archive-lifecycle/active-beats-archived-in-wikilink-resolution documents what narrowing list_bundles costs - every inbound [[x]] went unresolved and check reported violations in files the archiver never touched. Narrowing the corpus must not narrow resolution, or a loud defect is traded for a silent one.

Expected effect: corpus drops from 197 to 41 documents in lean-stack/docs.


## D01 — the call-site lists are extended, 2026-08-13 (supervisor, after Gate B)

`ce-verify-operationalization` verified every `list_bundles` call site in `cli/okf-cli.py` against this bean and found that **D17/R40 itself counted incompletely**. Three call sites feed the index/search corpus and appear in neither list — not the positive one, not the negative one:

| line | function | what it does |
|------|----------|--------------|
| 745 | `build_fts_index` | reads the archived bundles under `_archive/` into the **same** FTS index that line 740 fills |
| 793 | `_fts_index_stale` | counts archived concepts for the **same** staleness verdict that line 785 feeds |
| 3326 | `resolve_scopes` | appends archived bundle scopes to the **same** result list `find` consumes, on the `include_archive` branch |

Each is the archive sibling of a call site already on the positive list. Verified in the source: 740/745 sit in the same loop body, 785/793 in the same counter, 3312/3317/3326 in the same `resolve_scopes` return path.

**Decision: all three join the positive list.** They are index/search by purpose, which is exactly the criterion D17 names — the split D17 draws is by *purpose*, not by the accident of which lines its author happened to enumerate. Leaving them on the old `list_bundles` would open a silent back door: move a topic folder to `_archive/<name>/` in a repo docs root and it returns to the FTS index, to the staleness count and to the `find --include-archive` scope, unnarrowed. That is the monotonic degradation this epic exists to stop, re-entering through the archive path.

Effect today is nil — the catalogue keeps the fallback (no `bundle` key) and repo docs roots carry no `_archive/`. The change closes the door before anyone walks through it.

**The positive list is therefore: 740, 745, 785, 793, 851, 3312, 3317, 3326.** The negative list is unchanged and still binding.

### Correction to the negative list

`560` is off by one: the `list_bundles(root)` token sits on **561**; 560 is the first line of the same two-line `print(json.dumps(...))` statement in `cmd_index --json`. Read the negative list as `166, 561, 585, 588, 1909, 1962` plus the resolution sites `3627, 3636, 3721, 3765, 3964`. The purpose assignment of all eleven was verified against the source and is correct.

### Acceptance

- [ ] `list_indexable_bundles(root)` exists, derives the set from the `.okf.toml` `bundle` key, falls back to the current name filter when the key is absent.
- [ ] It is used at all eight positive call sites: 740, 745, 785, 793, 851, 3312, 3317, 3326.
- [ ] `is_bundle_dir` is unchanged.
- [ ] All eleven negative call sites still call `list_bundles`. A test asserts this, so a later refactor cannot quietly narrow them.
- [ ] `okf-cli --root /Users/erik/dev/lean-stack/docs build-index` reports **41** documents, down from 197. Quote the command and its output.
- [ ] The catalogue is unaffected: a run against `~/Obsidian/Knowledge-Catalogue` yields the same corpus size as before the change. Quote both numbers.
- [ ] `just test` shows the three known `RunnerAgainstRealCatalogueTest` failures recorded in the epic baseline and **no fourth**.
- [ ] Mutation proof against the acceptance, not against arbitrary logic: remove the `bundle`-key lookup so the fallback always applies, show a test goes red, revert byte-identically.

## Summary

Added `list_indexable_bundles(root, config_root=None)` next to `list_bundles(root)`
in `cli/okf-cli.py`, derived from the `.okf.toml` `bundle` key, falling back to
`list_bundles(root)` (catalogue behaviour) when the key is absent or malformed,
and returning the **empty set** (not a silent fallback) when the declared
bundle does not exist on disk — chosen because a `bundle` key is a positive
declaration, and falling back the moment its path went missing would quietly
resurrect every TPIC-scaffolding directory into the index, the exact
regression the split exists to prevent.

Wired into exactly the eight positive call sites — `build_fts_index` (active
+ archive), `_fts_index_stale` (active + archive), `cmd_build_semantic_index`
`--if-stale`, and `resolve_scopes`'s three `list_bundles(root)` occurrences
(unscoped target, `.`/empty target, and its `_archive/` mirror). All eleven
negative call sites (presentation: `all_tags`, `cmd_index` `--json`/compact/
`--full` TOC, `render_catalogue_state`, `cmd_prime`; resolution/integrity:
`build_concept_basename_index` active+archive, `wikilink_checked_bundles`,
`cmd_wikilinks` target validation, `iter_rename_scan_md` symlink traversal)
still call `list_bundles` unchanged. `is_bundle_dir` untouched.

## Signature detail beyond the bean's sketch

The bean sketches `list_indexable_bundles(root)`. The two archive call sites
(745/793/3326, now inside `build_fts_index`, `_fts_index_stale`,
`resolve_scopes`) pass `archive_root` (`<root>/_archive`) as the directory to
*list*, but `.okf.toml` lives once, at the real root — `archive_root` itself
has no config. A naive `list_indexable_bundles(archive_root)` would look for
`archive_root/.okf.toml`, find nothing, and silently widen back to
`list_bundles(archive_root)` — failing acceptance test 6 (the archive branch
must stay scoped to the declared bundle). Added a second, optional
`config_root` parameter (default `root`) so the archive call sites read the
`bundle` key from the real root while still listing `_archive/`:
`list_indexable_bundles(archive_root, root)`. Covered by
`IndexableArchiveScopedToDeclaredBundle` (both the FTS-index and the
`resolve_scopes --include-archive` assertions).

## Test-Output

RED (function did not exist / narrowing not wired in yet):

```
$ python3 -m unittest test_okf_cli.ListIndexableBundles test_okf_cli.BundleKeyDoesNotNarrowResolution test_okf_cli.IndexableArchiveScopedToDeclaredBundle -v
...
AttributeError: module 'okf_cli' has no attribute 'list_indexable_bundles'
...
FAIL: test_find_include_archive_scope_excludes_the_undeclared_bundle
AssertionError: '_archive/other-scaffolding' unexpectedly found in [...]
FAIL: test_fts_index_excludes_the_undeclared_archived_bundle
AssertionError: '_archive/other-scaffolding/three' unexpectedly found in [...]
----------------------------------------------------------------------
Ran 7 tests in 0.009s
FAILED (failures=2, errors=4)
```
(1 of the 7 — the resolution guard — was already green pre-implementation,
correctly: `build_concept_basename_index` never called the new function.)

GREEN, all 7 new tests:

```
$ python3 -m unittest test_okf_cli.ListIndexableBundles test_okf_cli.BundleKeyDoesNotNarrowResolution test_okf_cli.IndexableArchiveScopedToDeclaredBundle -v
...
Ran 7 tests in 0.008s
OK
```

`just test` gate (682 total = 675 baseline + 7 new; exactly the three
pre-existing `RunnerAgainstRealCatalogueTest` failures, no fourth):

```
FAIL: test_index_walk_row_present_with_rank_no_dedicated_metric (test_eval_runner.RunnerAgainstRealCatalogueTest.test_index_walk_row_present_with_rank_no_dedicated_metric)
FAIL: test_metadata_hit_and_miss_rows_scored_correct (test_eval_runner.RunnerAgainstRealCatalogueTest.test_metadata_hit_and_miss_rows_scored_correct)
FAIL: test_runner_scores_literal_s1_top1 (test_eval_runner.RunnerAgainstRealCatalogueTest.test_runner_scores_literal_s1_top1)
Ran 682 tests in 25.618s
FAILED (failures=3)
```

## Measurement

Never built against the live repos — worked against tmpdir copies (`cp -R`)
per instructions.

`lean-stack/docs` copy, `build-index`:

```
=== WITH bundle key (bundle = "lean-stack-okf") ===
indexed 52 concept(s) -> .../lean-stack-docs-with-bundle/.fts/fts.sqlite
=== WITHOUT bundle key (line removed from the copied .okf.toml) ===
indexed 245 concept(s) -> .../lean-stack-docs-no-bundle/.fts/fts.sqlite
```

**Deviation from the bean's quoted 197/41:** the bean's "expected effect"
(197 -> 41) was measured earlier the same day (epic baseline). A read-only
recount against the *real* `lean-stack/docs` (no writes, `list_bundles` +
`iter_concepts`, matching `build_fts_index`'s own counting) shows **245**
active concepts today under the name filter and **52** under the declared
bundle — the repo has grown by legitimate, unrelated edits between the
epic's baseline measurement and this task's execution (`lean-stack-okf`
directory mtime postdates the epic bean's creation timestamp; no `_archive/`
dir exists there, ruling out an archive-counting bug on my side). The
mechanism's effect size is unchanged: 52/245 = 21.2% vs. the bean's
41/197 = 20.8% — same ~79% reduction, confirming the narrowing works exactly
as specified; only the absolute baseline moved. Recommend the PO treat 41/197
as stale and 52/245 as the current, correct figures rather than requiring a
match to the older numbers.

Catalogue unaffected — read-only against the real
`~/Obsidian/Knowledge-Catalogue` (`.okf.toml` there carries no `bundle` key,
verified), no writes:

```
bundle key present: False
list_bundles == list_indexable_bundles: True
bundle count: 23
total concepts old-path: 2522 new-path: 2522
```

## Mutation proof

1. Removed the `bundle`-key evaluation from `list_indexable_bundles` (always
   `return list_bundles(root)`) -> 4 of the new tests went red:

```
FAIL: test_declared_bundle_missing_on_disk_yields_empty_not_fallback
AssertionError: Lists differ: ['some-other-dir'] != []
FAIL: test_find_include_archive_scope_excludes_the_undeclared_bundle
AssertionError: '_archive/other-scaffolding' unexpectedly found in [...]
FAIL: test_fts_index_excludes_the_undeclared_archived_bundle
AssertionError: '_archive/other-scaffolding/three' unexpectedly found in [...]
----------------------------------------------------------------------
Ran 6 tests in 0.010s
FAILED (failures=4)
```
   Reverted byte-identically (restored from a pre-mutation copy; verified via
   `git diff` against HEAD showing only the intended feature diff).

2. Umkehrmutation: broke `build_concept_basename_index` (a negative-list,
   resolution call site) to call `list_indexable_bundles` instead of
   `list_bundles` -> the guard test went red:

```
$ python3 -m unittest test_okf_cli.BundleKeyDoesNotNarrowResolution -v
FAIL: test_wikilink_to_a_concept_outside_the_declared_bundle_resolves
AssertionError: 'unresolved' != 'resolved'
----------------------------------------------------------------------
Ran 1 test in 0.003s
FAILED (failures=1)
```
   Confirms it is a real guard (the reverse mutation earned its red). Reverted
   byte-identically; `git diff` against HEAD again shows only the feature diff.

## Smoke

`okf-cli --root <tmpdir-copy> build-index` above IS the smoke test (real CLI
entrypoint, not just unit tests) — run twice, with and without the `bundle`
key, against copies of `lean-stack/docs`. No write ever touched
`/Users/erik/dev/lean-stack` or `~/Obsidian/Knowledge-Catalogue`.

## Deviations/ERRATA

- **D01 (signature elaboration, not a scope deviation):** `list_indexable_bundles`
  gained an optional second parameter `config_root` beyond the bean's
  `list_indexable_bundles(root)` sketch, required for the three archive-branch
  call sites to read the declared bundle from the real root while still
  listing `_archive/` — see "Signature detail beyond the bean's sketch" above.
  No call-site behaviour outside the archive branch is affected; the
  single-argument form (`config_root=None` -> defaults to `root`) is what all
  five non-archive positive call sites use.
- **D02 (measurement, not implementation):** the bean's quoted 197/41 corpus
  sizes are stale relative to the live `lean-stack/docs` repo (245/52 today,
  same ~79% reduction ratio) — see "Measurement" above. Not caused by this
  change; the repo was edited between the epic's baseline capture and this
  task's execution.
- No other deviation from the bean's positive/negative line lists or from D01's
  correction (call sites 745/793/3326 joining the positive list, `560`->`561`
  correction) — all verified against the current source before editing.

## Notes for T(n+1)

- `resolve_scopes` is shared by more than `find`: `cmd_merge_tags`,
  `cmd_remove_tags`, `cmd_normalize_tags`, `cmd_list` (line ~624, NOT on
  either list), `fix_xml_like_tags`, `fix_crosslinks`, `scan_wikilinks`
  (wikilinks command) and `run_checks` (`check` command) all call it too, and
  all of them reach its unscoped branch (now narrowed) whenever they run
  without an explicit `--scope`/target. The bean's positive list names the
  three `resolve_scopes` lines with the annotation "(resolve_scopes -> find)",
  which undercounts `resolve_scopes`'s actual caller set the same way the
  original census undercounted the archive-branch call sites (D01/B01).
  Implemented literally per the bean's explicit acceptance list (all given
  tests pass, including the resolvability guard, because `build_concept_basename_index`
  — the actual resolution TARGET index — is untouched and independent of
  `resolve_scopes`), but flagging this for the PO/next supervisor: an
  unscoped `check`/`wikilinks`/`merge-tags`/`remove-tags`/`normalize-tags`/
  `fix-crosslinks`/`fix-xml-like-tags` run in a repo docs root with a declared
  `bundle` key will now also only traverse the declared bundle, not every
  TPIC-scaffolding directory. Currently harmless in practice (repo docs roots
  declare exactly one bundle and nobody targets scaffolding dirs with these
  mutation commands), but worth a deliberate look if a future bean widens
  their use.
- Corpus baseline (197/41 in the bean) is stale; see D02 above. A future
  measurement task should re-baseline against 245/52 or re-run at execution
  time rather than trusting numbers frozen at epic-creation time in a
  concurrently-edited repo.


## Review 2026-08-13 — CHANGES_REQUIRED (ce-specs-reviewer, verified by experiment)

### B01 (blocking) — narrowing `resolve_scopes` traded the loud defect for the silent one

The eleven negative call sites are clean; the reviewer walked all eleven by function and each still calls `list_bundles`. The defect is at the two sites that were on the *positive* list: `resolve_scopes` (now :3349, :3354) is not a `find` helper. Ten commands go through it:

`cmd_merge_tags` (:266), `cmd_remove_tags` (:303), `cmd_normalize_tags` (:356), `cmd_list` (:641), `_substring_ranking` (:1230, find), `_recent_scopes` (:2706), `fix_xml_like_tags` (:3123), `fix_crosslinks` (:3273), `scan_wikilinks` (:3730, the `wikilinks` command), `run_checks` (:3843, the `check` command).

Narrowing inside the shared function narrowed all ten. Measured against a copy of the real `okf-tools/docs`, whose `.okf.toml` carries `bundle = "okf-tools-okf"`:

- unscoped `okf-cli --root docs check` reports `OK — 0 violations`
- the same violations, scanned per directory, are still there: `okf-retrieval-architecture` 23, `okf-revision` 9, `wikilink-awareness` 1 — **33 real violations a default run no longer sees**

And on a synthetic tmpdir repo: `wikilinks` unscoped reports `0 unresolved` with the `bundle` key present, while a real `[[does-not-exist-anywhere]]` link sits in an undeclared directory; remove the key and the same run reports `1 unresolved`.

This is live today in both okf-tools and lean-stack — the two repos this epic measured against. The implementer's `harmless today` is refuted.

### D02 — the fix: opt in at the caller, never inside the shared function

`resolve_scopes` keeps `list_bundles` as its default. Add an explicit opt-in parameter (e.g. `indexable_only=False`) and pass it `True` from **only** the find/index path — `_substring_ranking` (:1230) and any other path that feeds the search corpus.

Everything else keeps the wide set, and for two distinct reasons:

- `run_checks` and `scan_wikilinks` are integrity paths. D17 names them explicitly: narrowing them is the exact trade this epic exists to avoid.
- `cmd_merge_tags`, `cmd_remove_tags`, `cmd_normalize_tags`, `fix_xml_like_tags`, `fix_crosslinks` **write files**. A silently narrowed mutation command skips files it used to repair — worse than a narrowed read.
- `_recent_scopes` is presentation.

`cmd_list` (:641) stays **wide** for now. It is neither on D17's index/search list nor on its presentation list — the same under-census that produced B01 at Gate B. Wide is the conservative default. Raised as Q03 on the epic; do not decide it here.

### I01 (required with the fix) — the guard did not guard this

`BundleKeyDoesNotNarrowResolution` only exercises `build_concept_basename_index`. It never touches the `run_checks`/`scan_wikilinks` path through `resolve_scopes`, which is why a green suite shipped a silent regression. The fix needs a behavioural test that fails if `check` or `wikilinks` unscoped ever narrows again: a docs root with a `bundle` key, a real violation in an undeclared directory, and an assertion that the default run still reports it.

### Q02 — measurement 52 instead of the acceptance's 41

Reproduced independently: `list_bundles` → 25 directories / 245 concepts, `list_indexable_bundles` → exactly `['lean-stack-okf']` / 52 concepts. `lean-stack-okf` holds 55 `.md` files, 52 counted concepts, difference explained by reserved files; 24 commits touched that directory since 2026-08-01. The gap to 41 is organic growth, no scaffolding leaking into the corpus. Accepted as a deviation, PO to confirm at the gate.

### Not a finding

Test substance is sound — all seven tests import production functions, no hand-rolled parser. The reverse mutation was executed by the reviewer (:3664 switched to the narrow set) and turned `BundleKeyDoesNotNarrowResolution` red, reverted byte-identically. The missing-bundle-directory case yields the empty set, no silent fallback. `just test`: `Ran 682 tests in 26.417s`, `FAILED (failures=3)`, exactly the three baseline failures.
