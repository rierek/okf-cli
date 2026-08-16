---
type: Spec
title: "read — EARS-Requirements READ-1..READ-7"
description: "Print one concept's full text — the last step of progressive disclosure after find, index and toc."
tags:
  - okf-cli
  - ears
  - requirements
  - spec
---

# read — EARS-Requirements READ-1..READ-7

`read` prints one concept's full text, addressed by `path`. It is the last step of progressive disclosure — after `find`, `index` and `toc` have narrowed the question to one page.

Die Querschnitts-Regeln gelten unverändert; hier steht nur, was `read` darüber hinaus leistet.

## Requirements

| ID | EARS-Requirement |
|----|------------------|
| READ-1 | THE okf binary SHALL accept a required positional `path` naming a concept to print. |
| READ-2 | WHERE `path` resolves to a concept file, THE okf binary SHALL print that file's full text. |
| READ-3 | WHERE `path` resolves to a directory holding an `index.md`, THE okf binary SHALL print that `index.md`'s full text. |
| READ-4 | WHERE the store is a bundle, THE okf binary SHALL resolve `path` as a concept-id below the bundle root, without a leading bundle segment. |
| READ-5 | IF `path` resolves to neither a concept file nor a directory below the store root, THEN THE okf binary SHALL exit 2. |
| READ-6 | IF `path` resolves to a directory without an `index.md`, THEN THE okf binary SHALL exit 1. |
| READ-7 | WHERE JSON output is requested, THE okf binary SHALL emit into `data` the resolved file's store-relative path and its full text. |

## Grounding

`cmd_read()` (`cli/okf-cli.py:1479-1480`) prints `resolve_concept(root, args.path)` verbatim. Resolution lives in `resolve_concept()` (`cli/okf-cli.py:1457-1476`): a direct file hit wins (1465-1466), a directory falls back to its `index.md` (1467-1471), a directory without one exits 1 with a "not found" message (1472-1474), and anything else exits 1 the same way (1475-1476) — today both failure branches share exit 1, which READ-5/READ-6 split. Parser registration: `cli/okf-cli.py:4257-4258`, `path` is a required positional with no `--json`.

## Deltas gegenüber heute

| Delta | Deckung |
|---|---|
| Exit 2 statt Exit 1, wenn `path` gar nicht auflöst | I09, COM-23 |
| Exit 1 bleibt für eine Verzeichnis-Adresse ohne `index.md` — eine Aussage über den Store, kein Tippfehler | COM-22 |
| Bundle-Modus: `path` ohne Bundle-Segment | D06 |
| `--json` global mit Envelope statt reinem Text | I04 |

## Offene Fragen

Ob `data` bei JSON-Ausgabe Frontmatter-Felder (`title`, `type`) separat vom Rohtext führt, ist nicht entschieden — kein Finding/Decision deckt es. Hier: `data` trägt nur `path` und `text`, die Frontmatter bleibt Teil von `text`.
