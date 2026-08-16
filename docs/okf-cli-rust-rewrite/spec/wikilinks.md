---
type: Spec
title: "wikilinks — EARS-Requirements"
description: "Obsidian-Wikilinks je Scope aufgelöst und klassifiziert als resolved, ambiguous oder unresolved — reine Diagnose, keine Konformitätsprüfung."
tags:
  - okf-cli
  - ears
  - requirements
  - spec
---

# wikilinks — EARS-Requirements

`wikilinks` beantwortet für einen Scope, welche `[[…]]`-Vorkommen auf genau einen Concept zeigen, auf keinen oder auf mehr als einen. Wikilinks sind OKF v0.1 unbekannt (check.md, Abschnitt „Zuordnung zur Norm"): dieses Kommando ist reine Diagnose, keine Konformitätsprüfung. Ob ein `unresolved`- oder `ambiguous`-Vorkommen als Verstoß zählt, entscheidet allein `check`s eigene, an einen Schalter gebundene Regel (CHECK-7, CHECK-9) — dieses Kommando kennt keine Severity und lehnt nichts ab, es meldet nur den Zustand.

## Requirements

### Geltungsbereich

| ID | EARS-Requirement |
|----|------------------|
| WIKILINKS-1 | WHERE no target is given, THE okf binary SHALL scan every concept file in the store. |
| WIKILINKS-2 | WHERE a target names a bundle or a subdirectory, THE okf binary SHALL scan only the files below that target. |
| WIKILINKS-3 | WHERE the store is a bundle, THE okf binary SHALL scan the bundle root as the single scope. |
| WIKILINKS-4 | THE okf binary SHALL include reserved files in the scan. |
| WIKILINKS-5 | IF the target argument does not name a scannable directory in the store, THEN THE okf binary SHALL name the path it tried. |

### Klassifikation

| ID | EARS-Requirement |
|----|------------------|
| WIKILINKS-6 | WHERE no concept in the store carries the basename named by a wikilink occurrence's page part, THE okf binary SHALL classify the occurrence as unresolved. |
| WIKILINKS-7 | WHERE a wikilink occurrence's page part carries a path segment and no basename candidate's own path ends with that segment, THE okf binary SHALL classify the occurrence as unresolved. |
| WIKILINKS-8 | WHERE a wikilink occurrence's page part carries a path segment, THE okf binary SHALL narrow its basename candidates to those whose own path ends with that segment. |
| WIKILINKS-9 | WHERE exactly one candidate remains for a wikilink occurrence after narrowing, THE okf binary SHALL classify the occurrence as resolved. |
| WIKILINKS-10 | WHERE more than one candidate remains for a wikilink occurrence and exactly one of them lives in the same bundle as the file carrying the occurrence, THE okf binary SHALL classify the occurrence as resolved to that candidate. |
| WIKILINKS-11 | WHERE more than one candidate remains for a wikilink occurrence after every narrowing step, THE okf binary SHALL classify the occurrence as ambiguous. |
| WIKILINKS-12 | WHERE a wikilink occurrence's status is ambiguous, THE okf binary SHALL list every candidate concept for it. |

### Filter und Zählung

| ID | EARS-Requirement |
|----|------------------|
| WIKILINKS-13 | WHERE `--unresolved` is given, THE okf binary SHALL list only wikilink occurrences whose status is not resolved. |
| WIKILINKS-14 | THE okf binary SHALL total every wikilink occurrence in the scope by status, independent of any listing filter. |
| WIKILINKS-15 | THE okf binary SHALL state, for the scan, the total link count and the resolved, ambiguous and unresolved counts. |

### JSON

| ID | EARS-Requirement |
|----|------------------|
| WIKILINKS-16 | WHERE JSON output is requested, THE okf binary SHALL place every listed occurrence in `data`. |
| WIKILINKS-17 | WHERE JSON output is requested, THE okf binary SHALL place a count by status per bundle in `data`. |
| WIKILINKS-18 | WHERE JSON output is requested, THE okf binary SHALL place the unfiltered status totals in `data`. |
| WIKILINKS-19 | WHERE JSON output is requested, THE okf binary SHALL state in `data` whether the listed occurrences are filtered. |

## Grounding

Scope-Auflösung: `scan_wikilinks()` (`cli/okf-cli.py:3306-3318`) ruft `resolve_scopes()` (`cli/okf-cli.py:2940-2959`) für die Bundle-Liste und `iter_all_md()` (`cli/okf-cli.py:2582-2591`) je Bundle — reservierte Dateien eingeschlossen, `assets/` und `_`-präfigierte Staging-Verzeichnisse ausgeschlossen. Zielpfad-Validierung inklusive „not a directory"/„not a scannable bundle path" in `cmd_wikilinks()` (`cli/okf-cli.py:3370-3387`).

Vorkommen-Extraktion: `parse_wikilinks()` (`cli/okf-cli.py:3176-3205`) liefert je `[[…]]` einen Record mit `region` (frontmatter/body), `raw`, `page`, `alias`, `embed`-Flag und `span`; maskiert Codespans und Kommentare vorher über `wikilink_scan_text()`.

Klassifikationsalgorithmus: `resolve_wikilink()` (`cli/okf-cli.py:3268-3295`), drei Schritte in fester Reihenfolge — Basename-Match case-insensitiv, Pfadsegment-Einengung bei `[[dir/name]]`, Bundle-Tiebreak bei verbleibender Kollision. Kandidatentabelle aus `build_concept_basename_index()` (`cli/okf-cli.py:3208-3265`), die bei fehlendem aktivem Kandidaten auf einen `_archive`-Tier zurückfällt (`cli/okf-cli.py:3234-3262`).

Ausgabe: `cmd_wikilinks()` (`cli/okf-cli.py:3370-3414`) — Text-Summenzeile `cli/okf-cli.py:3413-3414`, `--unresolved`-Filter `cli/okf-cli.py:3392`, unfiltered Totals `cli/okf-cli.py:3389-3391`, JSON-Objekt `{links, by_bundle, totals, filtered}` `cli/okf-cli.py:3393-3404`. Parser-Registrierung: `cli/okf-cli.py:4324-4330`.

Die switch-gebundene Konformitätsregel, die auf denselben Resolver aufsetzt: `wikilink_checked_bundles()` (`cli/okf-cli.py:3321-3347`) und `check_wikilink_resolvable()` (`cli/okf-cli.py:3349-3367`) — Teil von check.md, nicht dieser Datei.

## Deltas gegenüber heute

| Delta | Deckung |
|---|---|
| Zielpfad-Validierung meldet Exit 2 statt Exit 1 | I09, COM-23 |
| Envelope statt eigenem JSON-Objekt | I04, COM-26 |
| Bundle-Modus als Scope | D06, WIKILINKS-3 |

## Anmerkungen

**WIKILINKS-6 bis WIKILINKS-11 sind sechs Zeilen, nicht eine.** Jede beschreibt einen eigenen Schritt der Auflösungsreihenfolge — Kein-Treffer, Pfad-Einengung ohne Treffer, Pfad-Einengung mit Kandidatenreduktion, Eindeutigkeit nach Einengung, Bundle-Tiebreak, verbleibende Kollision. Der Präzedenzfall COM-29/COM-30/COM-31 splittet aus demselben Grund: jeder Schritt ist unabhängig von den anderen verletzbar, eine zusammengefasste Zeile wäre nur zur Hälfte prüfbar.

**Keine der Klassifikationszeilen weicht vom heutigen Verhalten ab** — `resolve_wikilink()` bleibt unter R2 frei portierbar (andere Datenstruktur, gleiche Ergebnisse), aber die Fähigkeit selbst ist unverändert und braucht deshalb keine Finding-Deckung.

**WIKILINKS-14 schützt die Zählung vor dem Filter**, aus demselben Grund wie CHECK-10 die Regelmenge vor dem Profil schützt: ein Scan mit `--unresolved` und ein sauberer Scan dürften sich in den Totals nicht angleichen, sonst verschwindet die Information, die der Filter gerade ausblendet.

**Severity ist bewusst außen vor.** Ob ein `unresolved`- oder `ambiguous`-Fund einen Konformitäts-Scan rot macht, ist CHECK-6/CHECK-7/CHECK-9 (check.md), nicht diese Datei — `wikilinks` selbst kennt weder `--strict` noch Fehler-/Warn-Einstufung.

## Offene Fragen

**Ob das Kommando `wikilinks` selbst je einen Schalter trägt.** Heute läuft es unbedingt, unabhängig vom Profil — nur die zugehörige `check`-Regel ist an einen Schalter gebunden (CHECK-7). Ob T06 das Kommando künftig ebenfalls an einen Schalter bindet (etwa um es unter dem `okf`-Profil ganz abzuschalten), ist offen; diese Datei geht vom heutigen, unbedingten Verhalten aus.

**Ob der `_archive`-Fallback-Tier der Kandidatentabelle einen eigenen Schalter bekommt.** Er ist heute fest verdrahtet, nicht Teil von `wikilink_checked_bundles`. Kein Finding und keine Entscheidung adressiert ihn; T06-Kandidat.
