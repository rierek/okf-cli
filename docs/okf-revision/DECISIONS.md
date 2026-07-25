# DECISIONS — okf-cli + okf-mcp Reifegraderhöhung

| Dxx | Hintergrund | Entscheidung | Status |
|-----|-------------|--------------|--------|
| D01 | Scope-Frage Q01 | Full-scope: Session erstellt fundierten Reifegrad-Plan, nicht nur B01-Fix | 🟢 |
| D02 | User-Beobachtung deckt sich mit I01/B01 | MCP↔CLI-Abweichung ist Kernthema, aber getrennt: B01 (kaputt) ≠ I01 (fehlt) | 🟢 |
| D03 | Retrieval = Hauptzweck | Retrieval-Zweckmäßigkeit kritisch geprüft, nicht als gegeben angenommen | 🟢 |
| D04 | Q05: find keyword-only, `.tagvec` verwaist, Synonym→Null-Treffer | **Retrieval-Strategie = Hybrid**: semantischen Fallback in `find` verdrahten; `.tagvec` Herkunft/Umfang erst prüfen (T08), dann aktivieren oder auf Body-Embeddings erweitern. Höchster Reifegrad-Hebel | 🟢 |
| D05 | Q02: Agents erreichen okf nur via MCP; Retrieval-Core schon gebrückt; Admin-Verben ungenutzt | **MCP-Parität = nur agent-relevante Lücken** (Kandidaten check/tags/refs). Write/Admin-Verben bewusst CLI-only, als Absicht dokumentiert | 🟢 |
| D06 | Q03: Test-Suite existiert, ruft aber nur Python-Funktionen direkt | B01-Ursache = Integration-Gap an MCP→Subprozess-Grenze. Reifegrad-Plan enthält Integration-Test-Layer (T09) | 🟢 |
| D07 | User-Mid-Turn: Doc stale aber relevant | `okf-cli-mcp-overview.md` bleibt **kanonische Referenz** — erhalten + entstalen (T04), nicht durch reine `--help`-Generierung ersetzen. Höchstens Verb-Tabellen teil-generiert | 🟢 |
| D08 | Global-Regel: Pläne gehören ins Repo, nicht in Vault | Research-Sammlung bleibt in `Vault/okf-revision/`; der ausführbare **PLAN** der Folge-Session gehört nach `tools/okf-tools/docs/okf-revision/PLAN.md` | 🟢 |
| D09 | Optimierung muss messbar sein (User) | **Eval-first**: Keyword-Baseline (S1–S4, 2 Query-Klassen) wird VOR WS1 eingefroren; WS1-Erfolg = Metrik-Delta. Mechanischer Runner (Modus A) ist Metrik-Basis, agentisch (B) nur Sanity | 🟢 |
| D10 | S2-Analyse | S2 misst Location-Sensitivity komparativ, nicht find-Recall — `find` ist per Design ortsblind (`:544`), das ist selbst der Befund | 🟢 |
