---
type: Reference
title: "Rewrite-SPEC — Konventionen und Schreibregeln"
description: "Wie die EARS-Requirements dieser SPEC geschrieben, nummeriert und maschinell geprüft werden — verbindlich für jeden, der eine Kommando-Datei ergänzt."
tags:
  - okf-cli
  - ears
  - requirements
  - spec
---

# Rewrite-SPEC — Konventionen und Schreibregeln

Verbindlich für jede Datei in diesem Ordner. Wer eine Kommando-SPEC schreibt, liest zuerst dieses README und dann [`_common.md`](./_common.md).

Diese SPEC beschreibt das **Ziel** des Rust-Rewrites, nicht den Ist-Zustand der Python-CLI. Sie ist der Fixpunkt, gegen den das Rust-Binary geprüft wird — die Antwort auf [AUDIT.md](../AUDIT.md) Q01, wonach die 548 Python-Tests als Fixpunkt wegfallen, sobald Byte-Gleichheit aufgegeben wird.

## Notation

[[ears-notation]] (Mavin et al., RE'09), **ausschließlich `SHALL`**. Der Haus-Validator akzeptiert genau sechs Formen, alle Keywords in Großbuchstaben:

| Muster | Form | Einsatz |
|---|---|---|
| Ubiquitous | `THE <system> SHALL <response>.` | immer geltende Eigenschaft |
| Event-driven | `WHEN <trigger>, THE <system> SHALL <response>.` | Auslöser/Ereignis |
| State-driven | `WHILE <state>, THE <system> SHALL <response>.` | zustandsabhängig |
| Unwanted behavior | `IF <condition>, THEN THE <system> SHALL <response>.` | Fehler-/Grenzfall |
| Optional feature | `WHERE <feature>, THE <system> SHALL <response>.` | feature-gebunden |
| Complex | `WHILE <state>, WHEN <trigger>, THE <system> SHALL <response>.` | mehrbedingt |

**Systemname ist immer `THE okf binary`.** Nicht „the CLI", nicht „okf", nicht der Kommandoname — der Validator verlangt zwischen Präfix und `SHALL` ein `THE`, und ein einheitlicher Systemname macht die Requirements über 24 Dateien hinweg vergleichbar.

`WHERE` trägt in dieser SPEC eine besondere Last: es ist das Muster für alles, was von einem Profil-Schalter (D05) oder vom Store-Modell (D06) abhängt. Ein Requirement, das nur im Catalogue-Modus oder nur bei aktivierter Erweiterung gilt, ist ein `WHERE`-Requirement — nie ein `THE … SHALL` mit einer Einschränkung in Klammern.

## Format

Markdown-Tabelle wie in [[dev-cli-conformance]], jede Zeile eine Ja/Nein-Audit-Zelle.

````
| ID | EARS-Requirement |
|----|------------------|
| CHECK-1 | WHERE at least one error-severity violation is found, THE okf binary SHALL exit 1. |
````

Genau zwei Spalten. Keine Zusatzspalten für Priorität, Status oder Herkunft — die Zelle ist der Prüfpunkt, alles andere verwässert ihn.

## Nummernraum

**Pro Datei ein eigenes Präfix**, abgeleitet vom Kommandonamen in Großbuchstaben; Querschnitt in `_common.md` ist `COM`.

| Datei | Präfix | Beispiel |
|---|---|---|
| `_common.md` | `COM` | `COM-1` |
| `check.md` | `CHECK` | `CHECK-1` |
| `find.md` | `FIND` | `FIND-1` |
| `fix-crosslinks.md` | `FIX-CROSSLINKS` | `FIX-CROSSLINKS-1` |
| `mcp.md` | `MCP` | `MCP-1` |

Der Grund ist mechanisch: die Kommando-Dateien entstehen **parallel**. Ein globaler Nummernraum kollidiert, sobald zwei Autoren gleichzeitig schreiben; ein Präfix pro Datei kann das nicht. Nummern werden innerhalb einer Datei ab `1` fortlaufend vergeben und **nie wiederverwendet** — eine gestrichene Anforderung hinterlässt eine Lücke, wie `DC-12` im Präzedenzfall.

Der Parser liest die Nummer als die Ziffern nach dem **letzten** Bindestrich, ein Präfix darf also selbst Bindestriche tragen.

## Gate

````
just spec-check                          # alle Dateien
just spec-check docs/okf-cli-rust-rewrite/spec/check.md   # eine
````

`scripts/ears-table-check.js` zieht die Tabellenzeilen und reicht jede Aussage an `validateEarsStatement()` aus dem Haus-Validator `ce-beans-operationalize/scripts/ears-validator.js` weiter. Der Validator wird **nicht** hierher kopiert — es soll genau ein EARS-Regelwerk geben, kein zweites, das davon abdriftet. Zusätzlich prüft der Adapter auf doppelte IDs innerhalb einer Datei.

**Grün ist Abgabekriterium.** Eine SPEC-Datei gilt nicht als fertig, solange `just spec-check` sie rot meldet.

## Fallen

**Modalverben gelten für die ganze Zeile, nicht nur für den SHALL-Kern.** Verboten sind `should, must, will, can, may, might, could, would` — auch im Begründungs-Nebensatz. Ein Requirement wie „… SHALL reject the path, since a relative path **could** escape the root" fällt durch, obwohl der Kern korrekt ist. Ausgenommen sind Vorkommen in Anführungszeichen: der Validator blendet `"…"` und `'…'` aus, damit eine zitierte Ausgabemeldung nicht anschlägt.

Begründungen gehören deshalb **nicht in die Tabelle**, sondern in einen Fließtext-Abschnitt darunter. `dev-cli-conformance` macht das mit seinem Abschnitt „DC-10/DC-11 — warum zwei Zeilen" vor.

**Kein EARS-Keyword kleingeschrieben, solange es nicht auch groß vorkommt.** Betroffen sind `when, the, shall, if, then, while, where`. Die Validator-Regel feuert, wenn ein Keyword in einer Zeile *ausschließlich* klein auftaucht. Praktisch heißt das:

- `the` ist frei, weil jedes Requirement `THE okf binary` enthält.
- `when`, `if`, `where`, `while`, `then` sind **nicht** frei. Ein `WHERE`-Requirement, das im Fließtext „when the index is stale" schreibt, fällt durch. Umformulieren („with a stale index"), nicht großschreiben — ein zweites Muster-Keyword mitten im Satz macht die Zeile unlesbar.

**Ein Flagname mit Bindestrich zerfällt in Tokens.** Der Validator matcht auf Wortgrenze (`\bif\b`), nicht auf Substring — „specifies" und „whenever" schlagen deshalb nicht an. Ein Bindestrich *ist* aber eine Wortgrenze, und damit enthält `--if-stale` ein freistehendes `if`. Betroffen ist jeder Flagname, dessen Bestandteile ein EARS-Keyword treffen. Lösung: die Zelle in einfache Anführungszeichen setzen (`'--if-stale'`), denn der Validator blendet `'…'` und `"…"` aus. **Backticks reichen nicht** — sie werden nicht ausgeblendet.

**Der Präzedenzfall ist nicht validator-konform.** `dev-cli-conformance` fällt mit 16 von 16 Requirements durch (`The dev-CLI SHALL …` statt `THE … SHALL`). Die Tabellenform von dort ist übernommen, die Schreibweise der Statements **nicht** — hier gilt die Validator-Form, weil hier ein Gate läuft. Wer die beiden nebeneinander liest, sollte das wissen und nicht die dortige Schreibweise kopieren.

**Ein Requirement, eine Aussage.** Ein `AND` in der Systemantwort ist fast immer zwei Requirements. Der Präzedenzfall hat genau daran eine Zeile gespalten, nachdem ein Feld-Audit zeigte, dass die beiden Hälften unabhängig voneinander verletzt werden.

**Kein Ist-Zustand ohne Beschluss.** Diese SPEC beschreibt das Ziel. Wo sie vom heutigen Verhalten abweicht, muss die Abweichung durch ein Finding aus [AUDIT.md](../AUDIT.md) (I01–I14, B01–B06) oder eine Entscheidung aus [DECISIONS.md](../DECISIONS.md) (D01–D07) gedeckt sein. Neue Anforderungen zu erfinden, die nirgends beschlossen sind, ist der häufigste Fehler beim parallelen Schreiben — im Zweifel als offene Frage unter die Tabelle schreiben, nicht als Requirement.

**Grounding-Pflicht.** Jede Kommando-Datei nennt unter der Tabelle die Stelle im heutigen Code, aus der das Verhalten stammt, als `cli/okf-cli.py:<zeile>`. Eine SPEC ohne Grounding ist eine Wunschliste.

## Aufbau einer Kommando-Datei

````markdown
---
type: Spec
title: "<command> — EARS-Requirements"
description: "…"
tags: [okf-cli, ears, requirements, spec]
---

# <command> — EARS-Requirements

Ein Absatz: was das Kommando leistet und für wen.

## Requirements

| ID | EARS-Requirement |
|----|------------------|
| …  | …                |

## Grounding

Wo das Verhalten heute lebt, mit `cli/okf-cli.py:<zeile>`.

## Deltas gegenüber heute

Was sich ändert, je mit Verweis auf das deckende Finding (I0n/B0n/D0n).

## Offene Fragen

Nur falls vorhanden.
````
