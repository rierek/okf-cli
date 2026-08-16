---
type: Spec
title: "normalize-tags — EARS-Requirements NORMALIZE-TAGS-1..NORMALIZE-TAGS-8"
description: "Convert inline `tags: [a, b]` frontmatter fields to YAML block-list form within a scope — a local catalogue convention, not an OKF requirement. Dry-run by default, the preview ends with the exact re-run invocation."
tags:
  - okf-cli
  - ears
  - requirements
  - spec
---

# normalize-tags — EARS-Requirements NORMALIZE-TAGS-1..NORMALIZE-TAGS-8

`normalize-tags` rewrites every concept's non-empty inline `tags: [a, b]` field into YAML block-list form, harmonising the one spelling that drifts from this catalogue's own convention — both forms stay valid OKF, so this command carries no §9 conformance weight.

Die Querschnitts-Regeln gelten unverändert; hier steht nur, was `normalize-tags` darüber hinaus leistet.

## Requirements

### Umfang des Rewrites

| ID | EARS-Requirement |
|----|------------------|
| NORMALIZE-TAGS-1 | WHERE no scope is given, THE okf binary SHALL normalize tags across every concept file in the store. |
| NORMALIZE-TAGS-2 | WHERE a scope names a bundle or a subdirectory, THE okf binary SHALL normalize tags only in the files below that scope. |
| NORMALIZE-TAGS-3 | WHERE the store is a bundle, THE okf binary SHALL treat the bundle root as the single scope. |
| NORMALIZE-TAGS-4 | THE okf binary SHALL exclude reserved files from the scope of the rewrite. |

### Normalisierungs-Mechanik

| ID | EARS-Requirement |
|----|------------------|
| NORMALIZE-TAGS-5 | WHERE a concept's tags field is a non-empty inline list, THE okf binary SHALL rewrite that field into YAML block-list form. |
| NORMALIZE-TAGS-6 | IF a concept's tags field is already in block-list form, carries no tags field, or is an empty inline list, THEN THE okf binary SHALL leave that concept unmodified. |

### Vorschau und Schreiben

| ID | EARS-Requirement |
|----|------------------|
| NORMALIZE-TAGS-7 | WHERE the okf binary reports intended writes for a normalization, THE okf binary SHALL end that report with the exact invocation that performs them, carrying the scope given. |
| NORMALIZE-TAGS-8 | THE okf binary SHALL name in the report the count of files it touches. |

## Grounding

`cmd_normalize_tags()` lebt heute in `cli/okf-cli.py:318-333`.

Scope-Auflösung: `resolve_scopes()` (`cli/okf-cli.py:2940-2959`) — derselbe fehlende Bundle-Modus wie bei `merge-tags` und `check.md`s CHECK-3.

Reserved-Datei-Ausschluss: `iter_concepts()` (`cli/okf-cli.py:81-90`) gegen `RESERVED` (`cli/okf-cli.py:31`).

Normalisierungs-Mechanik: `normalize_tags_in_file()` (`cli/okf-cli.py:296-315`) liefert `None` — und damit „unmodified" — in vier Fällen laut eigenem Docstring (`cli/okf-cli.py:299-301`): keine Frontmatter, kein `tags`-Feld, bereits Block-Liste, oder eine leere Inline-Liste (`[]`). Anders als bei `merge-tags`/`remove-tags` unterscheidet der Code diese vier Fälle nicht — keiner davon wird als „unparseable" gemeldet, sie sind schlicht nicht Teil des Rewrites (`cli/okf-cli.py:322-325`).

Vorschau/Schreiben-Zweig und die heutige Zusammenfassungszeile: `cli/okf-cli.py:330-333` — ohne Folgebefehl, derselbe Befund wie bei `merge-tags`/`remove-tags` gegen `cmd_rename`s Vorbild (`cli/okf-cli.py:3951-3954`).

Argument-Parser heute: `cli/okf-cli.py:4244-4248` — `--scope`-Flag (wird zum NORMALIZE-TAGS-Positional, COM-41), `--apply`. Kein Tags- oder `--into`-Argument: `normalize-tags` nimmt keine Zielwerte, nur einen Scope.

## Deltas gegenüber heute

| Delta | Deckung |
|---|---|
| Vorschau endet mit der exakten Re-run-Invocation (heute: Zusammenfassungszeile ohne Folgebefehl) | I03, I07, COM-31 |
| Scope als optionales Positional statt `--scope`-Flag | I02, COM-41 |
| Bundle als zusätzliches Store-Modell (heute: nur Catalogue) | D06 |

## Anmerkungen

**NORMALIZE-TAGS-7 wiederholt COM-31 mit Inhaltsangabe absichtlich**, aus demselben Grund wie in `merge-tags.md` und `remove-tags.md`: diese Datei ist eine der drei, die die Aufgabe explizit als heute nicht-konform benennt. Die Inhaltsangabe fällt hier schmaler aus als bei den beiden anderen — nur der Scope, weil `normalize-tags` keine Tag-Argumente kennt, deren Wiederholung sonst redundant zur Scope-Angabe wäre.

**NORMALIZE-TAGS-6 führt keine eigene „unparseable"-Kategorie ein**, obwohl der Python-Code vier unterscheidbare Gründe fürs Auslassen kennt (`cli/okf-cli.py:299-301`). Eine feinere Meldung — etwa eine Unterscheidung zwischen „bereits normalisiert" und „kein Tags-Feld" — wäre eine neue Anforderung ohne Deckung durch ein Finding; sie steht stattdessen unter Offene Fragen.

**NORMALIZE-TAGS-4 steht bewusst neben CHECK-4**, aus demselben Grund wie bei `merge-tags` und `remove-tags`: `check` bezieht reservierte Dateien in den Scan ein, `normalize-tags` schließt sie aus, weil sie keinen Tag-Bestand im Sinne dieses Kommandos führen. Heutiges Verhalten, kein Delta.

## Offene Fragen

Ob die vier Auslass-Gründe aus NORMALIZE-TAGS-6 (bereits Block-Liste / kein Feld / leere Liste / keine Frontmatter) im Report unterschieden werden — heute nicht, und kein Finding verlangt es. Offen für T02/T06.

Ob die Vorschau (ohne `--apply`) `--json`-fähig ist — COM-25 bindet `--json` an „jedes lesende Kommando", `normalize-tags` ist ein schreibendes Kommando. Keine Deckung für eine Anforderung in die eine oder andere Richtung; offen für T02/T06.
