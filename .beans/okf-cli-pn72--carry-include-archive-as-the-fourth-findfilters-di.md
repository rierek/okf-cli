---
# okf-cli-pn72
title: carry include_archive as the fourth FindFilters dimension
status: completed
type: task
priority: normal
created_at: 2026-08-09T19:14:21Z
updated_at: 2026-08-09T21:03:20Z
parent: okf-cli-scd5
---

`FindFilters` (cli/okf-cli.py:761) documents at its own head why a filter dimension must live in the value object: the same three filters were once implemented three times, travelled as loose arguments through five signatures, and were missing from the semantic arm entirely (I01/B01). The visibility switch follows the same discipline, and the scope rule falls out of the same predicate.

### Requirement 1: Archive visibility as a filter dimension

**Objective:** As a searcher, I want the archive excluded by default and reachable with one flag, so that the default answer describes the active catalogue and nothing is silently lost.

#### Acceptance Criteria

1. THE okf-cli SHALL carry `include_archive` as a field of `FindFilters`, defaulting to excluded.
2. WHILE `include_archive` is not set THE okf-cli SHALL treat every path beginning with `_archive/` as no match.
3. THE okf-cli SHALL compare a scope against the path with its leading `_archive/` segment removed, so that a scoped query reaches the archived concepts of that same bundle.
4. THE okf-cli SHALL escape the underscore in the SQL LIKE predicate so that a bundle named `xarchive` is not excluded by it.

#### Success Criteria

- SC-01: `find <term>` without the flag returns no archived concept even though the concept is present in the index.
- SC-02: `find <term> --include-archive` returns it under its `_archive/<bundle>/<cid>` path.
- SC-03: `find <term> --scope <bundle> --include-archive` returns archived concepts of that bundle and none from another.
- SC-04: A bundle named `xarchive` remains visible without the flag.
- SC-05: Removing the default-exclusion predicate turns SC-01's test red; the test stays in the repo.

_Requirements: R-08, R-09, R-10_

## Recommended Skills

- `superpowers:test-driven-development`



## Summary

`FindFilters` (`cli/okf-cli.py:761`) gained `include_archive` as its fourth field, default `False`. `sql_where()` widens the scope OR-chain to also match `_archive/<scope>` and `_archive/<scope>/%` (R-09, SQL side), and adds the default exclusion `AND path NOT LIKE '\_archive/%' ESCAPE '\'` when `include_archive` is unset (R-08/R-10). `path_in_scope()` — the one non-SQL primitive both `matches()` and `matches_loaded()` already funnel through — carries the same two rules for the file-walking arms (R-08/R-09): a path under `_archive/` is invisible unless `include_archive` is set, and once it is, scope compares against the path with that leading segment stripped. `cmd_find` gained `--include-archive` (`action="store_true"`) and passes it into `FindFilters`.

`FindFilters.__bool__` stays defined over `scope/type/tag` only (unchanged), and the `if not self: return True` fast-path in `matches()` was removed instead of folding `include_archive` into `__bool__` — the first draft did fold it in, which broke `_fts_ranking`'s `assert not residual, "docs table covers every filter dimension"` (the residual's `include_archive` is now always carried through, so a residual with `__bool__` sensitive to it would look "non-empty" even when every dimension was SQL-covered). Removing the shortcut instead keeps `__bool__`'s existing contract (used by that assertion) untouched and still guarantees `path_in_scope()` runs unconditionally.

## RED output (verbatim, before any production change)

```
test_sc01_default_excludes_archived_concept_present_in_index ... FAIL
test_sc02_include_archive_flag_returns_it_under_its_archive_path ... ok
test_sc03_scoped_include_archive_reaches_only_that_bundle ... FAIL
test_sc04_bundle_named_xarchive_stays_visible_without_the_flag ... ok

FAIL: test_sc01_default_excludes_archived_concept_present_in_index
AssertionError: '_archive/bundle-a/hidden' unexpectedly found in
['_archive/bundle-a/hidden', 'bundle-a/active', 'xarchive/visible',
'_archive/bundle-b/other-hidden']

FAIL: test_sc03_scoped_include_archive_reaches_only_that_bundle
AssertionError: '_archive/bundle-a/hidden' not found in ['bundle-a/active']

Ran 4 tests in 0.019s
FAILED (failures=2)
```

SC-02 and SC-04 pass trivially pre-change — documented, not concealed: pre-change there is no default-exclusion predicate to *override* (SC-02) and no `_archive/%` predicate to be *unescaped* against yet (SC-04). Both become real regression guards the moment the predicate exists, which the mutation table below proves.

## Test-per-SC

| SC | Test | Codestelle |
|---|---|---|
| SC-01 | `FindIncludeArchive.test_sc01_default_excludes_archived_concept_present_in_index` | `cli/test_okf_cli.py:2053` |
| SC-02 | `FindIncludeArchive.test_sc02_include_archive_flag_returns_it_under_its_archive_path` | `cli/test_okf_cli.py:2058` |
| SC-03 | `FindIncludeArchive.test_sc03_scoped_include_archive_reaches_only_that_bundle` | `cli/test_okf_cli.py:2062` |
| SC-04 | `FindIncludeArchive.test_sc04_bundle_named_xarchive_stays_visible_without_the_flag` | `cli/test_okf_cli.py:2068` |
| SC-05 | same test object as SC-01 (mutation proof, not a separate test) | `cli/test_okf_cli.py:2053` |

Additional, not one of the five named SC but required so R-08/R-09 aren't dead code on the primitive `okf-cli-iwx4`/`okf-cli-6dsl` will build on — `_substring_ranking`/semantic-arm traversal don't route any archived path through `path_in_scope()` today, so without a direct test its archive-exclusion branch would be unguarded:

| Primitive | Test | Codestelle |
|---|---|---|
| `path_in_scope` default-excludes | `PathInScopeArchiveRule.test_archived_path_excluded_by_default` | `cli/test_okf_cli.py:2085` |
| `path_in_scope` honours the flag | `PathInScopeArchiveRule.test_archived_path_included_when_flagged` | `cli/test_okf_cli.py:2089` |
| `path_in_scope` scope-strip | `PathInScopeArchiveRule.test_scope_compares_against_archive_stripped_path` | `cli/test_okf_cli.py:2093` |

## Mutation table

| Kriterium | Mutation | Roter Test | Warum |
|---|---|---|---|
| AC2/R-08 (SQL exclusion) | Guarded the `NOT LIKE '\_archive/%' ESCAPE '\'` block behind `if False and ...` in `sql_where()` | `test_sc01_...` | Without the exclusion clause the FTS arm's `docs` query no longer filters `_archive/` paths out, so the archived concept surfaces in the default (no-flag) answer. |
| AC3/R-09 (SQL scope widening) | Reverted the scope OR-chain to the original 2-clause form (`col = ? OR col LIKE ?`), dropping the `_archive/<scope>` / `_archive/<scope>/%` arms | `test_sc03_...` | `--scope bundle-a --include-archive` now only matches literal `bundle-a[/...]`; the archived path `_archive/bundle-a/hidden` no longer satisfies any OR-branch and drops out of the scoped answer. |
| AC4/R-10 (ESCAPE) | Removed `ESCAPE '\\'` and the backslash-escaping of the underscore, leaving `NOT LIKE '_archive/%'` unescaped | `test_sc04_...` | `_` is a LIKE single-char wildcard when unescaped, so the pattern also matches `xarchive/visible` (`_` standing in for `x`), and the default predicate wrongly excludes a bundle merely named similarly. |
| AC2/AC3 primitive (`path_in_scope`) | Removed `if archived and not self.include_archive: return False` from `path_in_scope()` | `PathInScopeArchiveRule.test_archived_path_excluded_by_default` | With the guard line gone, `path_in_scope()` no longer distinguishes an archived path from an active one at all — an unscoped filter now treats `_archive/bundle-a/hidden` as in scope. |

All four mutations applied, run, observed red, then reverted via targeted `Edit` back to the exact original text — `git diff --stat cli/okf-cli.py` shows only the net intended change (71 insertions / 16 deletions) after every mutation cycle, no residue.

## Umkehrmutation (Guard-hat-einen-Guard-Probe)

Each of the four mutations above *is* the reverse-mutation proof required by Gate item 6: each removes exactly the enforcement line the corresponding test exists to guard, and each turns a specific, correctly-attributed test red (not a collateral failure elsewhere) — see the "Warum" column. No mutation left a false-green outcome.

## Full suite

`just test`: baseline `Ran 573 tests … OK` → after this task `Ran 580 tests in 64.546s` → `OK` (573 + 4 `FindIncludeArchive` + 3 `PathInScopeArchiveRule`).

## Read-only smoke against the real catalogue

`okf-cli find "retry" --limit 3` and the same call with `--include-archive` against `~/Obsidian/Knowledge-Catalogue` produced byte-identical stdout (catalogue carries no `_archive/` yet, so this is the expected verhaltensneutral result, not a functional proof). `git -C ~/Obsidian/Knowledge-Catalogue status --short` empty afterwards — no write occurred (no `--apply` was used; `find` is read-only by construction). `okf-cli find --help` shows the new `--include-archive` line.

## Notes for T(n+1)

**`okf-cli-iwx4`** (resolve_scopes → `_substring_ranking` (:969) → `cmd_list` (:582)): the visibility/scope-strip predicate is already the single named place — `FindFilters.path_in_scope(self, path) -> bool` — and `_substring_ranking`'s existing call `filters.matches_loaded("{}/{}".format(prefix, cid), fm, text)` (line ~994) already routes through it, unchanged, needing **no** edit. What iwx4 actually needs to add is upstream of that: `resolve_scopes(root, target)` (:2940) itself never yields an `_archive/<bundle>` directory to traverse (bundle discovery excludes `_`-prefixed dirs via `is_bundle_dir`), so today no archived file is ever *read* by the substring arm regardless of the predicate. Extend `resolve_scopes`'s signature (e.g. `resolve_scopes(root, target, include_archive=False)`) to additionally yield the matching `_archive/<bundle>` directory/directories when set, and have `_substring_ranking` pass `filters.include_archive` into it. `cmd_list` needs its own `pls.add_argument("--include-archive", ...)` (not yet present) plus `FindFilters(..., include_archive=...)` construction and the same widened `resolve_scopes` call — `cmd_list` does not currently use `FindFilters` at all per SPEC §Nicht-Ziele ("Keine Umstellung von cmd_list auf FindFilters über das hinaus, was die geteilte Scope-Auflösung verlangt"), so check that boundary before wiring more than the scope-resolution call.

**`okf-cli-6dsl`** (semantic arm's non-coverage of `--include-archive` made ansagbar): `cmd_find` (`cli/okf-cli.py:1348+`) already has the `semantic_hits` local and the `filters` object in scope at the point it decides ownership (~line 1450, next to the existing `"note: semantic arm owns this ranking"` stderr print). The condition to gate the new note on is `filters.include_archive and semantic_hits` — SPEC §4.3 (PF-4: one note per degraded arm per invocation) — write it to stderr exactly once per `cmd_find` call, not per hit.

**`okf-cli-9e2b`** (MCP passthrough): `mcp/okf_mcp.py:27` `_BOOL_FLAGS` — add `"include_archive"` there and to the parameter lists of `okf_find`/`okf_list` only (SPEC §5, R-14: no other command gets the flag). `FindFilters` itself needs no MCP-side change; the MCP layer's job is purely `build_argv` emitting `--include-archive` when the tool parameter is true, mirroring how the existing bool flags already round-trip.

## ERRATA / Abweichungen

1. `__bool__` was NOT extended with `include_archive` (a plausible first design, tried and reverted — see Summary) because it collides with `_fts_ranking`'s `assert not residual`. Documented in the method's own docstring/comment so a future reader doesn't reintroduce the same break.
2. SC-02 and SC-04 are green even in the pre-change RED run (see RED output). This is expected and explained there, not a hidden gap — SC-01 and SC-03 are the two that meaningfully RED, and the mutation table separately proves SC-02's and SC-04's underlying predicates.
3. Added a third test class, `PathInScopeArchiveRule` (3 tests), beyond the five named SC — justified in "Test-per-SC" above: without it, `path_in_scope`'s archive-exclusion branch is presently unreachable through any production call site (no scope creep into iwx4/6dsl's traversal work, purely a direct unit-level guard on code this bean adds).
4. Did not touch the pre-existing, unescaped `self.scope + "/%"` LIKE pattern in the same `sql_where()` (a bundle name containing `_` has the identical wildcard exposure AC4 fixes for the archive predicate). Out of scope for R-08/R-09/R-10, which name only the archive-exclusion predicate; flagging it here rather than silently fixing or silently ignoring it. Candidate for a follow-up bean if the PO wants it filed.

## Gate evidence

`just test` → `Ran 580 tests in 64.546s` → `OK`. Four targeted mutations against the acceptance criteria (table above), each independently reddened the correct test for the stated reason, each reverted via targeted `Edit`, `git diff --stat cli/okf-cli.py` confirmed no residue after every cycle. Read-only smoke against the real catalogue, byte-identical, `git status --short` clean there. Commit `5d5fc76`.
