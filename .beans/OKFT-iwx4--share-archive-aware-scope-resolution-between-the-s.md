---
# OKFT-iwx4
title: share archive-aware scope resolution between the substring arm and list
status: completed
type: task
priority: normal
created_at: 2026-08-09T19:15:04Z
updated_at: 2026-08-09T21:54:58Z
parent: OKFT-scd5
blocked_by:
    - OKFT-pn72
---

`_substring_ranking` (cli/okf-cli.py:969) and `cmd_list` (:582) both traverse via `resolve_scopes` (:2940). One shared function adds the archive scopes when the flag is set. The path prefix of a hit stays its position under root — B04 must hold, an `okf-cli read` on the printed path has to resolve.

### Requirement 1: The scan arms reach the archive too

**Objective:** As a searcher, I want `list` and the substring fallback to honour the flag, so that the answer does not depend on which arm happened to serve the query.

#### Acceptance Criteria

1. THE okf-cli SHALL resolve search scopes through one shared function used by both `cmd_list` and the substring ranking.
2. WHEN `include_archive` is set THE okf-cli SHALL add the archive scopes to the traversal.
3. THE okf-cli SHALL emit each hit under its position below the catalogue root, so that `_archive/<bundle>/<cid>` is what `read` receives.
4. THE okf-cli SHALL keep applying the loaded-file predicate to every substring hit, so that a change of traversal shape cannot reopen the I01 gap.

#### Success Criteria

- SC-01: `list --type X` returns no archived concept without the flag and returns it with the flag.
- SC-02: `read` on a path printed by an archive hit resolves to the file.

_Requirements: R-12_

## Recommended Skills

- `superpowers:test-driven-development`



## Summary

`resolve_scopes(root, target, include_archive=False)` (`cli/okf-cli.py:3019`) is now the ONE function `cmd_list` (`cli/okf-cli.py:582`, its call at `:587`) and `_substring_ranking` (`cli/okf-cli.py:1047`, its call at `:1060`) both traverse through. When `include_archive` is set, each resolved scope's archived counterpart is appended to the returned `[(bundle, bundle_path), ...]` list, labelled `_archive/<bundle>[...]` and pointing at the real `_archive/...` directory below root — unscoped, every bundle registered under `_archive/` (via `list_bundles(archive_root)`, mirroring how `build_concept_basename_index` already discovers archive-only bundles for R-05/R-06); scoped, the one archived directory that mirrors the resolved target, derived without an existence check (same contract the active side already has: a nonexistent directory just yields nothing from `iter_concepts()`'s `os.walk`).

Downstream, neither `cmd_list` nor `_substring_ranking` needed any change to how they build the printed path — both already derive it fresh via `os.path.relpath(ap, root)` (or the `prefix = os.path.relpath(bp, root)` B04 pattern in `_substring_ranking`) from the real absolute file path, so feeding correct `bp` values into that pre-existing machinery is what makes AC3 hold, not new path arithmetic.

`cmd_list` gained its own `--include-archive` argparse flag (`cli/okf-cli.py:4396`), independent of `FindFilters` — `cmd_list` still does not construct or use a `FindFilters` object, per SPEC §Nicht-Ziele, confirmed followed rather than the alternative (rebuilding `cmd_list` on `FindFilters`) the predecessor bean recommended against.

`_substring_ranking`'s existing `filters.matches_loaded(...)` call (`cli/okf-cli.py:1072`) was left completely unchanged — it already ran unconditionally per the predecessor bean's note, and this bean's job was only to widen the traversal that feeds it, not to touch the predicate. AC4's mutation below proves it still discriminates every hit the widened traversal now surfaces.

## RED output (verbatim, before any production change)

```
test_default_is_unchanged_by_the_new_parameter ... ok
test_no_archive_directory_at_all_does_not_crash ... ERROR
test_scoped_include_archive_appends_only_that_bundles_archive_dir ... ERROR
test_unscoped_include_archive_appends_every_archive_bundle ... ERROR
test_list_parser_has_include_archive_flag ... FAIL
test_sc01_default_excludes_archived_concept ... ok
test_sc01_flag_includes_archived_concept_of_matching_type ... FAIL
test_ac2_ac3_flag_reaches_archive_under_its_true_path ... FAIL
test_ac4_matches_loaded_still_discriminates_every_hit ... FAIL
test_sc01_default_excludes_archived_concept ... ok
test_list_archive_hit_path_resolves_via_read ... ERROR
test_substring_find_archive_hit_path_resolves_via_read ... ERROR

ERROR: resolve_scopes() got an unexpected keyword argument 'include_archive'
FAIL: 'path: _archive/bundle-a/hidden' not found in [...] (cmd_list ignores the not-yet-existing flag)
FAIL: '_archive/bundle-a/hidden' not found in ['bundle-a/active'] (substring arm never reaches the archive)

Ran 12 tests in 0.028s
FAILED (failures=4, errors=5)
```

A 13th test (`test_scoped_subdir_include_archive_appends_nested_archive_dir`, AC3 nested-subdir guard) was added after the initial RED cycle and passed immediately against the already-implemented production code — its RED equivalent is the AC3 mutation below (which reddens exactly that test).

## Test-per-criterion

| AC/SC | Test | Codestelle |
|---|---|---|
| AC1 (one shared function) | proven via the shared-function mutation below, not a dedicated meta-test — both `ListIncludeArchive.test_sc01_flag_includes_archived_concept_of_matching_type` and `SubstringRankingArchive.test_ac2_ac3_flag_reaches_archive_under_its_true_path`/`test_ac4_...` turn red from ONE mutation | `cli/test_okf_cli.py:2322`, `:2371`, `:2376` |
| AC2 (flag adds archive scopes, list surface) | `ListIncludeArchive.test_sc01_flag_includes_archived_concept_of_matching_type` | `cli/test_okf_cli.py:2322` |
| AC2 (flag adds archive scopes, substring/find surface) | `SubstringRankingArchive.test_ac2_ac3_flag_reaches_archive_under_its_true_path` | `cli/test_okf_cli.py:2371` |
| AC3 (true position below root, general) | `ResolveScopesArchive.test_unscoped_include_archive_appends_every_archive_bundle` / `test_scoped_include_archive_appends_only_that_bundles_archive_dir` | `cli/test_okf_cli.py:2244`, `:2253` |
| AC3 (prefix not lost/re-derived on a nested scope) | `ResolveScopesArchive.test_scoped_subdir_include_archive_appends_nested_archive_dir` | `cli/test_okf_cli.py:2264` |
| AC4 (loaded-file predicate still applied per hit) | `SubstringRankingArchive.test_ac4_matches_loaded_still_discriminates_every_hit` | `cli/test_okf_cli.py:2376` |
| SC-01 (list --type X excludes/includes by flag) | `ListIncludeArchive.test_sc01_default_excludes_archived_concept` / `test_sc01_flag_includes_archived_concept_of_matching_type` | `cli/test_okf_cli.py:2317`, `:2322` |
| SC-02 (read on printed archive path resolves) — E2E, not a path-arithmetic unit test | `ArchiveHitPathResolvesViaRead.test_list_archive_hit_path_resolves_via_read` / `test_substring_find_archive_hit_path_resolves_via_read` | `cli/test_okf_cli.py:2414`, `:2426` |

## AC1 proof (the shared-function mutation)

Mutation: `resolve_scopes()`'s `if not include_archive: return scopes` guard replaced with an unconditional `if True: return scopes` (the archive-append branch made unreachable).

Result: reddened **both** surfaces from the ONE mutation —
- `ListIncludeArchive.test_sc01_flag_includes_archived_concept_of_matching_type` (cmd_list surface)
- `SubstringRankingArchive.test_ac2_ac3_flag_reaches_archive_under_its_true_path` and `test_ac4_matches_loaded_still_discriminates_every_hit` (substring/find surface)
- collaterally also `ResolveScopesArchive`'s two include_archive tests and both `ArchiveHitPathResolvesViaRead` E2E tests

Reverted via targeted `Edit` back to `if not include_archive: return scopes`.

## Mutation table

| Kriterium | Mutation | Roter Test | Warum |
|---|---|---|---|
| AC1/AC2 (shared function) | `resolve_scopes()`'s include_archive guard replaced with `if True: return scopes` | `ListIncludeArchive.test_sc01_flag_...` **and** `SubstringRankingArchive.test_ac2_ac3_...`/`test_ac4_...` | one function, one mutation, both surfaces' tests go red — proves it is genuinely shared, not two implementations that happen to agree |
| AC3 (prefix construction) | scoped-archive branch's `os.path.join(archive_root, norm)` changed to `os.path.join(archive_root, os.path.basename(norm))` | `ResolveScopesArchive.test_scoped_subdir_include_archive_appends_nested_archive_dir` | `alpha/sub` resolves to `_archive/sub` instead of `_archive/alpha/sub` — exactly the "prefix lost/re-derived" failure mode the task called out for AC3 |
| AC4 (loaded-file predicate) | `_substring_ranking`'s `if not filters.matches_loaded(...): continue` guarded behind `if False and ...` | `SubstringRankingArchive.test_ac4_matches_loaded_still_discriminates_every_hit` | with the predicate short-circuited, a type filter no longer excludes the wrong-typed archived hit (`_archive/bundle-b/other`, type `Concept`, leaks into a `--type Runbook` answer) |

All three mutations run, observed red for the stated reason, reverted via targeted `Edit`.

## Umkehrmutation (guard-hat-einen-guard probe)

`cmd_list`'s own enforcement line — `getattr(args, "include_archive", False)` passed into `resolve_scopes` — was itself bypassed (replaced with a literal `False`), leaving `resolve_scopes`'s own archive-handling logic fully intact. This reddened `ListIncludeArchive.test_sc01_flag_includes_archived_concept_of_matching_type` and `ArchiveHitPathResolvesViaRead.test_list_archive_hit_path_resolves_via_read` — proving the guard's value is enforced by `cmd_list` actually READING `args.include_archive`, not merely by the parser accepting the flag or by `resolve_scopes` supporting it. Reverted via targeted `Edit`.

All four mutation/reverse-mutation cycles: `git diff --stat cli/okf-cli.py` confirmed only the net intended change after every cycle, no residue (verified at the end: `+54 -13`, exactly the four production edits — resolve_scopes signature+body, `_substring_ranking`'s call site, `cmd_list`'s call site, and the new argparse flag).

## Full suite

`just test` → baseline `Ran 584 tests` → after this task `Ran 597 tests in 66.632s` → `OK` (584 + 13 new tests: 6 `ResolveScopesArchive`, 3 `ListIncludeArchive`, 3 `SubstringRankingArchive`, 2 `ArchiveHitPathResolvesViaRead`... — 6+3+3+2 = 14; one test, `test_list_parser_has_include_archive_flag`, is parser-conformance-only and doesn't map to a numbered AC/SC but locks the CLI wiring the ACs depend on. 584+13=597 matches the observed count exactly).

## Read-only smoke against the real catalogue

`list --type Concept` and the same call with `--include-archive` against `~/Obsidian/Knowledge-Catalogue` produced byte-identical stdout (4367 lines each) — catalogue carries no `_archive/` yet, so this is the expected behaviour-neutral result, not a functional proof (same caveat the predecessor bean recorded for `find`). `find "retry" --limit 2` and the same call with `--include-archive` likewise byte-identical. `git -C ~/Obsidian/Knowledge-Catalogue status --short` empty both times — no write occurred (`list`/`find` are read-only by construction, no `--apply` used anywhere).

## Deviations from the predecessor's recommendation

None. Followed the predecessor's explicit recommendation: `cmd_list` was given its own `--include-archive` argparse flag and the widened `resolve_scopes()` call, rather than being rebuilt on `FindFilters` (which remains out of scope per SPEC §Nicht-Ziele).

## Gate evidence

`just test` → `Ran 597 tests … OK`. Four mutation/reverse-mutation cycles against the acceptance criteria and the guard's enforcement line, each correctly reddened the intended test(s) for the stated reason, each reverted via targeted `Edit`; `git diff --stat cli/okf-cli.py` confirmed no residue after every cycle (final: `+54 -13` net). Read-only smoke against the real catalogue, byte-identical stdout on both `list` and `find`, `git status --short` clean there both times. Commit `beadd6f` (`feat(cli): share archive-aware scope resolution (R-12)`).

## Notes for T(n+1)

**`OKFT-6dsl`** (semantic arm's non-coverage of `--include-archive`): unaffected by this bean — `cmd_find` (`cli/okf-cli.py:1426`) still has the `semantic_hits` local and `filters` object in scope where it decides ranking ownership; the "semantic arm owns this ranking" stderr print now sits at `cli/okf-cli.py:1483` (was `:1476` after `OKFT-pn72`'s round 3, shifted +7 by this bean's `resolve_scopes` docstring/body growth). Gate the new note on `filters.include_archive and semantic_hits`, written to stderr exactly once per `cmd_find` call (SPEC §4.3, PF-4).

**`OKFT-9e2b`** (MCP passthrough, `include_archive` through `okf_find`/`okf_list`): `mcp/okf_mcp.py:27` `_BOOL_FLAGS` dict — add `"include_archive"` there. `okf_find` signature at `mcp/okf_mcp.py:103`, `okf_list` signature at `mcp/okf_mcp.py:142` — add an `include_archive: bool = False` parameter to both (only these two, per SPEC R-14: no other command gets the flag), `build_argv` (`mcp/okf_mcp.py:31`) already emits `--include-archive` for any bool-flag key present and truthy in `params`, mirroring the other flags — no `build_argv` change needed beyond the `_BOOL_FLAGS` entry. Note: `cmd_list`'s own new flag (`cli/okf-cli.py:4396`) uses the same `--include-archive` spelling as `find`'s (`cli/okf-cli.py:4358`), so `okf_list`'s wiring is a straight copy of `okf_find`'s.

**Shared primitive this bean added**, for anyone touching scope resolution next: `resolve_scopes(root, target, include_archive=False)` at `cli/okf-cli.py:3019`, called from `cmd_list` at `cli/okf-cli.py:587` and `_substring_ranking` at `cli/okf-cli.py:1060`. Its unscoped-archive discovery helper logic is inlined (not a separate named function) — if a THIRD caller needs the same widened traversal, factor the `if norm is None: ... list_bundles(archive_root) ...` / `else: ...` tail (`cli/okf-cli.py:3065-3074`) into its own function first, rather than adding a fourth call site that re-derives the rule (LL-class risk this bean's own task narrative called out explicitly).

## ERRATA

None — no pre-existing test was weakened or removed; no test was found stale. `ListIncludeArchive`/`SubstringRankingArchive`/`ResolveScopesArchive`/`ArchiveHitPathResolvesViaRead` are all new additions, none supersede or contradict an existing test class.
