---
# okf-cli-x60r
title: Conformance gate does not cover top-level options
status: todo
type: bug
priority: low
created_at: 2026-07-26T14:05:28Z
updated_at: 2026-07-26T14:05:28Z
parent: okf-cli-wuiv
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
