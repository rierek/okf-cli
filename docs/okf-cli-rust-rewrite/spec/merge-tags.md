---
type: Spec
title: "merge-tags — EARS-Requirements MERGE-TAGS-1..MERGE-TAGS-10"
description: "Merge one or more source tags into a destination tag across concept frontmatter within a scope — dry-run by default, the preview ends with the exact re-run invocation."
tags:
  - okf-cli
  - ears
  - requirements
  - spec
---

# merge-tags — EARS-Requirements MERGE-TAGS-1..MERGE-TAGS-10

`merge-tags` rewrites the `tags:` field of every concept whose tag list carries one of the named source tags, replacing each occurrence with a single destination tag — the mechanism a catalogue maintainer reaches for after `tags` (Kommando) surfaces near-duplicate spellings such as `workflow`/`workflows`.

Die Querschnitts-Regeln gelten unverändert; hier steht nur, was `merge-tags` darüber hinaus leistet.

## Requirements

### Umfang des Rewrites

| ID | EARS-Requirement |
|----|------------------|
| MERGE-TAGS-1 | WHERE no scope is given, THE okf binary SHALL rewrite tags across every concept file in the store. |
| MERGE-TAGS-2 | WHERE a scope names a bundle or a subdirectory, THE okf binary SHALL rewrite tags only in the files below that scope. |
| MERGE-TAGS-3 | WHERE the store is a bundle, THE okf binary SHALL treat the bundle root as the single scope. |
| MERGE-TAGS-4 | THE okf binary SHALL exclude reserved files from the scope of the rewrite. |

### Merge-Mechanik

| ID | EARS-Requirement |
|----|------------------|
| MERGE-TAGS-5 | WHERE a concept's tags carry one of the named source tags, THE okf binary SHALL replace every occurrence of that source tag with the destination tag named by `--into`. |
| MERGE-TAGS-6 | WHERE the replacement leaves a duplicate tag in the resulting list, THE okf binary SHALL collapse it to a single occurrence. |
| MERGE-TAGS-7 | THE okf binary SHALL preserve the position of every tag the merge does not touch. |
| MERGE-TAGS-8 | IF a concept's tags field is not in inline or block-list form, THEN THE okf binary SHALL exclude that concept from the rewrite and SHALL name it as unparseable in the report. |

### Vorschau und Schreiben

| ID | EARS-Requirement |
|----|------------------|
| MERGE-TAGS-9 | WHERE the okf binary reports intended writes for a merge, THE okf binary SHALL end that report with the exact invocation that performs them, carrying the source tags, the destination tag and the scope given. |
| MERGE-TAGS-10 | THE okf binary SHALL name in the report the count of files it touches and the count of files it excludes as unparseable. |

## Grounding

`cmd_merge_tags()` lebt heute in `cli/okf-cli.py:227-258`.

Scope-Auflösung: `resolve_scopes()` (`cli/okf-cli.py:2940-2959`) — der Bundle-Modus aus MERGE-TAGS-3 existiert dort nicht, derselbe Fund wie in `check.md`s Grounding zu CHECK-3.

Reserved-Datei-Ausschluss: `iter_concepts()` (`cli/okf-cli.py:81-90`) überspringt jeden Dateinamen aus `RESERVED` (`cli/okf-cli.py:31`); der Ausschluss ist nicht optional und nicht profilabhängig.

Merge- und Dedup-Mechanik: `cli/okf-cli.py:236-241` baut `new_tags` unter Beibehaltung der Ursprungsreihenfolge und verwirft Duplikate über ein `seen`-Set. Die eigentliche Feldrewrite-Logik, die die inline/block-Form erkennt und erhält, sitzt in `rewrite_tags_in_frontmatter()` (`cli/okf-cli.py:179-201`); liefert sie `None`, landet die Datei in `unparseable` (`cli/okf-cli.py:246-247`) und wird als solche gemeldet (`cli/okf-cli.py:255-256`).

Vorschau/Schreiben-Zweig und die heutige Zusammenfassungszeile: `cli/okf-cli.py:250-258`. Der Präzedenzfall für die fehlende Zeile ist `cmd_rename`s Dry-run-Block, der mit `"Re-run with --apply."` endet (`cli/okf-cli.py:3951-3954`) — `merge-tags`s Zusammenfassung (`cli/okf-cli.py:257-258`) hat kein Äquivalent.

Argument-Parser heute: `cli/okf-cli.py:4237-4243` — `--scope`-Flag (wird zum MERGE-TAGS-Positional, COM-41), `--into` (required), `--apply`.

## Deltas gegenüber heute

| Delta | Deckung |
|---|---|
| Vorschau endet mit der exakten Re-run-Invocation (heute: Zusammenfassungszeile ohne Folgebefehl) | I03, I07, COM-31 |
| Scope als optionales Positional statt `--scope`-Flag | I02, COM-41 |
| Bundle als zusätzliches Store-Modell (heute: nur Catalogue) | D06 |

## Anmerkungen

**MERGE-TAGS-9 wiederholt COM-31 mit Inhaltsangabe absichtlich.** `_common.md` schreibt bereits vor, dass jede Vorschau mit der exakten Invocation endet; diese Datei ist genau eine der drei, die das heute nicht tun (Auftrag der Aufgabe, Finding I03). Die Zeile hier legt zusätzlich fest, *was* die Invocation trägt — Quelltags, Zieltag, Scope — analog zur Begründung, mit der `check.md` CHECK-13/CHECK-14 gegen COM-21/COM-22 dupliziert: der Vertrag wird an der Stelle prüfbar, an der er heute fehlt.

**MERGE-TAGS-4 steht bewusst neben CHECK-4.** `check` bezieht reservierte Dateien in den Scan ein, weil es ihre §6/§7-Struktur prüft; `merge-tags` schließt sie aus, weil es ihr `tags:`-Feld schreibt und reservierte Dateien keinen Tag-Bestand im Sinne dieses Kommandos führen. Beides ist heutiges Verhalten, kein Delta.

## Offene Fragen

Ob das Ausschließen einer unparseable Datei als „adverse finding about the store" unter COM-22 zählt (Exit 1) — heute exitiert `merge-tags` in keinem Fall ungleich 0. Kein Finding deckt eine Entscheidung; kein Exit-Code-Requirement hierfür in dieser Datei.

Ob die Vorschau (ohne `--apply`) `--json`-fähig ist — COM-25 bindet `--json` an „jedes lesende Kommando", `merge-tags` ist ein schreibendes Kommando. Keine Deckung für eine Anforderung in die eine oder andere Richtung; offen für T02/T06.
