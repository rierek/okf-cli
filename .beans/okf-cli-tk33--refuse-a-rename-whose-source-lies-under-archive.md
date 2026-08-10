---
# okf-cli-tk33
title: refuse a rename whose source lies under _archive
status: draft
type: task
priority: normal
created_at: 2026-08-10T10:22:51Z
updated_at: 2026-08-10T10:22:51Z
parent: okf-cli-0xkj
---

A `rename` whose source lies under `_archive/` currently succeeds and leaves the same invisible empty-directory residue that `okf-cli-gqss` closed for the `archive --restore` path. This leaf makes that path refuse and name the verb that does the job properly.

## Origin — PO decision on Q02, 2026-08-10

Raised as decision D01 of the `ce-specs-reviewer` verdict on `okf-cli-gqss`, escalated to the PO as `Q02` in the parent epic `okf-cli-0xkj`, decided the same day.

The reviewer verified the gap with his own smoke run: after `okf-cli-gqss` shipped, this still reproduces the original defect —

```
okf-cli.py rename _archive/<bundle>/old.md <bundle>/old.md --apply
```

— leaving `_archive/<bundle>/` and `_archive/` standing, invisible to `git status` because git does not track empty directories.

Three readings were put to the PO: leave it, extend the prune to `cmd_rename`, or refuse the path. The PO chose the third, verbatim:

> ein rename, dessen Quelle unter _archive/ liegt, verweigert und verweist auf archive --restore

**Interpretation.** A `rename` whose resolved source lies under `_archive/` is refused with a non-zero exit and an error naming `archive --restore`. Every other `rename` path is untouched. The residue then cannot be produced through `rename` at all, so the guarantee of `okf-cli-gqss` becomes command-independent without any pruning logic entering the shared code.

**Why this reading and not the second one.** `docs/okf-archive-lifecycle/SPEC.md` section 2 requires (R-04/A15) that `rename` behaviour stay byte-identical, provable by the unchanged `rename` test set. Moving the prune into `perform_rename` would have broken that explicit promise. A refusal is a new guard on the caller, not a change to what a successful `rename` does — the existing `rename` test set exercises no source under `_archive/`, so its behaviour stays byte-identical in the sense R-04/A15 means it.

## Placement — the same rule that governs `okf-cli-5436`

The guard belongs in `cmd_rename`, NOT in `perform_rename`. That function is shared with `archive`, and `archive --restore` legitimately moves a source out of `_archive/` — a guard inside the shared function would refuse the very operation the PO is pointing users at. This is the same reasoning that put the three direction guards and the `okf-cli-5436` counterpart check in `cmd_archive`: archive-specific knowledge belongs in the specific caller, per SPEC section 2.

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

_Requirements: PO decision on Q02, 2026-08-10; reviewer finding D01 on `okf-cli-gqss`_

## Recommended Skills

- `superpowers:test-driven-development` — SC-03 and SC-04 are regression guards on existing behaviour and have to exist before the refusal is written, otherwise there is no way to tell the untouched paths stayed untouched.

## Note on the residue

This leaf does not add pruning to `rename`. It removes the only way to reach the residue through `rename`. If a future change ever makes a source under `_archive/` renameable again, the prune question of `okf-cli-gqss` returns with it — record that here rather than discovering it twice.
