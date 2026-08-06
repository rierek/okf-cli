---
type: DesignSpec
title: "SPEC — okf-recent"
description: "okf-cli recent listet die zuletzt angelegten Konzepte eines Katalogs, datiert über den git-Commit, der die Datei hinzugefügt hat, und löst symlinkte Bundles gegen ihr eigenes Repo auf."
tags:
  - tpic
  - okf-recent
  - okf-cli
timestamp: 2026-08-06T02:59:17Z
---
# SPEC — `okf-cli recent`

Status: implementiert 2026-08-06 · Grounded at `cli/okf-cli.py` (Stand dieses Commits) · Messwerte gegen `~/Obsidian/Knowledge-Catalogue`, 21 Bundles, 2553 Konzepte

## Problem

Kein Kommando beantwortet „welche Konzepte sind zuletzt in den Katalog gekommen". `list` filtert Frontmatter und sortiert alphabetisch; `log` rendert Commit-Historie als SPEC-§7-Changelog auf Commit-Granularität, nicht auf Konzept-Granularität.

Der naheliegende Weg — das Frontmatter-Feld `timestamp` — trägt nicht. Gemessen: 1789 von 2553 Konzepten haben eines, `qm-wiki` mit 765 Konzepten hat zwei. Wo es existiert, ist es ein Migrations-Batchstempel: 510 verschiedene Werte über 1789 Konzepte, der häufigste 125-mal sekundengenau identisch. Innerhalb eines Batches gibt es keine Ordnung.

## Non-Goals

- **Kein `list --recent`.** `list` ist ein reiner Datei-Scan; eine git-Abhängigkeit dort vermischt Metadaten-Filter mit Historie.
- **Kein `--since`.** Zeitfenster beantwortet `log --since` auf Commit-Ebene; für Konzept-Ebene fehlt bisher der Bedarf.
- **Kein MCP-Tool.** `recent` gehört zur history-lesenden Familie um `log`, die nach WS3 in `../okf-tools-okf/revision/cli-mcp-maturity-design.md` bewusst CLI-only bleibt.
- **Keine Reparatur des Doppel-Lesens in `cmd_list`** (`meta_of` plus `read_file`) — bekannt, außerhalb des Umfangs.

## Context (as-is)

`iter_concepts` (`cli/okf-cli.py:80`) definiert, was ein Konzept ist: RESERVED-Namen, `assets/` und Dot-Verzeichnisse fallen raus. `resolve_scopes` (`:2650`) löst `--scope` auf Bundle-Pfade auf. `cmd_log` (`:2176`) liest seit jeher git; die Datei kennt keinen geteilten git-Helper, drei Call-Sites rollen je eigenes.

Fünf der 21 Bundles sind Symlinks in fremde Repos und im Katalog-Repo je ein Eintrag mit Mode 120000 — `git log` dort liefert für alle 78 enthaltenen Konzepte nur das Datum, an dem der Symlink gelegt wurde.

## Constraints and Decisions

| ID | Entscheidung | Grund |
|---|---|---|
| D01 | Eigenes Kommando `recent`, Gruppe `navigation` | kapselt die git-Abhängigkeit; `list` bleibt reiner Datei-Scan |
| D02 | Zeitquelle git `--diff-filter=A`, nicht `timestamp`, nicht mtime | `timestamp` deckt 70% ab und ist ein Batchstempel; mtime überlebt weder `normalize-tags`/`reindex`/`fix-crosslinks` noch einen Clone |
| D03 | Default-Scope ganzer Katalog, `--scope` grenzt ein, keine cwd-Inferenz | konsistent mit `find` und `list` |
| D04 | Symlink-Bundles werden gegen ihr eigenes Repo aufgelöst | sonst 78 Konzepte mit dem Datum des Symlinks |
| D05 | Eine Zeile je Konzept | zehn Blöcke à fünf Zeilen sind nicht scanbar |
| D06 | `--limit` plus die `list`-Filter `--type`/`--tag`/`--scope`/`--json` | kleinste Fläche, die die Frage beantwortet |
| D07 | `--no-renames` | Rename-Erkennung klassifiziert `git mv` als `R`, `--diff-filter=A` verwirft das; `okf-cli rename` erzeugt genau das. Gemessen: 4 Konzepte ohne Datum mit Erkennung an, 0 mit aus |
| D08 | git-Schlüssel aus `prefix + concept_id`, nie aus `os.path.relpath` | `relpath` ist lexikalisch und löst keine Symlinks auf; gemessen 78 von 78 Konzepten ohne Treffer |
| D09 | Undatierte Konzepte sortieren ans Ende | beim `_inbox`-Drain sind Dutzende gleichzeitig untracked; vorn einsortiert verbrauchen sie das ganze `--limit` |
| D10 | Kein git / kein Repo ist Exit 1; Teilausfälle degradieren weich mit einer Notiz | D15/PF-4 setzt einen zweiten Arm voraus, den es hier nicht gibt — ein `recent` ohne Datumsquelle behauptete eine Ordnung, die es nicht hat |
| D11 | Bei mehrfachem Add gewinnt der jüngste | unter D07 ist der Rename-Commit der einzige Add eines umbenannten Konzepts; jüngster-gewinnt macht D+A und `mv` gleich behandelbar |

## Requirements

### REQ-01 Datumsquelle

`recent` datiert jedes Konzept über den git-Commit, der seinen Pfad hinzugefügt hat, ermittelt mit `--no-renames --diff-filter=A --format=@%at --name-only`.

- AC-01.1 test: `RecentAddEventParse` prüft den Stanza-Strom gegen `{pfad: unix_ts}`.
- AC-01.2 test: `RecentAgainstRealGit.test_add_events_round_trip_through_real_git` prüft dieselbe Funktion gegen echte git-Ausgabe mit gepinnten Commit-Daten.
- AC-01.3 test: `RecentAgainstRealGit.test_git_mv_keeps_the_concept_datable` schlägt fehl, sobald `--no-renames` aus der argv verschwindet (D07).

### REQ-02 Symlink-Auflösung

Ein Bundle, dessen realer Pfad außerhalb des Katalog-Roots liegt, wird über `git rev-parse --show-toplevel` seinem eigenen Repo zugeordnet und dort abgefragt.

- AC-02.1 test: `RecentAgainstRealGit.test_symlinked_bundle_dates_resolve_against_the_foreign_repo` — zwei echte Repos, Symlink dazwischen.
- AC-02.2 test: `RecentAgainstRealGit.test_catalogue_repo_knows_only_the_symlink_itself` zeigt, dass die Fremdabfrage notwendig und nicht dekorativ ist.
- AC-02.3 test: `RecentConceptGitKey.test_key_never_contains_dotdot` verhindert die `relpath`-Ableitung (D08).
- AC-02.4 test: `RecentCommand.test_symlinked_bundle_resolves_against_its_own_repo` prüft den Weg end-to-end durch `cmd_recent`.

### REQ-03 Ein git-Prozess je Repo

Bundles mit gemeinsamem Repo werden zu einem Aufruf zusammengefasst.

- AC-03.1 test: `RecentRepoGrouping` prüft Kollaps, Trennung und first-seen-Reihenfolge.

### REQ-04 Konzeptmenge und Sortierung

`iter_concepts` ist die Autorität über die Konzeptmenge; git liefert nur Daten. Sortierung ist absteigend nach Zeitstempel, gleiche Zeitstempel alphabetisch nach Pfad, undatierte zuletzt.

- AC-04.1 test: `RecentRanking` prüft Reihenfolge, Tie-Break, Position der Undatierten und `--limit`.
- AC-04.2 test: `RecentCommand.test_reserved_and_assets_are_not_concepts`.
- AC-04.3 test: `RecentCommand.test_untracked_concept_listed_undated_at_the_end`.

### REQ-05 Ausgabekontrakt

Eine Zeile je Konzept: Zeitspalte 16 Zeichen, Typspalte auf den breitesten Typ im Ergebnis, dann `<bundle>/<concept-id>` ohne Endung. Trailer `recent: {gezeigt} of {gesamt} concept(s)`. Leerfall `(no matches)` ohne Trailer. `--json` liefert `created`, `created_ts`, `title`, `type`, `path`, `description`; leeres Ergebnis `[]`.

- AC-05.1 test: `RecentRendering` prüft Zeilenform, Spaltenbreite und Platzhalter.
- AC-05.2 test: `RecentCommand.test_trailer_names_shown_and_total`, `…test_no_matches_on_empty_catalogue`.
- AC-05.3 test: `RecentCommand.test_json_carries_created_and_created_ts`, `…test_json_undated_concept_has_null_dates`, `…test_json_empty_result_is_empty_array`.

### REQ-06 Degradation

Fehlt git oder ist der Katalog kein Repo, endet das Kommando mit Exit 1 und einer Meldung auf stderr. Ein unerreichbares Fremd-Repo, ein gebrochener Symlink im `--scope` und undatierte Konzepte erzeugen je eine Notiz auf stderr; stdout bleibt davon unberührt.

- AC-06.1 test: `RecentDegradationNotes.test_missing_git_binary_is_a_hard_error`, `…test_non_repo_root_is_a_hard_error`.
- AC-06.2 test: `…test_unreachable_foreign_repo_names_the_bundle_and_lists_undated`, `…test_broken_symlink_scope_notes_and_lists_nothing`.
- AC-06.3 test: `…test_undated_note_is_aggregated_not_per_concept`, `…test_undated_note_suppressed_when_the_repo_itself_failed`.
- AC-06.4 test: `…test_stdout_is_identical_with_and_without_notes`.

### NFR-01 Laufzeit

Bei Default-Scope 12 git-Prozesse (ein `rev-parse` für den Root, fünf für die Fremd-Bundles, sechs `log`). Gemessen 0.06s für den vollen Katalog-Walk. Ohne `--type`/`--tag` wird Frontmatter erst für die überlebenden Zeilen gelesen — zehn statt 2553 Lesevorgänge.

Kein `--max-count`: die N jüngsten Add-*Commits* sind nicht die N jüngsten Add-*Pfade*, weil ein Commit vierzig Konzepte anlegt.

## Interfaces and Contracts

````
okf-cli.py recent [--limit N] [--scope TARGET] [--type TYPE] [--tag TAG] [--json]
````

Der Pfad in der Ausgabe ist derselbe wie bei `list` konstruiert und direkt als Argument für `read` und `toc` verwendbar.

## Assumptions

- ASM-01: Der Katalog-Root liegt in einem git-Repo. Verletzt der Nutzer das, sagt REQ-06 es ihm mit Exit 1.
- ASM-02: Ein umbenanntes Konzept datiert auf den Rename, nicht auf die ursprüngliche Anlage. Folge von D07, betrifft im echten Katalog vier Konzepte. Die Alternative — Rename-Ketten über `--diff-filter=AR --name-status` verfolgen — wurde als unverhältnismäßig verworfen.

## Traceability

| Anforderung | Produktionscode | Test |
|---|---|---|
| REQ-01 | `parse_add_events`, `_git_add_events` | `RecentAddEventParse`, `RecentAgainstRealGit` |
| REQ-02 | `concept_git_key`, `_git_toplevel`, `_recent_scopes` | `RecentConceptGitKey`, `RecentAgainstRealGit`, `RecentCommand` |
| REQ-03 | `group_scopes_by_repo` | `RecentRepoGrouping` |
| REQ-04 | `rank_recent`, `cmd_recent` | `RecentRanking`, `RecentCommand` |
| REQ-05 | `format_created`, `render_recent_lines`, `iso_created`, `cmd_recent` | `RecentRendering`, `RecentCommand` |
| REQ-06 | `_recent_scopes`, `cmd_recent` | `RecentDegradationNotes` |
| Registrierung | `COMMAND_DISPATCH`, `_sub(…, "recent", "navigation", …)` | `CommandHelpConformance`, `CommandDirectoryOrder` |

### Umkehrmutationen

Jede muss die Suite rot machen; belegt am 2026-08-06:

| Mutation | erwartet rot | beobachtet |
|---|---|---|
| `--no-renames` aus der argv entfernen | `RecentAgainstRealGit.test_git_mv_keeps_the_concept_datable` | 1 Fehler, genau dort |
| `concept_git_key` über `os.path.relpath` ableiten | `RecentConceptGitKey`, `RecentAgainstRealGit`, `RecentCommand` | 8 Fehler |
| Sortierschlüssel der Undatierten von `-1` auf `+inf` | `RecentRanking.test_undated_sort_after_every_dated` | 2 Fehler |
