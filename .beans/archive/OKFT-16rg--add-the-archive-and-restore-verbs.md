---
# OKFT-16rg
title: add the archive and restore verbs
status: completed
type: task
priority: normal
created_at: 2026-08-09T19:14:39Z
updated_at: 2026-08-09T19:54:28Z
parent: OKFT-ubxk
blocked_by:
    - OKFT-2lj0
---

The destination is derived, never typed: `<bundle>/<cid>.md` becomes `_archive/<bundle>/<cid>.md` and back, with a multi-level concept id keeping its substructure. Two nuisances are already checked and need no work: `bundle_of` (:3470) returns `_archive`, so the move counts as cross-bundle and the outbound pass runs but changes nothing because `link_expr` (:3476) emits catalogue-root-absolute links; and `reindex_tree` finds no `index.md` under `_archive/` while the origin bundle's index correctly loses the entry.

### Requirement 1: Archive and restore a concept

**Objective:** As a catalogue maintainer, I want one command that moves a concept into the archive and back, so that the lifecycle step is a single reversible operation instead of a hand-typed path.

#### Acceptance Criteria

1. THE okf-cli SHALL accept `archive <bundle>/<concept>` and move the file to `_archive/<bundle>/<concept>.md`, preserving any subdirectory structure of the concept id.
2. THE okf-cli SHALL treat a run without `--apply` as a dry run that changes no file.
3. THE okf-cli SHALL accept `archive --restore _archive/<bundle>/<concept>.md` and move the file back to `<bundle>/<concept>.md`, deriving the destination without a second path argument.
4. IF the source of `archive` already lies under `_archive/` THEN THE okf-cli SHALL refuse the operation with a message naming the reason.
5. IF the source of `archive --restore` does not lie under `_archive/` THEN THE okf-cli SHALL refuse the operation with a message naming the reason.
6. IF an archive path carries no bundle segment THEN THE okf-cli SHALL refuse the restore, because the destination is not derivable from it.
7. THE okf-cli SHALL report how many active concepts still link to the concept it archived.

#### Success Criteria

- SC-01: A dry run prints the plan and leaves the working tree untouched.
- SC-02: An applied run leaves the file under `_archive/<bundle>/`, tracked by git, and names whether git or the filesystem performed the move.
- SC-03: Archiving and then restoring a concept returns it to its original path with byte-identical content.
- SC-04: Each of the three refusals exits non-zero with its own message.

_Requirements: R-01, R-02, R-03_

## Recommended Skills

- `superpowers:test-driven-development`


## 2026-08-09 — Prelude from the review of OKFT-2lj0 (finding F01, minor)

`perform_rename` is yours to wrap, and it carries one open wording gap you inherit.

Measured, not claimed: before the refactor (`e62dfb8`) a missing source reported `rename: source not found: a/nope.md` — the raw CLI string. After it (`3310656`) the same call reports `rename: source not found: /abs/path/a/nope.md` — the resolved path. Same for "destination exists". The spec-fixed signature (`docs/okf-archive-lifecycle/SPEC.md:51`) carries only `old_abs`/`new_abs`, so the raw string no longer exists inside the function. No test pins either wording.

Two consequences for this task:

1. **Do not assume the old wording.** If any acceptance criterion of yours asserts an error message, assert the wording you actually observe, and say so in your report.
2. **Do not "fix" it on your own initiative.** Whether the resolved path is acceptable is a PO call, not an implementer call — it is with the PO now. If the answer arrives during your run, the supervisor relays it to you. If it does not, leave the behaviour as it stands.

The reviewer's framing, for context: SC-01 defines "unchanged" operationally as "the 60 existing rename tests stay green unmodified", and that criterion is met. The gap is against the literal AC4 wording, not against the tested contract.


## Summary
`cmd_archive(root, args)` (cli/okf-cli.py) is a thin wrapper over `perform_rename` (OKFT-2lj0). It never types the counterpart path: for `archive <bundle>/<cid>[.md]` it prepends `_archive/`; for `archive --restore _archive/<bundle>/<cid>[.md]` it strips that leading segment. Three archive-specific direction guards run before delegating, since they belong to archive and not to the shared rename core (SPEC.md §2): a plain `archive` refuses a source already under `_archive/`; `--restore` refuses a source outside `_archive/`; `--restore` refuses an archive path with fewer than 2 segments after `_archive/` (no bundle to derive a destination from). Before calling `perform_rename`, if the source file exists, `cmd_archive` calls `plan_rename` itself (per OKFT-2lj0's T(n+1) note — `perform_rename` returns `None`, it does not hand back the plan) and prints the count of distinct active concepts whose markdown crosslinks point at the source (AC7). The command is registered alphabetically in `build_parser()` (before `build-index`, per `CommandDirectoryOrder.test_commands_are_listed_alphabetically`) with `path`, `--restore`, `--apply`, `--force`, group `maintenance`, and wired into `COMMAND_DISPATCH`.

## Test-Output
RED (13 new tests against the not-yet-existing `cmd_archive`):
```
$ python3 -m unittest test_okf_cli.ArchiveConcept -v
...
AttributeError: module 'okf_cli' has no attribute 'cmd_archive'
(13 ERROR of the same shape — Ran 13 tests in 0.178s, FAILED (errors=13))
```
GREEN after implementation:
```
$ python3 -m unittest test_okf_cli.ArchiveConcept -v
test_apply_moves_file_under_archive_bundle_dir_fs_fallback ... ok
test_apply_moves_file_via_real_git_when_tracked ... ok
test_archive_refuses_a_source_already_under_archive ... ok
test_dry_run_accepts_bare_concept_id_without_md_suffix ... ok
test_dry_run_prints_the_plan_and_touches_nothing ... ok
test_each_direction_guard_is_distinguishable_by_message ... ok
test_report_counts_active_concepts_still_linking_to_it ... ok
test_report_is_zero_when_nothing_links_to_it ... ok
test_restore_derives_destination_without_a_second_path ... ok
test_restore_preserves_multi_level_concept_id_substructure ... ok
test_restore_refuses_a_source_outside_archive ... ok
test_restore_refuses_an_archive_path_without_a_bundle_segment ... ok
test_round_trip_archive_then_restore_is_byte_identical_including_links ... ok
Ran 13 tests in 0.261s
OK
```
Full suite:
```
$ just test
Ran 565 tests in 34.065s
OK
```
(552 baseline + 13 new `ArchiveConcept` tests. `CommandHelpConformance` and `CommandDirectoryOrder` pass unmodified against the new registration.)

## Mutation
Checkpointed at commit `90c06b9` (later folded into `149554f` via `git reset --soft`, git-restorable); each mutation reverted via `git checkout -- cli/okf-cli.py` immediately after observing red.

| AC | Mutation | Test(s) gone red | Why |
|----|----------|-------------------|-----|
| AC1 (dest is `_archive/<bundle>/<cid>.md`, substructure kept) | `dest_rel = "/".join(segs)` (dropped the `["_archive"] + …` prefix) | 9 of 13 (e.g. `test_dry_run_prints_the_plan_and_touches_nothing`, `test_restore_preserves_multi_level_concept_id_substructure`) | Source and derived destination became identical, so `perform_rename` died with "source and destination are identical" instead of moving into `_archive/` — exactly the failure mode SPEC.md:42 predicts for a broken direction. |
| AC2/SC-01 (dry-run changes no file) | Hardcoded `True` instead of `args.apply` in the `perform_rename(...)` call | `test_dry_run_prints_the_plan_and_touches_nothing` | A dry-run call moved the file for real ("moved (fs) …" appeared, "would move" did not) — `apply=False` from the caller was never honoured. |
| AC3 (restore derives destination without a second path) | `dest_rel = "/".join(segs)` in the restore branch (kept the `_archive` prefix instead of stripping it) | `test_restore_derives_destination_without_a_second_path` | Restore computed a destination equal to its own source; `perform_rename` died with "source and destination are identical" — restore no longer went anywhere. |
| AC4 (archive refuses a source already under `_archive/`) | Removed the `if segs[0] == "_archive": die(...)` guard | `test_archive_refuses_a_source_already_under_archive`, `test_each_direction_guard_is_distinguishable_by_message` | `SystemExit not raised` — archiving an already-archived path silently proceeded toward `_archive/_archive/…`. |
| AC5 (`--restore` refuses a source outside `_archive/`) | Removed the `if segs[0] != "_archive": die(...)` guard | `test_restore_refuses_a_source_outside_archive`, `test_each_direction_guard_is_distinguishable_by_message` | The call fell through to the "no bundle segment" guard instead (wrong message, `'must lie under _archive/' not found`) — proves the two guards are not interchangeable and each carries its own wording (SC-04). |
| AC6 (`--restore` refuses an archive path with no bundle segment) | Removed the `if len(segs) < 3: die(...)` guard | `test_restore_refuses_an_archive_path_without_a_bundle_segment`, `test_each_direction_guard_is_distinguishable_by_message` | The call fell through to `perform_rename`'s generic "path must be inside a bundle" guard (different wording) — same interchangeability proof as AC5. |
| AC7 (report of active inbound references) | `n_concepts = 0` (forward direction) then `n_concepts = 5` (reverse direction) | `test_report_counts_active_concepts_still_linking_to_it` red on the `0` mutation; `test_report_is_zero_when_nothing_links_to_it` red on the `5` mutation | Both directions of the printed count are pinned by two separate tests — a single test asserting only "some number appears" would have missed either mutation. |
| (supporting, not a listed AC but asserted by its own test) `[.md]` optional in the CLI signature | `ref = args.path` (dropped the `.endswith(".md")` strip-before-append) | `test_dry_run_prints_the_plan_and_touches_nothing` | `a/old.md` became `a/old.md.md` internally, so `perform_rename` died with "source not found" for a path that plainly exists. |

SC-03 (round trip, including links) is its own dedicated test (`test_round_trip_archive_then_restore_is_byte_identical_including_links`), not composed from the directional AC1/AC3 tests — it asserts byte-identical content of both the moved concept and the linking file after the full archive→restore cycle, and is covered transitively by the AC1 and AC3 mutations above (both make the round trip fail before it can complete).

## Smoke
Fixture catalogue (`git init`-backed, real subprocess CLI, cleaned up afterward):
- Dry-run `archive dev-wiki/patterns/retry` → prints inbound count + plan, leaves `dev-wiki/patterns/retry.md` in place.
- Apply → `moved (git mv)  dev-wiki/patterns/retry.md  ->  _archive/dev-wiki/patterns/retry.md`, `caller.md`'s markdown crosslink rewritten to `/_archive/…`.
- Restore dry-run then `--apply` → file back at `dev-wiki/patterns/retry.md`, `caller.md`'s link back to `/dev-wiki/patterns/retry.md`, byte-identical to before. `git status --short` clean after the full round trip.
- Error paths: `archive` on an already-archived path, `--restore` on a non-archived path, `--restore` on an archive path with no bundle segment — all three exit 2 with their own distinct message (matches the mutation table above).
- Real catalogue (`~/Obsidian/Knowledge-Catalogue`), dry-run only, no `--apply`: `archive okf-tools-okf/capability-surface/find-score-formula-drift` printed "3 active concept(s) still link to this concept" plus the full plan; `git status --short` in the catalogue unchanged before and after.
- `just check`: `OK — 0 violations` (28 pre-existing WARNING lines, none new — same count class as the pre-existing baseline).

## Deviations/ERRATA
- The known, in-scope-elsewhere gap surfaced during smoke, as SPEC.md §3 predicts: the fixture's `[[retry]]` wikilink was **not** rewritten by the archive move (only the markdown crosslink was) and stayed as `[[retry]]`, unresolved, after the move. This is R-05/R-06/R-07 territory (`build_concept_basename_index` does not yet index `_archive/<bundle>/**`) — explicitly out of this leaf's scope (R-01..R-03 only) and left untouched, per the bean's own framing ("R-05 gehört nicht hierher" is implicit in the requirement split). Not a regression: the same wikilink was equally unresolved before this bean existed, since `archive` did not exist before.
- No other deviation from the bean or SPEC.md §1/§2.

## Notes for T(n+1)
For whichever bean picks up R-05/R-06/R-07 (wikilink resolution into `_archive/`):
- `cmd_archive` (cli/okf-cli.py) already prepends/strips exactly one `_archive/` segment and preserves any deeper concept-id substructure — no path-shape work is needed there.
- The inbound-reference count `cmd_archive` prints only counts markdown crosslinks (`plan_rename(...)["inbound"]`), not wikilinks — once `build_concept_basename_index` learns `_archive/`, consider whether that report line should grow a wikilink count too, or whether it stays crosslink-only by design (SPEC.md §1 only mentions "per Markdown-Crosslink").
- `plan_rename` and `plan_wikilink_rewrites` are called with paths that may not exist yet resolved-side (restore direction) or may cease to exist mid-call (archive direction, since `cmd_archive` computes the plan *before* `perform_rename` moves anything) — both functions tolerate this today via string-only operations on the basename; do not add an `os.path.isfile` assumption to either without re-checking `cmd_archive`'s call site.
- The three archive-specific direction guards are deliberately placed in `cmd_archive`, not `perform_rename`, per SPEC.md §2 ("archive's own guards ... must run in cmd_archive before calling perform_rename, since they are not part of this shared core") — do not fold them into `perform_rename` even if a future bean wants `restore` semantics elsewhere.
