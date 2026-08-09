---
type: Spec
title: "reindex — EARS-Requirements REINDEX-1..REINDEX-18"
description: "Marker-bounded index.md generation across concept directories — --init for first-time marker creation and flat-index migration, --force for multi-section flattening, and the dry-run-by-default / --apply write polarity of COM-29–COM-32 (I03)."
tags:
  - okf-cli
  - ears
  - requirements
  - spec
---

# reindex — EARS-Requirements REINDEX-1..REINDEX-18

`reindex` (re)generates the bullet listing between a pair of marker comments in an `index.md`, from the directory's own subdirectories and concept files — the mechanism that keeps OKF §6 navigation pages in sync with the store without hand-curation. `--init` brings a directory or a hand-curated flat listing into the marker-managed form; without it, `reindex` only refreshes directories that already carry markers.

Die Querschnitts-Regeln gelten unverändert; hier steht nur, was `reindex` darüber hinaus leistet.

## Requirements

### Umfang des Reindex

| ID | EARS-Requirement |
|----|------------------|
| REINDEX-1 | WHERE no target is given, THE okf binary SHALL reindex every concept directory below the store root. |
| REINDEX-2 | WHERE the store is a bundle, THE okf binary SHALL reindex the bundle root as the single scope. |

### Markierte Blöcke

| ID | EARS-Requirement |
|----|------------------|
| REINDEX-3 | THE okf binary SHALL replace the content between the marker comments in an index.md with its immediate subdirectories that carry an index.md, followed by its concept files, each group ordered case-insensitively by title. |
| REINDEX-4 | THE okf binary SHALL address every listed entry by a path absolute from the store root. |
| REINDEX-5 | IF an index.md carries no marker comments, THEN THE okf binary SHALL leave its content unchanged. |

### Erstanlage (--init)

| ID | EARS-Requirement |
|----|------------------|
| REINDEX-6 | WHERE `--init` is given, THE okf binary SHALL ensure the target root carries an index.md with an empty marker block. |
| REINDEX-7 | WHERE `--init` is given, THE okf binary SHALL create no index.md below the target root. |
| REINDEX-8 | WHERE `--init` is given, THE okf binary SHALL migrate every marker-less index.md in the target subtree whose body is a single heading followed only by a bullet list into a managed marker block. |
| REINDEX-9 | WHERE `--force` accompanies `--init`, THE okf binary SHALL migrate into a managed marker block a marker-less index.md with more than one heading provided each section holds only headings and bullets. |
| REINDEX-10 | IF a marker-less index.md holds prose or a table beneath a heading, THEN THE okf binary SHALL leave that file unchanged independent of `--force`. |
| REINDEX-11 | WHERE `--init` skips a directory instead of converting it, THE okf binary SHALL name the reason for the skip. |

### Vorschau und Schreiben

| ID | EARS-Requirement |
|----|------------------|
| REINDEX-12 | WHERE `--apply` is absent, THE okf binary SHALL list every index.md whose computed marker block differs from its current content as a pending update. |
| REINDEX-13 | WHERE `--apply` is absent, THE okf binary SHALL list every concept-holding directory whose index.md carries no marker comments as uncovered. |
| REINDEX-14 | WHERE `--init` is given and `--apply` is absent, THE okf binary SHALL include its conversion candidates in the same report as the pending marker updates. |
| REINDEX-15 | WHERE `--apply` is given, THE okf binary SHALL write the marker block of every index.md whose computed content differs from its current content. |
| REINDEX-16 | WHERE `--init` accompanies `--apply`, THE okf binary SHALL perform the marker-block refresh in the same run as the `--init` migration. |
| REINDEX-17 | WHERE the okf binary reports intended writes for a reindex, THE okf binary SHALL end that report with the exact invocation that performs them, carrying the target and the flags given. |
| REINDEX-18 | WHERE `--apply` is given, THE okf binary SHALL name in the report every index.md it leaves untouched for carrying no marker comments. |

## Grounding

Marker-Konstanten: `MARK_START`/`MARK_END`/`EXEMPT` (`cli/okf-cli.py:33-37`).

Block-Zusammensetzung: `list_dir_concepts()` (`cli/okf-cli.py:1905-1919`, Konzeptdateien casefold nach Titel sortiert), `list_subdirs_with_index()` (`cli/okf-cli.py:1946-1962`, Unterverzeichnisse mit `index.md` casefold nach Titel sortiert), `render_block()` (`cli/okf-cli.py:1963-1983`, catalogue-root-absolute Links) und `replace_managed_block()` (`cli/okf-cli.py:1984-1995`, ersetzt nur den Inhalt zwischen den Markern und lässt Dateien ohne Marker unangetastet).

Erstanlage: `ensure_markers()` (`cli/okf-cli.py:2037-2049`) legt eine `index.md` ausschließlich am `target`-Wurzelverzeichnis an (`dirpath`, nicht rekursiv) — REINDEX-6/7. Migration bestehender, marker-loser `index.md`-Dateien im gesamten Teilbaum: `convert_flat_index()` (`cli/okf-cli.py:1996-2036`, Single-Section immer, Multi-Section nur mit `force=True` und nur bei reinen Headings+Bullets, Prosa/Tabelle verweigert immer) über `init_indexes()` (`cli/okf-cli.py:2050-2072`, ruft `convert_flat_index` je gefundener `index.md` auf und sammelt `(relpath, status)`).

`uncovered_index_dirs()` (`cli/okf-cli.py:2073-2092`) findet marker-lose `index.md`-Dateien, deren Verzeichnis Konzeptdateien enthält — REINDEX-13.

Orchestrierung, Zielprüfung und heutige Vorschau/Schreib-Verzweigung: `cmd_reindex()` (`cli/okf-cli.py:2093-2151`). Der `--init`-Zweig endet heute bei `args.check` vorzeitig mit `sys.exit(0)` (`cli/okf-cli.py:2149-2150`), **bevor** die Stale/Uncovered-Ermittlung läuft — der Befund hinter REINDEX-14. Die heutige `--check`-Zusammenfassung (`cli/okf-cli.py:2144-2146`) endet mit einer reinen Zählzeile, ohne Folgebefehl — der Befund hinter REINDEX-17. Zielvalidierung (`cli/okf-cli.py:2095-2097`, `not a directory` → `sys.exit(1)`) fällt unter COM-23/COM-32, hier nicht wiederholt.

Argument-Parser heute: `cli/okf-cli.py:4274-4283` — `target`-Positional (required), `--init`, `--check`, `--force`, Purpose-Group `maintenance`.

## Deltas gegenüber heute

| Delta | Deckung |
|---|---|
| `target` wird optionales Positional, Default: ganzer Store | I02, COM-41 |
| Bundle als zusätzliches Store-Modell | D06 |
| `--check` entfällt; Standard ist Preview, `--apply` schreibt | I03, COM-29–COM-32 |
| Preview vereint `--init`-Konversionskandidaten und Marker-Refresh in einem Report (heute: `--init --check` bricht vorher ab) | I03, COM-29 |
| Preview endet mit der exakten Re-run-Invocation (heute: reine Zählzeile ohne Folgebefehl) | I03, COM-31 |
| Nichtexistenter Target-Pfad: Exit 2 statt Exit 1 | I09, COM-23, COM-32 |

## Anmerkungen

**REINDEX-14 ist neu und schließt eine Lücke, die COM-29 sonst nur zur Hälfte einlöst.** `reindex` hat zwei unabhängige Schreibmechanismen — Erstanlage/Migration (`--init`) und Marker-Refresh. COM-29 verlangt, dass eine Preview *die* beabsichtigten Schreibvorgänge meldet, nicht eine Teilmenge davon. Der heutige Code meldet unter `--init --check` nur die Konversionskandidaten und bricht danach ab, statt auch die Stale/Uncovered-Lage desselben Laufs zu zeigen — ein Nutzer, der nur diese Ausgabe sieht, hält den Rest des Ziels fälschlich für sauber. REINDEX-14 macht daraus einen Report.

**REINDEX-17 wiederholt COM-31 mit Inhaltsangabe absichtlich**, aus demselben Grund wie MERGE-TAGS-9 in [`merge-tags.md`](./merge-tags.md): `_common.md` nennt als Präzedenzfall für die fehlende Folgebefehl-Zeile die drei Tag-Kommandos, aber `reindex`s heutige `--check`-Zusammenfassung (`cli/okf-cli.py:2144-2146`) trifft dieselbe Lücke — sie endet mit einer Zählzeile, nicht mit einem lauffähigen `okf reindex … --apply`. Die Zeile hier legt zusätzlich fest, was die Invocation trägt.

## Offene Fragen

Ob die Preview (ohne `--apply`) `--json`-fähig ist — COM-25 bindet `--json` an „jedes lesende Kommando", `reindex` ist ein schreibendes Kommando. Keine Deckung für eine Anforderung in die eine oder andere Richtung; offen für T02/T06, wie in [`merge-tags.md`](./merge-tags.md) für dieselbe Frage vermerkt.

`--force` bedeutet bei `reindex` „reine Multi-Section-Listings zusätzlich flatten", bei `rename` „Ziel überschreiben + Ambiguität akzeptieren" (AUDIT.md A4). COM-36 verlangt gleiche Bedeutung je Flag-Name über alle Kommandos hinweg; kein Finding und keine Decision lösen diesen Konflikt auf. Diese Datei nennt keinen neuen Namen für `reindex`s `--force` — das gehört zu T02/T06.
