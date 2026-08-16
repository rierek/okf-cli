---
type: Spec
title: "rename — EARS-Requirements RENAME-1..RENAME-26"
description: "Concept-Move mit synchroner Crosslink- und Wikilink-Rewrite über git mv, plus Reindex der betroffenen Bundles — Vorbedingungen, Ziel-existiert-Fälle und mehrdeutige Wikilink-Auflösung."
tags:
  - okf-cli
  - ears
  - requirements
  - spec
---

# rename — EARS-Requirements RENAME-1..RENAME-26

`rename` bewegt eine Konzept-Datei von einem Quell- zu einem Zielpfad und hält dabei zwei unabhängige Referenzarten synchron — Markdown-Crosslinks und Wikilinks —, während es die Datei per `git mv` verschiebt und jedes betroffene Bundle reindiziert. Es dient Menschen, die eine Datei umbenennen oder in ein anderes Bundle verschieben, und Agenten, die einen Refactor über den ganzen Store fahren, ohne jede eingehende Referenz von Hand nachzuziehen. Die Querschnitts-Regeln (COM-1 bis COM-41) gelten unverändert, insbesondere die Mutations-Polarität aus COM-29 bis COM-31 — `rename` ist dort bereits heute der Präzedenzfall, der den Folgebefehl nennt, keine Abweichung davon; hier steht nur, was `rename` darüber hinaus leistet.

## Requirements

### Pfade und Vorbedingungen

| ID | EARS-Requirement |
|----|------------------|
| RENAME-1 | THE okf binary SHALL move one concept file from a source path to a destination path within the store. |
| RENAME-2 | IF the source path or the destination path does not end in `.md`, THEN THE okf binary SHALL refuse the move. |
| RENAME-3 | IF the source path or the destination path does not lie under the store root, THEN THE okf binary SHALL refuse the move. |
| RENAME-4 | WHERE the store is a catalogue, THE okf binary SHALL require every source and destination path to name a bundle segment. |
| RENAME-5 | WHERE the store is a bundle, THE okf binary SHALL accept a source or destination path that names a concept file directly under the store root. |
| RENAME-6 | IF the source path names a reserved file, THEN THE okf binary SHALL refuse the move. |
| RENAME-7 | IF the destination path names a reserved file, THEN THE okf binary SHALL refuse the move. |
| RENAME-8 | IF the destination basename is empty or holds only whitespace, THEN THE okf binary SHALL refuse the move. |
| RENAME-9 | IF the destination basename contains a control character or a character forbidden in filenames, THEN THE okf binary SHALL refuse the move. |
| RENAME-10 | IF the source path and the destination path are identical, THEN THE okf binary SHALL refuse the move. |

### Ziel existiert bereits

| ID | EARS-Requirement |
|----|------------------|
| RENAME-11 | WHILE the destination path names the same file as the source on a case-insensitive filesystem, THE okf binary SHALL allow the move without `--force`. |
| RENAME-12 | IF `--apply` is present, the destination path exists and does not name the same file as the source, and `--force` is absent, THEN THE okf binary SHALL refuse the move and SHALL exit 1. |
| RENAME-13 | WHEN `--force` overwrites an existing destination, THE okf binary SHALL report the count of inbound references that now address different content. |

### Crosslinks

| ID | EARS-Requirement |
|----|------------------|
| RENAME-14 | WHEN a move changes a crosslink's resolved target, THE okf binary SHALL rewrite that crosslink to address the destination. |
| RENAME-15 | WHILE a move keeps the file's bundle unchanged, THE okf binary SHALL leave the moved file's own crosslinks unrewritten. |
| RENAME-16 | WHEN a move changes the file's bundle, THE okf binary SHALL rewrite the moved file's own crosslinks to keep addressing their original targets. |

### Wikilinks

| ID | EARS-Requirement |
|----|------------------|
| RENAME-17 | WHEN a move changes a wikilink occurrence's resolution to name the destination, THE okf binary SHALL rewrite that occurrence to the destination. |
| RENAME-18 | IF an inbound wikilink occurrence already resolves ambiguously among candidates that include the source, THEN THE okf binary SHALL leave that occurrence unrewritten and SHALL report it. |
| RENAME-19 | WHEN the destination basename is already used by another concept, THE okf binary SHALL report that collision. |
| RENAME-20 | IF `--apply` is present, the move leaves at least one inbound wikilink ambiguous, and `--force` is absent, THEN THE okf binary SHALL refuse the move and SHALL exit 1. |

### Git-Move

| ID | EARS-Requirement |
|----|------------------|
| RENAME-21 | WHEN a move applies, THE okf binary SHALL move the source file with `git mv`. |
| RENAME-22 | WHEN the source file is not tracked by git or git is unavailable, THE okf binary SHALL fall back to a plain filesystem move. |
| RENAME-23 | WHEN a move applies, THE okf binary SHALL report whether it used `git mv` or a plain filesystem move. |

### Reindex

| ID | EARS-Requirement |
|----|------------------|
| RENAME-24 | WHEN a move applies, THE okf binary SHALL reindex every bundle the move affects. |
| RENAME-25 | WHEN a move applies, THE okf binary SHALL report the count of index files it rewrote and the bundles it reindexed. |

### Vorschau

| ID | EARS-Requirement |
|----|------------------|
| RENAME-26 | WHERE a move is not applied, THE okf binary SHALL name every inbound crosslink rewrite, every outbound crosslink rewrite, every wikilink rewrite and every bundle the move affects. |

## Grounding

Der ganze Mechanismus lebt in `perform_rename()` (`cli/okf-cli.py:3869-4012`), aufgerufen von `cmd_rename()` (`cli/okf-cli.py:4015-4018`); die Parser-Registrierung mit `old`/`new`/`--apply`/`--force` steht bei `cli/okf-cli.py:4290-4297`.

Die Vorbedingungs-Guards (RENAME-2 bis RENAME-10) sitzen alle am Kopf von `perform_rename`: `.md`-Endung (`cli/okf-cli.py:3879-3880`), Quelle nicht gefunden (`3881-3882`), reservierte Quelle (`3883-3884`), reserviertes Ziel (`3885-3890`), leerer/whitespace-Basisname (`3891-3900`), Kontrollzeichen (`3901-3903`), identische Pfade (`3904-3905`), außerhalb der Store-Wurzel (`3906-3907`), Bundle-Tiefe — „path must be inside a bundle" (`3908-3910`) — und verbotene Zeichen (`3911-3913`). Die Bundle-Tiefen-Prüfung existiert heute ausschließlich in der Catalogue-Form (RENAME-4); den Bundle-Modus (RENAME-5) kennt der heutige Code nicht — Grund für D06, siehe Deltas.

Der Ziel-existiert-Zweig (RENAME-11 bis RENAME-13) steht bei `cli/okf-cli.py:3914-3919` (Guard, inklusive `os.path.samefile`-Ausnahme für Case-only-Renames) und `cli/okf-cli.py:3980-3985` (Meldung, wie viele eingehende Referenzen beim `--force`-Überschreiben umadressiert werden).

Die Crosslink-Seite (RENAME-14 bis RENAME-16) wird von `plan_rename()` geplant (`cli/okf-cli.py:3718-3757`, inbound `3727-3735`, outbound nur bei Bundle-Wechsel `3736-3752`) und von `_apply_link_rewrites()` angewandt (`cli/okf-cli.py:3760-3782`).

Die Wikilink-Seite (RENAME-17 bis RENAME-20) wird von `plan_wikilink_rewrites()` geplant (`cli/okf-cli.py:3619-3690`) und von `_apply_wikilink_rewrites()` angewandt (`cli/okf-cli.py:3805-3830`). Die drei Ergebniszustände sind dort benannt: `rewrite` (RENAME-17), `skipped-ambiguous` (RENAME-18, Zeile `3677-3679`) und `collision-affected`/`turns_ambiguous` (RENAME-19/20, Zeile `3680-3686` und Guard `3956-3961`). `_index_after_move()` (`cli/okf-cli.py:3693-3707`) ist die Simulation, gegen die vorher/nachher aufgelöst wird.

Der Move selbst ist `_git_mv()` (`cli/okf-cli.py:3855-3866`, RENAME-21/22), das Ergebnis wird bei `cli/okf-cli.py:4006` berichtet (RENAME-23). Der Reindex ist `reindex_tree()` (`cli/okf-cli.py:3833-3852`), aufgerufen bei `cli/okf-cli.py:4003-4005` (RENAME-24), berichtet bei `cli/okf-cli.py:4011` (RENAME-25).

Die Vorschau (RENAME-26) steht bei `cli/okf-cli.py:3963-3978`, inklusive der Zeile, die COM-31 bereits heute erfüllt: „Re-run with --apply." (`cli/okf-cli.py:3974-3975`) — das ist der Präzedenzfall, den COM-31 verallgemeinert, keine rename-eigene Anforderung mehr.

## Deltas gegenüber heute

| Delta | Deckung |
|---|---|
| Exit 1 (Sachbefund) statt Exit 2 für „Ziel existiert bereits, `--force` fehlt" | I09, COM-22 |
| Exit 1 (Sachbefund) statt Exit 2 für „Move macht einen eingehenden Wikilink mehrdeutig, `--force` fehlt" | I09, COM-22 |
| Bundle-Modus: Pfad ohne Bundle-Segment zulässig, wenn der Store ein Bundle ist | D06 |

## Anmerkungen

**RENAME-18 und RENAME-20 sind zwei verschiedene Sachverhalte, keine Dopplung.** RENAME-18 beschreibt einen Wikilink, der schon vor dem Move mehrdeutig war — `rename` rät nicht, welches Ziel gemeint ist, und lässt ihn unangetastet. RENAME-20 beschreibt das Gegenteil: einen Wikilink, der vor dem Move eindeutig war und durch genau diesen Move mehrdeutig würde. Das erste ist ein Bestandsbefund, den `rename` nur meldet; das zweite ist eine Korruption, die `rename` selbst verursachen würde und deshalb ohne `--force` verweigert.

**RENAME-12 und RENAME-20 sind Ausnahmen von COM-30, keine Widersprüche.** COM-30 sagt, dass ein Kommando mit gesetztem `--apply` schreibt. Hier ist `--apply` gesetzt und trotzdem wird nicht geschrieben, weil ein Sachbefund über den Store — nicht über die Aufrufform — den Move blockiert. Das ist derselbe Grund, aus dem beide Fälle exit 1 statt exit 2 tragen (siehe Deltas).

**RENAME-22 lässt offen, ob der Fallback als Degradation nach COM-19 anzukündigen ist.** Der heutige Code fällt still auf eine reine Dateisystem-Verschiebung zurück, ohne stderr-Notiz. Ob ein einzelner untracked Move unter COM-19s „ein degradiertes Subsystem" fällt, ist eine COM-Frage und wird hier nicht entschieden — RENAME-22 legt nur den Trigger und die Rust-Zielantwort fest.

## Offene Fragen

Ob `--json` (COM-25 spricht nur von „every read command") für `rename` überhaupt gilt und was dann in `data` steht, ist durch COM nicht gedeckt und wird hier nicht entschieden.

Ob RENAME-4/RENAME-5 (Bundle-Segment-Pflicht je Store-Modell) unverändert für `archive` gelten, das denselben `perform_rename`-Kern nutzt, ist Sache der `archive`-Datei, nicht dieser.
