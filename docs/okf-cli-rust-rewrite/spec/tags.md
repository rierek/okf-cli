---
type: Spec
title: "tags — EARS-Requirements TAGS-1..TAGS-20"
description: "Auftrennung der vier heutigen tags-Modi in tags list/find/register/validate, mit der TAGS.md-Registrierung an einen Profil-Schalter gebunden."
tags:
  - okf-cli
  - ears
  - requirements
  - spec
---

# tags — EARS-Requirements TAGS-1..TAGS-20

`tags` beantwortet vier verschiedene Fragen unter einem Kommandonamen: welche Tags gibt es im Store (Voll-Audit), welches registrierte Tag passt zu einem Kandidaten (Fuzzy-Suche), welches Tag wird neu in die Registrierung aufgenommen, und hält ein Tag die Registrierung ein. I01 trennt die vier Modi in eigene Subkommandos. Die Querschnitts-Regeln gelten unverändert; hier steht nur, was `tags` darüber hinaus leistet.

## Requirements

### Modus-Aufteilung

| ID | EARS-Requirement |
|----|------------------|
| TAGS-1 | THE okf binary SHALL group the tag command as `tags list`, `tags find`, `tags register` and `tags validate`. |

### tags list — Voll-Audit

| ID | EARS-Requirement |
|----|------------------|
| TAGS-2 | THE okf binary SHALL emit under `tags list` every tag found in the store together with its usage count. |
| TAGS-3 | WHERE `tags list` finds no tag in the store, THE okf binary SHALL report that none exist. |
| TAGS-4 | WHERE `--singletons` is given on `tags list`, THE okf binary SHALL restrict the result to tags used exactly once. |

### tags find — Fuzzy-Suche

| ID | EARS-Requirement |
|----|------------------|
| TAGS-5 | THE okf binary SHALL accept under `tags find` one or more candidate strings as positional arguments. |
| TAGS-6 | THE okf binary SHALL rank the tags found in the store by similarity to each candidate given to `tags find`. |
| TAGS-7 | WHERE a candidate given to `tags find` matches no similar tag, THE okf binary SHALL report the candidate as a new tag. |
| TAGS-8 | WHERE a candidate given to `tags find` matches, THE okf binary SHALL report each match together with its usage count. |

### tags register — Registrierung (an einen Schalter gebunden)

| ID | EARS-Requirement |
|----|------------------|
| TAGS-9 | THE okf binary SHALL accept under `tags register` one or more tag strings as positional arguments. |
| TAGS-10 | WHERE the switch for the tag registry is enabled, THE okf binary SHALL treat `tags register` as a write command that adds every given tag not yet present to the registry. |
| TAGS-11 | WHERE a tag given to `tags register` is already present in the registry, THE okf binary SHALL report it as already registered. |
| TAGS-12 | WHERE `tags register` adds a tag under `--apply`, THE okf binary SHALL attempt a best-effort embedding of that tag. |
| TAGS-13 | IF the embedding attempt for a newly added tag fails, THEN THE okf binary SHALL report the failure on stderr. |
| TAGS-20 | WHERE the registry is absent, THE okf binary SHALL create it under `tags register` with the tags it adds. |

### tags validate — Prüfung gegen die Registrierung (an denselben Schalter gebunden)

| ID | EARS-Requirement |
|----|------------------|
| TAGS-14 | WHERE the switch for the tag registry is enabled, THE okf binary SHALL treat `tags validate` as a read command that checks every given tag against the registry. |
| TAGS-15 | WHERE a tag given to `tags validate` is absent from the registry, THE okf binary SHALL report it as unknown. |
| TAGS-16 | WHERE every tag given to `tags validate` is present in the registry, THE okf binary SHALL report them as known. |
| TAGS-17 | WHERE `tags validate` reports at least one unknown tag, THE okf binary SHALL exit 1. |
| TAGS-18 | WHERE `tags validate` reports no unknown tag, THE okf binary SHALL exit 0. |
| TAGS-19 | IF the registry is absent although its switch is enabled, THEN THE okf binary SHALL announce the absence on stderr. |

## Grounding

Heute ist `tags` ein einziges Kommando mit vier Zweigen in `cmd_tags()` (`cli/okf-cli.py:418-464`): `--register` (`cli/okf-cli.py:419-426`), `--validate` (`cli/okf-cli.py:427-438`), Voll-Audit ohne `query` (`cli/okf-cli.py:439-453`) und Fuzzy-Suche mit `query` (`cli/okf-cli.py:454-464`). Die Parser-Registrierung mit allen vier Flags an einem Subparser steht in `cli/okf-cli.py:4304-4314`.

Voll-Audit zählt über `all_tags()` (`cli/okf-cli.py:163-171`), das jedes Bundle im Store scannt — nicht scope-fähig, daher kein Positional für einen engeren Ausschnitt (COM-41 greift hier nicht, weil das Kommando heute nichts einschränkt).

Fuzzy-Suche läuft über `fuzzy_matches()` (`cli/okf-cli.py:336-368`), das `fzf --filter` als Subprozess und `difflib.SequenceMatcher` kombiniert; der `fzf`-Aufruf ist die Laufzeitabhängigkeit aus I11.

Registrierung: `register_tags()` (`cli/okf-cli.py:2550-2558`) liest `TAGS.md` über `_read_tag_rows()` (`cli/okf-cli.py:2533-2541`) und schreibt es über `write_tags_registry()` (`cli/okf-cli.py:2543-2548`) neu, inklusive Kopfzeile aus `TAGS_HEADER` (`cli/okf-cli.py:2523-2531`) — die Datei wird beim ersten `register` neu angelegt, wenn sie fehlt. Der Aufruf schreibt heute sofort, ohne Vorschau oder Bestätigung (B05, I03). Im Erfolgsfall folgt ein Best-effort-Embedding über `auto_embed_new_tags()` (`cli/okf-cli.py:390-412`), das laut eigenem Docstring nie eine Exception nach außen durchreicht.

Prüfung: `load_tags()` (`cli/okf-cli.py:2511-2519`) liefert `None`, wenn `TAGS.md` fehlt; `cmd_tags()` behandelt das als „closed vocabulary not enabled" und druckt die Meldung heute auf stdout statt stderr (`cli/okf-cli.py:429-430`).

Der MCP exponiert nur die beiden Lese-Modi als ein einziges Tool `okf_tags(query, limit)` (`mcp/okf_mcp.py:183-187`); der Docstring nennt `--register` ausdrücklich als „CLI-only by intent". Diese Datei ändert daran nichts — kein Finding verlangt, `register`/`validate` über den MCP freizugeben.

## Deltas gegenüber heute

| Delta | Deckung |
|---|---|
| Vier Modi eines Kommandos werden vier Subkommandos | I01 |
| Kombinierte `--register`/`--validate`-Aufrufe sind grammatisch ausgeschlossen statt eine Flag-Priorität still zu gewinnen | B05 |
| `tags register` schreibt nicht mehr sofort; `--apply` wird Voraussetzung fürs Schreiben, die Vorschau nennt den Folgebefehl | I03, COM-29 bis COM-31 |
| `tags find`-Limit-Default 10 statt 8 | I08, COM-37 |
| Kurzformen `-j`/`-l`/`-r` auf allen vier Subkommandos | I05, COM-35 |
| Registrierungs-Mechanik (`register` und `validate`) an einen Profil-Schalter gebunden statt immer verfügbar | D05, siehe CHECK-7 in `check.md` als Präzedenzfall derselben Bindung |
| Fehlende Registry wird als Degradation auf stderr angekündigt statt knapp auf stdout kommentiert | COM-18, COM-19 |
| `fzf`-Subprozess entfällt zugunsten eines In-Process-Matchers | I11, D04 |
| `--json` und der gemeinsame Envelope gelten für alle vier Subkommandos, statt dass `tags` (wie heute) gar kein `--json` kennt | I04, COM-25, COM-26 |
| Exit-Codes folgen dem Vier-Code-Kontrakt statt der gemischten Exit-1-Bedeutung anderer Kommandos | I09, COM-21 bis COM-24 |

## Anmerkungen

**TAGS-17 und TAGS-18 wiederholen COM-21 und COM-22 absichtlich.** `tags validate` ist das Kommando, das ein Pre-Commit-Hook oder eine CI-Stufe typischerweise gegen einen Exit-Code auswertet, genau wie bei CHECK-13/CHECK-14 in `check.md` begründet. Der heutige Code trifft die Unterscheidung bereits exakt so (`sys.exit(1 if unknown else 0)`, `cli/okf-cli.py:438`); die beiden Zeilen machen den Vertrag an der Stelle prüfbar, an der er benutzt wird.

**TAGS-19 folgt demselben Muster wie CHECK-15.** Eine fehlende Registry ist eine Degradation im Sinn von COM-19, kein Fehlerfall: `tags validate` meldet nichts als unbekannt, wenn es gegen keine Registrierung prüfen kann — TAGS-18 greift dann automatisch, weil keine Zeile einen unbekannten Tag meldet. Eine eigene Exit-Zeile dafür wäre eine vierte, überflüssige Aussage.

**TAGS-10 und TAGS-14 nennen keinen Schalternamen**, wie von der Aufgabenstellung verlangt. Die Bindung selbst ist durch D05 gedeckt (jede Erweiterung gegenüber OKF v0.1 trägt einen benannten Schalter) und durch den Präzedenzfall CHECK-7, der dieselbe Bindung für die `tag-registered`-Check-Regel bereits ausspricht — TAGS.md ist dieselbe Erweiterung, hier von der Registrierungsseite statt der Prüfseite aus betrachtet.

## Offene Fragen

Wie sich `tags register` und `tags validate` verhalten, wenn der Schalter für die Registrierung **deaktiviert** ist — Exit 2 mit Verweis auf den Schalter (Muster COM-16) oder ein stilles No-Op (Muster CHECK-8) — ist nicht durch AUDIT.md oder DECISIONS.md gedeckt und gehört zu T06.

Ob `tags list`/`tags find` im Zug von T07 ein optionales Scope-Positional erhalten (COM-41), ist offen; heute schneidet keiner der vier Modi den Store ein, und kein Finding verlangt eine Änderung.

Ob das Fuzzy-Ranking von `fuzzy_matches()` (Score-Schwelle 0.5, Merge-Reihenfolge fzf-Treffer vor Differenz-Treffern) 1:1 erhalten bleibt oder unter D04 durch `nucleo-matcher`/`strsim` mit einer anderen internen Gewichtung ersetzt wird, ist laut Portierungsanalyse in AUDIT.md nicht vorgeschrieben — die Capability „ähnliche Tags finden" ist der Fixpunkt, nicht dieses konkrete Ranking.

Ob die MCP-Oberfläche künftig `register`/`validate` zusätzlich zu `list`/`find` exponiert, ist nicht durch ein Finding gedeckt; der heutige Docstring markiert das als bewusste CLI-only-Entscheidung, und nichts in AUDIT.md widerspricht dem für `tags` speziell.
