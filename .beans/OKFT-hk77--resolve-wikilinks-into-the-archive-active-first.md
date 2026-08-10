---
# OKFT-hk77
title: resolve wikilinks into the archive, active first
status: completed
type: task
priority: normal
created_at: 2026-08-09T19:14:21Z
updated_at: 2026-08-09T20:13:45Z
parent: OKFT-xlck
---

Without this, archiving a concept turns every inbound `[[x]]` into an unresolved target and `check` reports it in the five opted-in bundles — in files the archiver never touched. The precedence rule is what keeps archive-then-recreate from making the same link ambiguous instead.

### Requirement 1: Archive as a resolution target

**Objective:** As a catalogue maintainer, I want archived concepts to stay wikilink-resolvable, so that archiving one concept does not break links in unrelated files.

#### Acceptance Criteria

1. THE okf-cli SHALL include `_archive/<bundle>/**` in the basename index built by `build_concept_basename_index`.
2. WHEN a basename has at least one active candidate THE okf-cli SHALL resolve it against the active candidates only.
3. WHEN a basename has no active candidate THE okf-cli SHALL resolve it against the archived candidates.
4. WHEN a basename has two or more active candidates THE okf-cli SHALL report it as ambiguous, unchanged from today.

#### Success Criteria

- SC-01: After archiving a concept that an active concept links to, `check` over the five opted-in bundles reports zero violations.
- SC-02: With an active and an archived concept sharing a basename, the link resolves to the active one rather than reporting ambiguity.
- SC-03: Removing the precedence rule from the index turns SC-02's test red — the guard is proven by its own reversal, and the test stays in the repo.
- SC-04: A basename with two or more active candidates is still reported `ambiguous` once archive resolution is in place — a same-named archived concept must not join the candidate set or defuse the ambiguity (AC4, Gate-B finding F01).

_Requirements: R-05, R-06_

## Recommended Skills

- `superpowers:test-driven-development`


## 2026-08-09 — Prelude from Gate B (ce-verify-operationalization, finding F01)

AC4 ("WHEN a basename has two or more active candidates THE okf-cli SHALL report it as ambiguous, unchanged from today", spec A07, `docs/okf-archive-lifecycle/SPEC.md:159`) carries no success criterion. SC-01 … SC-03 only cover AC1 … AC3.

Do this first, in this task, not in a follow-up: add an SC-04 that asserts a basename with two active candidates is still reported as ambiguous once archive resolution is in place, and cover it with a named test. Adding a test that secures an existing acceptance criterion is not a plan deviation and needs no escalation.

## Summary

`build_concept_basename_index` (cli/okf-cli.py) now folds `_archive/<bundle>/**` into the basename index as a lower-priority tier. A basename with at least one active candidate resolves against the active candidate(s) only; a basename with no active candidate falls through to its archived candidate(s); a basename with two or more active candidates stays `ambiguous` regardless of any same-named archived concept. Closes R-05 and R-06 of `docs/okf-archive-lifecycle/SPEC.md`. SC-04 was added to the bean per the Gate-B prelude (F01) and covered by a named test.

## Test-Output (RED -> GREEN, verbatim)

RED, before the implementation edit (`python3 -m unittest test_okf_cli.WikilinkArchiveResolution test_okf_cli.WikilinkCheck.test_link_into_the_archive_does_not_warn -v`):

```
test_active_candidate_wins_over_an_archived_one_of_the_same_name ... ok
test_archived_candidate_used_only_when_no_active_one_exists ... FAIL
test_archived_concept_is_a_resolution_target ... FAIL
test_two_active_candidates_stay_ambiguous_even_with_an_archived_third ... ok
test_two_archived_candidates_with_no_active_are_ambiguous ... FAIL
test_link_into_the_archive_does_not_warn ... FAIL

AssertionError: Tuples differ: ('unresolved', []) != ('resolved', ['/_archive/a/old.md'])
AssertionError: Lists differ: [('wikilink-resolvable', 'a/x.md', 'unresolved wikilink target(s): [[old]]')] != []

----------------------------------------------------------------------
Ran 6 tests in 0.007s

FAILED (failures=4)
```

Two of the six pass by coincidence pre-implementation (no archive candidate exists in the index at all yet, so the active-only / two-active-still-ambiguous cases already produce the expected shape) — they are the regression guards, not the new-behaviour proof; the four FAILs are the new-behaviour proof.

GREEN, after the implementation edit, same command:

```
test_active_candidate_wins_over_an_archived_one_of_the_same_name ... ok
test_archived_candidate_used_only_when_no_active_one_exists ... ok
test_archived_concept_is_a_resolution_target ... ok
test_two_active_candidates_stay_ambiguous_even_with_an_archived_third ... ok
test_two_archived_candidates_with_no_active_are_ambiguous ... ok
test_link_into_the_archive_does_not_warn ... ok

----------------------------------------------------------------------
Ran 6 tests in 0.006s

OK
```

Full suite, baseline before this task (`just test`):

```
Ran 565 tests in 25.275s

OK
```

Full suite, after (`just test`):

```
Ran 571 tests in 25.783s

OK
```

## Mutation (per criterion)

Mutations applied on top of committed code (`471f48c`), reverted after each with `Edit` back to the exact original bytes; `git diff cli/okf-cli.py` was empty after every revert (byte-identical).

| Criterion | Mutation | Test(s) that turned red | Why |
|---|---|---|---|
| AC1 (`_archive/<bundle>/**` included in the index) | `if os.path.isdir(archive_root):` -> `if False and os.path.isdir(archive_root):` (archive scan disabled) | `test_archived_concept_is_a_resolution_target` | The only concept with basename `old` lives under `_archive/a/`; with the scan disabled the index never learns of it, so `resolve_wikilink` reports `unresolved` instead of `resolved`. |
| AC3 (fall through to archived when no active candidate) | same mutation as AC1 | `test_archived_candidate_used_only_when_no_active_one_exists`, `test_two_archived_candidates_with_no_active_are_ambiguous` | Both fixtures have zero active candidates; with archive scanning disabled there is nothing in the index for that basename at all, so both go `unresolved` instead of `resolved` / `ambiguous`. |
| SC-01 (archiving does not break an inbound link in an untouched file) | same mutation as AC1 | `test_link_into_the_archive_does_not_warn` | `check_wikilink_resolvable` now sees `[[old]]` as unresolved (index empty for that basename), so the opted-in bundle `a` gets a `wikilink-resolvable` warning instead of a clean run. |
| AC2 / SC-02 (active wins over archived) and its SC-03 guard-reversal | `idx.setdefault(k, v)` -> `idx[k] = v` (unconditional overwrite — reverses the precedence direction, "Drehe die Reihenfolge im Code um") | `test_active_candidate_wins_over_an_archived_one_of_the_same_name` | With the direction reversed, the archived candidate for basename `old` unconditionally overwrites the active one already in the index, so resolution now returns `resolved -> /_archive/z/old.md` instead of `resolved -> /a/old.md`. This IS SC-03: "removing the precedence rule from the index turns SC-02's test red." |
| AC4 / SC-04 (two active candidates stay ambiguous regardless of an archived namesake) | same mutation as AC2 | `test_two_active_candidates_stay_ambiguous_even_with_an_archived_third` | Basename `g` has two active candidates (`a/g.md`, `b/g.md`); the reversed direction lets the single archived candidate (`_archive/z/g.md`) unconditionally overwrite BOTH, so resolution collapses to `resolved -> /_archive/z/g.md` instead of staying `ambiguous` over the two active files. This is the required "inverted order" probe for AC4 specifically. |

Two mutations, five criteria — AC1/AC3/SC-01 share one root cause (archive not scanned at all), AC2/SC-02/SC-03/AC4/SC-04 share the other (precedence direction reversed). Each row above names the specific test and the specific mechanical reason it went red, not a collateral failure.

## Smoke

Read-only against `~/Obsidian/Knowledge-Catalogue`, no `--apply`:

- `okf-cli.py --root ~/Obsidian/Knowledge-Catalogue check` -> `OK — 0 violations` (pre-existing `crosslink-format`/`tag-registered` warnings in `home-lab-wiki` unrelated to this change; zero `wikilink-resolvable` findings, matching the SPEC's D16 clean-run claim).
- `okf-cli.py --root ~/Obsidian/Knowledge-Catalogue wikilinks lean-stack-okf` -> `wikilinks: 153 link(s), 153 resolved, 0 ambiguous, 0 unresolved`.
- `git -C ~/Obsidian/Knowledge-Catalogue status --short` -> empty, before and after — the catalogue has no `_archive/` today and this run wrote nothing to it.

## Deviations/ERRATA

- Searched the existing wikilink test suite (`grep -n "_archive" cli/test_okf_cli.py`) for a test that pins "an inbound link into `_archive/` stays unresolved" as correct behaviour, per Gate item 6. None exists — the archive feature (`cmd_archive`, `OKFT-16rg`) predates this task but no wikilink-resolution test against it existed yet, so there was no stale test to fix or flag.
- `docs/LESSONS-LEARNED.md` (repo root) does not contain a "wikilink-awareness" section as the dispatch prompt implied; the actual reference material is `docs/wikilink-awareness/SPEC.md` (a separate, earlier-closed topic folder, git history `657a515`). Read that instead — recorded here since the prompt's pointer was imprecise and a later reader should not repeat the same dead-end search.
- No other deviations from the bean/SPEC.

## Notes for T(n+1) (OKFT-pnyf — precedence rule in the move simulation)

The precedence rule lives entirely inside `build_concept_basename_index` (cli/okf-cli.py) — signature `build_concept_basename_index(root)`, returns `dict[str, list[str]]` mapping a lowercased basename (no `.md`) to a sorted list of catalogue-root-absolute paths. The rule: active candidates (from `list_bundles(root)`) are collected first into `idx`; archived candidates (from `list_bundles(os.path.join(root, "_archive"))`, i.e. `_archive/<bundle>/**`) are then folded in per basename with `idx.setdefault(k, v)` — meaning an archived list is written ONLY if that basename has no active entry yet. It is never merged with an existing active list.

`_index_after_move` (cli/okf-cli.py:3670, your target per R-07) takes the ALREADY-BUILT index (produced by `build_concept_basename_index`, precedence already applied) and simulates removing `old_link` / adding `new_link` (plus `collisions`) on top of it. Two things to carry over:

1. If `_index_after_move` is ever called with a index built via `build_concept_basename_index`, the precedence is already baked in — you do not need to re-derive active-vs-archived there, UNLESS the move itself crosses the active/archived boundary (i.e. this IS what `archive`/`archive --restore` does: the move source or destination lies under `_archive/`). In that case the post-move key for `new_link`'s basename must re-apply the SAME rule: if any active candidate remains for that basename after the simulated move, the archived candidates must NOT appear in the post-move candidate set for that key, and vice versa.
2. Concretely: `_index_after_move`'s final line `out[key] = sorted(set(out.get(key, [])) | {new_link} | set(collisions))` unconditionally unions everything under `key`. If `new_link` is an archive path (e.g. simulating `archive --apply`) and `out[key]` still holds an active path from elsewhere, blindly unioning them will incorrectly make the simulated post-move state show BOTH as candidates (violating the precedence rule the same way my AC2/AC4 mutation above did) — the dry-run would then report a spurious `turns_ambiguous` or a wrong candidate set. You will likely need to split `out[key]` into an active and archived partition before the union and apply `setdefault`-style precedence there too, mirroring `build_concept_basename_index` exactly, so the simulation and the real index agree.
