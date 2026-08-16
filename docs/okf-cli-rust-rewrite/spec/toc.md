---
type: Spec
title: "toc — EARS-Requirements TOC-1..TOC-13"
description: "Print a concept's headings before its body — the cheapest way to decide whether a page is worth reading in full."
tags:
  - okf-cli
  - ears
  - requirements
  - spec
---

# toc — EARS-Requirements TOC-1..TOC-13

`toc` prints a concept's headings before its body, the cheapest way to decide whether a page is worth reading in full or to name the section actually needed.

Die Querschnitts-Regeln gelten unverändert; hier steht nur, was `toc` darüber hinaus leistet.

## Requirements

### Auflösung von `path`

| ID | EARS-Requirement |
|----|------------------|
| TOC-1 | THE okf binary SHALL accept a required positional `path` naming a concept to list headings for. |
| TOC-2 | WHERE `path` resolves to a concept file, THE okf binary SHALL list that file's headings. |
| TOC-3 | WHERE `path` resolves to a directory holding an `index.md`, THE okf binary SHALL list that `index.md`'s headings. |
| TOC-4 | WHERE the store is a bundle, THE okf binary SHALL resolve `path` as a concept-id below the bundle root, without a leading bundle segment. |
| TOC-5 | IF `path` resolves to neither a concept file nor a directory below the store root, THEN THE okf binary SHALL exit 2. |
| TOC-6 | IF `path` resolves to a directory without an `index.md`, THEN THE okf binary SHALL exit 1. |

### Ausgabe

| ID | EARS-Requirement |
|----|------------------|
| TOC-7 | THE okf binary SHALL print the concept's title and its `type` frontmatter value as the first line. |
| TOC-8 | THE okf binary SHALL default `--level` to 2. |
| TOC-9 | WHERE `--level` is 0, THE okf binary SHALL list every heading as an indented tree reflecting heading depth. |
| TOC-10 | WHERE `--level` names a level above 0, THE okf binary SHALL list only headings at that exact level. |
| TOC-11 | THE okf binary SHALL exclude headings that sit inside fenced code blocks. |
| TOC-12 | WHERE no heading matches the requested level, THE okf binary SHALL state that none was found. |
| TOC-13 | WHERE JSON output is requested, THE okf binary SHALL emit into `data` the concept's title, its `type` and its headings as level/text pairs. |

## Grounding

`cmd_toc()` (`cli/okf-cli.py:1676-1690`) resolves `path` through the same `resolve_concept()` (`cli/okf-cli.py:1457-1476`) as `read` — today both failure branches there share exit 1, which TOC-5/TOC-6 split the same way READ-5/READ-6 do. The title line is built from frontmatter (1678-1680), heading extraction is `iter_headings()` (`cli/okf-cli.py:1496-1507`), which skips fenced code (1500-1504). Level filtering and the tree/flat branches sit in `cmd_toc()` (1683-1688), the "no heading" fallback at 1689-1690. Parser registration: `cli/okf-cli.py:4315-4319`, `--level` defaults to `2`, no `--json`.

## Deltas gegenüber heute

| Delta | Deckung |
|---|---|
| Exit 2 statt Exit 1, wenn `path` gar nicht auflöst | I09, COM-23 |
| Exit 1 bleibt für eine Verzeichnis-Adresse ohne `index.md` — eine Aussage über den Store, kein Tippfehler | COM-22 |
| Bundle-Modus: `path` ohne Bundle-Segment | D06 |
| `--json` global mit Envelope statt reinem Text | I04 |

## Offene Fragen

Ob `--level` eine Kurzform bekommt, ist nicht entschieden — COM-35 nennt dafür keine. Hier: keine Kurzform.
