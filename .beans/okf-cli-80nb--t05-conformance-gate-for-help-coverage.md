---
# okf-cli-80nb
title: T05 Conformance gate for help coverage
status: todo
type: task
priority: normal
created_at: 2026-07-26T13:03:25Z
updated_at: 2026-07-26T13:03:39Z
parent: okf-cli-5uog
blocked_by:
    - okf-cli-8rwy
---

Plan: `docs/okf-cli-capability-surface/PLAN.md` → **Task 5**.

The durable half of `okf-cli-6zhw`: after this, an undocumented command or option fails the suite instead of being noticed in a review — or not.

### Requirement 1: An undocumented command or option cannot be merged

**Objective:** As a reviewer, I want the help-coverage invariants asserted by the test suite, so that documentation gaps are caught by the machine rather than by attention.

#### Acceptance Criteria

1. THE test suite SHALL fail WHEN any subcommand has an empty `description`.
2. THE test suite SHALL fail WHEN any positional or option of any subcommand has empty help (the auto-added `-h` excluded).
3. THE test suite SHALL fail WHEN the set of registered commands differs from `COMMAND_GROUPS` or from `COMMAND_DISPATCH`.
4. THE eight arguments still lacking help SHALL be given it: `index bundle` `:2585`, `find query` `:2597`, `read path` `:2611`, `toc path` `:2618`, `visualize bundle` `:2622`, `refs --json` `:2627`, `rewrite-path old` `:2629`, `rewrite-path new` `:2630`.

#### Success Criteria

- SC-01: before the fix, `test_every_option_and_positional_has_help` fails with exactly `['find query', 'index bundle', 'read path', 'refs json', 'rewrite-path old', 'rewrite-path new', 'toc path', 'visualize bundle']` — commands in sorted order, actions in registration order. A different list means the plan's inventory was incomplete: stop and reconcile before changing anything.
- SC-02: after the fix, all three conformance tests green.
- SC-03: mutation self-test — drop `help=` from `read`'s `path` again, clear `__pycache__`, observe `AssertionError: ['read path'] != []`, revert, confirm `md5 cli/okf-cli.py` is unchanged before and after. A gate never seen failing is not evidence (LL-01, LL-07).
- SC-04: full suite at `Ran 275 tests`, exactly 19 failures / 2 errors.

**Files:** `cli/okf-cli.py` (the eight registrations) · `cli/test_okf_cli.py` (append class `CommandHelpConformance`)

## Steps

- [ ] Write the `CommandHelpConformance` tests
- [ ] Run them; check the failure list against SC-01 exactly
- [ ] Give the eight arguments the help text from the plan
- [ ] Re-run the gate, then the full suite
- [ ] Mutation self-test with md5 before/after (SC-03)
- [ ] Commit `feat(cli): conformance gate for help coverage`

## Recommended Skills

- superpowers:test-driven-development
