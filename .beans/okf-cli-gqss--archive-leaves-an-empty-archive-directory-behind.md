---
# okf-cli-gqss
title: archive leaves an empty _archive directory behind
status: todo
type: bug
priority: normal
created_at: 2026-08-10T09:15:35Z
updated_at: 2026-08-10T09:52:40Z
parent: okf-cli-0xkj
---

A restore that empties _archive/<bundle>/ leaves both directories on disk. Git does not track empty directories, so git status stays clean and the leftover is invisible.


## Observed twice, on the real catalogue both times

First during the R-15 round trip (`okf-cli-fv7y`, 2026-08-09), where the operator removed the leftover by hand with `rmdir`. Again during the PO review on 2026-08-10: after `archive --restore _archive/agent-memory/mein-konzept.md --apply`, `git -C ~/Obsidian/Knowledge-Catalogue status` reported nothing, while `ls -d ~/Obsidian/Knowledge-Catalogue/_archive` still resolved. Both `_archive/` and `_archive/agent-memory/` were left standing, empty.

The invisibility is the point. Git does not track empty directories, so the usual "is the tree clean" check reports clean and the operator concludes the round trip was complete. It was not. This is the same failure shape as the symlink bug next door (`okf-cli-mk7m`): a residue that the obvious verification cannot see.

Second-order consequence: a later `archive` run into a bundle that already carries an empty `_archive/<bundle>/` looks like it is resuming an existing archive rather than creating one. Nothing breaks, but the operator's mental model of the store is wrong.

Split from `okf-cli-mk7m` deliberately — same run, different mechanism, independently fixable.

### Requirement 1: The archive directory does not outlive its contents

**Objective:** As a catalogue maintainer, I want a restore to leave no trace on disk, so that a clean `git status` actually means a clean store.

#### Acceptance Criteria

1. WHEN a restore removes the last concept from `_archive/<bundle>/` THE okf-cli SHALL remove that directory.
2. WHEN removing `_archive/<bundle>/` empties `_archive/` itself THE okf-cli SHALL remove `_archive/` as well.
3. IF `_archive/<bundle>/` still holds any file THEN THE okf-cli SHALL leave the directory in place.

#### Success Criteria

- SC-01: An archive-then-restore round trip on a fixture leaves neither `_archive/` nor `_archive/<bundle>/` on disk, asserted by a filesystem check rather than by `git status`.
- SC-02: A restore that leaves a sibling concept behind in the same archived bundle keeps the directory, asserted in its own test.
- SC-03: Removing the directory-cleanup call turns SC-01 red.

_Requirements: PO review 2026-08-10, second finding of the R-15 run_

## Recommended Skills

- `superpowers:test-driven-development` — the assertion has to be a filesystem check, and a test written after the fix would pass against `git status` alone.


## Prelude 2026-08-10 — carried over from the review of `okf-cli-mk7m`

Three non-blocking findings from the `ce-specs-reviewer` verdict on `okf-cli-mk7m` (APPROVED). None of them is work on this leaf's behaviour; they are process obligations for whoever implements next. Handle them as part of your ordinary work, not as a separate commit.

**I02 — commits carry a `Refs:` footer.** Neither `bf2b5d2` nor `49ea46f` had one. The convention is documented in the OKF concept `claude-code-wiki/git-workflow/git-conventions` ("Footer: `Refs: <issue/bean-id>`") and is style-only, not hook-enforced — which is exactly why it gets dropped. Every commit of this leaf carries `Refs: okf-cli-gqss`.

**I01 — commit subject soft target.** `bf2b5d2` ran to 55 characters. The hard limit of 72 held and the hook did not fire, so this is a miss against the 50-character soft target, not a violation. Aim for 50.

**I03 — mutation proofs cite the exact line, not the branch name.** The mk7m report described its AC1 mutation as "disabled the foreign-repo retry branch". Two different `if` lines answer to that description: mutating the inner condition (`cli/okf-cli.py:4092`) turns exactly one test red, mutating the outer one (`cli/okf-cli.py:4087`) turns two red — a wider collateral failure that the report did not disclose. The reviewer reproduced the narrow one and had to discover the discrepancy himself. State `file:line` and the mutated expression verbatim, so a reviewer reproduces your proof rather than a neighbouring one.
