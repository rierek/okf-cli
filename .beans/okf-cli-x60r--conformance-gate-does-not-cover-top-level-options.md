---
# okf-cli-x60r
title: Conformance gate does not cover top-level options
status: completed
type: bug
priority: low
created_at: 2026-07-26T14:05:28Z
updated_at: 2026-07-26T17:02:24Z
parent: okf-cli-iksi
---

## Finding

Raised by `ce-specs-reviewer` while reviewing okf-cli-80nb (T05, conformance gate) on 2026-07-26. Non-blocking for that task: PLAN.md Task 5 did not ask for this coverage, and there is no live defect. Recorded so the epic's claim is not overstated.

## What the gate covers, and what it does not

`CommandHelpConformance.test_every_option_and_positional_has_help` iterates `subcommand_parsers(ap)` — the subparser choices dict — and never the top-level parser `ap` itself. An undocumented option on the top-level parser therefore passes the gate.

Verified by mutation during the review: `ap.add_argument("--root", help=...)` reduced to `ap.add_argument("--root")`, then `python3 -m unittest cli.test_okf_cli.CommandHelpConformance -v` reported `OK`. The mutation was reverted and `md5 cli/okf-cli.py` confirmed byte-identical (`9147b341e630be011f15ff8965b022e1`).

Confirmed as genuinely covered, by the same review: `store_true` actions, `nargs="?"` positionals, and whitespace-only help strings (both assertions call `.strip()`). No nested subparsers exist in this CLI.

## Why it matters

The epic okf-cli-5uog ships the claim that an undocumented command or option is unmergeable rather than merely noticeable. As shipped, that claim holds for the 21 subcommands and their arguments. It does not hold for the top-level parser. `--root` is documented today, so nothing is broken; the exposure is a future top-level option added without help text.

## Likely fix

Extend the assertion to iterate the top-level parser's own actions alongside the subcommand parsers. `parser_actions()` already exists and already filters `argparse._HelpAction`, so the change is expected to be small. Whether the top-level parser belongs in the same test method or its own is an open design point.

## Not scheduled

No leaf of okf-cli-5uog covers this. Left for the PO to prioritise.



### Requirement 1: The conformance gate covers the top-level parser too

**Objective:** As someone adding an option to this CLI, I want the suite to reject it if it carries no help text, so that the promise "an undocumented option cannot merge" holds for the whole surface and not only for the subcommands.

#### Acceptance Criteria

1. THE conformance gate SHALL assert that every option of the top-level parser carries non-empty help text, in addition to the options and positionals of the 21 subcommands.
2. THE gate SHALL ignore the auto-added -h/--help action on the top-level parser, as parser_actions already does for the subcommands.
3. WHEN a top-level option carries help text that is empty or whitespace-only, THE gate SHALL fail and name that option in its assertion message.
4. THE existing three assertions of CommandHelpConformance SHALL keep passing unchanged.

#### Success Criteria

- SC-01: Removing the help text from --root turns the suite red, and the assertion message names --root. The mutation is observed failing, then reverted, and the revert is confirmed byte-identical.
- SC-02: With the gate extended and no source mutation in place, the full suite reads exactly 19 failures and 2 errors plus the tests added by this leaf, all green.
- SC-03: The closing summary states whether the extension caught any option beyond --root that was already undocumented; if it did, each one is listed with the help text authored for it.

## Notes for the implementer

The reviewer's mutation transcript is in the finding above: stripping --root of its help left the gate green, which is the defect. parser_actions already filters argparse._HelpAction, so it is reusable as-is on the top-level parser object.

One open design point, deliberately not decided here: the top-level assertion can live inside the existing test_every_option_and_positional_has_help or in a method of its own. A separate method gives a clearer failure message; a single method keeps one list of offenders. Pick one and say why in the closing summary.

_Requirements: R-02_

## Recommended Skills

- superpowers:test-driven-development



## Summary

Extended `CommandHelpConformance` in `cli/test_okf_cli.py` with a new method,
`test_top_level_option_has_help`, that iterates `okf.parser_actions(self.ap)`
on the top-level parser object (the same helper the existing subcommand
assertion already uses). `parser_actions()` already filters
`argparse._HelpAction` — reusable as-is for that part (AC-2). Applying it to
the top-level parser also surfaces the `add_subparsers()` dispatch action
itself (`dest="cmd"`), which is not a user-facing option and whose own
subcommand summaries are already asserted by
`test_every_subcommand_has_a_summary`; the new test filters
`argparse._SubParsersAction` out locally (an `import argparse` was added to
the test file for this). No production code was changed — the fix is
entirely in `cli/test_okf_cli.py`, `--root` already carried adequate help
text.

**Design point (deliberately left open by the bean):** chose a separate
method (`test_top_level_option_has_help`) over folding into
`test_every_option_and_positional_has_help`. Reason: a separate method keeps
the existing method's assertion byte-for-byte untouched (cleanest possible
reading of AC-4 — "the existing three assertions... keep passing
unchanged"), and gives a failure message scoped to the top-level surface
(`['root']`) rather than mixed into a per-subcommand `"name dest"` list that
would need a synthetic name for the top-level parser.

## Test-Output

**RED (SC-01 mutation on `--root`'s help=):**

```
$ python3 -m unittest cli.test_okf_cli.CommandHelpConformance.test_top_level_option_has_help -v
test_top_level_option_has_help (cli.test_okf_cli.CommandHelpConformance.test_top_level_option_has_help)
R-02 (okf-cli-x60r): the subcommand-only gate above missed the ... FAIL

======================================================================
FAIL: test_top_level_option_has_help (cli.test_okf_cli.CommandHelpConformance.test_top_level_option_has_help)
R-02 (okf-cli-x60r): the subcommand-only gate above missed the
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/Users/erik/Obsidian/tools/okf-tools/cli/test_okf_cli.py", line 2722, in test_top_level_option_has_help
    self.assertEqual(missing, [])
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^
AssertionError: Lists differ: ['root'] != []

First list contains 1 additional elements.
First extra element 0:
'root'

- ['root']
+ []

----------------------------------------------------------------------
Ran 1 test in 0.003s

FAILED (failures=1)
```

Assertion message names the offending option (`'root'`), satisfying AC-3's
naming requirement. Mutation reverted; `md5 cli/okf-cli.py` before mutation
= `9147b341e630be011f15ff8965b022e1`, after revert = the same
(`9147b341e630be011f15ff8965b022e1`); `git status --short` showed
`cli/okf-cli.py` absent from the changed-files list both before and after.

**Supplementary AC-3 proof (whitespace-only help, not the mutation SC-01
names but explicitly required by AC-3's wording):** set
`ap.add_argument("--root", help="   ")`, reran the same test — identical
failure, `AssertionError: Lists differ: ['root'] != []`. Reverted; md5
confirmed byte-identical again (`9147b341e630be011f15ff8965b022e1`).

**GREEN, no mutation, new test alone:**

```
$ python3 -m unittest cli.test_okf_cli.CommandHelpConformance -v
test_every_command_is_grouped_and_dispatchable ... ok
test_every_option_and_positional_has_help ... ok
test_every_subcommand_has_a_summary ... ok
test_top_level_option_has_help ... ok

Ran 4 tests in 0.009s

OK
```

All three pre-existing assertions in the class pass unchanged (AC-4).

**Full-suite gate (SC-02):**

```
$ python3 -m unittest discover -s cli -p "test_*.py" 2>&1 | grep -E "^(Ran |OK|FAILED)"
Ran 282 tests in 18.130s
FAILED (failures=19, errors=2)
```

Baseline stated in the epic/task was `Ran 281 tests` / `FAILED
(failures=19, errors=2)`. Observed here is 282 tests (281 + this leaf's one
new test), still exactly 19 failures / 2 errors — i.e. the new test is
green and none of the pre-existing 19F/2E count moved. Reconciled: +1 test,
+0 failures, +0 errors.

## Smoke

`python3 cli/okf-cli.py --help` still prints normally (top-level parser
unaffected — no production code was touched):

```
$ python3 cli/okf-cli.py --help | head -3
usage: okf-cli.py [-h] [--root ROOT]
                   {build-index,check,find,...} ...
```

## Deviations/ERRATA

- **`argparse._SubParsersAction` filtering, not anticipated by the bean's
  "Notes for the implementer".** The bean stated `parser_actions()` is
  "reusable as-is" on the top-level parser. That is true only for the
  `-h/--help` exclusion (AC-2); applying it naively to the top-level parser
  also yields the `add_subparsers(dest="cmd", ...)` action, which has no
  `help=` and is not a per-option help gap — it is the subcommand
  dispatcher, and its own subcommands' documentation is already asserted
  elsewhere in the same test class. Filtering it out was necessary to avoid
  a permanent false-positive (`'cmd'` in every future run), so the new test
  excludes `isinstance(act, argparse._SubParsersAction)` locally, and
  `import argparse` was added to the test file for that check.
  `parser_actions()` itself in `cli/okf-cli.py` was left untouched — the
  scope boundary reserved production-code changes for authoring genuinely
  missing help text (SC-03), and this is not that; it stays a test-local
  filter.
- No change to `cli/okf-cli.py` was needed or made. `--root` already had
  adequate help text before this leaf.

## Notes for T(n+1)

- SC-03 answer: the extension did **not** catch any top-level option beyond
  `--root` that was undocumented. It did initially flag `cmd` (the
  subparsers dispatch action) as a false positive of naively reusing
  `parser_actions()` on the top-level parser; that is a structural artifact
  handled by the local `_SubParsersAction` filter above, not an
  undocumented option, and no help text was authored for it in
  `cli/okf-cli.py`.
- If a future top-level option is added, this gate will fail it exactly as
  it now fails `--root` under mutation.
