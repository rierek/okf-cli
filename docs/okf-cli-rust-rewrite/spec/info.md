---
type: Spec
title: "info — EARS-Requirements INFO-1..INFO-6"
description: "Print the store's schema docs — TYPES.md and PROPERTIES.md — in one call."
tags:
  - okf-cli
  - ears
  - requirements
  - spec
---

# info — EARS-Requirements INFO-1..INFO-6

`info` prints the store's schema docs — `TYPES.md` and `PROPERTIES.md` — in one call, so an agent loads the type vocabulary and the property spec without two separate `read` calls.

Die Querschnitts-Regeln gelten unverändert; hier steht nur, was `info` darüber hinaus leistet.

## Requirements

| ID | EARS-Requirement |
|----|------------------|
| INFO-1 | THE okf binary SHALL treat `TYPES.md` and `PROPERTIES.md` at the store root as the schema docs. |
| INFO-2 | WHERE a schema doc is present, THE okf binary SHALL print its full text. |
| INFO-3 | WHERE a schema doc is absent, THE okf binary SHALL announce the absence on stderr. |
| INFO-4 | WHERE a schema doc is absent, THE okf binary SHALL print nothing for that doc on stdout. |
| INFO-5 | WHERE JSON output is requested, THE okf binary SHALL emit `data` as an object mapping each present schema doc's file name to its full text. |
| INFO-6 | WHERE JSON output is requested and a schema doc is absent, THE okf binary SHALL omit that file's key from `data`. |

## Grounding

`cmd_info()` (`cli/okf-cli.py:1483-1493`) reads both docs from `root` unconditionally and prints a placeholder `"(missing: {})"` on stdout for an absent one (`cli/okf-cli.py:1491-1492`) — INFO-3/INFO-4 move that signal to stderr as a degradation instead of mixing it into the stdout payload. Parser registration: `cli/okf-cli.py:4223-4224`, a bare `_sub()` call with no `--json`.

`info` takes no target positional today and none is added here: it addresses the store root, not part of it, so COM-41 does not apply. Store-root resolution (COM-1..COM-6) already covers both store models — a bundle's root is its own schema-doc location, the same code path as a catalogue's root, so no bundle-specific requirement is needed here.

## Deltas gegenüber heute

| Delta | Deckung |
|---|---|
| Fehlendes Schema-Dokument wird als Degradation auf stderr angekündigt, nicht mehr im stdout-Payload vermischt | COM-19 |
| `--json` global mit Envelope statt reinem Text | I04 |
| Fehlendes Dokument fehlt im JSON-`data` statt Platzhaltertext | COM-19, COM-28 |

## Offene Fragen

Ob `info` künftig auf einen Bundle-Scope innerhalb eines Catalogues einschränkbar wird (z. B. bundle-lokale Schema-Docs), ist nicht entschieden — kein Finding/Decision deckt das. Heute existieren Schema-Docs nur auf Store-Root-Ebene, deshalb bleibt `info` hier ohne Positional.
