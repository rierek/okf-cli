---
# okf-cli-5436
title: 'archive: point at --restore when the missing source sits in the archive'
status: completed
type: feature
priority: high
created_at: 2026-08-10T06:45:10Z
updated_at: 2026-08-10T10:19:03Z
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

## Summary

`cmd_archive` (`cli/okf-cli.py:4333-4346`) now checks, right after `dest_abs` is derived and before delegating to `perform_rename`, whether the source is missing but its derived counterpart exists — if so it dies with a message naming that counterpart and the verb that reaches it, instead of falling through to `perform_rename`'s bare "source not found" (AC1/AC2/AC4). The check lives entirely in `cmd_archive`; `perform_rename` (`cli/okf-cli.py:4106-4119`) is untouched, so `rename` keeps its plain message (AC4, guarded by a dedicated test — see Deviations). A missing source with no counterpart anywhere still hits the original, unmodified `perform_rename` die and produces the byte-identical old message (AC3).

## Test-Output

RED (before the new branch, `ArchiveMissingSourcePointsAtCounterpart`, both new-behaviour tests failing while the SC-02 regression test — added and confirmed green first, against unmodified code — already passes):

```
FAIL: test_sc01_missing_source_with_archived_counterpart_names_restore
AssertionError: '_archive/a/old.md' not found in 'archive: source not found: /var/.../a/old.md\n'
FAIL: test_ac2_missing_restore_source_with_active_counterpart_names_it
AssertionError: 'archive: source not found: .../_archive/a/old.md — the active copy already exists at a/old.md\n' != 'archive: source not found: .../_archive/a/old.md\n'
ok test_sc02_missing_source_with_no_counterpart_keeps_current_message
Ran 3 tests in 0.003s
FAILED (failures=2)
```

GREEN (after implementing the branch, same class, then full suite):

```
ok test_ac2_missing_restore_source_with_active_counterpart_names_it
ok test_sc01_missing_source_with_archived_counterpart_names_restore
ok test_sc02_missing_source_with_no_counterpart_keeps_current_message
Ran 3 tests in 0.002s
OK
```

```
Ran 622 tests in 26.650s
OK
```

Baseline at HEAD `fefe80c` was 618 tests; this leaf adds 4 (3 in `ArchiveMissingSourcePointsAtCounterpart` for AC1/AC2/SC-02, 1 `test_ac4_missing_source_with_file_at_destination_stays_plain` in `PerformRenameDirectCall` for AC4), landing at 622.

## Mutation proofs

**SC-03** — removed the whole new branch (`cli/okf-cli.py:4341-4346`, the `if not os.path.isfile(src_abs) and os.path.isfile(dest_abs):` block and both `die(...)` calls under it). Result: `test_sc01_missing_source_with_archived_counterpart_names_restore` and `test_ac2_missing_restore_source_with_active_counterpart_names_it` went RED, `test_sc02_missing_source_with_no_counterpart_keeps_current_message` stayed GREEN — exactly SC-03's requirement. Reverted with `git checkout -- cli/okf-cli.py`; `git diff --stat` came back empty.

**AC1/AC2 vs AC3** — mutated `cli/okf-cli.py:4341` from `if not os.path.isfile(src_abs) and os.path.isfile(dest_abs):` to `if not os.path.isfile(src_abs):` (dropped the counterpart check, so the new branch now fires unconditionally on any missing source). `test_sc02_missing_source_with_no_counterpart_keeps_current_message` went RED — the no-counterpart case (AC3) started producing the new wording — while SC-01 and AC2 stayed GREEN. Reverted with `git checkout -- cli/okf-cli.py`; clean.

**AC4** — could not name an existing test that would catch this check being placed in `perform_rename` instead of `cmd_archive`, so per the gate instructions I broke the behaviour: mutated `cli/okf-cli.py:4118-4119` from `if not os.path.isfile(old_abs): die("source not found: {}".format(old_abs))` to add a nested `if os.path.isfile(new_abs): die(...)` branch inside `perform_rename` itself — i.e. moved AC1's logic into the shared core. Ran the full suite: 621/621 green, confirming the violation was genuinely untested. Wrote `test_ac4_missing_source_with_file_at_destination_stays_plain` in `PerformRenameDirectCall` (calls `perform_rename` directly with a missing `old_abs` and an existing `new_abs`, asserts the literal plain `"rename: source not found: {}\n"` message), confirmed it GREEN against the correct code, then re-applied the same mutation and confirmed it RED. Reverted with `git checkout -- cli/okf-cli.py`; clean. This test is now committed (`5547511`) as the standing AC4 guard.

## Smoke

Real `okf-cli.py` run against a throwaway temp directory (not `~/Obsidian/Knowledge-Catalogue`), covering the PO's exact repro plus the mirrored and no-counterpart cases:

```
=== 1. archive it (apply) ===
0 active concept(s) still link to this concept
moved (fs)  agent-memory/mein-konzept.md  ->  _archive/agent-memory/mein-konzept.md
  untracked — git declined: fatal: not a git repository (or any of the parent directories): .git
staged for commit — run `okf-cli.py check` before committing.

=== 2. archive it again (the PO's repro — new message) ===
archive: source not found: .../agent-memory/mein-konzept.md — already archived at _archive/agent-memory/mein-konzept.md (use --restore to bring it back)

=== 3. mirrored restore case: restore something that never left ===
archive: source not found: .../_archive/agent-memory/active-one.md — the active copy already exists at agent-memory/active-one.md

=== 4. no-counterpart case: unchanged message ===
archive: source not found: .../agent-memory/never-existed.md
```

Temp directory removed after the run (`rm -rf`); `~/Obsidian/Knowledge-Catalogue` was never touched.

## Deviations/ERRATA

None from the bean's shape or AC1-AC4. One addition beyond the bean's explicit SC list: the AC4 mutation proof surfaced that no existing test would catch this check leaking into `perform_rename` (full suite stayed green under that mutation), so I added `test_ac4_missing_source_with_file_at_destination_stays_plain` to `PerformRenameDirectCall` — a regression guard on `rename`'s plain message, committed separately (`5547511`). Per this leaf's own instructions this is not a plan deviation needing escalation: it secures an existing acceptance criterion (AC4) that the bean already states, not new scope.

I01 (commit-subject soft target) from the prelude: both commit subjects in this leaf measured — `fix(archive): point missing source at --restore` is 47 bytes, `test(archive): guard AC4 placement of the source signal` is 55 bytes (checked against the 50-byte soft target and the 72-byte hard limit before committing). The second is 5 over soft target; noted rather than silently repeating the miss the prelude flagged.

## Notes for T(n+1)

I02 from the prelude (`_prune_empty_archive_dirs`'s broad `except OSError`) is untouched — out of this leaf's scope, still standing as documented.

Q01/Q02 in the parent epic (`okf-cli-0xkj`) remain open PO decisions unrelated to this leaf's behaviour.

The message wording chosen here (`"already archived at {dest_rel} (use --restore to bring it back)"` / `"the active copy already exists at {dest_rel}"`) is an implementer judgment call within the AC's freedom — the AC only requires the archived/active path and the `--restore` verb to appear, not exact phrasing; flagging in case the PO wants different wording.
