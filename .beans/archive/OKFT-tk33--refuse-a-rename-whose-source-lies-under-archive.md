---
# OKFT-tk33
title: refuse a rename whose source lies under _archive
status: completed
type: task
priority: normal
created_at: 2026-08-10T10:22:51Z
updated_at: 2026-08-10T10:40:02Z
parent: OKFT-0xkj
---

A `rename` whose source lies under `_archive/` currently succeeds and leaves the same invisible empty-directory residue that `OKFT-gqss` closed for the `archive --restore` path. This leaf makes that path refuse and name the verb that does the job properly.

## Origin — PO decision on Q02, 2026-08-10

Raised as decision D01 of the `ce-specs-reviewer` verdict on `OKFT-gqss`, escalated to the PO as `Q02` in the parent epic `OKFT-0xkj`, decided the same day.

The reviewer verified the gap with his own smoke run: after `OKFT-gqss` shipped, this still reproduces the original defect —

```
okf-cli.py rename _archive/<bundle>/old.md <bundle>/old.md --apply
```

— leaving `_archive/<bundle>/` and `_archive/` standing, invisible to `git status` because git does not track empty directories.

Three readings were put to the PO: leave it, extend the prune to `cmd_rename`, or refuse the path. The PO chose the third, verbatim:

> ein rename, dessen Quelle unter _archive/ liegt, verweigert und verweist auf archive --restore

**Interpretation.** A `rename` whose resolved source lies under `_archive/` is refused with a non-zero exit and an error naming `archive --restore`. Every other `rename` path is untouched. The residue then cannot be produced through `rename` at all, so the guarantee of `OKFT-gqss` becomes command-independent without any pruning logic entering the shared code.

**Why this reading and not the second one.** `docs/okf-archive-lifecycle/SPEC.md` section 2 requires (R-04/A15) that `rename` behaviour stay byte-identical, provable by the unchanged `rename` test set. Moving the prune into `perform_rename` would have broken that explicit promise. A refusal is a new guard on the caller, not a change to what a successful `rename` does — the existing `rename` test set exercises no source under `_archive/`, so its behaviour stays byte-identical in the sense R-04/A15 means it.

## Placement — the same rule that governs `OKFT-5436`

The guard belongs in `cmd_rename`, NOT in `perform_rename`. That function is shared with `archive`, and `archive --restore` legitimately moves a source out of `_archive/` — a guard inside the shared function would refuse the very operation the PO is pointing users at. This is the same reasoning that put the three direction guards and the `OKFT-5436` counterpart check in `cmd_archive`: archive-specific knowledge belongs in the specific caller, per SPEC section 2.

Consequence to verify rather than assume: `cmd_archive --restore` must still work after this change, because it calls `perform_rename` with a source under `_archive/` on purpose.

### Requirement 1: `rename` out of the archive refuses and points at `--restore`

**Objective:** As a catalogue maintainer, I want `rename` to refuse a source inside `_archive/`, so that the one command able to leave invisible residue points me at the command that cleans up after itself.

#### Acceptance Criteria

1. IF the resolved source of a `rename` invocation lies under `_archive/` THEN THE okf-cli SHALL refuse the operation with a non-zero exit and an error naming `archive --restore`.
2. THE okf-cli SHALL apply this refusal on the planning path as well as under `--apply`, so that a dry run does not promise a move that `--apply` would refuse.
3. THE okf-cli SHALL leave every `rename` whose source lies outside `_archive/` unchanged, including a rename whose DESTINATION lies under `_archive/`.
4. THE okf-cli SHALL implement the refusal in `cmd_rename`, not in `perform_rename`.
5. THE okf-cli SHALL keep `archive --restore` working, which moves a source out of `_archive/` through the same shared function.

#### Success Criteria

- SC-01: `rename _archive/<bundle>/old.md <bundle>/old.md --apply` exits non-zero with a message containing `archive --restore`, and leaves the file where it was.
- SC-02: The same invocation without `--apply` refuses identically rather than printing a `would move` line.
- SC-03: An ordinary `rename` between two active paths, and a `rename` whose destination is under `_archive/`, both keep their current behaviour, asserted against the existing messages.
- SC-04: The pre-existing `rename` and `archive` test sets stay green without modification, and an `archive --restore` round trip still succeeds.
- SC-05: Removing the refusal turns SC-01 and SC-02 red while leaving SC-03 and SC-04 green.

_Requirements: PO decision on Q02, 2026-08-10; reviewer finding D01 on `OKFT-gqss`_

## Recommended Skills

- `superpowers:test-driven-development` — SC-03 and SC-04 are regression guards on existing behaviour and have to exist before the refusal is written, otherwise there is no way to tell the untouched paths stayed untouched.

## Note on the residue

This leaf does not add pruning to `rename`. It removes the only way to reach the residue through `rename`. If a future change ever makes a source under `_archive/` renameable again, the prune question of `OKFT-gqss` returns with it — record that here rather than discovering it twice.


## Prelude 2026-08-10 — carried over from the review of `OKFT-5436`

**I01 — the third commit escapes the subject count.** `4e74677` came in at 51 bytes against the 50-byte soft target, and the leaf's own ERRATA section checked only the two code commits (47 and 55 bytes), not the bean-closing one. Three leaves in a row have now overshot by one or five bytes. The pattern is not the length, it is that the closing commit is written after the gate is green and skips the discipline the same report demands. Count every subject, including the one that closes the bean.

Still in force from the earlier reviews: every commit carries a `Refs: OKFT-tk33` footer (style, not hook-enforced, which is why it gets dropped), and mutation proofs cite `file:line` plus the mutated expression verbatim rather than the semantic name of the branch.

## Worked precedent — read `OKFT-5436` before starting

That leaf is closed, APPROVED, and structurally identical to this one: a guard placed in the archive-specific caller rather than in the shared `perform_rename`, turning a silent or misleading outcome into a signpost. Two things from its review transfer directly:

1. **The placement guard needs its own test in `PerformRenameDirectCall`.** In `OKFT-5436` the first attempt was silently green under the AC4 mutation — moving the check into the shared function broke nothing, because every test reached it through the specific caller. The fix was a test that calls `perform_rename` DIRECTLY, so it fails if archive/rename-specific knowledge migrates into the shared core. AC4 of this bean has the same shape and needs the same kind of test.
2. **Reuse the existing message phrasing.** The reviewer confirmed `OKFT-5436` was right to lift `use --restore to bring it back" verbatim from the existing direction guard (`cli/okf-cli.py:4329-4330`) instead of inventing new terminology. Your refusal message names the same verb — match the established wording rather than coining a variant.

## Summary

`cmd_rename` (`cli/okf-cli.py:4267-4292`) now refuses, unconditionally before the apply/dry-run branch, any `rename` whose RESOLVED source lies under `_archive/` — `os.path.realpath(old_abs)` compared against `os.path.realpath(root/_archive)`, the same `x == root or x.startswith(root + os.sep)` idiom already used by `_prune_empty_archive_dirs` (`:4286-4288`) and `_git_mv` (`:4084-4087`). The guard exits 2 with a message naming `archive --restore` and lives entirely in `cmd_rename` (AC4) — `perform_rename` (`:4106`) is untouched, so `archive --restore` keeps moving sources out of `_archive/` through the same shared core (AC5). Every other `rename` path — active-to-active, and a destination that itself lies under `_archive/` — is unaffected (AC3).

## Test-Output

RED (`cli/test_okf_cli.py`, class `RenameSourceUnderArchiveRefuses` + one addition to `PerformRenameDirectCall`, against unmodified `cmd_rename`):

```
test_ac1_symlink_resolving_into_archive_is_refused ... FAIL
test_ac1_traversal_argument_that_resolves_into_archive_is_refused ... FAIL
test_ac2_dry_run_and_apply_refuse_with_the_identical_message ... FAIL
test_sc01_apply_refuses_and_names_archive_restore ... FAIL
test_sc02_dry_run_refuses_identically_not_a_would_move_line ... FAIL
test_sc03_ordinary_rename_between_active_paths_is_unchanged ... ok
test_sc03_rename_with_destination_under_archive_is_unchanged ... ok
test_sc04_archive_restore_of_a_deep_path_still_works ... ok
Ran 8 tests in 0.113s
FAILED (failures=5)
```
(the SC-03/SC-04 regression guards and the `PerformRenameDirectCall` placement test were written first and already passed against the untouched code, per the gate's TDD-order instruction.)

GREEN (targeted classes, then full suite):

```
Ran 93 tests in 0.783s
OK
```
```
Ran 631 tests in 24.743s
OK
```
Baseline at HEAD `c90e13e` was 622 tests (per the task prelude); this leaf adds 9 (8 in `RenameSourceUnderArchiveRefuses`, 1 `test_ac4_direct_call_with_source_under_archive_is_not_refused` in `PerformRenameDirectCall`), landing at 631.

## Mutation proofs

Made recoverable via commit `21dae3f` before mutating; every mutation below was reverted with `git checkout -- cli/okf-cli.py` and confirmed by `git diff --stat` coming back empty.

**SC-05** — deleted the entire guard block from `cmd_rename` (`cli/okf-cli.py:4271-4292` at commit time, the `archive_root = os.path.realpath(...)` through `sys.exit(2)` block). Result: `test_sc01_apply_refuses_and_names_archive_restore`, `test_sc02_dry_run_refuses_identically_not_a_would_move_line`, `test_ac2_dry_run_and_apply_refuse_with_the_identical_message`, `test_ac1_traversal_argument_that_resolves_into_archive_is_refused` and `test_ac1_symlink_resolving_into_archive_is_refused` went RED; `test_sc03_ordinary_rename_between_active_paths_is_unchanged`, `test_sc03_rename_with_destination_under_archive_is_unchanged` and `test_sc04_archive_restore_of_a_deep_path_still_works` stayed GREEN — exactly SC-05's shape.

**AC1 (resolved source, not raw argument)** — two sub-mutations to isolate what "resolved" buys:
1. `resolved_old = os.path.realpath(old_abs)` → `resolved_old = old_abs` (keeping `archive_root` realpath'd). All 5 refusal-shaped tests went RED, including the plain SC-01 case — because on macOS `tempfile.mkdtemp()` itself returns a path under `/var/...` which is a symlink to `/private/var/...`, so even the ordinary (non-symlink, non-traversal) case needs realpath to compare correctly against `root/_archive`. This is why `resolved_old` alone dropping realpath breaks everything, not just the symlink test.
2. To isolate the symlink-specific claim, also dropped realpath from `archive_root` (`archive_root = os.path.join(root, "_archive")`, `resolved_old = old_abs` — purely lexical/abspath comparison on both sides). Result: only `test_ac1_symlink_resolving_into_archive_is_refused` went RED; `test_ac1_traversal_argument_that_resolves_into_archive_is_refused` and all others stayed GREEN — `os.path.abspath` already collapses a `..`-traversal argument lexically (that normalization happens in `cmd_rename` before the guard even runs), so only a real symlink resolution needs `os.path.realpath`'s symlink-following behaviour. This confirms the code comment's claim precisely.

**AC2 (planning path refuses identically)** — mutated `cli/okf-cli.py:4290` (line offset at mutation time) from `if resolved_old == archive_root or resolved_old.startswith(archive_root + os.sep):` to `if args.apply and (resolved_old == archive_root or resolved_old.startswith(archive_root + os.sep)):`. Result: `test_sc02_dry_run_refuses_identically_not_a_would_move_line` and `test_ac2_dry_run_and_apply_refuse_with_the_identical_message` went RED (2 failures); the rest stayed GREEN.

**AC3 (every other path, incl. destination under `_archive/`, unchanged)** — mutated `resolved_old = os.path.realpath(old_abs)` to `resolved_old = os.path.realpath(new_abs)` (checked the destination instead of the source). Result: `test_sc03_rename_with_destination_under_archive_is_unchanged` went RED (errored — the destination-under-archive case, which must stay a normal successful move, now wrongly refused), alongside the other refusal-shaped tests losing their real signal; `test_sc03_ordinary_rename_between_active_paths_is_unchanged` and `test_sc04_archive_restore_of_a_deep_path_still_works` stayed GREEN.

**AC4 (placement in `cmd_rename`, not `perform_rename`)** — removed the guard from `cmd_rename` and re-inserted the identical check (using `die()` and `verb`) at the top of `perform_rename`, right after its own `die` closure is defined (`cli/okf-cli.py:4112-4114`), before `if not old_abs.endswith(".md")...`. Ran the FULL suite (not just the targeted class), since the trap is that a caller-blind test would stay green: **7 tests went RED** — `ArchiveConcept.test_restore_derives_destination_without_a_second_path`, `ArchiveConcept.test_restore_preserves_multi_level_concept_id_substructure`, `ArchiveConcept.test_round_trip_archive_then_restore_is_byte_identical_including_links`, `ArchiveConcept.test_sc01_restore_of_last_concept_removes_empty_archive_dirs`, `ArchiveConcept.test_sc02_restore_with_sibling_concept_keeps_the_directory`, `RenameSourceUnderArchiveRefuses.test_sc04_archive_restore_of_a_deep_path_still_works`, and — the dedicated placement guard — `PerformRenameDirectCall.test_ac4_direct_call_with_source_under_archive_is_not_refused`. This both confirms AC4 (the guard's presence in the shared core is caught) and AC5 in the same swing (moving it there breaks `archive --restore`, which is exactly the operation AC5 protects).

**AC5 (archive --restore keeps working)** — proven negatively by the AC4 mutation above (7 tests including 4 pre-existing `archive`-suite tests broke) and positively by the unmutated code's green run of `ArchiveConcept.test_round_trip_archive_then_restore_is_byte_identical_including_links` and the new `RenameSourceUnderArchiveRefuses.test_sc04_archive_restore_of_a_deep_path_still_works`.

## Smoke

Real `cli/okf-cli.py` run via `python3 cli/okf-cli.py --root "$SMOKE" ...` against a throwaway `mktemp -d` directory (never `~/Obsidian/Knowledge-Catalogue`), covering every scenario the gate names:

```
=== 1. refused rename OUT of _archive/, no --apply ===
rename: source lies under _archive/ — use archive --restore to bring it back: _archive/a/old.md
exit=2

=== 2. refused rename OUT of _archive/, --apply ===
rename: source lies under _archive/ — use archive --restore to bring it back: _archive/a/old.md
exit=2

=== 3. ordinary rename (active -> active), --apply ===
moved (fs)  a/active.md  ->  a/active2.md
...
exit=0

=== 4. rename whose DESTINATION lies under _archive/, --apply ===
moved (fs)  a/active2.md  ->  _archive/a/active2.md
...
exit=0

=== 5. archive --restore round trip (old.md back out) ===
0 active concept(s) still link to this concept
moved (fs)  _archive/a/old.md  ->  a/old.md
...
exit=0
```

Filesystem state before: `_archive/a/old.md`, `a/active.md`, `a/index.md`. Filesystem state after: `_archive/a/active2.md`, `a/index.md`, `a/old.md` — the refused steps (1, 2) left `_archive/a/old.md` untouched, the ordinary rename (3) and the destination-under-archive rename (4) moved the file as expected, and the restore (5) brought `old.md` back to `a/`. Temp directory removed after the run (`rm -rf`).

## Deviations/ERRATA

None from the bean's shape or AC1-AC5. As instructed by the gate ("Adding a test that secures an existing acceptance criterion is NOT a plan deviation and needs no escalation"), `PerformRenameDirectCall.test_ac4_direct_call_with_source_under_archive_is_not_refused` was written proactively at TDD time (not discovered later as a gap) precisely because the `OKFT-5436` precedent and this bean's own prelude call out the exact same placement trap — no separate commit or escalation, folded into the single implementation commit.

Commit subject measured before committing (prelude I01, in force): `fix(rename): refuse a source under _archive/` is 44 bytes — inside the 50-byte soft target, and this is the only commit in the leaf (implementation + all new tests together, since the AC4 placement test was proactive, not a later-discovered deviation requiring its own commit per the `OKFT-5436` precedent's rationale).

Message wording (`"source lies under _archive/ — use archive --restore to bring it back: {path}"`) reuses, verbatim, the phrase `"use --restore to bring it back"` already established at `cli/okf-cli.py:4328-4330` (per the bean's explicit instruction), prefixed with the full command name `archive --restore` since this refusal fires from `rename`'s own context, where `archive` cannot be inferred from a bare `--restore`. This is an implementer judgment call within the AC's stated freedom (AC1 only requires the message to name `archive --restore`, not exact phrasing) — flagging in case the PO wants different wording, same posture `OKFT-5436`'s closing report took for its own wording choice.

## Notes for T(n+1)

`_prune_empty_archive_dirs`'s broad `except OSError` (I02 from the `OKFT-5436`/`OKFT-gqss` chain) remains untouched and out of scope here, as it was there.

The "Note on the residue" in this bean's own body is honoured: no pruning logic was added to `rename` or to `perform_rename`; this leaf only removes the one way `rename` could reach the residue. If a future change ever makes a source under `_archive/` renameable again through `rename`, the prune question of `OKFT-gqss` returns with it, per that note.

Epic `OKFT-0xkj`'s Q02/D02 is now fully closed by this leaf; no open question remains there for this thread. Q01 in the same epic remains open for the PO, unrelated to this leaf.

Commit: `21dae3f05c114c925d02063ff5d1772e9da0b9fd` — `fix(rename): refuse a source under _archive/` (`Refs: OKFT-tk33`).
