---
type: Tasks
title: "TASKS — okf-revision"
description: "Actionable units of the maturity revision at full scope, aimed at a grounded plan."
tags:
  - tpic
  - okf-revision
timestamp: 2026-07-25T22:43:35Z
---
# TASKS — okf-cli + okf-mcp Reifegraderhöhung

Scope: full. Ziel = fundierter Plan. Grounds: `00`, `06`, `07`.yaml.
Status: 🟣 Offen · 🔵 In Arbeit · 🟢 Done · 🔴 Abgelehnt · 🟡 Unklar.
Prio-Reihung nach Reifegrad-Hebel (Retrieval > Correctness > Parität-Politur > Doc).

| Txx | Prio | Aufgabe | Quelle | Status |
|-----|------|---------|--------|--------|
| T06 | high | **Retrieval-Fallback**: Synonym/Paraphrase-Null-Treffer beheben — semantische oder hybride Suche in `find` verdrahten. `.tagvec` ist bereits befüllt aber toter Code (nie referenziert) → Kandidat zum Aktivieren ODER bewusst neu bauen | Q05 / 06-retrieval | 🟡 gated Frage A |
| T01 | high | B01 fixen: `okf_index` + `okf_list` MCP-Tools — `--json`-Mismatch okf_mcp.py↔CLI-argparse | B01 / LIVE02-03 | 🟣 |
| T09 | high | Integration-Tests an MCP→Subprozess-Grenze (Tests rufen CLI real als Prozess, nicht nur Python-Funktion) — fängt B01-Klasse | Q03 / 07-tests | 🟣 |
| T02 | med | MCP-Parität: entscheiden + brücken, welche der Wartungs-Verben MCP-Tool werden (Evidenz: Retrieval-Core schon da; Admin-Verben ungenutzt) | I01 / Q02 | 🟡 gated Frage B |
| T03 | med | Root-Safety: Default-`--root` = Script-Dir → Auto-Detect Catalogue oder hart failen | I02 | 🟣 |
| T04 | low | Doc: 18→20 Verben korrigieren (`prime`, `remove-tags`), "100%"-Falschaussage | I03 | 🟣 |
| T05 | low | Doc-Drift: generierte `--help`→md-Referenz statt zeilennummer-verankert | I04 / Q04 | 🟡 gated Q04 |
| T08 | med | `.tagvec`-Herkunft klären: Ad-hoc-Offline-Skript außerhalb Repo → in Repo holen + dokumentieren, sonst nicht reproduzierbar | 06-retrieval | 🟣 |
| T10 | high | Mechanischen Eval-Runner bauen: Golden-File (query→Pfad+Schwelle), ruft find/list/index, emittiert Metrik-Tabelle (Recall@k, MRR, Zero-Hit, Score) | EVAL-DESIGN | 🟣 |
| T11 | high | Golden-Fixtures S1–S4 als versteckte Fake-Konzepte anlegen, je 2 Query-Klassen (literal + paraphrase), Ground-Truth definieren | EVAL-DESIGN | 🟣 |
| T12 | high | **Keyword-Baseline JETZT einfrieren** (vor WS1) — Metriken pro Szenario als Vorher-Wert speichern, sonst Delta nicht messbar | EVAL-DESIGN | 🟣 |
| T13 | low | Agentischer Realismus-Check (Modus B): Test-Agent mit nur okf-Tools + Aufgabe, Erfolg messen. Nicht Metrik-Basis | EVAL-DESIGN | 🟡 gated Q07 |
