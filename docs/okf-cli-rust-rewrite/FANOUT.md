---
type: Runbook
title: "SPEC-Fan-out — Zuschnitt, Prompt und Abnahme"
description: "Wie die 22 verbleibenden Kommando-SPECs auf zehn Subagents verteilt werden, was in jedem Prompt steht und woran die Abnahme hängt."
tags:
  - okf-cli
  - spec
  - subagents
---

# SPEC-Fan-out — Zuschnitt, Prompt und Abnahme

Arbeitsdokument für die Orchestrierung. Es steht auf Platte, damit die Fortsetzung nach einem Kontext-Compact nicht vom Gedächtnis abhängt.

## Stand

| Was | Wo |
|---|---|
| Branch | `docs/rust-rewrite-spec`, Worktree `/Users/erik/dev/okf-tools-spec`, Basis `main @ a73a60e` |
| Commits | `68c4573` Grundlage · `9a16222` Pilot `check` |
| Fertig | `spec/README.md`, `spec/_common.md` (COM-1..COM-41), `spec/check.md` (CHECK-1..CHECK-20) |
| Gate | `just spec-check` — 62 Requirements, 0 Verstöße |
| Offen | die 22 Dateien unten, danach T06 |
| Zweiter Branch | `fix/b01-b02-bundle-validation` @ `b5a9f1d` — der `cmd_index`/`cmd_visualize`-Fix, wartet auf Rebase |

**Koordination:** Eine parallele Session realisiert Milestone `okf-cli-huow` im Haupt-Workdir `/Users/erik/dev/okf-tools` direkt auf `main`. Regel in beide Richtungen: kein Merge auf `main` ohne gegenseitiges grünes Licht, und **keine** Schreiboperation im Haupt-Workdir — Löschen eingeschlossen. Der Peer meldet sich nach seinem Blatt `okf-cli-fu7o` (fasst `cmd_index` an) und am Kettenende mit dem finalen `main`-Stand für den Rebase.

## Zuschnitt

Zehn Agenten, 22 Dateien. Gebündelt wird nach fachlicher Verwandtschaft, nicht nach Dateigröße — ein Agent, der `fix-crosslinks` und `fix-xml-tags` zusammen schreibt, sieht ihre gemeinsame Struktur; zwei getrennte Agenten erfinden sie zweimal verschieden.

| # | Agent | Dateien | Warum zusammen |
|---|---|---|---|
| 1 | trivial-readers | `info.md` `read.md` `toc.md` | Drei kleine Leser ohne Filter, fast identische Struktur |
| 2 | listing-readers | `list.md` `index.md` `recent.md` | Gefilterte Listen; `index` trägt die `--full`-Dualität (I08), `recent` die git-Abhängigkeit |
| 3 | search | `find.md` `build-index.md` | Schwergewicht: zwei Arme, Handover-Gate, Score-Skalen, Degradation; `build-index` ist die Voraussetzung des lexikalen Arms |
| 4 | references | `refs.md` `wikilinks.md` | Beide lösen Links auf, beide unterscheiden resolved/ambiguous/unresolved |
| 5 | tags-verbs | `tags.md` | Vier Modi, die zu Subkommandos werden (I01) — allein, weil die Auftrennung eine eigene Denkaufgabe ist |
| 6 | tag-mutations | `merge-tags.md` `remove-tags.md` `normalize-tags.md` | Eine Familie mit identischer Mutations-Mechanik; ein Agent hält sie konsistent |
| 7 | text-fixers | `fix-crosslinks.md` `fix-xml-tags.md` `rewrite-path.md` | Drei Textersetzer, alle heute `--check`, künftig `--apply` (I03) |
| 8 | structure | `reindex.md` | Marker-Blöcke, `--init`, `--force`, Multi-Section-Refusal — eigene Mechanik |
| 9 | rename | `rename.md` | Schwergewicht: Referenz-Integrität über Crosslinks *und* Wikilinks, `git mv`, Reindex der betroffenen Bundles |
| 10 | surface | `prime.md` `log.md` `visualize.md` `mcp.md` | Ausgabe-Oberflächen ohne gemeinsame Mechanik; `mcp.md` gehört hierher, weil es dieselbe Frage stellt — was reicht das Tool nach außen |

Reihenfolge: 1, 2, 4, 6, 7 können sofort parallel laufen. 3, 5, 9, 10 sind die inhaltlich schweren und bekommen mehr Aufmerksamkeit im Review. 8 ist mittel.

## Prompt-Gerüst

Jeder Agent bekommt denselben Rahmen, nur die Dateiliste wechselt.

````
Du schreibst EARS-SPEC-Dateien für den Rust-Rewrite der okf-CLI.

Arbeitsverzeichnis: /Users/erik/dev/okf-tools-spec
Deine Dateien: docs/okf-cli-rust-rewrite/spec/<X>.md, <Y>.md

PFLICHTLEKTÜRE, in dieser Reihenfolge, vollständig:
1. docs/okf-cli-rust-rewrite/spec/README.md   — Notation, Format, Nummernraum, Fallen
2. docs/okf-cli-rust-rewrite/spec/_common.md  — COM-1..COM-41, gelten für dein Kommando mit
3. docs/okf-cli-rust-rewrite/spec/check.md    — die Referenz-Datei. Bau deine genauso.
4. docs/okf-cli-rust-rewrite/AUDIT.md         — Findings B01-B06, I01-I14
5. docs/okf-cli-rust-rewrite/DECISIONS.md     — D05-D07

REGELN
- Systemname ist immer "THE okf binary". Sechs zugelassene EARS-Formen, siehe README.
- Präfix je Datei ist der Kommandoname in Großbuchstaben, Nummern ab 1.
- Wiederhole keine COM-Regel. Verweise auf die COM-Nummer und spezifiziere nur,
  was dein Kommando darüber hinaus leistet oder anders macht.
- Jede Anforderung, die vom heutigen Verhalten abweicht, braucht Deckung durch ein
  Finding (I0n/B0n) oder eine Entscheidung (D0n). Ohne Deckung: nicht als Requirement
  schreiben, sondern unter "Offene Fragen" notieren.
- Nenne KEINEN Profil-Schalternamen. Die Schalter-Definition ist Task T06 und
  bewusst noch offen. Schreib "an einen Schalter gebunden", nicht den Namen.
- Grounding-Pflicht: jeder Abschnitt "Grounding" nennt cli/okf-cli.py:<zeile>.
  Lies den echten Code. Eine SPEC ohne Grounding ist eine Wunschliste.
- Falle: die EARS-Keywords when/if/where/while/then dürfen in einer Zeile nicht
  ausschließlich kleingeschrieben vorkommen. Umformulieren, nicht großschreiben.
  "the" ist frei, weil jedes Requirement "THE okf binary" enthält.
- Falle: Modalverben should/must/will/can/may/might/could/would sind in der
  ganzen Zeile verboten, auch im Nebensatz. Begründungen kommen in einen
  Fließtext-Abschnitt unter die Tabelle, nicht in die Tabelle.

ABGABEKRITERIUM
  cd /Users/erik/dev/okf-tools-spec && just spec-check docs/okf-cli-rust-rewrite/spec/<X>.md
muss "0 violations" melden. Committe NICHT. Schreibe nur deine Dateien.

RÜCKGABE (genau dieses Format)
  datei: <pfad>
  requirements: <n>
  gate: OK | FAIL
  deltas: <Liste der Finding-IDs, die du als Deckung benutzt hast>
  offene_fragen: <Liste, oder "keine">
  grounding_zeilen: <Liste der cli/okf-cli.py:<zeile>-Referenzen>
````

## Abnahme

Das Gate ist notwendig, nicht hinreichend. `just spec-check` prüft Syntax, Duplikate und Modalverben — es prüft **nicht**, ob eine Anforderung stimmt, vollständig ist oder erfunden wurde. Nach dem Fan-out deshalb drei Durchgänge:

1. **Deckungsprüfung.** Jedes Delta gegen `AUDIT.md`/`DECISIONS.md` verifizieren. Ein Agent, der ein Finding zitiert, das die Anforderung nicht trägt, hat sie erfunden.
2. **Grounding-Stichprobe.** Pro Datei zwei bis drei `cli/okf-cli.py:<zeile>`-Referenzen öffnen und prüfen, ob dort steht, was behauptet wird. Halluzinierte Zeilennummern sind die wahrscheinlichste Fehlerklasse.
3. **Konsistenz-Review über alle Dateien.** Widersprechen sich zwei Kommando-SPECs? Nennt eine ein Flag, das eine andere anders benutzt (COM-36)? Hat jemand doch einen Schalternamen erfunden? Das ist der Schritt, den man am ehesten auslässt, und der einzige, der den Fan-out als Ganzes prüft.

Erst danach T06, dann die Rust-Arbeit.
