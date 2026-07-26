---
# okf-cli-6zhw
title: Self-documenting help across all okf-cli commands
status: todo
type: feature
priority: normal
created_at: 2026-07-26T12:22:54Z
updated_at: 2026-07-26T13:03:40Z
parent: okf-cli-5uog
blocked_by:
    - okf-cli-z0tt
    - okf-cli-lbh1
    - okf-cli-8rwy
    - okf-cli-80nb
---

## Origin

PO review 2026-07-26, raised alongside the US-07 reject. The PO's own framing:

> Rework sollte a) sauber feststellen, was die Fähigkeiten der CLI konkret sind und diese in --help ausgeben. Zudem schlage ich vor, dass 'okf-cli --help' und 'okf-cli <command> --help' selbstdokumentierend sind. Dazu entsprechendes System implementieren.

## Why this is a feature and not part of the bug

The concrete defects (missing `help=` on three subparsers, undocumented `--limit`, no per-command pointer, unsorted listing) are tracked in the sibling bug bean and can be fixed one line at a time. This bean is the durable part: the CLI has grown to 21 subcommands with a hand-maintained prose "Commands:" block in the module docstring *in addition to* argparse's generated listing. Two descriptions of the same surface, maintained by hand, drift apart — the current state is already an instance of that drift, since the prose block documents `find` in detail while the generated listing omits it entirely.

## The actual problem to solve

**One source of truth for "what can this CLI do", rendered into both help levels.** A new subcommand should be undocumentable-by-omission: if it ships without a description, that should be visible or impossible, not silent.

Open design questions for whoever picks this up, deliberately not decided here:

- Does the hand-written `Commands:` prose block in the docstring stay, or is it generated from the parser? Generating it removes the drift class entirely but loses the grouped, example-carrying prose that makes the block readable today.
- Should there be a conformance check (in the spirit of `okf-cli check`) that fails when a subparser lacks `help=` or an option lacks a description? That converts the whole class from "notice it in a review" to "cannot merge it".
- Alphabetical sorting vs. grouped-by-purpose. Alphabetical is what the PO asked for and is trivially predictable; grouping (navigation / search / tags / maintenance) is more useful at 21 commands. These pull in opposite directions and the PO should decide.

## Constraint

Standard library only, no install — the CLI's defining constraint (see the module docstring). Any solution using an external CLI framework is out.
