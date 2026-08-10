---
# okf-cli-gqss
title: archive leaves an empty _archive directory behind
status: completed
type: bug
priority: normal
created_at: 2026-08-10T09:15:35Z
updated_at: 2026-08-10T10:02:01Z
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

## Summary

Added `_prune_empty_archive_dirs(root, freed_dir)` (`cli/okf-cli.py:4273-4295`), a plain filesystem walk (no git involved, since the residue was never git-tracked in the first place) that removes every directory from a vacated concept's original directory up to and including `_archive/`, stopping at the first directory that still holds content. Wired it into `cmd_archive` (`cli/okf-cli.py:4349-4351`) so it runs only after a successful `--restore --apply` move — `archive` in the other direction only ever adds to `_archive/`, never empties it, so it needs no cleanup. `perform_rename` itself is untouched: the prune lives entirely in `cmd_archive`, so `rename`'s behaviour (R-04/A15, byte-identical) is not at risk.

## Test-Output

RED (test written first, against the unmodified defect):

```
test_sc01_restore_of_last_concept_removes_empty_archive_dirs ... FAIL
FAIL: test_sc01_restore_of_last_concept_removes_empty_archive_dirs
  File "cli/test_okf_cli.py", line 5596, in test_sc01_restore_of_last_concept_removes_empty_archive_dirs
    self.assertFalse(os.path.isdir(self._ap("_archive/a")))
AssertionError: True is not false

Ran 2 tests in 0.072s
FAILED (failures=1)
```

GREEN (full suite, after the fix):

```
Ran 618 tests in 25.970s
OK
```

618 = baseline 616 + `test_sc01_restore_of_last_concept_removes_empty_archive_dirs` (SC-01) + `test_sc02_restore_with_sibling_concept_keeps_the_directory` (SC-02/AC3).

## Mutation proofs

All mutations were made git-recoverable first (`git commit -q -m "wip: ..."`, later reshaped into the final commit via `git reset --soft`), each mutation was run against the suite, then reverted; `git diff --stat` came back empty after every one of them.

- **SC-03 — remove the whole cleanup call.** Mutated `cli/okf-cli.py:4350` from `if args.restore and args.apply:` to `if False and args.restore and args.apply:`. Ran `python3 -m unittest cli.test_okf_cli`: exactly `test_sc01_restore_of_last_concept_removes_empty_archive_dirs` went red (`Ran 522 tests ... FAILED (failures=1)`), nothing else. Reverted; `git diff --stat` empty.
- **AC1+AC2, combined blast radius.** The SC-03 mutation above already demonstrates both: `test_sc01` asserts `_archive/a` gone (AC1) and `_archive` gone (AC2) in two consecutive `assertFalse` calls.
- **AC2 in isolation, distinct line and blast radius from AC1.** Mutated `cli/okf-cli.py:4288` from `while d == archive_root or d.startswith(archive_root + os.sep):` to `while d.startswith(archive_root + os.sep):` (drops the equality arm, so the walk climbs into direct children of `_archive/` but never processes `_archive/` itself). Result: `test_sc01` failed on its *second* assertion only (`self.assertFalse(os.path.isdir(self._ap("_archive")))`, line 5597) — the first assertion (`_archive/a` gone, AC1) passed silently, proving AC1 and AC2 are independently exercised even though they share one test. Reverted; `git diff --stat` empty.
- **AC3 — the "leave it in place" guard.** First tried mutating `cli/okf-cli.py:4290-4292` (`if os.listdir(d): break` / `os.rmdir(d)`) down to a bare `os.rmdir(d)` relying only on the `except OSError` catch below it. Suite stayed **green** — `os.rmdir` itself refuses on a non-empty directory and raises `OSError`, which the existing `except OSError: break` (line 4293-4294) already catches, so the `listdir` check is a redundant optimisation, not AC3's actual enforcement point. Per the gate's own instruction ("if it stays green, that criterion is untested — write the missing test"), I searched for a mutation that plausibly violates AC3 and does turn something red: replaced the `if os.listdir(d): break / os.rmdir(d)` pair with a bare `shutil.rmtree(d)` (`cli/okf-cli.py:4290-4292`, imitating the bug class "force-delete instead of remove-if-empty"). That turned exactly `test_sc02_restore_with_sibling_concept_keeps_the_directory` red (the sibling file was deleted along with the directory). This is the test that actually stands guard over AC3; the `listdir` check and the `except OSError` catch are two redundant expressions of the same OS-level guarantee, not two separate defended behaviours. Reverted; `git diff --stat` empty.

## Second-order case (bean's own question)

"A later `archive` into a bundle that already carries an empty `_archive/<bundle>/` looks like it is resuming an existing archive rather than creating one" — via the `archive`/`archive --restore` command pair, this state is now unreachable: the only way `_archive/<bundle>/` could previously go empty was a restore, and every restore now prunes it (and `_archive/` itself) immediately. Verified this end-to-end in the real-layout smoke run below (archive both siblings, restore one — directory survives; restore the other — directory and `_archive/` both vanish).

It is **not** unreachable in general: `cmd_rename` shares `perform_rename` with `cmd_archive` but the prune call lives only in `cmd_archive`'s `--restore` branch (deliberately, to keep `rename` byte-identical per R-04/A15). A user who calls `okf-cli.py rename _archive/<bundle>/x.md <bundle>/x.md` directly — bypassing the `archive` command's own direction guards and its cleanup — reproduces the original residue. Verified this with a direct `cmd_rename` call in a throwaway fixture: `_archive/<bundle>/` and `_archive/` both survived. This is outside SPEC.md's documented interface (`archive --restore` is the only restore path SPEC.md §1 describes) and outside this bean's scope, but it means the defect is closed for the supported command, not for every path that can technically reach the same filesystem state.

## Smoke

Real throwaway git repo under a temp dir (not `~/Obsidian/Knowledge-Catalogue`), full transcript in-session; abbreviated here:

```
archive agent-memory/mein-konzept.md --apply
  moved (git mv)  agent-memory/mein-konzept.md -> _archive/agent-memory/mein-konzept.md
archive --restore _archive/agent-memory/mein-konzept.md --apply
  _archive exists: NO
  _archive/agent-memory exists: NO
  git status --short: (empty)

archive agent-memory/mein-konzept.md --apply
archive agent-memory/sibling.md --apply
  find _archive: _archive, _archive/agent-memory, _archive/agent-memory/sibling.md, _archive/agent-memory/mein-konzept.md
archive --restore _archive/agent-memory/mein-konzept.md --apply
  find _archive: _archive, _archive/agent-memory, _archive/agent-memory/sibling.md
  _archive exists: YES   _archive/agent-memory exists: YES
  git status --short: R  agent-memory/sibling.md -> _archive/agent-memory/sibling.md

archive --restore _archive/agent-memory/sibling.md --apply
  _archive exists: NO
  git status --short: (empty)
  find . (excl .git): ./agent-memory, ./agent-memory/mein-konzept.md, ./agent-memory/sibling.md
```

## Deviations/ERRATA

None from the bean's scope or SPEC.md. One disclosed boundary, not a deviation: the fix is wired into `cmd_archive` only, not into `perform_rename` — see "Second-order case" above for the `rename`-bypass consequence this leaves open. I judged this correct rather than a gap to also close, because folding cleanup into `perform_rename` would touch `rename`'s own behaviour, which R-04/A15 (SPEC.md §2, §7) requires to stay byte-identical, and the bean's own scope boundary says fix only the empty-directory residue of `archive`/`archive --restore`, not reshape shared code neighbouring it.

Prelude items I01-I03 honoured: commit subject is 50 chars exactly (`fix(archive): prune empty _archive dirs on restore`), footer `Refs: okf-cli-gqss` present, and this report cites `file:line` and the mutated expression verbatim for every mutation above rather than describing branches by name.

## Notes for T(n+1)

- The `rename`-bypass gap above (a direct `okf-cli.py rename` call out of `_archive/` reproduces the original residue) is a plausible follow-up bean if the PO wants the guarantee to hold regardless of which command is used. It was not raised as a new bean here since it is outside this bean's stated scope and the bean's own text frames the defect specifically around `archive --restore`.
- `okf-cli-0xkj` (parent epic) still carries the open PO question Q01 about `okf-cli-mk7m`'s AC1 reading — unrelated to this leaf, unaffected by this change.

Commits: `20b42c0` — `fix(archive): prune empty _archive dirs on restore`.
