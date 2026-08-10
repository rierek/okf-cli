---
# OKFT-2lj0
title: extract perform_rename from cmd_rename
status: completed
type: task
priority: normal
created_at: 2026-08-09T19:14:20Z
updated_at: 2026-08-09T20:11:42Z
parent: OKFT-ubxk
---

`cmd_rename` (cli/okf-cli.py:3846) is validation, planning and application in one handler that reads its parameters off an argparse namespace (`args.old`, `args.new`, `args.apply`, `args.force`). A wrapper that assembles such a namespace would be coupled to every later flag change without a test showing it. Lift the body into a function both commands call.

### Requirement 1: Shared rename core

**Objective:** As a CLI maintainer, I want the rename body callable as a plain function, so that `archive` reuses the move machinery instead of forging an argparse namespace.

#### Acceptance Criteria

1. THE okf-cli SHALL provide `perform_rename(root, old_abs, new_abs, apply, force, verb)` holding the validation, planning and application logic currently inside `cmd_rename`.
2. THE okf-cli SHALL implement `cmd_rename` as a call into `perform_rename` with its two paths resolved.
3. WHERE `verb` is supplied THE okf-cli SHALL use it as the prefix of the command's error messages.
4. THE okf-cli SHALL leave the observable behaviour of `rename` unchanged, including its dry-run output, its ambiguity guards and its exit codes.

#### Success Criteria

- SC-01: The existing `rename` test set passes unmodified against the refactored code.

_Requirements: R-04_

## Recommended Skills

- `superpowers:test-driven-development`


## Summary
`cmd_rename` (cli/okf-cli.py) is now a five-line wrapper: it resolves `args.old`/`args.new` to absolute paths and calls `perform_rename(root, old_abs, new_abs, args.apply, args.force)`. `perform_rename(root, old_abs, new_abs, apply, force, verb="rename")` holds the full validation/planning/application body that used to live inline in `cmd_rename`, unchanged except that it reads `apply`/`force`/`verb` as plain parameters instead of `args.apply`/`args.force`/a hardcoded `"rename"` prefix. `_git_mv`, `plan_rename`, `plan_wikilink_rewrites`, `reindex_tree` are called exactly as before, from inside `perform_rename`.

## Test-Output
RED (characterization test against the new signature, added first in commit 8c648b8):
```
ERROR: test_apply_moves_the_file_and_rewrites_inbound_links (test_okf_cli.PerformRenameDirectCall...)
AttributeError: module 'okf_cli' has no attribute 'perform_rename'
(3 more ERROR of the same shape — Ran 4 tests in 0.000s, FAILED (errors=4))
```
GREEN after the refactor (commit 3310656):
```
$ python3 -m unittest test_okf_cli.PerformRenameDirectCall -v
test_apply_moves_the_file_and_rewrites_inbound_links ... ok
test_default_verb_is_rename ... ok
test_dry_run_makes_no_change_and_reports_it_would_move ... ok
test_explicit_verb_prefixes_the_error_message ... ok
Ran 4 tests in 0.017s
OK
```
Full suite:
```
$ just test
Ran 552 tests in 23.539s
OK
```
(548 baseline + 4 new `PerformRenameDirectCall` tests. All 60 pre-existing `RenameConcept`+`RenameWikilinks` tests pass unmodified — SC-01.)

## Mutation
Checkpointed at commit 3310656 (git-restorable); each mutation reverted via `git checkout -- cli/okf-cli.py` immediately after observing red.

| AC | Mutation | Test gone red | Why |
|----|----------|----------------|-----|
| AC1 (perform_rename holds validation/planning/application) | Removed the `.md`-extension guard from inside `perform_rename` | `RenameWikilinks.test_non_md_destination_is_refused` | The guard now lives only in `perform_rename`; removing it there makes the `rename` command (which delegates to it) stop refusing a `.txt` destination — `SystemExit not raised`. |
| AC2 (cmd_rename calls perform_rename with resolved paths) | Made `cmd_rename` pass `args.old`/`args.new` unresolved instead of `old_abs`/`new_abs` | `RenameWikilinks.test_inbound_plain_is_rewritten` | With relative paths, `perform_rename`'s `os.path.isfile(old_abs)` check fails against a path that was never joined to `root` — the run dies with "source not found", proving `cmd_rename` must resolve before delegating. |
| AC3 (verb prefixes error messages) | Hardcoded `die()`'s prefix to `"rename"`, ignoring the `verb` parameter | `PerformRenameDirectCall.test_explicit_verb_prefixes_the_error_message` | Calling `perform_rename(..., verb="archive")` on a bad destination still wrote `"rename: ..."` to stderr instead of `"archive: ..."` — `assertTrue(err.startswith("archive:"))` failed. |
| AC4 (dry-run output unchanged) | Turned `if not apply:` into `if False:` (dry-run branch unreachable) | `RenameWikilinks.test_dry_run_lists_and_writes_nothing` | Without `--apply` the run should print the wikilink dry-run lines and touch nothing; with the branch dead it fell through to the real move — `len(wl_lines)` was `0` instead of `2`. |
| AC4 (ambiguity guard unchanged) | Turned `if apply and wl_ambiguous and not force:` into `if False:` | `RenameWikilinks.test_basename_preserving_move_that_turns_a_link_ambiguous_is_refused` | A move that turns an inbound wikilink ambiguous must be refused under `--apply` without `--force`; with the guard dead the move went through — `SystemExit not raised`. |
| AC4 (exit codes) | Covered by the same two mutations above — both assert `SystemExit`/exit code 2 and both went red when the guarded behaviour was removed. | (see rows above) | — |

SC-01 is the full-suite run itself: all 60 pre-existing `RenameConcept`/`RenameWikilinks` tests pass unmodified (verified separately: `Ran 60 tests ... OK`), not just the new ones.

## Smoke
Real catalogue, non-destructive:
- Nonexistent source: `okf-cli.py --root ~/Obsidian/Knowledge-Catalogue rename nonexistent-bundle/nope.md nonexistent-bundle/still-nope.md` → `rename: source not found: /Users/erik/Obsidian/Knowledge-Catalogue/nonexistent-bundle/nope.md`, exit 2 — default verb still `"rename"` end-to-end through `cmd_rename`.
- Dry-run against a real concept file (`dev-wiki/sstds/sstd-...future-stubs.md` → `...-RENAMED-SMOKE.md`, no `--apply`) reproduced the full expected report shape (`would move`, `inbound`, `reindex`, the `rename (dry-run): ...` summary line) with nothing written to disk.
- `just check` against the real catalogue: `OK — 0 violations` (pre-existing WARNING lines only, none new).

## Deviations/ERRATA
- The two `die()` messages that used to interpolate the caller's raw `args.old`/`args.new` string ("source not found: {}", "destination exists (use --force to overwrite): {}") now interpolate the resolved `old_abs`/`new_abs` instead, because `perform_rename`'s fixed signature (`root, old_abs, new_abs, apply, force, verb`) per `docs/okf-archive-lifecycle/SPEC.md` §2 takes only resolved paths, not the raw CLI strings. Confirmed via smoke test above (absolute path shown instead of the relative one typed). No existing test asserts the raw-vs-resolved spelling of these two messages, so SC-01 and the full suite are unaffected; flagging it here because it is a real, if untested, text change relative to the pre-refactor byte stream. Not a scope deviation — the signature itself is spec-mandated (SPEC.md line 51), not a choice I made.
- No other deviation from the bean/design.

## Notes for T(n+1)
For `OKFT-16rg` (archive/`archive --restore` as a thin wrapper):
- Signature: `perform_rename(root, old_abs, new_abs, apply, force, verb="rename")`. `root` is the catalogue root; `old_abs`/`new_abs` must already be resolved, absolute, filesystem-cased-or-not paths (perform_rename canonicalises case itself via `canonical_case_path` — you do not need to pre-canonicalise case, only pre-resolve `~`/relative-to-cwd/relative-to-root into absolute form the way `cmd_rename` does: `os.path.abspath(p if os.path.isabs(p) else os.path.join(root, p))`).
- Return value: **`None`** on both the dry-run and the apply path (matches the pre-refactor `cmd_rename`, which never returned anything explicit — a bare `return` on the dry-run branch, falls off the end on apply). If `cmd_archive` needs the inbound-reference count for its own report line (SPEC.md §1: "Der Report nennt zusätzlich zur Move-Zeile die Zahl der aktiven Konzepte..."), call `plan_rename(root, old_abs, new_abs)` yourself before/beside calling `perform_rename` — do not expect `perform_rename` to hand you the plan.
- All output goes to `stdout` via `print(...)` (dry-run report, "moved (...)", "rewrote N inbound/outbound...", "reindexed N index file(s)...", "staged for commit..."). None of those lines are parameterised by `verb` — only the `die()` prefix is. If `archive` needs different wording anywhere else (e.g. not saying "staged for commit — run okf-cli.py check"), that has to be a post-call transformation or a separate `cmd_archive`-local print, not a `perform_rename` change, per SPEC.md §2 ("`verb` steuert ausschließlich die Wortwahl der Ausgabe... 'would move' bleibt 'would move'").
- On refusal, `perform_rename` calls `sys.exit(2)` directly (via its internal `die()`) — it does not raise/return an error object. A wrapper that wants to catch-and-translate has to intercept `SystemExit`, same as `cmd_rename` always implicitly relied on argparse/the CLI entry point to do.
- Guard ordering inside `perform_rename` (all before any filesystem mutation): `.md` extension → source exists → reserved source basename → reserved destination basename → empty/whitespace/control-char destination basename → identical source/destination → both paths under `root` → both paths inside a bundle → forbidden filename chars → destination-exists-without-force (samefile-aware) → [canonicalise case] → plan → ambiguity-without-force. `archive`'s own guards (SPEC.md §1: "archive --restore verweigert eine Quelle, die nicht unter _archive/ liegt") must run in `cmd_archive` *before* calling `perform_rename`, since they are not part of this shared core.
- Known pre-existing gap you inherit unchanged: there is no test in `RenameWikilinks`/`RenameConcept` asserting the exact text of the "source not found" or "destination exists" messages — only that *some* refusal with exit code 2 happens. If `archive`'s tests want to pin exact wording, write it fresh; don't assume it's covered.



## 2026-08-09 — PO decision D01: error-message wording is not protected

AC4 ("leave the observable behaviour of `rename` unchanged") does not extend to the literal wording of the `die()` messages. The refactor made two of them report the resolved absolute path (`rename: source not found: /abs/root/a/nope.md`) where the old inline body echoed the raw CLI string (`rename: source not found: a/nope.md`). No test pinned either form; the 60 existing rename tests — the operational definition of SC-01 — stay green.

The PO accepts the resolved path: for an agent consumer it is the more useful message, and restoring the old wording would cost an extra raw-string parameter that `SPEC.md` §2 does not know. Message wording under `perform_rename` is therefore explicitly out of AC4 scope; a future change to it is not a regression against this task.
