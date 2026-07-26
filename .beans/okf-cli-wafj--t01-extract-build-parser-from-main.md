---
# okf-cli-wafj
title: T01 Extract build_parser from main
status: scrapped
type: task
priority: normal
created_at: 2026-07-26T13:02:30Z
updated_at: 2026-07-26T13:23:29Z
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

- [ ] Write the failing `ParserExtraction` tests
- [ ] Run them, confirm the `AttributeError` names `subcommand_parsers`
- [ ] Add `COMMAND_DISPATCH`, `subcommand_parsers()`, `parser_actions()`
- [ ] Rename `main()` to `build_parser()`, `return ap`; write the new thin `main()`
- [ ] Prove byte-identical help via `git stash` + `diff` (SC-03)
- [ ] Full suite, then commit `refactor(cli): split build_parser out of main`

## Recommended Skills

- superpowers:test-driven-development



Scrapped 2026-07-26: orphaned duplicate of okf-cli-z0tt (same operationalization run, 14s earlier, no parent, no blocked_by). The canonical leaf under epic okf-cli-5uog is okf-cli-z0tt.
