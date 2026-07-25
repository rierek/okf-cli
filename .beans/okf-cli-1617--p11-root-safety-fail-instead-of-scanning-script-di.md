---
# okf-cli-1617
title: 'P11 — Root-safety: fail instead of scanning script dir'
status: completed
type: task
priority: normal
created_at: 2026-07-25T18:13:10Z
updated_at: 2026-07-25T19:35:02Z
parent: okf-cli-5hg4
blocked_by:
    - okf-cli-5qmn
---

## Objective (User Story)
As a user, I want okf-cli to refuse to run against an accidental root so that it never silently scans its own script directory as if it were a catalogue.

## EARS Acceptance
- WHEN no `--root` is passed AND no catalogue is auto-detectable, THE CLI SHALL hard-fail with a clear message naming `--root` (never silently scan the script dir).
- WHEN `--root` is passed, THE behavior SHALL be unchanged.
- Auto-detect: if cwd (or ancestor) contains catalogue markers (SPEC.md + TYPES.md at root, or a .okf.toml), use it; else fail.

## Success Criteria
- SC-001: no-root + no-catalogue -> SystemExit, message mentions `--root`.
- SC-002: `--root` path behavior unchanged (existing tests green).
- SC-003: marker auto-detect picks up a valid catalogue from cwd.

## Affected code
- `cli/okf-cli.py:72-73` rewrite `catalogue_root`; `:1981-1984` fail on None.
- Test: `cli/test_okf_cli.py`
Full steps: PLAN.md Task 11.
Commit: `fix(cli): fail on missing root instead of scanning script dir`


## Summary

Rewrote `catalogue_root(explicit)` in `cli/okf-cli.py`: an explicit `--root`
still returns `abspath(explicit)` unchanged (even if nonexistent — `main()`
validates that separately). Absent `--root`, it now walks cwd upward looking
for a catalogue marker (`.okf.toml`, or `SPEC.md` + `TYPES.md` together) and
returns that ancestor dir; if no marker is found anywhere up to the
filesystem root, it returns `None` instead of silently falling back to the
script's own directory. `main()` now hard-fails with
`ERROR: no catalogue found in cwd or its ancestors; pass --root <path>`
when `catalogue_root` returns `None`, distinct from the pre-existing
"root not found: <path>" message for an explicit-but-nonexistent `--root`
(f26791c, untouched). Updated the `--root` argparse help text to match.

## Test-Output

Command: `python3 -m unittest cli.test_okf_cli cli.test_okf_mcp cli.test_eval_fixtures cli.test_eval_runner`
- BASELINE (pre-existing, before this task): 19 failures / 2 errors / 126 tests
- AFTER (this task): 19 failures / 2 errors / 133 tests (7 new `RootSafety` tests, all green)
- Same 19F/2E identity confirmed by name-diff against the pre-existing failure list — zero new failures/errors, none in the new `RootSafety` class.
- No existing test pinned the old script-dir-default behavior (searched for `dirname(__file__)`, `script dir`, `catalogue_root(` in test file — none found), so no alt-test needed changing.

RED proof (before implementation, `RootSafety` class only):
`python3 -m unittest cli.test_okf_cli.RootSafety -v` -> 6 of 7 fail
(`test_explicit_root_returns_abspath_unchanged` passed trivially since abspath
was already correct for the explicit case; the other 6 failed against the
old always-return-scriptdir `catalogue_root`).

GREEN after fix: `python3 -m unittest cli.test_okf_cli.RootSafety -v` -> 7/7 ok.

## Smoke

1. No `--root`, no env override, run from `cli/` (script dir) — must hard-fail:
   `cd cli && python3 okf-cli.py find "test"`
   -> `ERROR: no catalogue found in cwd or its ancestors; pass --root <path>`
   (exit 1). Confirmed it did NOT scan `cli/` as a catalogue.

2. With explicit `--root` (note: `--root` is a top-level flag, must precede
   the subcommand — pre-existing argparse structure, unchanged):
   `python3 okf-cli.py --root ~/Obsidian/Knowledge-Catalogue find "test"`
   -> normal ranked `find` output (score/title/type/path/description blocks),
   exit 0. Unchanged behavior confirmed (SC-002).

3. MCP path (`mcp/okf_mcp.py`) checked, not modified: every `okf_*` tool
   function declares `root: str` as a REQUIRED positional param (no default)
   and `build_argv()` always prepends `["--root", root, ...]` to the
   okf-cli.py subprocess call. The auto-detect/hard-fail branch in
   `catalogue_root` is therefore never reached via the MCP path — MCP always
   supplies an explicit root. No P10 (`mcp/okf_mcp.py`) impact, no fix needed
   there.

4. Eval chain checked, not modified: `cli/eval/runner.py` (`--root
   required=True`) and `cli/eval/fixtures.py` both pass `--root` explicitly
   to okf-cli.py subprocess calls. `cli/eval/results/baseline-f0714b2.json`
   confirmed untouched (`git diff --stat` empty). Eval tests included in the
   full-suite run above stayed green/unaffected.

## Deviations/ERRATA

- Commit subject in the bean/plan recipe (`fix(cli): fail on missing root
  instead of scanning script dir`, 61 chars) exceeded the repo's 50-char
  title hard cap (git-enforce hook E1). Used `fix(cli): hard-fail missing
  root, no script scan` (48 chars) instead — same intent, shorter wording.
- Line numbers in the bean/PLAN (`okf-cli.py:72-73`, `:1981-1984`) had
  drifted from the current file state (actual: `catalogue_root` at line 73,
  root-validation block at ~2026-2030) due to intervening commits on the
  branch history (B01/prime changes). Edited by content-match, not literal
  line number — no behavioral deviation.
- No alt-tests needed changing: grepped `test_okf_cli.py` for any test
  pinning the old script-dir-default behavior (`dirname(__file__)`, "script
  dir", `catalogue_root(`) — none exist. All 19F/2E pre-existing failures are
  unrelated (crosslink/rename/refs suites), confirmed by name-diff.

## Notes for T(n+1)

- MCP (`mcp/okf_mcp.py`, owned by parallel P10) is unaffected by this change
  — verified above, no action needed there.
- The `--root` argparse help text now reads "auto-detect from cwd; hard-fails
  if none found" (was: "default: script directory") — cosmetic, matches new
  behavior.
