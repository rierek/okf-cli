---
# okf-cli-z0tt
title: T01 Extract build_parser from main
status: completed
type: task
priority: normal
created_at: 2026-07-26T13:02:44Z
updated_at: 2026-07-26T13:28:56Z
parent: okf-cli-5uog
---

Plan: `docs/okf-cli-capability-surface/PLAN.md` → **Task 1**. Follow it step by step; it carries the literal code, commands and expected output.

Pure refactor. Nothing else in this epic can be tested until the parser can be built without executing a command.

### Requirement 1: The command surface is inspectable without running a command

**Objective:** As a test author, I want to build and render the parser in isolation, so that help output becomes assertable instead of only observable by hand.

#### Acceptance Criteria

1. THE CLI SHALL expose `build_parser()` returning the fully configured `argparse.ArgumentParser`, with `main()` reduced to parse + dispatch.
2. THE CLI SHALL expose `COMMAND_DISPATCH` as a module-level mapping of command name to handler, replacing the dict inlined in `main()`.
3. THE CLI SHALL expose `subcommand_parsers(ap)` returning `{name: parser}` and `parser_actions(parser)` returning every action except the auto-added `-h`.
4. THE rendered help output SHALL be byte-identical to before this change, for the top level and for at least one subcommand.

#### Success Criteria

- SC-01: `set(subcommand_parsers(build_parser())) == set(COMMAND_DISPATCH)` — 21 commands, no orphan on either side.
- SC-02: `parser_actions(parsers["read"])` contains `path` and not `help`.
- SC-03: `diff` of `okf-cli.py --help` and `okf-cli.py find --help` before vs. after prints nothing. Quote the literal `diff` invocations and their result in `## Test-Output` — a "behaviour-preserving" claim without the command that established it does not count (LL-13).
- SC-04: full suite at `Ran 261 tests`, exactly 19 failures / 2 errors.

**Files:** `cli/okf-cli.py:2578-2712` · `cli/test_okf_cli.py` (append class `ParserExtraction`)

## Steps

- [x] Write the failing `ParserExtraction` tests
- [x] Run them, confirm the `AttributeError` names `subcommand_parsers`
- [x] Add `COMMAND_DISPATCH`, `subcommand_parsers()`, `parser_actions()`
- [x] Rename `main()` to `build_parser()`, `return ap`; write the new thin `main()`
- [x] Prove byte-identical help via `git stash` + `diff` (SC-03)
- [x] Full suite, then commit `refactor(cli): split build_parser out of main` (67f7b3e)

## Recommended Skills

- superpowers:test-driven-development



## Summary

Pure refactor per PLAN.md Task 1. `main()` (`cli/okf-cli.py:2578-2716` before
the change) split into `build_parser()` (all `ArgumentParser`/subparser
registration, ending `return ap`) and a thin `main()` (`build_parser().parse_args()`
+ root resolution + `COMMAND_DISPATCH[args.cmd](root, args)`). The inline
20-key dispatch dict literal that used to live at the bottom of `main()` is
now the module-level `COMMAND_DISPATCH` (same keys, same handler functions,
no reordering). Added `subcommand_parsers(ap)` (walks `ap._actions` for the
`_SubParsersAction`, returns its `.choices` dict) and `parser_actions(parser)`
(every action except the auto-added `-h/--help`) so the parser can be
inspected without executing a command. No behaviour, help text, or command
registration changed — only the location of the code that builds them.

**Files:** `cli/okf-cli.py` (new `COMMAND_DISPATCH`/`subcommand_parsers`/
`parser_actions` inserted above the renamed `build_parser()`, ~line 2578;
`main()` rewritten to 6 lines beneath it) · `cli/test_okf_cli.py` (appended
class `ParserExtraction`, 2 tests, at end of file).

## Test-Output

RED (`subcommand_parsers` did not exist yet):

```
$ rm -rf cli/__pycache__ && python3 -m unittest cli.test_okf_cli.ParserExtraction -v
ERROR: test_every_registered_command_is_dispatchable ... AttributeError: module 'okf_cli' has no attribute 'subcommand_parsers'
ERROR: test_parser_actions_skips_the_auto_help_action ... AttributeError: module 'okf_cli' has no attribute 'subcommand_parsers'
Ran 2 tests in 0.001s
FAILED (errors=2)
```

GREEN after Steps 3-4:

```
$ rm -rf cli/__pycache__ && python3 -m unittest cli.test_okf_cli.ParserExtraction -v
test_every_registered_command_is_dispatchable ... ok
test_parser_actions_skips_the_auto_help_action ... ok
Ran 2 tests in 0.004s
OK
```

**SC-03 — byte-identical help, before vs. after (LL-13: the command, not the
conclusion)**, run on the working tree with the refactor applied, stashing it
out for the "before" capture and popping it back for "after":

```
$ git stash && python3 cli/okf-cli.py --help > /tmp/help_before.txt 2>&1 && \
  python3 cli/okf-cli.py find --help > /tmp/find_before.txt 2>&1 && git stash pop
Saved working directory and index state WIP on main: 596d07f chore(beans): scrap orphaned duplicate leaves
On branch main
Changes not staged for commit: ... (working tree restored, `git status --short` confirmed
the same 3 modified files as before the stash, nothing lost)
Dropped refs/stash@{0} ...

$ python3 cli/okf-cli.py --help > /tmp/help_after.txt 2>&1
$ python3 cli/okf-cli.py find --help > /tmp/find_after.txt 2>&1
$ diff /tmp/help_before.txt /tmp/help_after.txt && diff /tmp/find_before.txt /tmp/find_after.txt && echo "IDENTICAL"
IDENTICAL
```

Both `diff` invocations exited 0 (no output) before the `echo` ran, for both
the top-level `--help` and `find --help`.

**SC-04 — full suite:**

```
$ python3 -m unittest discover -s cli -p "test_*.py" 2>&1 | grep -E "^(Ran |OK|FAILED)"
Ran 261 tests in 18.602s
FAILED (failures=19, errors=2)
```

261 = 259 baseline + 2 new `ParserExtraction` tests. `failures=19, errors=2`
unchanged from the pre-task baseline (measured live before starting:
`Ran 259 tests` / `FAILED (failures=19, errors=2)`) — no new failure, none
silenced.

Commit: `refactor(cli): split build_parser out of main` (`67f7b3e`).

## Deviations

None. Implemented exactly per PLAN.md Task 1 Steps 1-7, no scope beyond
`cli/okf-cli.py:2578-2716` and the one new test class.
