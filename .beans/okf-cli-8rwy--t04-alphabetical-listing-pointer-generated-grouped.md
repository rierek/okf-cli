---
# okf-cli-8rwy
title: T04 Alphabetical listing, pointer, generated grouped overview
status: todo
type: task
priority: normal
created_at: 2026-07-26T13:03:25Z
updated_at: 2026-07-26T13:03:39Z
parent: okf-cli-5uog
blocked_by:
    - okf-cli-2ljd
---

Plan: `docs/okf-cli-capability-surface/PLAN.md` → **Task 4**.

Both help layouts come from the same registrations, so neither can go stale. The hand-written block that already drifted is deleted.

### Requirement 1: The command directory is predictable and self-pointing

**Objective:** As someone looking up a known command, I want the listing alphabetical and a pointer to per-command detail, so that I neither scan registration order nor guess that `<command> --help` exists.

#### Acceptance Criteria

1. THE subcommands SHALL be registered in alphabetical order, since registration order is what argparse prints.
2. THE top-level help SHALL contain the literal string `<command> --help`.

### Requirement 2: The purpose-grouped overview is rendered, not maintained

**Objective:** As a newcomer to a 21-command CLI, I want the commands grouped by purpose, without that view being a second thing to keep in sync.

#### Acceptance Criteria

1. THE CLI SHALL render the epilog from the registered parsers via `render_command_overview(sub)`, grouping by `COMMAND_GROUPS` in `_GROUP_ORDER` sequence and wrapping its own lines (the top-level parser uses `RawDescriptionHelpFormatter`, `cli/okf-cli.py:2579-2580`).
2. THE module docstring SHALL no longer list commands by hand; the `Commands:` block at `cli/okf-cli.py:8-45` is replaced by a three-line pointer.
3. THE docstring's blank line `:46`, the `Run from the catalogue root, or pass --root <path>.` line `:47` and the terminator `"""` `:48` SHALL survive unchanged — the replacement range ends at `:45`.

#### Success Criteria

- SC-01: `list(subcommand_parsers(build_parser())) == sorted(...)`.
- SC-02: top-level help contains `<command> --help` and `commands by purpose:` and one heading per group in `_GROUP_ORDER`.
- SC-03: every name in `COMMAND_GROUPS` appears in the overview section of the help text.
- SC-04: `okf.__doc__` contains neither `okf-cli.py find` nor `okf-cli.py merge-tags`.
- SC-05: full suite at `Ran 272 tests`, exactly 19 failures / 2 errors.
- SC-06: `python3 cli/okf-cli.py --help` is run by hand and its full output pasted into `## Smoke`.

**Files:** `cli/okf-cli.py:8-45` (docstring), `:49-62` (add `import textwrap`), `build_parser()` (order + `ap.epilog`), new `render_command_overview()` · `cli/test_okf_cli.py` (append classes `CommandDirectoryOrder`, `GroupedOverview`)

## Steps

- [ ] Write the failing `CommandDirectoryOrder` + `GroupedOverview` tests
- [ ] Run them, confirm the order mismatch and the missing pointer/overview
- [ ] Add `import textwrap`; add `render_command_overview()`
- [ ] Sort the 21 registrations alphabetically, moving each command's own `add_argument` calls with it; set `ap.epilog`
- [ ] Replace the docstring block `:8-45` only — check `:46-48` survived
- [ ] Full suite; read the help as a user; commit `feat(cli): generated command directory in help`

## Recommended Skills

- superpowers:test-driven-development
