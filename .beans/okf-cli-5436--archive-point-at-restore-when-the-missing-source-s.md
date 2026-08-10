---
# okf-cli-5436
title: 'archive: point at --restore when the missing source sits in the archive'
status: in-progress
type: feature
priority: high
created_at: 2026-08-10T06:45:10Z
updated_at: 2026-08-10T10:11:49Z
parent: okf-cli-0xkj
---

PO side finding, 2026-08-10 review of US-04.


## Origin — PO review 2026-08-10, side finding on US-04

The PO ran `archive agent-memory/mein-konzept --apply` twice in a row. The second run answered:

```
archive: source not found: /Users/erik/Obsidian/Knowledge-Catalogue/agent-memory/mein-konzept.md
```

Formally correct — `cmd_archive` only guards the *direction* (R-03), and `agent-memory/mein-konzept` does not lie under `_archive/`, so the miss falls through to the generic "source not found" of `perform_rename`. The three direction guards themselves were verified working in the same session and are not in question.

### Why the PO wants it anyway (verbatim, German)

> also mir ist es ja passiert - daher wäre das wichtig, dass auch dieser Fehler abgefangen wird. Denn wenn bspw. ein Verweis in einer Unterlage liegt und stale ist, dann ist das der direkte Hinweis, dass ich dann im Archiv schauen kann.

That reframes the finding. This is not cosmetics on an error string: the message is a navigation signal. A reader who follows a stale reference out of some document and lands on a missing concept needs to be told the concept still exists, one directory over. The tool already holds that fact at the moment it errors — it computed `dest_rel` two lines earlier — and withholds it.

### Shape of the fix

In `cmd_archive` (cli/okf-cli.py:4214), on the non-restore path, before delegating to `perform_rename`: if `src_abs` does not exist but `dest_abs` does, fail with a message that names the archived path and the `--restore` verb instead of the bare "source not found". The mirrored case on the `--restore` path is worth considering too — a restore of something that already sits active.

Do not move the check into `perform_rename`. That function is shared with `rename`, which has no archive semantics; archive-specific knowledge belongs in the archive-specific caller, same reasoning as the three existing direction guards (SPEC.md section 2).

Acceptance: a missing source whose derived archive path exists errors with a message naming that path and `--restore`; a missing source with no archived counterpart keeps the current message.


### Requirement 1: A missing source that sits in the archive says so

**Objective:** As a reader following a stale reference, I want the tool to tell me the concept moved into the archive, so that the error message points me at where it went instead of only saying it is gone.

#### Acceptance Criteria

1. IF the source of an `archive` invocation does not exist AND its derived archive path does exist THEN THE okf-cli SHALL report the archived path and name the `--restore` verb.
2. IF the source of an `archive --restore` invocation does not exist AND its derived active path does exist THEN THE okf-cli SHALL report the active path.
3. IF the source does not exist AND no counterpart exists at the derived path THEN THE okf-cli SHALL keep its current "source not found" message unchanged.
4. THE okf-cli SHALL implement this check in `cmd_archive`, not in `perform_rename`.

#### Success Criteria

- SC-01: `archive <bundle>/<cid>` on a concept already archived exits non-zero with a message containing both the `_archive/…` path and `--restore`.
- SC-02: `archive <bundle>/<cid>` on a concept that exists nowhere produces the unchanged current message, asserted against the literal string.
- SC-03: Removing the new branch turns SC-01 red while leaving SC-02 green.

_Requirements: PO review 2026-08-10, side finding on US-04_

## Recommended Skills

- `superpowers:test-driven-development` — SC-02 is a regression guard on an existing message, so it has to exist before the new branch is written.


## Prelude 2026-08-10 — carried over from the review of `okf-cli-gqss`

Two non-blocking findings from the `ce-specs-reviewer` verdict on `okf-cli-gqss` (APPROVED). Neither is work on this leaf's behaviour; carry them as obligations on your own work, no separate commit.

**I01 — commit subject soft target, again.** `1bbcfe3` came in at 51 bytes against the 50-byte soft target. The hard limit of 72 is hook-enforced and held; this is a miss, not a violation. It is the second leaf in a row that overshoots by a hair — count the subject before committing.

**I02 — a broad `except` can recreate the residue this epic is closing.** `_prune_empty_archive_dirs` (`cli/okf-cli.py:4293-4294`) catches every `OSError` subclass and breaks, not only `ENOTEMPTY`. On a permission error or a race the prune aborts silently and leaves exactly the invisible empty-directory state that `okf-cli-gqss` was written to eliminate. The reviewer confirmed this matches the codebase idiom (`cli/okf-cli.py:3739`, `:4077` catch equally broadly) and that AC1-AC3 of that bean demand no error diagnostics, so it was correctly left alone there. It is recorded here so the next person touching that function knows the silent-abort path exists.

**Prelude items still in force from the mk7m review:** every commit carries a `Refs: okf-cli-5436` footer (style, not hook-enforced, which is why it gets dropped), and mutation proofs cite `file:line` plus the mutated expression verbatim rather than the semantic name of the branch.
