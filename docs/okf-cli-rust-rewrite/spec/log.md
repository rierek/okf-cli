---
type: Spec
title: "log — EARS-Requirements LOG-1..LOG-9"
description: "Render git history for the store or a bundle as an OKF v0.1 §7 changelog, on stdout or materialized into log.md."
tags:
  - okf-cli
  - ears
  - requirements
  - spec
---

# log — EARS-Requirements LOG-1..LOG-9

`log` turns git commit history into a changelog a human reads, either on demand on stdout or materialized into a bundle's or the store's `log.md`. It is the only command whose date source is git rather than frontmatter, because commit history is the one date a rewrite, a reindex or a bulk tag edit cannot silently move.

The cross-cutting rules apply unchanged; this file states only what `log` adds on top of them.

## Requirements

### Umfang und Rendering

| ID | EARS-Requirement |
|----|------------------|
| LOG-1 | THE okf binary SHALL render git history as a date-grouped changelog following OKF v0.1 §7. |
| LOG-2 | WHERE no bundle is named, THE okf binary SHALL render history for the whole store. |
| LOG-3 | WHERE a bundle is named, THE okf binary SHALL scope the history to commits touching files under that bundle. |
| LOG-4 | WHERE --since is given, THE okf binary SHALL exclude commits before that point. |

### Materialisierung

| ID | EARS-Requirement |
|----|------------------|
| LOG-5 | WHERE --apply is absent, THE okf binary SHALL print the rendered changelog to stdout as the report of the intended write. |
| LOG-6 | WHERE --apply is present, THE okf binary SHALL write the rendered changelog into log.md at the scoped location. |
| LOG-7 | WHERE log.md already carries a prior snapshot region, THE okf binary SHALL replace only that region. |
| LOG-8 | WHERE log.md carries content outside the snapshot region, THE okf binary SHALL preserve that content unchanged. |

### Maschinenlesbarkeit

| ID | EARS-Requirement |
|----|------------------|
| LOG-9 | WHERE JSON output is requested, THE okf binary SHALL emit `data` as a list of objects each carrying a date and a subject. |

## Grounding

`log` lives in `cmd_log()` (`cli/okf-cli.py:2466-2492`): it shells out to `git -C <root> log --date=short --format=%ad\t%s` (`2470-2478`), optionally `--since` (`2471-2472`), scoped to the bundle path or `.` (`2473`). Rendering is `render_git_log()` (`cli/okf-cli.py:2154-2164`, docstring names it "SPEC §7 date-grouped flat list"; the wider §7 reading — "Creation" as a log entry type — is in the comment at `cli/okf-cli.py:2197-2200`). Materialization is `splice_log()` (`cli/okf-cli.py:2167-2184`), using the markers `LOG_START`/`LOG_END` (`cli/okf-cli.py:35-36`) and notice text `LOG_NOTICE` (`cli/okf-cli.py:38`): if the markers are present in the existing file only the block between them is replaced (`2175-2178`), otherwise a header is written and any prior content is kept below as a frozen archive (`2179-2184`). The parser registers the `bundle` positional, `--since` and `--write` at `cli/okf-cli.py:4232-4236`; today's flag is `--write`, not `--apply` (see Anmerkungen).

## Deltas gegenüber heute

| Delta | Deckung |
|---|---|
| `--write` wird zu `--apply` vereinheitlicht (eine Mutations-Polarität über den ganzen Binary) | I03, COM-29–31 |
| Existenzprüfung des bundle-Positionals vor dem Scan (heute keine) | COM-32 |
| Fehlschlag des git-Unterprozesses meldet Exit 3 statt Exit 1 | I09, COM-24 |

## Anmerkungen

**Die Umbenennung `--write` → `--apply` ist eine Ableitung, kein wörtlich benanntes Finding.** AUDITs A3-Verstoßliste zählt `log --write` nicht mit — sie nennt `fix-*`, `reindex`, `rewrite-path`, `tags --register` und `okf_reindex`, weil deren heutiger Default sofort schreibt. `log` ist davon nicht betroffen: ohne `--write` wird nichts geschrieben, der volle Report geht nach stdout — das ist bereits die dry-run-Form, die COM-29 verlangt. COM-29 bis COM-31 sind aber als Querschnitt für **jedes** schreibende Kommando formuliert und nennen `--apply` als den einen Flag-Namen dafür (I03: „eine Mutations-Polarität … ohne Ausnahme"). Der Präzedenzfall für die Umbenennung liegt bereits im Code: `archive` (`cli/okf-cli.py:4163-4173`, außerhalb dieser Datei) trägt in der aktuellen Registrierung schon `--apply` für genau dasselbe Preview/Perform-Paar.

**Die git-Fehlerbehandlung wird hier nicht als eigene Zeile wiederholt.** Heute meldet `cmd_log` einen fehlgeschlagenen `git`-Aufruf mit Exit 1 (`cli/okf-cli.py:2474-2478`). Das ist ein Fehler außerhalb des Stores und außerhalb der Eingabe — genau der Fall, den COM-24 querschnittlich auf Exit 3 legt. Eine LOG-spezifische Zeile würde COM-24 nur wiederholen.

## Offene Fragen

Keine.
