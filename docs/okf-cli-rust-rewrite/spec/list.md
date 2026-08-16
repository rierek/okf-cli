---
type: Spec
title: "list — EARS-Requirements LIST-1..LIST-10"
description: "List concepts filtered by frontmatter type and/or tag, scoped to a target — the catalogue browsed by field, not by hierarchy."
tags:
  - okf-cli
  - ears
  - requirements
  - spec
---

# list — EARS-Requirements LIST-1..LIST-10

`list` answers a different question than `index`: not "what does this bundle contain" but "which concepts carry this type, this tag, or both" — across one target or the whole store.

Die Querschnitts-Regeln gelten unverändert; hier steht nur, was `list` darüber hinaus leistet.

## Requirements

### Scope

| ID | EARS-Requirement |
|----|------------------|
| LIST-1 | WHERE a target names a bundle or a subdirectory, THE okf binary SHALL list only the concepts below that target. |
| LIST-2 | WHERE no target is given, THE okf binary SHALL list concepts across the whole store. |
| LIST-3 | WHERE the store is a bundle, THE okf binary SHALL treat the store root as the single scope. |

### Filter und Sortierung

| ID | EARS-Requirement |
|----|------------------|
| LIST-4 | IF neither `--type` nor `--tag` is given, THEN THE okf binary SHALL exit 2. |
| LIST-5 | WHERE `--type` is given, THE okf binary SHALL include only concepts whose frontmatter `type` equals that value. |
| LIST-6 | WHERE `--tag` is given, THE okf binary SHALL include only concepts whose tags contain that value. |
| LIST-7 | THE okf binary SHALL sort matching concepts by title, case-insensitively. |

### Ausgabe

| ID | EARS-Requirement |
|----|------------------|
| LIST-8 | WHERE JSON output is requested, THE okf binary SHALL emit each matching concept with its title, type, path and description. |
| LIST-9 | WHERE JSON output is not requested and no concept matches the filter, THE okf binary SHALL print a line stating that no concept matched. |
| LIST-10 | THE okf binary SHALL end plain-text output with a count of matching concepts. |

## Grounding

`cmd_list()` (`cli/okf-cli.py:582-614`) scans `resolve_scopes(root, args.scope)` (`cli/okf-cli.py:2940-2959`), filtering each concept's `meta_of()` type and `extract_tags()` result. The missing-filter guard sits at `cli/okf-cli.py:583-585`, printing to stderr and exiting 1 — LIST-4 keeps the guard, changes only the exit code. Sorting is `hits.sort(key=lambda x: x[0].casefold())` at `cli/okf-cli.py:597`. The JSON branch is `cli/okf-cli.py:598-603`, the empty-result line `cli/okf-cli.py:604-606`, the footer `cli/okf-cli.py:613-614`. Parser registration, including today's `--scope` flag that LIST-1/LIST-2 replace with a positional target: `cli/okf-cli.py:4225-4231`. MCP exposure exists today as `okf_list()` (`mcp/okf_mcp.py:142-144`), without a scope parameter.

## Deltas gegenüber heute

| Delta | Deckung |
|---|---|
| `--scope` wird zum optionalen Positional | I02, COM-41 |
| Exit 1 für den fehlenden Filter wird zu Exit 2 | I09, COM-23 |
| Envelope statt barem Array | I04, COM-26 |

## Anmerkungen

**LIST-4 wiederholt COM-23 absichtlich.** AUDIT A5 nennt „Nutzungsfehler (`list` ohne Filter)" namentlich als einen der drei Exit-1-Bedeutungen, die der Rewrite auflöst. Die Zeile macht den Vertrag genau an der Stelle prüfbar, an der der heutige Bug sitzt, statt ihn nur über die Querschnitts-Regel zu behaupten — derselbe Grund, aus dem CHECK-13/CHECK-14 COM-21/COM-22 wiederholen.

## Offene Fragen

Ob `list` ohne `--type`/`--tag` künftig alle Konzepte auflistet statt Exit 2 zu melden, ist nicht entschieden. Diese SPEC hält am heutigen Pflichtfeld-Verhalten fest — nur der Exit-Code ändert sich (COM-23). Eine Änderung der Pflicht selbst berührt A2/A4 neu und bräuchte ein eigenes Finding.
