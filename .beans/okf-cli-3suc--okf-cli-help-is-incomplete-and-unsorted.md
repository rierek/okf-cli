---
# okf-cli-3suc
title: okf-cli --help is incomplete and unsorted
status: todo
type: bug
priority: deferred
created_at: 2026-07-26T12:22:36Z
updated_at: 2026-08-03T19:37:56Z
parent: okf-cli-5uog
blocked_by:
    - okf-cli-lbh1
    - okf-cli-2ljd
    - okf-cli-8rwy
---

## Origin

PO review 2026-07-26, reject of US-07 (`--expand-tags`). The flag itself behaved as specified; the reject is about what `--help` tells a user about the CLI's capabilities.

**PO feedback, verbatim:**

> Mir sind ein paar Dinge aufgefallen, die ich als Beispiele nennen. Rework sollte a) sauber feststellen, was die Fähigkeiten der CLI konkret sind und diese in --helb ausgeben. Zudem schlage ich vor, dass 'okf-cli --help' und 'okf-cli <command> --help' selbstdokumentierend sind. Dazu entsprechendes System implementieren.
>
> 'okf-cli find --help':
> '--limit LIMIT' hat keine Beschreibung
>
> 'okf-cli --help'
> - scheint unvollständig, denn 'find' wird nicht aufgeführt.
> - Die Hilfestellung 'command --hlep' für Details je command wird nicht ausgegeben
> - ist nich alphabetisch sortiert

## Verified, all four points reproduce

Run against the shipped CLI on 2026-07-26:

1. **`--limit` carries no help text.** `python3 cli/okf-cli.py find --help` prints the bare `--limit LIMIT` with an empty description column, while every sibling option (`--type`, `--tag`, `--scope`, `--breakdown`, `--expand-tags`) has one.
2. **`find` is missing from the subcommand listing — and it is worse than reported.** `find` appears in the `{index,list,find,read,…}` choices tuple, but has no description line in the `positional arguments` block. Same for `index` and `read`. Cause: their `add_parser(...)` calls omit `help=`, and argparse only lists subparsers that carry one. The primary command of this entire feature is invisible in the command directory.
3. **No `<command> --help` pointer.** Neither the top-level help nor any subcommand help tells the reader that per-command detail exists.
4. **Not alphabetically sorted.** Registration order (`index, list, find, read, prime, info, toc, visualize, refs, rewrite-path, rename, build-index, reindex, log, tags, …`) is what the user sees.

## Additional finding, not raised by the PO

`--expand-tags`'s help text reads "experimental, off by default until measured". It **has** been measured (T11, bean `okf-cli-ftri`), the result was negative, and the flag stays off for a structural reason. The wording promises a pending decision that has in fact been made. Fix candidate: state that expansion was measured and does not currently pay, pointing at Q05.

## Scope note

This bean covers the concrete, verifiable gaps above. The systemic request — a capability inventory and a self-documenting help system — is tracked separately as a feature, because it is a design task rather than a defect.



## Resolved by epic okf-cli-5uog (2026-07-26) — awaiting PO acceptance

Left on `todo` deliberately: this is an acceptance record, and closing it is the PO's call at the review gate, not the implementing agent's.

Findings and the leaf that fixed each, all reviewed APPROVED by `ce-specs-reviewer` with independent re-verification:

| Finding | Fixed by | Commit |
|---|---|---|
| B01 — `find`, `index`, `read` invisible in the command directory | okf-cli-lbh1 (T02) | 4f6ac34 |
| B02 — `--limit` renders with an empty description | okf-cli-2ljd (T03) | ea18873 |
| B03 — no pointer to `<command> --help` | okf-cli-8rwy (T04) | ecd2058 |
| B04 — listing follows registration order, not alphabetical | okf-cli-8rwy (T04) | ecd2058 |
| B05 — `--expand-tags` promises a measurement that already happened | okf-cli-2ljd (T03) | ea18873 |

What to look at: `python3 cli/okf-cli.py --help` now lists all 21 commands alphabetically, each with a summary, followed by a purpose-grouped overview rendered from the same registrations, followed by the `<command> --help` pointer.
