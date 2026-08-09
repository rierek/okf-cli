---
type: Spec
title: "check — EARS-Requirements CHECK-1..CHECK-20"
description: "Konformitäts-Scan über den Store: die drei OKF-§9-Klauseln in jedem Profil, jede darüber hinausgehende Regel an einen Profil-Schalter gebunden."
tags:
  - okf-cli
  - ears
  - requirements
  - spec
---

# check — EARS-Requirements CHECK-1..CHECK-20

`check` beantwortet eine Frage: hält der Store die Regeln, die für ihn gelten. Welche Regeln das sind, entscheidet das aktive Profil (COM-10 bis COM-17) — mit einer Untergrenze, die kein Profil unterschreitet.

Diese Untergrenze ist keine Konvention dieses Projekts, sondern OKF v0.1 §9. Die Norm nennt dort **drei** Konformitäts-Klauseln und untersagt Konsumenten im selben Abschnitt ausdrücklich, ein Bundle wegen unbekannter `type`-Werte, zusätzlicher Frontmatter-Keys, kaputter Cross-Links oder fehlender `index.md` abzulehnen. Alles, was `check` heute darüber hinaus prüft, ist deshalb per Definition eine Erweiterung und gehört an einen Schalter.

Die Querschnitts-Regeln gelten unverändert; hier steht nur, was `check` darüber hinaus leistet.

## Requirements

### Umfang des Scans

| ID | EARS-Requirement |
|----|------------------|
| CHECK-1 | WHERE no target is given, THE okf binary SHALL scan every concept file in the store. |
| CHECK-2 | WHERE a target names a bundle or a subdirectory, THE okf binary SHALL scan only the files below that target. |
| CHECK-3 | WHERE the store is a bundle, THE okf binary SHALL scan the bundle root as the single scope. |
| CHECK-4 | THE okf binary SHALL include reserved files in the scan. |

### Regelmenge und Profil

| ID | EARS-Requirement |
|----|------------------|
| CHECK-5 | THE okf binary SHALL evaluate the three conformance clauses of OKF v0.1 §9 under every profile. |
| CHECK-6 | THE okf binary SHALL report a violation of an OKF v0.1 §9 clause at error severity. |
| CHECK-7 | WHERE a rule reaches beyond the three clauses of OKF v0.1 §9, THE okf binary SHALL bind that rule to a named switch. |
| CHECK-8 | WHERE the active profile leaves a rule disabled, THE okf binary SHALL evaluate no file against that rule. |
| CHECK-9 | WHERE the `okf` profile is active, THE okf binary SHALL evaluate the three clauses of OKF v0.1 §9 and no further rule. |
| CHECK-10 | THE okf binary SHALL report every rule it evaluated and every rule it left disabled. |

### Severity und Exit

| ID | EARS-Requirement |
|----|------------------|
| CHECK-11 | THE okf binary SHALL assign each violation either error severity or warning severity. |
| CHECK-12 | WHERE `--strict` is given, THE okf binary SHALL raise every warning to error severity. |
| CHECK-13 | WHERE the scan produces at least one error-severity violation, THE okf binary SHALL exit 1. |
| CHECK-14 | WHERE the scan produces no error-severity violation, THE okf binary SHALL exit 0. |

### Vokabular-Quellen

| ID | EARS-Requirement |
|----|------------------|
| CHECK-15 | WHERE a rule reads a vocabulary registry and that registry is absent, THE okf binary SHALL evaluate no file against that rule and SHALL announce the skip on stderr. |
| CHECK-16 | WHERE `--types` names a path, THE okf binary SHALL read the type vocabulary from that path. |
| CHECK-17 | WHERE `.okf.toml` names a type-vocabulary source and `--types` is absent, THE okf binary SHALL read the type vocabulary from that source. |

### Ausgabe

| ID | EARS-Requirement |
|----|------------------|
| CHECK-18 | THE okf binary SHALL name in every reported violation the rule, the file and the reason. |
| CHECK-19 | WHERE JSON output is requested, THE okf binary SHALL emit errors and warnings as two separate collections. |
| CHECK-20 | WHERE the scan produces no violation, THE okf binary SHALL state that the scanned scope holds. |

## Grounding

Der Scan lebt heute in `run_checks()` (`cli/okf-cli.py:3394`) und `cmd_check()` (`cli/okf-cli.py:3444`).

Die Regelmenge ist eine feste Liste in `per_file_checks` (`cli/okf-cli.py:3414-3427`) mit fest zugeordneter Severity, ergänzt um zwei Bundle-Regeln: `check_asset_placement()` (`cli/okf-cli.py:2797`, error) und `check_entry_file_description()` (`cli/okf-cli.py:2811`, warning).

`--strict` faltet Warnungen in Fehler (`cli/okf-cli.py:3452`). Der Exit-Code steht in `cli/okf-cli.py:3467`. Die Target-Validierung existiert bereits (`cli/okf-cli.py:3446`) und ist der Präzedenzfall, aus dem B01 und B02 abgeleitet wurden.

Vokabular-Quellen: `load_types()` (`cli/okf-cli.py:2501`) und `load_tags()` (`cli/okf-cli.py:2511`). Beide liefern `None`, sobald die Datei fehlt, und der zugehörige Check wird dadurch wirkungslos — heute ohne jede Meldung. CHECK-15 macht daraus eine angekündigte Degradation.

Reservierte Dateien sind Teil des Scans: `iter_all_md()` (`cli/okf-cli.py:2582`).

Der einzige heute existierende Schalter ist `wikilink_checked_bundles` (`cli/okf-cli.py:3298`), bundle-granular über `.okf.toml`. Er ist der Präzedenzfall für CHECK-7.

## Zuordnung zur Norm

Die heutigen dreizehn Regeln, gemessen an OKF v0.1 §9:

| Regel | §9 | Bemerkung |
|---|---|---|
| `frontmatter-parseable` | Klausel 1 | Norm |
| `type-nonempty` | Klausel 2 | Norm |
| `reserved-no-type` | Klausel 3 | Norm, prüft die §6/§7-Struktur reservierter Dateien |
| `type-registered` | — | §9 untersagt Ablehnung wegen unbekannter `type`-Werte; zentrale Registry widerspricht §1 |
| `tag-registered` | — | TAGS.md ist der Norm unbekannt |
| `english-keys` | — | §9 untersagt Ablehnung wegen zusätzlicher Keys |
| `crosslink-format` | — | §9 untersagt Ablehnung wegen kaputter Links; §5.1 verlangt zudem bundle-relative Form, dieser Catalogue schreibt catalogue-root-absolut |
| `wikilink-resolvable` | — | Wikilinks sind der Norm unbekannt |
| `tags-block-form` | — | im eigenen Docstring als lokale Konvention markiert |
| `xml-like-tags` | — | Obsidian-Rendering |
| `filename-chars` | — | Dateisystem- und Obsidian-Anforderung |
| `asset-placement` | — | der Norm unbekannt |
| `entry-file-description` | — | §9 untersagt Ablehnung wegen fehlender `index.md` |

Drei von dreizehn sind Norm. Die übrigen zehn sind der Kandidatensatz für T06.

## Deltas gegenüber heute

| Delta | Deckung |
|---|---|
| Regelmenge profilabhängig statt fest verdrahtet | D05, CHECK-7 bis CHECK-9 |
| `okf`-Profil prüft nur §9 — das Portabilitäts-Gate aus T08 | D05, CHECK-9 |
| Fehlende Registry wird angekündigt statt still übergangen | CHECK-15 |
| Scan meldet, welche Regeln liefen und welche nicht | CHECK-10 |
| Bundle-Modus als Scope | D06, CHECK-3 |
| Envelope statt eigenem JSON-Objekt | I04, COM-26 |
| Exit 2 für Nutzungsfehler statt Exit 1 wie heute | I09, COM-23 |

## Anmerkungen

**CHECK-10 ist neu und trägt das Profil-Konzept.** Sobald die Regelmenge konfigurierbar ist, ist ein „OK — 0 violations" ohne Angabe der geprüften Regeln nicht mehr interpretierbar: ein sauberer Scan und ein Scan mit zehn abgeschalteten Regeln sehen identisch aus. Die Zeile ist die Bedingung dafür, dass D05 nicht in ein stilles Abschalten von Prüfungen mündet.

**CHECK-13 und CHECK-14 wiederholen COM-21 und COM-22 absichtlich.** `check` ist das Kommando, dessen Exit-Code am häufigsten in Hooks und CI ausgewertet wird — `okf-meta-wiki/extensions/conformance-scan-before-commit-gate.md` beschreibt genau so ein Gate. Die beiden Zeilen machen den Vertrag an der Stelle prüfbar, an der er benutzt wird, statt ihn nur querschnittlich zu behaupten.

**CHECK-9 ist die Portabilitätsfrage.** Ein Bundle, das unter dem `okf`-Profil sauber durchläuft, hält OKF v0.1 auch ohne diesen Catalogue. Das ist T08 aus [DECISIONS.md](../DECISIONS.md), und es entsteht hier ohne eigenes Kommando — als Profil, nicht als Sonderfall.

## Offene Fragen

Die Schalternamen der zehn Erweiterungsregeln und ihre Zuordnung zum `catalogue`-Profil sind T06. Diese Datei nennt bewusst keinen.

Ob `wikilink-resolvable` seine bundle-granulare Opt-in-Liste behält oder im Profil-Modell zu einem einfachen Schalter wird, gehört ebenfalls zu T06. Die heutige Granularität hat einen Grund — sie hält den Gate ruhig, solange zwei große Bundles ihre Wikilinks nicht aufgeräumt haben — und das Profil-Modell darf ihn nicht verlieren.
