---
# okf-cli-16rg
title: add the archive and restore verbs
status: in-progress
type: task
priority: normal
created_at: 2026-08-09T19:14:39Z
updated_at: 2026-08-09T19:40:17Z
parent: okf-cli-ubxk
blocked_by:
    - okf-cli-2lj0
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


## 2026-08-09 — Prelude from the review of okf-cli-2lj0 (finding F01, minor)

`perform_rename` is yours to wrap, and it carries one open wording gap you inherit.

Measured, not claimed: before the refactor (`e62dfb8`) a missing source reported `rename: source not found: a/nope.md` — the raw CLI string. After it (`3310656`) the same call reports `rename: source not found: /abs/path/a/nope.md` — the resolved path. Same for "destination exists". The spec-fixed signature (`docs/okf-archive-lifecycle/SPEC.md:51`) carries only `old_abs`/`new_abs`, so the raw string no longer exists inside the function. No test pins either wording.

Two consequences for this task:

1. **Do not assume the old wording.** If any acceptance criterion of yours asserts an error message, assert the wording you actually observe, and say so in your report.
2. **Do not "fix" it on your own initiative.** Whether the resolved path is acceptable is a PO call, not an implementer call — it is with the PO now. If the answer arrives during your run, the supervisor relays it to you. If it does not, leave the behaviour as it stands.

The reviewer's framing, for context: SC-01 defines "unchanged" operationally as "the 60 existing rename tests stay green unmodified", and that criterion is met. The gap is against the literal AC4 wording, not against the tested contract.
