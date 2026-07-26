# okf-tools — Session State Transfer (Pointer-File)

> SSTD hält kein Wissen — nur Sink-Registry + Entry-Point (D01). Decisions/durables Wissen → OKF-Bundle, Work-State → beans, Code-Historie → git.

## Sink-Registry

| Sink | Hält | Lesen | Fundstelle |
|---|---|---|---|
| **OKF-Bundle** | Konzepte, Decisions, Patterns | `okf-cli find\|read\|toc\|index` | `docs/okf-tools-okf` |
| **beans** | Work-State, nächster Schritt | `beans list --ready` / `beans roadmap` | `.beans/` |
| **git** | Code-/Change-Verlauf | `git log` / `git diff` | dieses Repo |
| **SSTD.md** | Continuity/Entry-Point (dieses File) | Read | `docs/SSTD.md` |

## Entry-Point (Stand 2026-07-26, Realisierung abgeschlossen — PO-Merge-Gate offen)

- **Feature `okf-cli-cskz`** („Retrieval architecture: FTS5 arm + conditional handover") unter Milestone `okf-cli-wuiv` **shipped** — alle 13 Task-Leaves `completed` (T01-T13, siehe `beans list --parent okf-cli-cskz`). Nächster Schritt ist NICHT ein weiterer Leaf, sondern das **PO-Gate**: Review des Features + Merge nach `main`.
- **Gemessene Architektur:** `docs/okf-retrieval-architecture/DESIGN.md` — FTS5/BM25-Arm + `voyage-3-large`-Dokument-Embedding, fusioniert durch **bedingte Übergabe** statt Score-Mischung. Shipped-Zahlen (Task 9, reconciled R44, `eval/shipped_v2.json`, n=48, 2443 Konzepte): MRR 0.4509 (combined), Zero-Hit 0.167, p50 0.628 s — alle vier Gate-Kriterien aus `okf-cli-uagv` bestanden.
- **Messgrundlage liegt im Repo:** `docs/okf-retrieval-architecture/eval/` — `shipped_v2.json` (Rohdaten je Query), `taxonomy.md` (Fehlschlag-Klassifikation der 8 residualen Zero-Hits: 6 `ranking`, 2 `synonymy`, 0 `catalogue-gap`), `queries_v2.json`/`queries_real.json` (die 48-Query-Messgrundlage).
- **Was NICHT scharf ist:** `--expand-tags` (Tag-Vektor-Query-Expansion) bleibt flag-gated aus — gemessen wirkungslos für die R12-Klasse (Q05, D17); kein Threshold-Retuning vorgenommen.
- **Merge-Gate:** die einzige noch offene Entscheidung ist die PO's — Review + Merge von `okf-cli-cskz` nach `main`. Kein paralleler Owner mehr auf irgendeiner offenen Frage dieses Features.
- **Methoden-Erkenntnisse liegen im zentralen Katalog, nicht im Projekt-Bundle** — `okf-cli --root ~/Obsidian/Knowledge-Catalogue find "retrieval arme"` bzw. `find "score mischung"`: 4 Konzepte in `agent-memory` (Vollkorpus-Arme statt scoped Demo · Ground-Truth-Queries + Leak-Prüfung · Arm-Namespacing über die model-Spalte · Embedding-Last auf zweiten Ollama-Host) und 2 in `ai-wiki` (Score-Misch-Antipattern · Cosine ist Rang-, kein Konfidenzsignal). Projekt-spezifische Zahlen bleiben in `docs/okf-retrieval-architecture/`.
- Vorheriger Stand (Milestone-Review, weiterhin gültig):

## Vorheriger Entry-Point (2026-07-26, PO-Review + Grilling abgeschlossen)

- **Milestone `okf-cli-wuiv`: PO-Review durch, alle drei Epics `accepted`** (`okf-cli-2lpu`, `okf-cli-5hg4`, `okf-cli-oka0`). 10 User-Stories geprüft, 9 direkt accepted, 1 rejected (US-04 — Tags wurden nie automatisch embedded) → inline reworked (TDD, RED→GREEN, 2/2 Mutationsproben, commit `cc2696e`) → re-accepted.
- **Q01/Q02/Q04 entschieden** (`/ce-grilling`, D01/D02/D04 im Milestone-bean): D01 Eval bleibt `--json`-only · D02 `--bundle`-Alias bei `find` entfernt (commit `4a72755`, Test-Cleanup in `test_okf_cli.py`+`test_okf_mcp.py`) · D04 P15 gescrappt (`okf-cli-cfgj` → `scrapped`).
- **Nächster Schritt (historisch — inzwischen erledigt, s. Entry-Point oben):** Q03 wurde beantwortet und die Retrieval-Architektur über `okf-cli-cskz` vollständig realisiert; das Freigabe-Gate für den Merge nach `main` ist der aktuell einzige offene Schritt.
- **Q03 — beantwortet, nicht mehr offen.** Die parallele Think-Session ist fertig und committet (`docs/okf-retrieval-architecture/`, DESIGN + DECISIONS D01–D13 + REFERENCES R01–R43 + `eval/`). Ergebnis: Chunking verworfen (D11), Dokument-Embedding bleibt, der eigentliche Defekt war die Fusionsregel (D12), produktives Modell ist `voyage-3-large` (D13). Realisierung läuft über `okf-cli-cskz` — der Warnhinweis „nicht parallel gegenarbeiten" ist damit gegenstandslos.
- **Follow-up-bean neu:** `okf-cli-iw0d` (Nebenbefund PO-Review — OKF-Katalog-Lücke: kein Konzept deckt „Mockup als HTML via Tailscale" vollständig ab).
- **Bewusst offen:** P13 (`okf-cli-e9hm`) Step 3 — Modus-B-Lauf in SEPARATER Agent-Session (Task-Set fertig: `cli/eval/modus-b-tasks.md`).
- **Beweislage:** Suite 187 Tests, exakt 19F/2E pre-existing (Crosslink-Suiten), 0 neue. Baseline `cli/eval/results/baseline-f0714b2.json` (frozen) vs `hybrid-39d6c0a.json`: Gate PASS, Paraphrase-Zero-Hit 1.000→0.500, keine Literal-Regression. Katalog + Live-`.tagvec` pristine (Tag-Embeddings produktiv vervollständigt: 752 bge-m3-Zeilen, 0 offen; `concept_emb` bewusst weiter 0 — Q03).
- Lessons: `docs/LESSONS-LEARNED.md` LL-01…LL-07 (mein Repo-Anteil) + LL-08/LL-09 (parallele Session, Retrieval-Architektur-Experiment).
- Glossar geseedet: `docs/okf-tools-okf/GLOSSARY.md` — semantic backstop, document-embedding, chunk-embedding, tag-vector expansion.
- Repo-Konvention (s. `/tools/CLAUDE.md`): **Worktree-Weiche = main-direkt erlaubt** (Solo); bei parallelen Sessions im selben Workdir: fremde Datei-Änderungen niemals mitstagen (s. Attention).

## Attention (noch nicht in kanonischer Senke)

- `plugin/`-Zweck/Scope offen (Platzhalter, keine Klasse-B-Substanz) — Entscheidung noch zu treffen, dann per `/okf-p` als Decision ins Bundle.
- `cli/test_okf_cli.py`: 19 Failures/2 Errors sind verifiziert pre-existing (vor der Extraktion aus der Knowledge-Catalogue identisch) — kein neuer Bug, aber noch nicht als `known-issue`/`dead_end`-Konzept im OKF-Bundle festgehalten.
- ~~Parallele Session mutiert `docs/LESSONS-LEARNED.md` + `docs/okf-retrieval-architecture/` + `docs/okf-revision/*.yaml`...~~ — **erledigt.** Diese Session ist `okf-cli-cskz` selbst; ihre Ergebnisse sind vollständig eingearbeitet (s. Entry-Point oben). Kein paralleler Owner mehr.
- `docs/plans/okf-cli-dwcq-cli-okf-prime-optimieren/` liegt noch unter dem alten `plans/`-Layout, das `docs/CLAUDE.md` bis T13 fälschlich vorschrieb (I01, jetzt korrigiert) — per PLAN.md Task 13 bewusst nicht verschoben, History bleibt an Ort und Stelle.
