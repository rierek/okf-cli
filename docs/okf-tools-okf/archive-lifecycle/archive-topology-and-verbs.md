---
type: Concept
title: The archive is a directory, and archive/restore are its only verbs
description: An archived concept lives at _archive/<bundle>/<cid>.md at catalogue level, never behind a frontmatter flag; archive and archive --restore each take one path and derive the other, guarded in both directions.
tags:
  - okf-cli
  - archive
  - architecture
timestamp: 2026-08-10T12:10:00Z
---

# The archive is a directory, and archive/restore are its only verbs

The convention comes from `lean-stack/docs/okf-knowledge-lifecycle/taxonomy-and-lifecycle/DESIGN.md` (sections 4 and 7, decisions D05-D08, D13, D14, D21). The okf-cli side of it shipped as milestone `okf-cli-huow` and its follow-up epic on 2026-08-09/10; this concept is what the SPEC of that theme said, kept after the SPEC itself was cleared away.

**The place is the statement.** An archived concept sits at `_archive/<bundle>/<concept-id>.md`, at catalogue level rather than inside a bundle. There is no `archived:` field in the frontmatter (D06) — a flag would be a second truth to keep in sync with the file's location, and the location is checkable. The bundle name is preserved inside the archive path on purpose (D14): it is what lets a scoped query still mean "this bundle's history".

A multi-level concept id keeps its substructure: `dev-wiki/patterns/retry.md` becomes `_archive/dev-wiki/patterns/retry.md` and back.

## One path in, the other derived

Both directions take exactly one path and derive the counterpart; nobody types a destination. Dry run is the default, `--apply` executes, `--force` behaves as it does for `rename`.

| Direction | Source | Destination |
|---|---|---|
| archive | `<bundle>/<cid>.md` | `_archive/<bundle>/<cid>.md` |
| restore | `_archive/<bundle>/<cid>.md` | `<bundle>/<cid>.md` |

Three direction guards sit in `cmd_archive`, in addition to everything `rename` already guards. Each exists because of a concrete failure, not for symmetry:

- `archive` refuses a source already under `_archive/`, which would otherwise produce `_archive/_archive/…`.
- `archive --restore` refuses a source **outside** the archive: the derivation would compute a destination identical to the source, and `rename` would die with "source and destination are identical" — a message that describes the symptom and hides the cause.
- `--restore` refuses an archive path without a bundle segment (`_archive/x.md`), because no destination is derivable from it.

**These guards belong in `cmd_archive`, not in the shared `perform_rename`.** That function is shared with `rename`, which has no archive semantics; and `archive --restore` legitimately moves a source out of `_archive/`, so a guard placed in the shared core would refuse the operation the tool points its users at. The rule generalizes: caller-specific knowledge goes in the caller.

## What the report has to admit

Two things the command says beyond "moved", both added because their absence misled someone:

**How many active concepts still link here.** `plan_rename` already knows the inbound set, so the count is free. Without it, archiving is silent about what it leaves behind.

**Which repository actually received the write, when git declined the move.** `_git_mv` runs `git mv` and falls back to `os.rename` when git refuses. The fallback used to print a bare `moved (fs)` and drop git's stderr unread. Two different causes produce that identical surface: a bundle that is a symlink into another repository (`fatal: not under version control, source=…, destination=…`, exit 128 — *not* `beyond a symbolic link`, which comes from `git add`), and an ordinary untracked file. Now the report names git's own reason and, where a different repository received part of the write, names that repository too. An operator pointing the tool at the catalogue otherwise gets changes in `~/dev/<project>` and looks for them in the wrong `git status`.

## Restoring leaves nothing behind, and `rename` cannot reach the archive

A restore that empties `_archive/<bundle>/` removes that directory, and removes `_archive/` when it was the last one. Git does not track empty directories, so the leftover was invisible to the check everyone runs — a clean `git status` meant nothing. A sibling concept still in the archived bundle keeps the directory standing.

The prune lives in `cmd_archive` only, which left one way to produce the residue anyway: a direct `rename` out of `_archive/`. Rather than move pruning into the shared function — which would have broken the byte-identical-`rename` promise (R-04/A15) — a `rename` whose **resolved** source lies under `_archive/` is now refused and points at `archive --restore`. Resolved means `os.path.realpath`: `abspath` alone collapses a `..` traversal, but only `realpath` also follows a symlink whose target lands inside the archive without the argument ever spelling `_archive/`. The refusal fires before the apply/dry-run split, so a preview never promises a move that `--apply` would decline.

## Deliberate non-goals

Recorded because each was asked for and declined:

- No batch archiving. One operation, one concept.
- No retention automation and no deadline (D19).
- No `check` rule against references from active material into the archive. Such a reference is not broken, it is historical — a rule against it would turn every archiving into a cleanup chain.
- No authority rank in ranking (D18). Type stays a filter, modification date stays display.
