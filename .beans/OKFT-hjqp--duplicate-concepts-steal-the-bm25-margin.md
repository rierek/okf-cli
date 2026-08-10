---
# OKFT-hjqp
title: Duplicate concepts steal the BM25 margin
status: completed
type: bug
priority: normal
created_at: 2026-08-10T12:58:43Z
updated_at: 2026-08-10T14:21:53Z
parent: OKFT-hkze
---

## Objective (User Story)
As the catalogue owner, I want a concept to exist once, so that a literal query does not lose its lexical top-1 margin to its own copies.

## Evidence (MODUS-B-REPORT B02)
`ralph-wiggum-loop` exists three times (`ai-wiki/`, `general-knowledge-wiki/ai-agentic-coding/`, `claude-code-wiki/sessions-workflow/`, three distinct md5), `integration` twice (`ai-wiki/`, `general-knowledge-wiki/ai-agentic-coding/`). In run R5 the query `ralph wiggum loop` matched three titles verbatim and STILL fell through to the semantic arm — the agent's hypothesis is that the copies split the margin the conditional-handover rule tests for.

## EARS Acceptance
- THE margin hypothesis SHALL be measured before any merge — `find` over the affected queries with and without the duplicates present, on a catalogue copy, never on the live one.
- WHERE the measurement confirms it, THE duplicates SHALL be merged through the `ce-okf` skill, keeping the richest copy and redirecting crosslinks.

## Success Criteria
- SC-001: measurement recorded, hypothesis confirmed or refuted in writing.
- SC-002: on confirmation, one canonical concept per topic and no dangling wikilinks (`okf-cli check` clean).

## Note
Whether more duplicates exist beyond these two is unknown — a catalogue-wide near-duplicate scan is part of the measurement, not a separate task.


## Done 2026-08-10 (commit 8ff2f64, Korrektur e242110)

Gemessen statt geglaubt. Vollständiger Befund: `docs/okf-revision/B02-DUPLICATE-MARGIN.md`.

SC-001 erfüllt, **die Hypothese ist widerlegt**. Auf einer Katalogkopie fällt bei `ralph wiggum loop` der Zweitplatzierte nach Entfernen zweier Kopien von `score 100` auf `78`; `_keyword_top1_is_confident` verlangt auf der 0..100-Skala aber `top2 <= 66`, die Schwelle reißt also weiterhin und der semantische Arm besitzt das Ranking unverändert. Bei `integration` war die Kopie nie der Zweitplatzierte — das war `km-wiki/integriertes-wissensmanagement` mit `98` — und nach dem Entfernen wird der Margin sogar schlechter (98 auf 99), das Zielkonzept verliert seinen lexikalischen Platz 1. Die Duplikate nehmen sich den Margin nicht; sie sind für dieses Ranking irrelevant.

SC-002 entfällt damit als Bedingung dieses beans: die EARS-Klausel bindet den Merge an eine Bestätigung der Messung, die nicht eingetreten ist. Der Merge bleibt sinnvoll — aber als Katalog-Hygiene, nicht als Retrieval-Fix, und mit einem anderen Akzeptanzkriterium als „danach gewinnt der lexikalische Arm". Er ist nach `OKFT-mac3` ausgelagert, weil der Scan die Größenordnung verändert hat: nicht zwei Gruppen, sondern 105 (88 Slug-, 17 zusätzliche Titel-Gruppen, 222 Dateien), davon 66 Gruppen mit 132 Dateien allein auf der Achse `ai-wiki` gegen `general-knowledge-wiki`. Das ist eine Richtungsentscheidung über zwei Bundles, keine Einzelfallbereinigung.

Der Katalog blieb bitweise unverändert: `git status` vor und nach der Messung leer, alle 2590 Konzeptdateien gegen die Eingangs-md5 nachgerechnet, 0 Abweichungen. Die Byte-Drift von `.fts/fts.sqlite` stammt nachweislich von einem parallel laufenden Fremdprozess, nicht von der Messung — Indexinhalt per BM25-Rohwertvergleich als identisch belegt.

Nebenbefund, der über dieses bean hinausgeht und nach `OKFT-8l96` ausgelagert ist: über alle 48 kanonischen Eval-Queries besitzt der lexikalische Arm das Ranking genau einmal, und das nur über `len(hits) == 1`. Der kleinste je gemessene `top2` über alle Mehrtreffer-Queries ist 69, nötig wären `<= 66`.
