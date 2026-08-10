---
type: TPIC
title: "QUESTIONS — okf-revision"
description: "Open questions of the maturity revision; convergence to a plan required the plan-relevant ones to be resolved first."
tags:
  - tpic
  - okf-revision
timestamp: 2026-07-25T22:43:35Z
---
# QUESTIONS — okf-cli + okf-mcp Reifegraderhöhung

Konvergenz zu Plan erst, wenn die planrelevanten Qs aufgelöst sind. Grounds: `06-retrieval-quality.yaml`, `07-tests-and-usage.yaml`.

| Qxx | Hintergrund | Relevanz | Frage | Status |
|-----|-------------|----------|-------|--------|
| Q01 | Scope | steuert alles | Nur Fix oder Hardening? | 🟢 full-scope (User 2026-07-25) |
| Q02 | 11 CLI-only-Verben; Evidenz: Agents erreichen okf nur via MCP, Retrieval-Core (find/read/toc/index/list) bereits gebrückt; Admin-Verben (merge/normalize/fix-xml/rename/log/visualize/prime/info) von Agents nie genutzt | bestimmt Parität-Umfang | Parität für alle oder nur Retrieval+Wartungs-Subset? | 🟡 Evidenz da, User-Entscheid offen (Frage A/B) |
| Q03 | Test-Suite existiert (`test_okf_cli.py`, 22 Klassen/98 Methoden), ruft aber Python-Funktionen direkt, nicht CLI-Subprozess | Reifegrad-Kern | Fehlt Integration-Layer an MCP→Subprozess-Grenze? | 🟢 Ja — Integration-Gap ist die B01-Ursache; Tests am MCP-Boundary fehlen (→ T07/T09) |
| Q04 | Doc zeilennummer-verankert, driftet | Wartbarkeit | Generierte Referenz aus `--help`? | 🟡 empfohlen ja, User-Präferenz offen |
| Q05 | **Retrieval-Zweckmäßigkeit** — `find` pure keyword/substring, kein Vektor-Aufruf; `.tagvec` (1277 Zeilen, bge-m3+voyage-3) real aber toter Code, nirgends referenziert; Synonym-Query → stiller Null-Treffer, kein Fallback | **höchster Reifegrad-Hebel** | Keyword-only akzeptabel, oder semantische/hybride Suche verdrahten? | 🟢 Hybrid (User) |
| Q06 | Eval-Fixtures (S1–S4) — Ablage | bestimmt Baseline-Sauberkeit vs. Realismus | Isolierter Eval-Root (sauber, reproduzierbar) oder in echten Katalog geseedet (konkurriert mit 1783 Docs)? | 🟡 deferred → Plan-Phase (nicht design-gatend) |
| Q07 | Eval-Modi (mechanisch A / agentisch B) | Aufwand vs. Realismus | Nur A (Metrik-Rückgrat) oder A+B (plus Agenten-Realismus-Check)? | 🟡 deferred → Plan-Phase (nicht design-gatend) |
