---
# OKFT-ubxk
title: archive command
status: todo
type: feature
priority: normal
tags:
    - accepted
created_at: 2026-08-09T19:13:45Z
updated_at: 2026-08-10T08:05:29Z
parent: OKFT-huow
---

The `archive` / `archive --restore` verbs and the refactor that lets them reuse `rename` instead of reimplementing it.

Covers R-01 … R-04 of `docs/okf-archive-lifecycle/SPEC.md`.


## Review 2026-08-10

US-01 · `archive <bundle>/<cid>` without `--apply` prints the move plan and the inbound-link count, changes nothing on disk · a


- US-02 · `archive <bundle>/<cid> --apply` moves the file to `_archive/<bundle>/<cid>.md` with a tracked `git mv`, rewrites inbound links, reports the path taken · a
- US-03 · `archive --restore <archive-path> --apply` restores the active path without a second path typed, content byte-identical · a
- US-04 · the three direction guards reject an already-archived source, a `--restore` on an active source, and an archive path without a bundle segment · a

First evaluation of US-04 was `r`, on a test case that did not reach the guards: the PO typed the *active* path twice, so the second run fell through to "source not found". Re-run against `_archive/…` produced all three guard messages verbatim. The wish behind the initial `r` is kept as a side finding, not as a reject: `OKFT-5436`.

US-02 and US-03 were first evaluated `a` on evidence showing `moved (fs)`, i.e. the non-git fallback A02 rules out. Cause was an untracked test file, not a defect. Both were re-run against a committed fixture and produced `moved (git mv)` plus a staged `R` rename in `git status`; US-03 left the tree empty, which is the A03 byte-equality proof.

R-04 (`perform_rename` extracted from `cmd_rename`, leaf `OKFT-2lj0`) carries no observable behaviour change and was not reviewed as a story. Its evidence is A15: the pre-existing `rename` test set stays green.
