---
type: Spec
title: "rewrite-path — EARS-Requirements REWRITE-PATH-1..REWRITE-PATH-8"
description: "Literaler Pfad-String-Rewrite über beliebige Textdateien — kein OKF-Konzeptdatei-Werkzeug und keine Norm-Erweiterung, daher ohne Profil-Schalter."
tags:
  - okf-cli
  - ears
  - requirements
  - spec
---

# rewrite-path — EARS-Requirements REWRITE-PATH-1..REWRITE-PATH-8

`rewrite-path` ersetzt einen literalen Pfad-String durch einen anderen über eine feste Menge von Textdateiendungen hinweg — Code, Config, Skripte, nicht nur Markdown. Es deckt Referenzen ab, die kein Markdown-Werkzeug sieht (Import-Pfade, YAML/TOML-Referenzen, Shell-Skripte). Anders als `fix-crosslinks` und `fix-xml-tags` implementiert `rewrite-path` keine der 13 `check`-Regeln aus [check.md](./check.md) — es ist kein OKF-Norm- oder Catalogue-Erweiterungswerkzeug, sondern generisches Textwerkzeug ohne Konzeptdatei-Semantik. Es trägt deshalb keine Profil-Schalter-Bindung.

Die Querschnitts-Regeln gelten unverändert; hier steht nur, was `rewrite-path` darüber hinaus leistet.

## Requirements

### Umfang des Rewrites

| ID | EARS-Requirement |
|----|------------------|
| REWRITE-PATH-1 | WHERE no target is given, THE okf binary SHALL scan every eligible file below the store root. |
| REWRITE-PATH-2 | WHERE a target names a directory, THE okf binary SHALL scan only the eligible files below that target. |
| REWRITE-PATH-3 | THE okf binary SHALL scan only a file whose extension appears in its fixed text-file extension list. |
| REWRITE-PATH-4 | THE okf binary SHALL exclude from the scan a directory whose name begins with a dot. |
| REWRITE-PATH-5 | THE okf binary SHALL exclude from the scan a directory named `node_modules`. |

### Match- und Ersetz-Semantik

| ID | EARS-Requirement |
|----|------------------|
| REWRITE-PATH-6 | THE okf binary SHALL replace with the new string every occurrence of the old string not bounded on either side by a word character, a dot, a slash or a hyphen. |
| REWRITE-PATH-7 | IF an occurrence of the old string is bounded on either side by a word character, a dot, a slash or a hyphen, THEN THE okf binary SHALL leave that occurrence unmodified. |

### Ausgabe

| ID | EARS-Requirement |
|----|------------------|
| REWRITE-PATH-8 | THE okf binary SHALL name, for each rewritten file, the file and the count of occurrences replaced. |

## Grounding

Eligible-Extension-Liste: `REWRITE_EXTS` (`cli/okf-cli.py:1821-1822`, heute `.md .py .js .ts .tsx .jsx .go .rs .rb .yml .yaml .toml .json .txt .rst .cfg .ini .sh`). Verzeichnis-Ausschluss beim Walk: `_prune_walk_dirs()` (`cli/okf-cli.py:1738-1740`, schließt `node_modules` und Dot-Verzeichnisse aus). Match-/Ersetz-Regex inklusive der Grenzzeichen-Klasse `[\w./-]`: `rewrite_path()` (`cli/okf-cli.py:1825-1845`, Pattern-Bau in `cli/okf-cli.py:1837`). Kommando-Einstieg: `cmd_rewrite_path()` (`cli/okf-cli.py:1848-1855`). Registrierung: `cli/okf-cli.py:4298-4303` (`--scan-root` als heutiger Scope-Mechanismus, `--check` als heutige Dry-run-Flagge, kein `--apply`-Gegenstück).

## Deltas gegenüber heute

| Delta | Deckung |
|---|---|
| `--check` entfällt zugunsten von `--apply`; Dry-run wird Default | I03, COM-29–COM-32 |
| `--scan-root` entfällt zugunsten des globalen `--root` plus optionalem positional Target | I02, COM-41 |

## Anmerkungen

**Kein Schalter, anders als `fix-crosslinks`/`fix-xml-tags`.** Beide Nachbardateien binden ihren Rewrite an einen Profil-Schalter, weil ihre Konvention (`crosslink-format`, `xml-like-tags`) als `check`-Regel bereits an D05 hängt. `rewrite-path` hat kein `check`-Pendant und keine OKF-Bezugsklausel — es ist reines Datei-Tooling, dessen Wirkung allein durch `old`/`new` und den Scope bestimmt wird. Eine Schalter-Bindung hätte hier keinen Bezugspunkt.

**REWRITE-PATH-6/7 spezifizieren dieselbe Grenzbedingung aus zwei Richtungen**, analog zu FIX-CROSSLINKS-7/8/10 in [fix-crosslinks.md](./fix-crosslinks.md): die eine Zeile trägt den Regelfall (Ersetzung), die andere den Grenzfall (Token eingebettet in einen längeren Pfad-String bleibt unangetastet), weil beide Hälften unabhängig voneinander verletzt werden können.

**`--scan-root` widerspricht in seiner heutigen Form der Scope-Vereinheitlichung nicht nur formal.** Der heutige Hilfetext („pass repo root for repo-wide") erlaubt einen Root **weiter** als der Store, während das vereinheitlichte `[TARGET]`-Positional (COM-41) den Scope nur **innerhalb** des Stores verengt. Die Auflösung: die weite Verwendung wandert zum bereits existierenden globalen `--root`/`-r` (COM-1, COM-35), der explizit auf einen beliebigen Pfad zeigen darf; das positionale `TARGET` verengt von dort aus wie bei jedem anderen Kommando.

## Offene Fragen

Ob die feste Extension-Liste (REWRITE-PATH-3) im Rust-Binary konfigurierbar wird, ist nicht entschieden; diese Datei übernimmt die heutige feste Liste unverändert.

Ob die „repo-wide"-Verwendung über den globalen `--root` in der Praxis dieselbe Ergonomie trägt wie das heutige eigene `--scan-root` (ein Flag statt einer Root-Neuauflösung mit allen Store-Erkennungsfolgen aus COM-1–COM-8), ist nicht verifiziert und bleibt ein Punkt für die Verifikationsstrategie aus Q01.
