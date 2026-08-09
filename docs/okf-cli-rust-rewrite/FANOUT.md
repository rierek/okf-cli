---
type: Runbook
title: "SPEC-Fan-out — Zuschnitt, Ertrag und Abnahme"
description: "Wie die 23 Kommando-SPECs auf zehn Subagents verteilt wurden, was der parallele Schnitt gefunden hat, was das Gate nicht sieht und wie der Wiedereinstieg läuft."
tags:
  - okf-cli
  - spec
  - subagents
---

# SPEC-Fan-out — Zuschnitt, Ertrag und Abnahme

Abgeschlossen. Dieses Dokument war der Plan und ist jetzt das Protokoll — Wiedereinstieg für die Arbeit danach steht unter [Stand](#stand) und [Was offen ist](#was-offen-ist).

## Stand

| Was | Wo |
|---|---|
| Branch | `docs/rust-rewrite-spec`, Worktree `/Users/erik/dev/okf-tools-spec`, Basis `main @ a73a60e` |
| Commits | `68c4573` Grundlage · `9a16222` Pilot `check` · `74a75d4` Fan-out-Plan · `84fdeef` die 23 Kommando-SPECs · `aeb4058` Abnahme-Korrekturen |
| Umfang | 26 Dateien, 348 Requirements |
| Gate | `just spec-check` — 0 Verstöße |
| Zweiter Branch | `fix/b01-b02-bundle-validation` @ `b5a9f1d`, Suite 559 grün — der `cmd_index`/`cmd_visualize`-Fix, wartet auf Rebase |
| Tracker | Milestone `okf-cli-03o1`, Spec-Phase `okf-cli-v225` (abgeschlossen) |

**Koordination:** Eine parallele Session realisiert Milestone `okf-cli-wuiv` im Haupt-Workdir `/Users/erik/dev/okf-tools` direkt auf `main`. Regel in beide Richtungen: kein Merge auf `main` ohne gegenseitiges grünes Licht, und **keine** Schreiboperation im Haupt-Workdir — Löschen eingeschlossen. Auch beans wurden deshalb aus dem Worktree heraus angelegt, der sein eigenes `.beans/` trägt.

## Zuschnitt

Zehn Agenten auf Sonnet, 23 Dateien, gebündelt nach fachlicher Verwandtschaft statt nach Dateigröße — ein Agent, der `fix-crosslinks` und `fix-xml-tags` zusammen schreibt, sieht ihre gemeinsame Struktur; zwei getrennte Agenten erfinden sie zweimal verschieden.

| # | Agent | Dateien | Reqs |
|---|---|---|---|
| 1 | trivial-readers | `info` `read` `toc` | 26 |
| 2 | listing-readers | `list` `index` `recent` | 34 |
| 3 | search | `find` `build-index` | 39 |
| 4 | references | `refs` `wikilinks` | 26 |
| 5 | tags-verbs | `tags` | 20 |
| 6 | tag-mutations | `merge-tags` `remove-tags` `normalize-tags` | 28 |
| 7 | text-fixers | `fix-crosslinks` `fix-xml-tags` `rewrite-path` | 31 |
| 8 | structure | `reindex` | 18 |
| 9 | rename | `rename` | 26 |
| 10 | surface | `prime` `log` `visualize` `mcp` | 34 |

Der Prompt trug über das gemeinsame Gerüst hinaus drei Dinge, die sich als nötig erwiesen: das Schreibverbot im Haupt-Workdir als harte Regel ganz oben, das Verbot von `AskUserQuestion` (ein Agent auf einem Modal meldet `working` und blockiert unsichtbar), und pro Agent den Kontext, den nur der Orchestrator hatte — `index`/`visualize` tragen den ungemergten B01/B02-Fix, `mcp` bekommt D07 ausformuliert, `rename` erfährt, dass es der Präzedenzfall für COM-31 ist und nicht das Delta.

## Der Ertrag des parallelen Schnitts

Sechs Querschnitts-Regeln, die kein einzelner Autor gefunden hätte. Sie wurden nicht dadurch sichtbar, dass jemand sorgfältiger las, sondern dadurch, dass mehrere unabhängige Autoren an derselben Stelle stolperten.

| Regel | Woher |
|---|---|
| COM-42 — `--json` auch auf Mutations-Vorschauen | vier Tag- und Struktur-Kommandos unabhängig |
| COM-43/COM-44 — ein abgeschalteter Schalter unterdrückt auch die Korrektur, nicht nur die Prüfung, und meldet das | `tags`, `fix-crosslinks`, `fix-xml-tags` |
| COM-45 — `--force` hat eine Bedeutung: über eine Sicherheitsverweigerung hinweggehen | `reindex` gegen `rename` |
| MCP-13/MCP-14 — Tool-Namen für Subkommandos, kein Tool für `mcp serve` | `tags.md` und `mcp.md` aus entgegengesetzter Richtung |

Ein einzelner Autor hätte jede dieser Lücken mehrfach umschifft, ohne sie zu bemerken. Das ist der eigentliche Grund für den Fan-out — nicht die Geschwindigkeit.

Drei Agenten haben außerdem aktiv gegengesteuert statt abgeliefert. Der `references`-Agent hat die Prämisse des Prompts widerlegt: `refs` löst über Dateisystempfade auf, Mehrdeutigkeit ist dort strukturell unmöglich, und statt sie zu erfinden hat er die Asymmetrie zu `wikilinks` in beiden Dateien dokumentiert. Der `surface`-Agent hat für den ungemergten B01/B02-Fix keine Zeilennummer erfunden, sondern offengelegt, dass er ihn per `git show` gelesen hat. Der `text-fixers`-Agent hat eine Kontrastentscheidung getroffen — Schalter-Bindung für die zwei Kommandos mit `check`-Pendant, bewusst keine für `rewrite-path` — und sie als Entscheidung dokumentiert statt als Lücke gelassen.

## Was das Gate nicht sieht

`just spec-check` prüft EARS-Form, doppelte IDs und Modalverben. Es prüft **nicht**, ob eine Anforderung stimmt, vollständig ist oder erfunden wurde.

**Fünf von 23 Dateien nannten für die Argparse-Registrierung einen fremden `_sub()`-Block** — `tags`, `refs`, `reindex`, `rename`, `wikilinks`, alle um 20 bis 30 Zeilen nach hinten verschoben. Die Funktionsrümpfe waren durchweg korrekt; nur dieser eine Block nicht. Ursache ist die Codeform: zwei Dutzend `_sub()`-Aufrufe hintereinander, und der Kommandoname kommt im Hilfetext des Nachbarn vor. Alle fünf gegen die Registrierungs-Karte berichtigt.

Wer diese SPEC fortschreibt, holt sich die Karte so:

````
grep -n '_sub(sub, "' cli/okf-cli.py
````

**Eine erfundene Bezeichnung in 26 Dateien:** `--summary` in `index.md`. Sie steht als D08 mit Status 🟡 im Decision-Log, ausdrücklich als nicht PO-bestätigt, und ist bean `okf-cli-e9l8`.

**Deckungsprüfung sauber.** Neun Delta-Zeilen stützen sich auf COM-Nummern statt auf ein Finding; jede zitierte COM-Regel ist ihrerseits gedeckt (COM-19 kodifiziert bestehendes Verhalten, COM-22 hängt an I09, COM-28 an I04, COM-32 an B02). Keine erfundene Anforderung. `resolve_concept()` wird nur von `read` und `toc` geerbt und ist dort konsistent gespalten.

## Wenn jemand das wiederholt

Der Prompt hatte zwei Defekte, die sich erst im Ergebnis zeigten.

**„Lies den echten Code" reicht nicht als Grounding-Auflage**, wenn die Zielstelle in einer langen Folge gleichförmiger Aufrufe liegt. Besser: dem Agenten die verbindliche Zeile mitgeben, statt sie ihn suchen zu lassen.

**Eine Bündelungsbegründung im Prompt ist eine Behauptung über den Code**, und sie kann falsch sein. Meine war es bei `refs`/`wikilinks`. Sie so formulieren, dass Widerspruch erwünscht ist — der Agent, der widersprochen hat, hat die bessere Datei geliefert.

Eine Validator-Falle kam dazu, die jetzt im [spec/README.md](./spec/README.md) steht: der Validator matcht auf Wortgrenze, und ein Bindestrich ist eine. `--if-stale` trägt deshalb ein freistehendes `if`, „specifies" dagegen nicht. Lösung ist einfaches Anführungszeichen, nicht Backtick.

## Was offen ist

| bean | Was |
|---|---|
| `okf-cli-bux0` | **T06** — Schalternamen der zehn Erweiterungsregeln, Zuordnung zu `okf`/`catalogue`. Alle Dateien verweisen hierher; `grep -rn T06 spec/` sammelt die Fragen ein. |
| `okf-cli-fcrc` | Rebase und Merge beider Branches, nach dem grünen Licht des Peers |
| `okf-cli-e9l8` | D08 bestätigen oder umbenennen |
| `okf-cli-bu0p` | T07 Store-Abstraktion pro Kommando |
| `okf-cli-fyx1` | T08 `check --profile okf` als Portabilitäts-Gate |
| `okf-cli-unxt` | T09 `plugin/` löschen, index-map-Zeile streichen |

Danach die Rust-Arbeit. Der Fixpunkt dafür ist diese SPEC, nicht die 548 Python-Tests — das ist die Antwort auf Q01 aus [AUDIT.md](./AUDIT.md).
