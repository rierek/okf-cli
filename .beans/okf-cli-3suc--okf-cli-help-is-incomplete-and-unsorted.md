---
# okf-cli-3suc
title: okf-cli --help is incomplete and unsorted
status: todo
type: bug
priority: normal
created_at: 2026-07-26T12:22:36Z
updated_at: 2026-07-26T12:22:36Z
parent: okf-cli-5uog
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
