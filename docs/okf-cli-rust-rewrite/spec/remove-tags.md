---
type: Spec
title: "remove-tags — EARS-Requirements REMOVE-TAGS-1..REMOVE-TAGS-10"
description: "Remove one or more tags from concept frontmatter within a scope, without a merge target — dry-run by default, the preview ends with the exact re-run invocation."
tags:
  - okf-cli
  - ears
  - requirements
  - spec
---

# remove-tags — EARS-Requirements REMOVE-TAGS-1..REMOVE-TAGS-10

`remove-tags` strips one or more named tags from every concept whose tag list carries them, symmetric to `merge-tags` but with no destination — the mechanism a catalogue maintainer reaches for after `tags` (Kommando) or `check` surfaces a stale or singleton tag.

Die Querschnitts-Regeln gelten unverändert; hier steht nur, was `remove-tags` darüber hinaus leistet.

## Requirements

### Umfang des Rewrites

| ID | EARS-Requirement |
|----|------------------|
| REMOVE-TAGS-1 | WHERE no scope is given, THE okf binary SHALL rewrite tags across every concept file in the store. |
| REMOVE-TAGS-2 | WHERE a scope names a bundle or a subdirectory, THE okf binary SHALL rewrite tags only in the files below that scope. |
| REMOVE-TAGS-3 | WHERE the store is a bundle, THE okf binary SHALL treat the bundle root as the single scope. |
| REMOVE-TAGS-4 | THE okf binary SHALL exclude reserved files from the scope of the rewrite. |

### Entfernungs-Mechanik

| ID | EARS-Requirement |
|----|------------------|
| REMOVE-TAGS-5 | WHERE a concept's tags carry one of the named target tags, THE okf binary SHALL remove every occurrence of that target tag from the tag list. |
| REMOVE-TAGS-6 | WHERE the removal empties a concept's tag list, THE okf binary SHALL strip the `tags:` field from the frontmatter instead of leaving an empty list. |
| REMOVE-TAGS-7 | THE okf binary SHALL preserve the position of every tag the removal does not touch. |
| REMOVE-TAGS-8 | IF a concept's tags field is not in inline or block-list form, THEN THE okf binary SHALL exclude that concept from the rewrite and SHALL name it as unparseable in the report. |

### Vorschau und Schreiben

| ID | EARS-Requirement |
|----|------------------|
| REMOVE-TAGS-9 | WHERE the okf binary reports intended writes for a removal, THE okf binary SHALL end that report with the exact invocation that performs them, carrying the target tags and the scope given. |
| REMOVE-TAGS-10 | THE okf binary SHALL name in the report the count of files it touches, the count of files it empties of tags, and the count of files it excludes as unparseable. |

## Grounding

`cmd_remove_tags()` lebt heute in `cli/okf-cli.py:261-293`, im eigenen Docstring als „symmetric to merge-tags" markiert (`cli/okf-cli.py:262-263`).

Scope-Auflösung: `resolve_scopes()` (`cli/okf-cli.py:2940-2959`) — derselbe fehlende Bundle-Modus wie bei `merge-tags` und `check.md`s CHECK-3.

Reserved-Datei-Ausschluss: `iter_concepts()` (`cli/okf-cli.py:81-90`) gegen `RESERVED` (`cli/okf-cli.py:31`).

Entfernungs- und Dedup-Mechanik: `cli/okf-cli.py:273-280` baut `new_tags` als Restliste unter Beibehaltung der Ursprungsreihenfolge; ist sie leer, ersetzt `remove_tags_field()` (`cli/okf-cli.py:204-224`) `rewrite_tags_in_frontmatter()` und die Datei landet zusätzlich in `emptied` (`cli/okf-cli.py:279-280`). Liefert keine der beiden Funktionen ein Ergebnis, landet die Datei in `unparseable` (`cli/okf-cli.py:281-283`) und wird als solche gemeldet (`cli/okf-cli.py:290-291`).

Vorschau/Schreiben-Zweig und die heutige Zusammenfassungszeile: `cli/okf-cli.py:287-293` — ohne Folgebefehl, derselbe Befund wie bei `merge-tags` gegen `cmd_rename`s Vorbild (`cli/okf-cli.py:3951-3954`).

Argument-Parser heute: `cli/okf-cli.py:4284-4289` — `--scope`-Flag (wird zum REMOVE-TAGS-Positional, COM-41), `--apply`. Kein `--into`-Äquivalent: `remove-tags` kennt kein Merge-Ziel.

## Deltas gegenüber heute

| Delta | Deckung |
|---|---|
| Vorschau endet mit der exakten Re-run-Invocation (heute: Zusammenfassungszeile ohne Folgebefehl) | I03, I07, COM-31 |
| Scope als optionales Positional statt `--scope`-Flag | I02, COM-41 |
| Bundle als zusätzliches Store-Modell (heute: nur Catalogue) | D06 |

## Anmerkungen

**REMOVE-TAGS-9 wiederholt COM-31 mit Inhaltsangabe absichtlich**, aus demselben Grund wie MERGE-TAGS-9 in `merge-tags.md`: dies ist eine der drei Dateien, die die Aufgabe explizit als heute nicht-konform benennt, und die Zusatzangabe (Zieltags, Scope) macht den Vertrag genau dort prüfbar, wo er heute fehlt — analog zu CHECK-13/CHECK-14 gegen COM-21/COM-22.

**REMOVE-TAGS-6 hat keine Entsprechung bei `merge-tags`**, weil ein Merge nie die gesamte Tagliste eines Concepts leert — der Zieltag ersetzt jedes Vorkommen, statt es zu streichen. Die Zeile ist `remove-tags`-eigen, kein wiederverwendetes COM- oder MERGE-TAGS-Requirement.

**REMOVE-TAGS-4 steht bewusst neben CHECK-4**, aus demselben Grund wie MERGE-TAGS-4: `check` bezieht reservierte Dateien in den Scan ein, `remove-tags` schließt sie aus, weil sie keinen Tag-Bestand im Sinne dieses Kommandos führen. Heutiges Verhalten, kein Delta.

## Offene Fragen

Ob eine geleerte Tagliste (REMOVE-TAGS-6) oder eine ausgeschlossene unparseable Datei als „adverse finding about the store" unter COM-22 zählt (Exit 1) — heute exitiert `remove-tags` in keinem Fall ungleich 0. Kein Finding deckt eine Entscheidung; kein Exit-Code-Requirement hierfür in dieser Datei.

Ob die Vorschau (ohne `--apply`) `--json`-fähig ist — COM-25 bindet `--json` an „jedes lesende Kommando", `remove-tags` ist ein schreibendes Kommando. Keine Deckung für eine Anforderung in die eine oder andere Richtung; offen für T02/T06.
