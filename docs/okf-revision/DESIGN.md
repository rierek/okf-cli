# DESIGN — Reifegraderhöhung okf-cli + okf-mcp

Konzeptionelles Verdichtungs-Artefakt der Think-Session (2026-07-25). Kein Code, keine EARS.
Evidenz: `00`–`07`.yaml. Entscheidungen: `DECISIONS.md`. Offene, nicht-gatende Punkte: `QUESTIONS.md`.

## Problem

Ausgangsfrage: „Wie gut sind okf-cli + okf-mcp aktuell?" Motiv: MCP↔CLI-Abweichung.

Befund nach Legwork + Live-Tests: **reifer Kern, schwache Ränder.** Die CLI ist ein solides,
dependency-freies Einzweck-Tool mit 20 Verben, referenzieller Integrität (`rename`) und einer
Test-Suite. Die Reifegrad-Lücken sitzen an drei Rändern:

1. **Retrieval-Semantik** (höchster Hebel) — `find` ist reines Keyword/Substring-Matching
   (okf-cli.py:538-574). Synonym-/Paraphrase-Queries liefern **stillen Null-Treffer**, kein
   Fallback. Eine semantische Fähigkeit existiert als Daten (`.tagvec`, 1277 Embeddings,
   bge-m3 + voyage-3-large), ist aber **toter Code** — nirgends im Repo referenziert.
2. **MCP→Subprozess-Grenze** — `okf_index`/`okf_list` werfen live Fehler (`--json`-Mismatch, B01).
   Die Test-Suite kann das strukturell nicht fangen: sie ruft Python-Funktionen direkt, nie die
   CLI als Prozess (wie es die MCP-Schicht tut).
3. **Root-Sicherheit + Doc-Drift** — Default-`--root` zeigt aufs Script-Verzeichnis; die
   kanonische Referenz-Doku ist stale (18 statt 20 Verben, behauptet "100%").

## Workstreams (entschieden)

Priorität nach Reifegrad-Hebel, nicht nach Aufwand.

### WS1 — Retrieval-Qualität (D04, höchster Hebel)
- `.tagvec`-Herkunft + embedded Scope klären (Tags vs. Body?) — gatet Umfang. (T08)
- Hybrid: semantischen Fallback in `find` verdrahten (Keyword-Primärpfad + semantischer
  Backstop bei schwachem/Null-Treffer). `.tagvec` aktivieren oder auf Body-Embeddings erweitern.
- **Search+Filter-Komposition** (08:FIL03/04): `find` kann nicht auf `type`/`tag`/`bundle`
  eingegrenzt werden; `find` und `list` sind disjunkt. Reifegrad = kombinierbar machen
  (Keyword-Suche mit Scope/Typ-Filter in einem Call).
- **Score-Transparenz** (08:SCO03): nur aggregiertes `score/max` ausgegeben, kein Feld-/Term-
  Breakdown → Ranking-Vertrauen begrenzt. Optional Breakdown emittieren.
- Offen (nicht-gatend): Ranking-Fusion Keyword×Semantik, Schwellwert für Fallback-Trigger.

### WS2 — Correctness + Test-Integrität (D06)
- B01 fixen: `--json`-Vertrag zwischen `okf_mcp.py` und CLI-argparse angleichen. (T01)
- Integration-Test-Layer, der MCP-Tools über den echten Subprozess-Pfad prüft — fängt
  B01-Klasse. (T09)

### WS3 — MCP-Parität, gezielt (D05)
- Nur agent-relevante Lücken brücken (Kandidaten: `check`, `tags`, `refs`). (T02)
- Write/Admin-Verben (`merge-tags`, `normalize-tags`, `fix-*`, `rename`, `log`, `visualize`,
  `prime`, `info`) bleiben bewusst CLI-only — als Absicht dokumentiert (Safety-Oberfläche klein).

### WS4 — Robustheit
- Root-Safety: Default-`--root` = Script-Dir entschärfen — Catalogue-Autodetect oder hart
  failen ohne `--root`. (T03)

### WS5 — Doku (D07)
- `okf-cli-mcp-overview.md` als kanonische Referenz **erhalten + entstalen**: 18→20 Verben,
  "100%"-Falschaussage raus. (T04)
- Optional: Verb-Tabellen teil-generiert aus `--help`, Prosa/Narrativ handgepflegt. (T05)

## Sequenzierung

```
WS2.B01 (schnell, entblockt MCP)  ─┐
WS1.T08 (.tagvec-Herkunft)  ───────┼─→  WS1-Hybrid (Kern-Arbeit)
WS2.T09 (Integration-Tests) ───────┘        │
WS3 / WS4 (parallel, unabhängig)            │
WS5-Doc (nachlaufend, spiegelt Endstand) ←──┘
```

Abhängigkeit: WS1-Hybrid startet erst nach T08 (Scope der Embeddings unklar bis dahin).
B01 + T09 sind unabhängig sofort machbar und liefern schnellen Reifegrad-Gewinn.

## Realisierungs-Kette (Think → Plan → Beans)

Persistenz-Pfad: **DESIGN → PLAN → BEANS**. Diese Session liefert DESIGN; der Planner verdichtet
zu PLAN (`tools/okf-tools/docs/okf-revision/PLAN.md`, D08); `ce-beans-operationalize` überführt
in beans. Erfolg wird an der Eval-Metrik (D09) gemessen, nicht an "fertig".

Phasen (Reihenfolge löst D09-eval-first mit User-Sequenz auf):

1. **Grundlagen-A — Mess- & Correctness-Fundament** (muss VOR der Optimierung stehen)
   - Eval-Harness + Golden-Fixtures S1–S4 + Keyword-**Baseline einfrieren** (T10, T11, T12)
   - B01-Fix (T01) + Integration-Test-Layer an MCP→Subprozess-Grenze (T09)
2. **Grundlagen-B — technische Optimierung** (das zu Messende)
   - WS1 Hybrid-Retrieval: `.tagvec`-Herkunft (T08) → semantischer Fallback + Search/Filter-
     Komposition + Score-Transparenz
   - WS3 gezielte MCP-Parität (T02), WS4 Root-Safety (T03)
3. **Test-Koordinator — Erfolgs-Gate** (NACH der Optimierung)
   - Eval erneut fahren → Delta pro Metrik/Szenario → Regressions-Gate + Reifegrad-Nachweis
   - Modus B (agentischer Realismus-Check) optional (T13)
4. **Doku nachlaufend**: WS5 (T04/T05) spiegelt Endstand.

Jede Phase wird als bean-Epos/Tasks persistiert; der Test-Koordinator ist ein eigenes bean, das
gegen die eingefrorene Baseline abnimmt.

## Out of Scope
- Volle MCP-Parität 20/20 (D05 verworfen).
- Reine `--help`-Generierung, die die Referenz-Prosa ersetzt (D07).
- Retrieval-UI/Visualisierung.

## Nicht-gatende offene Punkte (→ QUESTIONS.md)
- Q04: Grad der Doc-Auto-Generierung (Teil-Tabellen vs. voll).
- Ranking-Fusion + Fallback-Schwellwert (Detail von WS1, Plan-Phase).
