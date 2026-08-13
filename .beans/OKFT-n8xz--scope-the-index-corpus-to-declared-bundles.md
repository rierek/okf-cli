---
# OKFT-n8xz
title: Scope the index corpus to declared bundles
status: todo
type: task
priority: high
created_at: 2026-08-13T11:07:18Z
updated_at: 2026-08-13T11:24:27Z
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
