---
# OKFT-80nb
title: T05 Conformance gate for help coverage
status: completed
type: task
priority: normal
created_at: 2026-07-26T13:03:25Z
updated_at: 2026-07-26T14:01:07Z
parent: OKFT-5uog
blocked_by:
    - OKFT-8rwy
---

Plan: `docs/okf-cli-capability-surface/PLAN.md` → **Task 5**.

The durable half of `OKFT-6zhw`: after this, an undocumented command or option fails the suite instead of being noticed in a review — or not.

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

- [x] Write the `CommandHelpConformance` tests
- [x] Run them; check the failure list against SC-01 exactly
- [x] Give the eight arguments the help text from the plan
- [x] Re-run the gate, then the full suite
- [x] Mutation self-test with md5 before/after (SC-03)
- [x] Commit `feat(cli): conformance gate for help coverage` (`7dade90`)

## Recommended Skills

- superpowers:test-driven-development



## Prelude from the T01-T04 reviews (2026-07-26, non-blocking)

1. **The plan can contradict itself. When it does, adapt the text to the test, never the test to the test-passing shape.** T03 hit this and resolved it correctly. Your Task 5 is the inverse risk: it ships a GATE, so the temptation is to make the gate agree with the code. Do not. The plan's `CommandHelpConformance` is authored text — ship it unchanged, then fix what it catches.
2. **Step 2 is a load-bearing measurement, not a formality.** The plan predicts the gate catches exactly eight entries and prints the literal expected list, in a specific order (commands sorted, actions in registration order). If your observed list differs from the plan's by even one entry, stop and reconcile against finding B06 before changing any code — a longer list means the plan's inventory was incomplete and the extra arguments need help text authored here. Report the observed list verbatim either way. Note that Task 4 reordered the registrations alphabetically, which affects the order commands appear in that list but not the actions within a command.
3. **Step 5 (mutation self-test) is the point of the whole task.** A gate that has not been seen failing is not evidence (LL-01, LL-07). Drop the `help=` from one argument, watch the gate fail with the exact assertion, revert, re-run green, and record the md5 before and after to prove the revert was byte-identical.
4. The 50-character subject cap applies to EVERY commit, the bean-close meta commit included. No `commit-msg` hook exists in `.git/hooks/`; nothing catches an overrun.
5. For any before/after proof, snapshot with `git show <rev>:<path> > /tmp/<x>.py` and diff. Do not use `git stash`.


## Summary

`CommandHelpConformance` (3 tests) appended to `cli/test_okf_cli.py`, unchanged from the plan's Step 1 text. Step 2's RED run caught exactly the eight entries SC-01 predicts, verbatim and in the predicted order — no reconciliation against B06 was needed. The eight arguments named in Requirement 4 (`index bundle`, `find query`, `read path`, `toc path`, `visualize bundle`, `refs --json`, `rewrite-path old`, `rewrite-path new`) each gained the literal `help=` text from the plan's Step 3.

## Test-Output

Step 2 — RED, observed list matches SC-01 exactly:

```
$ rm -rf cli/__pycache__ && python3 -m unittest cli.test_okf_cli.CommandHelpConformance -v
test_every_command_is_grouped_and_dispatchable ... ok
test_every_option_and_positional_has_help ... FAIL
test_every_subcommand_has_a_summary ... ok

AssertionError: Lists differ: ['find query', 'index bundle', 'read path', 'refs json', 'rewrite-path old', 'rewrite-path new', 'toc path', 'visualize bundle'] != []
FAILED (failures=1)
```

Step 4 — GREEN after adding the eight `help=` strings:

```
$ rm -rf cli/__pycache__ && python3 -m unittest cli.test_okf_cli.CommandHelpConformance -v
test_every_command_is_grouped_and_dispatchable ... ok
test_every_option_and_positional_has_help ... ok
test_every_subcommand_has_a_summary ... ok

Ran 3 tests in 0.007s
OK
```

SC-04 — full suite:

```
$ python3 -m unittest discover -s cli -p "test_*.py" 2>&1 | grep -E "^(Ran |OK|FAILED)"
Ran 275 tests in 18.101s
FAILED (failures=19, errors=2)
```

275 = 272 baseline (post-T04) + 3 new `CommandHelpConformance` tests. `failures=19, errors=2` unchanged — no new failure, none silenced.

SC-03 — mutation self-test (dropped `help=` from `read`'s `path`, `pr.add_argument("path")`):

```
$ md5 cli/okf-cli.py
MD5 (cli/okf-cli.py) = 9147b341e630be011f15ff8965b022e1

[edit: drop help= from read path]

$ md5 cli/okf-cli.py
MD5 (cli/okf-cli.py) = 012b40b7e93dec8d62a70ff5798274c7

$ rm -rf cli/__pycache__ && python3 -m unittest cli.test_okf_cli.CommandHelpConformance -v
test_every_option_and_positional_has_help ... FAIL
AssertionError: Lists differ: ['read path'] != []
FAILED (failures=1)

[revert]

$ md5 cli/okf-cli.py
MD5 (cli/okf-cli.py) = 9147b341e630be011f15ff8965b022e1

$ rm -rf cli/__pycache__ && python3 -m unittest cli.test_okf_cli.CommandHelpConformance -v
Ran 3 tests in 0.006s
OK

$ git status --short
 M cli/okf-cli.py
 M cli/test_okf_cli.py
```

md5 before and after the mutation-and-revert cycle is identical (`9147b341e630be011f15ff8965b022e1`); `git status --short` after the revert shows only the two files carrying the actual fix (registration help strings + the new test class), nothing left over from the mutation.

Commit: `feat(cli): conformance gate for help coverage` (`7dade90`, 45 characters).

## Deviations

None. Implemented `CommandHelpConformance` byte-for-byte from the plan's Step 1, the eight `help=` strings byte-for-byte from Step 3, and executed Steps 2, 4, 5 exactly as specified. No scope beyond the eight registrations named in Requirement 4 and the one new test class.
