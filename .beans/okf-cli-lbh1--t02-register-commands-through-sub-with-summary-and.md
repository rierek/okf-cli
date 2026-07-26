---
# okf-cli-lbh1
title: T02 Register commands through _sub with summary and group
status: todo
type: task
priority: normal
created_at: 2026-07-26T13:02:44Z
updated_at: 2026-07-26T13:03:39Z
parent: okf-cli-5uog
blocked_by:
    - okf-cli-z0tt
---

Plan: `docs/okf-cli-capability-surface/PLAN.md` → **Task 2**, including **Step 4b**. Follow it step by step.

This is where the reported defect dies structurally: a command cannot be registered without a summary, because the helper takes it as a required positional.

### Requirement 1: Every command is documented at the place it is registered

**Objective:** As someone reading `okf-cli --help`, I want every command to carry a description, so that the CLI's primary command is not invisible in its own directory.

#### Acceptance Criteria

1. THE CLI SHALL register every subcommand through `_sub(sub, name, group, summary, **kwargs)`, which passes the summary as both `help=` and `description=` and records the group in `COMMAND_GROUPS`.
2. WHEN a group is not in `_GROUP_ORDER` THE helper SHALL raise `ValueError`.
3. THE commands `find`, `index` and `read` SHALL each carry a summary (they carry none today — `cli/okf-cli.py:2596`, `:2584`, `:2610`).
4. THE `find` subparser SHALL carry an epilog explaining both score scales, rendered verbatim.

### Requirement 2: The scoring explanation survives the docstring's deletion, corrected

**Objective:** As a user reading `find --help`, I want to know what `score: a/b` means on the arm that actually produced my result.

#### Acceptance Criteria

1. THE `find` epilog SHALL state that `a/100` covers the FTS5/BM25 lexical arm (relative to the run's own top hit) and the semantic arm (`round(100 * cosine)`), and that `a/(6 * n)` is the substring fallback.
2. THE epilog SHALL NOT repeat the docstring's claim that `6 * number of terms` is the maximum for every result — that has been false since the FTS arm shipped (`cli/okf-cli.py:912-928`, `:1140-1152`).

#### Success Criteria

- SC-01: `parsers[name].description` is non-empty for `find`, `index` and `read`.
- SC-02: `set(COMMAND_GROUPS) == set(subcommand_parsers(build_parser()))` — all 21, exactly once each, per the group table in Task 2 Step 4.
- SC-03: `parsers["find"].format_help()` contains `100`, `6 * number of terms` and `provenance`.
- SC-04: `read`'s summary appears in its own `--help` output (the summary reaches both levels).
- SC-05: full suite at `Ran 265 tests`, exactly 19 failures / 2 errors.
- SC-06: `okf-cli --help` is run by hand afterwards and its `positional arguments` block pasted into `## Smoke` — this is the artefact the PO rejected US-07 over.

**Files:** `cli/okf-cli.py` (new `_GROUP_ORDER`, `COMMAND_GROUPS`, `_sub()`, `_FIND_EPILOG` above `build_parser()`; all 21 registrations converted) · `cli/test_okf_cli.py` (append class `CommandDirectory`)

## Steps

- [ ] Write the failing `CommandDirectory` tests (4 methods)
- [ ] Run them, confirm `find has no summary` and the `COMMAND_GROUPS` AttributeError
- [ ] Add `_GROUP_ORDER`, `COMMAND_GROUPS`, `_sub()`
- [ ] Convert all 21 registrations; give `find`/`index`/`read` the summaries from the plan
- [ ] Add `_FIND_EPILOG` and register `find` with it plus `RawDescriptionHelpFormatter` (Step 4b)
- [ ] Full suite; look at `--help` with your own eyes; commit `fix(cli): every subcommand carries a summary`

## Recommended Skills

- superpowers:test-driven-development
