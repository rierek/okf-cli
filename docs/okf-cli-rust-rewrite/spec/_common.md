---
type: Spec
title: "Querschnitt — EARS-Requirements COM-1..COM-41"
description: "Store-Erkennung, Profile, Streams, Exit-Codes, JSON-Envelope, Mutations-Polarität, Flag-Vokabular und Selbstdokumentation — die Regeln, die für jedes Kommando gelten."
tags:
  - okf-cli
  - ears
  - requirements
  - spec
---

# Querschnitt — EARS-Requirements COM-1..COM-41

Diese Regeln gelten für **jedes** Kommando. Eine Kommando-Datei wiederholt sie nicht, sondern verweist auf die COM-Nummer und spezifiziert nur, was bei ihr davon abweicht oder darüber hinausgeht.

Systemname in allen Requirements ist `THE okf binary`.

## Requirements

### Store-Erkennung (D06)

| ID | EARS-Requirement |
|----|------------------|
| COM-1 | WHERE no explicit root is given, THE okf binary SHALL resolve the store root by walking the working directory upward until a catalogue marker is found. |
| COM-2 | THE okf binary SHALL recognise as a catalogue marker a `.okf.toml` file, or a `SPEC.md` and a `TYPES.md` alongside each other. |
| COM-3 | WHERE a catalogue marker is present at the store root, THE okf binary SHALL treat the store as a catalogue whose immediate subdirectories are bundles. |
| COM-4 | WHERE no catalogue marker is present at the store root, THE okf binary SHALL treat the store as a single bundle. |
| COM-5 | WHERE no catalogue marker is found in the working directory or any ancestor and no explicit root is given, THE okf binary SHALL exit 2 and SHALL name `--root` as the remedy. |
| COM-6 | WHERE the store is a bundle, THE okf binary SHALL treat the root itself as the single scope and SHALL address subdirectories as concept directories. |
| COM-7 | WHERE the `store` key in `.okf.toml` names a store model, THE okf binary SHALL apply that model in place of the detected one. |
| COM-8 | IF the store root does not exist, THEN THE okf binary SHALL exit 2 and SHALL name the path it tried. |

### Profile und Erweiterungen (D05)

| ID | EARS-Requirement |
|----|------------------|
| COM-9 | THE okf binary SHALL carry every extension over OKF v0.1 as a named switch that is readable and settable in `.okf.toml`. |
| COM-10 | THE okf binary SHALL provide a profile named `okf` that enables no extension beyond OKF v0.1. |
| COM-11 | THE okf binary SHALL provide a profile named `catalogue` that enables the extension set this catalogue relies on. |
| COM-12 | WHERE `.okf.toml` names a profile, THE okf binary SHALL apply that profile as the baseline for every switch the file leaves unset. |
| COM-13 | WHERE `.okf.toml` sets a switch, THE okf binary SHALL honour that switch over the profile baseline. |
| COM-14 | WHERE the store is a bundle and `.okf.toml` names no profile, THE okf binary SHALL apply the `okf` profile. |
| COM-15 | WHERE the store is a catalogue and `.okf.toml` names no profile, THE okf binary SHALL apply the `catalogue` profile. |
| COM-16 | IF `.okf.toml` names an unknown profile or an unknown switch, THEN THE okf binary SHALL exit 2 and SHALL list the names it accepts. |
| COM-17 | WHERE a profile is named on the command line, THE okf binary SHALL apply it in place of the profile from `.okf.toml`. |

### Streams und Diagnose

| ID | EARS-Requirement |
|----|------------------|
| COM-18 | THE okf binary SHALL write payload to stdout and diagnostics to stderr. |
| COM-19 | WHERE a degradation occurs, THE okf binary SHALL announce it on stderr as one note per degraded subsystem and SHALL produce the reduced result on stdout. |
| COM-20 | WHERE JSON output is requested, THE okf binary SHALL keep stdout parseable as a single JSON document. |

### Exit-Codes (I09)

| ID | EARS-Requirement |
|----|------------------|
| COM-21 | WHERE a command completes and reports no adverse finding, THE okf binary SHALL exit 0. |
| COM-22 | WHERE a command completes and reports an adverse finding about the store, THE okf binary SHALL exit 1. |
| COM-23 | IF the invocation is malformed, names an unknown flag, or names a path that does not exist, THEN THE okf binary SHALL exit 2. |
| COM-24 | IF a failure arises outside the store and outside the invocation, THEN THE okf binary SHALL exit 3 and SHALL name the failing subsystem. |

### JSON-Envelope (I04)

| ID | EARS-Requirement |
|----|------------------|
| COM-25 | THE okf binary SHALL accept `--json` as a global flag on every read command. |
| COM-26 | WHERE JSON output is requested, THE okf binary SHALL emit one object carrying `schema_version`, `command`, `data` and `notes`. |
| COM-27 | WHERE JSON output is requested, THE okf binary SHALL emit into `notes` every diagnostic it writes to stderr. |
| COM-28 | WHERE JSON output is requested and a command finds nothing, THE okf binary SHALL emit an empty `data` collection. |

### Mutations-Polarität (I03)

| ID | EARS-Requirement |
|----|------------------|
| COM-29 | WHERE a command writes to the store and `--apply` is absent, THE okf binary SHALL report the intended writes and SHALL perform none of them. |
| COM-30 | WHERE a command writes to the store and `--apply` is present, THE okf binary SHALL perform the writes. |
| COM-31 | WHERE a command reports intended writes, THE okf binary SHALL end that report with the exact invocation that performs them. |
| COM-32 | IF a command argument names a path that does not exist, THEN THE okf binary SHALL create nothing and SHALL exit 2. |

### Selbstdokumentation und Flag-Vokabular (A8, I05, I06, I08, I10)

| ID | EARS-Requirement |
|----|------------------|
| COM-33 | THE okf binary SHALL render its command directory, grouped by purpose, from the same registration that defines the commands. |
| COM-34 | THE okf binary SHALL reject at build time a command registration that carries no summary and no purpose group. |
| COM-35 | THE okf binary SHALL accept `-j` for `--json`, `-r` for `--root`, `-l` for `--limit`, `-t` for `--type`, `-T` for `--tag` and `-n` for the write report. |
| COM-36 | WHERE a flag name occurs on more than one command, THE okf binary SHALL give it the same meaning on each. |
| COM-37 | WHERE a command limits its result count by default, THE okf binary SHALL use 10 as that default. |
| COM-38 | THE okf binary SHALL prefix every error with `okf: error: `. |
| COM-39 | THE okf binary SHALL follow every error with a line starting `hint: ` that names a remedy. |
| COM-40 | THE okf binary SHALL name itself `okf` in every message, help text and hint it emits. |
| COM-41 | WHERE a command narrows its work to part of the store, THE okf binary SHALL accept that part as an optional positional argument. |

## Grounding

Stream-Disziplin und Degradations-Notizen bestehen bereits und sind der Maßstab, den COM-18 bis COM-20 festschreiben: `cli/okf-cli.py:895-941` (lexikaler Arm), `cli/okf-cli.py:1267-1276` (semantischer Arm), `mcp/okf_mcp.py:73-98` (Weitergabe an den MCP-Konsumenten).

Store-Erkennung heute: `catalogue_root()` in `cli/okf-cli.py:46-65`, Bundle-Begriff in `is_bundle_dir()`/`list_bundles()` ab `cli/okf-cli.py:68`. Der Bundle-Modus aus COM-4 und COM-6 existiert dort nicht.

Profile: der einzige heutige Erweiterungs-Schalter ist `wikilink_checked_bundles` in `.okf.toml`, ausgewertet in `wikilink_checked_bundles()` (`cli/okf-cli.py:3298`) und angewandt in `run_checks()` (`cli/okf-cli.py:3394`). Die übrigen Regeln stehen als feste Liste in `per_file_checks` (`cli/okf-cli.py:3414-3427`).

Selbstdokumentation: `_sub()` (`cli/okf-cli.py:4031`) und `render_command_overview()` (`cli/okf-cli.py:4045`), abgesichert durch `CommandHelpConformance` (`cli/test_okf_cli.py:3380`). COM-33 und COM-34 schreiben fest, was dort bereits gilt — COM-34 verschärft es von einem Test zu einem Build-Fehler, weil eine Registrierung in Rust ein Typ ist und kein Laufzeit-Aufruf.

## Deltas gegenüber heute

| Delta | Deckung |
|---|---|
| Bundle als Store-Modell, Marker-Umkehrung | D06 |
| Erweiterungen als Profil-Schalter statt fester Liste | D05 |
| `--json` global statt auf sechs von 23 Kommandos | I04 |
| Einheitlicher Envelope mit `schema_version` und `notes` | I04 |
| Vier unterscheidbare Exit-Codes statt Exit 1 in drei Bedeutungen | I09 |
| Eine Mutations-Polarität; `--check` entfällt zugunsten von `--apply` | I03 |
| Kurzformen | I05 |
| `okf: error: ` plus `hint: ` statt fünf Präfix-Stilen | I06 |
| `--limit` überall 10 statt 10/10/8 | I08 |
| Programmname `okf` statt `okf-cli` und `okf-cli.py` gemischt | I10 |
| Scope als Positional statt vier Mechanismen | I02 |
| Kein Verzeichnis für ein nicht existierendes Argument | B02, COM-32 |

## Anmerkungen

**COM-29 bis COM-31 sind drei Zeilen, nicht eine.** Der Präzedenzfall hat dieselbe Spaltung an DC-10/DC-11 vorgenommen, nachdem ein Feld-Audit zeigte, dass die Hälften unabhängig voneinander verletzt werden. Hier gilt dasselbe: ein Kommando kann die Vorschau korrekt erzeugen und trotzdem schreiben, oder korrekt nicht schreiben und den Folgebefehl verschweigen. Heute ist genau der zweite Fall real — `rename` nennt den Folgebefehl (`cli/okf-cli.py:3950`), die drei Tag-Kommandos nicht.

**COM-38 und COM-39 sind zwei Zeilen** aus demselben Grund: das Präfix ist billig und wird zuerst umgesetzt, der Remedy-Hinweis verlangt pro Fehlerklasse eine inhaltliche Entscheidung. Eine gemeinsame Zeile wäre auf Dauer halb erfüllt und damit als Audit-Zelle wertlos.

## Offene Fragen

COM-9 verlangt eine benannte Menge von Schaltern; welche das genau sind und wie sie auf die Profile `okf` und `catalogue` verteilt werden, ist Task T06 aus [DECISIONS.md](../DECISIONS.md). Bis T06 entschieden ist, nennt keine Kommando-Datei einen konkreten Schalternamen.

COM-35 vergibt `-T` für `--tag`, weil `-t` an `--type` geht. Die Zuordnung ist willkürlich und hält nur, solange kein Kommando beide gleichzeitig anders gewichtet.

COM-17 setzt ein Kommandozeilen-Flag für das Profil voraus, ohne es zu benennen. Der Name gehört zu T06.
