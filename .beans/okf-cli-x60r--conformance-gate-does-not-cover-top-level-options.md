---
# okf-cli-x60r
title: Conformance gate does not cover top-level options
status: todo
type: bug
priority: low
created_at: 2026-07-26T14:05:28Z
updated_at: 2026-07-26T16:43:39Z
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
