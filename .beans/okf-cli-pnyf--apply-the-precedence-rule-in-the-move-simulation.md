---
# okf-cli-pnyf
title: apply the precedence rule in the move simulation
status: completed
type: task
priority: normal
created_at: 2026-08-09T19:14:39Z
updated_at: 2026-08-09T20:35:22Z
parent: okf-cli-xlck
blocked_by:
    - okf-cli-hk77
---

`_index_after_move` (cli/okf-cli.py:3670) simulates the basename index after a move in order to decide `turns_ambiguous`. If it does not apply the same active-before-archived rule as the index itself, the dry run of `archive` reports ambiguity that never materialises and refuses to proceed without `--force`.

### Requirement 1: Consistent resolution before and after the move

**Objective:** As a catalogue maintainer, I want the move simulation to resolve links the way the real index does, so that archiving is not blocked by an ambiguity that does not exist.

#### Acceptance Criteria

1. THE okf-cli SHALL apply the active-before-archived precedence rule inside `_index_after_move`.
2. WHEN archiving a concept whose basename is also held by an active concept THE okf-cli SHALL NOT report the inbound links as turning ambiguous.

#### Success Criteria

- SC-01: `archive` of a concept sharing its basename with an active one completes without `--force` and reports no `turns-ambiguous` line.

_Requirements: R-07_

## Recommended Skills

- `superpowers:test-driven-development`


## Summary

`_index_after_move` (cli/okf-cli.py) folded the moved-to path (`new_link`) and any rename-scan `collisions` into whatever candidate list the real index already held for that basename, with a plain set union — never re-applying R-06's active-before-archived precedence. Archiving a concept whose basename an active concept also held therefore left the freshly archived path sitting next to the survivor as a second candidate in the simulation, even though the real post-move index would drop the archived one and resolve uniquely to the survivor. That falsely flagged a bystander link as `turns-ambiguous`, blocking the archive without `--force` for a move that would leave the catalogue perfectly resolvable.

Fix: the precedence rule was factored out of `build_concept_basename_index` into a new pure function `_apply_archive_precedence(candidates)` — active candidates win outright whenever at least one exists, archived candidates are the fallback only when none do. `build_concept_basename_index` now appends active and archived candidates into one raw list per basename and applies the shared function once at the end (previously it built two separate dicts and merged them per-key with `idx.setdefault(k, v)` — functionally identical, but the rule itself was inline and could not be called from anywhere else). `_index_after_move` applies the same shared function to the slot the move lands on (`key`), so the simulation and a freshly rebuilt real index agree — closing R-07.

Sharing was possible and used, per the task's explicit ask: the precedence rule now lives in exactly one function, called by both `build_concept_basename_index` (R-06, the real index) and `_index_after_move` (R-07, its move simulation). A mutation on that one shared function reddens tests from both hk77's `WikilinkArchiveResolution` class and this task's new `MoveSimulationArchivePrecedence`/`ArchiveConcept` tests in a single run — see Mutation table below.

## Test-Output (RED, verbatim)

`python3 -m unittest test_okf_cli.MoveSimulationArchivePrecedence test_okf_cli.ArchiveConcept.test_archive_does_not_falsely_flag_a_bystander_as_turning_ambiguous -v` (run from `cli/`, before the implementation edit):

```
test_precedence_applied_to_the_slot_the_move_lands_in (test_okf_cli.MoveSimulationArchivePrecedence.test_precedence_applied_to_the_slot_the_move_lands_in)
Archiving a/old.md while d/old.md stays active must leave "old" ... FAIL
test_archive_does_not_falsely_flag_a_bystander_as_turning_ambiguous (test_okf_cli.ArchiveConcept.test_archive_does_not_falsely_flag_a_bystander_as_turning_ambiguous)
archiving a/old.md, whose basename is also held by the active ... archive: this move leaves 1 inbound wikilink(s) ambiguous: a/other.md — the same corruption `skipped-ambiguous` declines to commit, so it may not happen by accident either (use --force to proceed)
ERROR

======================================================================
ERROR: test_archive_does_not_falsely_flag_a_bystander_as_turning_ambiguous (...)
...
SystemExit: 2

======================================================================
FAIL: test_precedence_applied_to_the_slot_the_move_lands_in (...)
AssertionError: Lists differ: ['/_archive/a/old.md', '/d/old.md'] != ['/d/old.md']
- ['/_archive/a/old.md', '/d/old.md']
+ ['/d/old.md']

----------------------------------------------------------------------
Ran 2 tests in 0.008s

FAILED (failures=1, errors=1)
```

GREEN, same command, after the implementation edit: both tests `ok`, `Ran 2 tests ... OK`.

Full suite, baseline before this task (`just test`): `Ran 571 tests ... OK` (hk77's post-state).
Full suite, after (`just test`): `Ran 573 tests in 25.143s` `OK`.

## Mutation (per criterion)

Both mutations applied on top of the committed fix (`327e0ad`), reverted after each with `Edit` back to the exact original bytes; `grep -n "_apply_archive_precedence" cli/okf-cli.py` and a full `just test` re-run confirmed byte-identical restoration each time (working tree carried no other pending edit at the time, so no `git diff` was available as the revert oracle — the mutate/re-run/revert/re-run cycle plus the grep-line check served as the equivalent proof).

| Criterion | Mutation | Test(s) that turned red | Why |
|---|---|---|---|
| AC1 (precedence applied inside `_index_after_move`) + AC2/SC-01 (no false `turns-ambiguous`) — also the Umkehrmutation (remove the R-07 enforcement line) | `out[key] = _apply_archive_precedence(...)` reverted to the pre-fix `out[key] = sorted(set(out.get(key, [])) \| {new_link} \| set(collisions))` (the exact line R-07 exists to change) | `MoveSimulationArchivePrecedence.test_precedence_applied_to_the_slot_the_move_lands_in`, `ArchiveConcept.test_archive_does_not_falsely_flag_a_bystander_as_turning_ambiguous` | With the raw union restored, `after["old"]` again holds both the freshly archived path and the surviving active one (`['/_archive/a/old.md', '/d/old.md']`) instead of the active one alone. The unit test asserts the exact candidate list directly; the E2E test then hits `perform_rename`'s `wl_ambiguous`/`--force` gate and raises `SystemExit(2)` with the `turns-ambiguous` message instead of completing. No other test in the class or the full suite turned red from this mutation — it is scoped precisely to R-07, not R-06 (`build_concept_basename_index` itself is untouched by this mutation). |
| Sharing proof (not a named AC, but the task's explicit "teilen statt duplizieren" instruction) | `_apply_archive_precedence` inverted: `archived`-tier candidates win outright whenever any exist, active only as fallback (swap of the filter predicate) | `MoveSimulationArchivePrecedence.test_precedence_applied_to_the_slot_the_move_lands_in`, `WikilinkArchiveResolution.test_active_candidate_wins_over_an_archived_one_of_the_same_name` (hk77, SC-02/SC-03), `WikilinkArchiveResolution.test_two_active_candidates_stay_ambiguous_even_with_an_archived_third` (hk77, SC-04) | A single mutation to the one shared function reddens 3 tests spanning two unrelated test classes written by two different tasks (hk77 and pnyf) — direct proof that `build_concept_basename_index` and `_index_after_move` both depend on the same precedence implementation rather than two independently-written copies of the same rule. `ArchiveConcept.test_archive_does_not_falsely_flag_a_bystander_as_turning_ambiguous` did NOT turn red under this specific mutation (its assertion only checks the absence of a `turns-ambiguous` line, and an archived-wins single-candidate result is still non-ambiguous, just resolved to the wrong target) — recorded here rather than silently omitted; the unit test and the two hk77 tests are what catch this mutation, and that is sufficient, not a collateral non-failure being counted as evidence. |

## Deviations/ERRATA

- The reachable fixture for AC2/SC-01 required more analysis than the bean's one-sentence framing suggested. A first reading of "archiving a concept whose basename is also held by an active concept" suggested any bystander `[[old]]` link would do; instrumented exploration (`_index_after_move` called directly against hand-built fixtures, plus a real before/after `build_concept_basename_index` comparison) showed `resolve_wikilink`'s own bundle-tiebreak and path-tail filtering mask the union bug for every bystander EXCEPT one specific shape: a bystander link living in the archived concept's OWN bundle (so it resolves to it uniquely, pre-move, via tiebreak) while a second active concept elsewhere shares the basename. That is the fixture both new tests use (`a/other.md` linking `[[old]]`, `a/old.md` being archived, `d/old.md` staying active). Recorded because a reader reproducing this bug from the bean's prose alone, without the bundle-placement detail, would build a fixture that never reproduces it (LL-13/LL-15-adjacent: the acceptance sentence was true but under-specified for reproduction).
- `build_concept_basename_index`'s internal mechanism changed (two dicts + per-key `setdefault` merge → one dict + a single shared-function pass at the end) even though its external behavior is unchanged and fully covered by hk77's existing `WikilinkArchiveResolution` suite (reran green, unmodified). This was necessary to create genuine sharing rather than two independently-maintained copies of the same rule, per the task's explicit instruction to check for and prefer sharing. hk77's bean-body mutation description ("`idx.setdefault(k, v)` -> `idx[k] = v`") now describes a code shape that no longer exists verbatim in the file; the rule and its guarantee (SC-02/SC-03/AC4/SC-04) still hold and are still covered by the identical tests, re-run green here — only the historical mutation *description* in hk77's already-closed bean body is now stale prose about a superseded internal shape, not a live claim about current code. Not edited there, since hk77 is closed and its own gate is not reopened by this; flagged here for visibility.
- Per the hk77 handoff note's own scoping (its "Notes for T(n+1)" point 1), `_index_after_move` re-derives precedence only for the slot the move lands on (`key`, `new_link`'s basename) — the one that gains a genuinely new candidate. Other keys (`out[k] = kept` in the loop) are left as-is, since they only ever *lose* a candidate (`old_link`) from an already precedence-correct list and cannot need re-derivation for R-07's stated purpose. A related but distinct gap was found and deliberately NOT fixed here, being out of R-07's stated scope (SPEC.md: "so that the dry run does not report an ambiguity that does not arise" — a false positive guard): when a move empties out a basename's sole surviving active candidate (e.g. a `rename` moving the only active concept holding a basename elsewhere, or an `archive` of the last active holder of a basename) while an ARCHIVED duplicate of that basename existed all along (invisible to the given `index` because R-06 precedence had already dropped it before the move), `_index_after_move` drops that key from `out` entirely (or falls back only to `new_link`+`collisions`) rather than resurrecting the masked archived candidate(s) the way a freshly-rebuilt `build_concept_basename_index` would. That is a false-NEGATIVE direction (dry run under-reports an ambiguity that WOULD arise) and is not covered by any AC in this bean; recorded for a future R-07-adjacent task rather than actioned here (no scope creep).
- No other deviations from the bean/SPEC.

## Smoke

Read-only against `~/Obsidian/Knowledge-Catalogue`, no `--apply`:

- `okf-cli.py --root ~/Obsidian/Knowledge-Catalogue check` -> `OK — 0 violations`, same pre-existing unrelated `crosslink-format`/`tag-registered` warnings as hk77's smoke, zero `wikilink-resolvable` findings.
- `okf-cli.py --root ~/Obsidian/Knowledge-Catalogue wikilinks lean-stack-okf` -> `wikilinks: 153 link(s), 153 resolved, 0 ambiguous, 0 unresolved` — identical to hk77's smoke result, confirming this change is behavior-neutral for a catalogue with no `_archive/` directory yet.
- `git -C ~/Obsidian/Knowledge-Catalogue status --short` -> empty, before and after.

## Notes for T(n+1)

The false-negative gap noted under Deviations/ERRATA (`_index_after_move` cannot resurrect an archived candidate that R-06 precedence masked out of the given `index` before the move, when the move empties out that basename's sole active survivor) is real and reproducible but out of this bean's stated scope. A future task closing it would need `_index_after_move` to accept the catalogue root (or a second, unfiltered raw index) rather than only the already-precedence-applied one, so it can re-derive `out[k]` for every key that loses its last active candidate, not only for `key` (`new_link`'s basename).
