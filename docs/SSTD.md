# okf-tools — Session State Transfer (Pointer-File)

> SSTD hält kein Wissen — nur Sink-Registry + Entry-Point (D01). Decisions/durables Wissen → OKF-Bundle, Work-State → beans, Code-Historie → git.

## Sink-Registry

| Sink | Hält | Lesen | Fundstelle |
|---|---|---|---|
| **OKF-Bundle** | Konzepte, Decisions, Patterns | `okf-cli find\|read\|toc\|index` | `docs/okf-tools-okf` |
| **beans** | Work-State, nächster Schritt | `beans list --ready` / `beans roadmap` | `.beans/` |
| **git** | Code-/Change-Verlauf | `git log` / `git diff` | dieses Repo |
| **SSTD.md** | Continuity/Entry-Point (dieses File) | Read | `docs/SSTD.md` |

## Entry-Point (Stand 2026-07-26, Plan-Phase abgeschlossen — Realisierung startet)

- **Aktive Arbeit: Feature `okf-cli-cskz`** („Retrieval architecture: FTS5 arm + conditional handover") unter Milestone `okf-cli-wuiv`. 13 Task-Leaves, `blocked_by` kodiert die Reihenfolge. Einstieg ohne Rückfrage: `beans list --ready` → aktuell `okf-cli-pean` (Producer-Batching) und `okf-cli-48qk` (Unicode-Tokenizer), zwei unabhängige Ketten.
- **Plan:** `docs/okf-retrieval-architecture/PLAN.md` — 13 Tasks mit literalem Code und Tests je Schritt. `ce-plan-reviewer` GRÜN nach 2 Runden, `ce-verify-operationalization` GRÜN nach 2 Runden (Gate A: 13/13 Leaves EARS-valide). Kein PO-Review des Plans — vom PO ausdrücklich übersprungen (2026-07-26).
- **Was gebaut wird:** die gemessene Zielarchitektur aus `docs/okf-retrieval-architecture/DESIGN.md` — FTS5/BM25-Arm + `voyage-3-large`-Dokument-Embedding, fusioniert durch **bedingte Übergabe** statt Score-Mischung. Heute findet `find` 1 von 48 Paraphrasen (R42); Zielmarke zero-hit ≤ 0.30, MRR ≥ 0.35.
- **Zwei Fallen, die schon zweimal fast zugeschlagen haben** (beide im Plan festgenagelt): die Confidence-Formel ist `top1 >= 1.5 * top2` (gemessen, `eval/hybrid_eval.py:151`) — **nicht** die 2×-Arithmetik des Altcodes. Und der Gate-Lauf braucht `fixtures.py --seed` **plus** einen Producer-Lauf für die geseedeten Fixtures, sonst misst er die Degradations-Pfad-Variante.
- **Geldausgabe:** `okf-cli-c922` (Vollbefüllung `concept_emb`, ~$0.71) braucht PO-Freigabe im Chat vor dem Lauf.
- Vorheriger Stand (Milestone-Review, weiterhin gültig):

## Vorheriger Entry-Point (2026-07-26, PO-Review + Grilling abgeschlossen)

- **Milestone `okf-cli-wuiv`: PO-Review durch, alle drei Epics `accepted`** (`okf-cli-2lpu`, `okf-cli-5hg4`, `okf-cli-oka0`). 10 User-Stories geprüft, 9 direkt accepted, 1 rejected (US-04 — Tags wurden nie automatisch embedded) → inline reworked (TDD, RED→GREEN, 2/2 Mutationsproben, commit `cc2696e`) → re-accepted.
- **Q01/Q02/Q04 entschieden** (`/ce-grilling`, D01/D02/D04 im Milestone-bean): D01 Eval bleibt `--json`-only · D02 `--bundle`-Alias bei `find` entfernt (commit `4a72755`, Test-Cleanup in `test_okf_cli.py`+`test_okf_mcp.py`) · D04 P15 gescrappt (`okf-cli-cfgj` → `scrapped`).
- **Nächster Schritt:** Q03 abwarten (siehe unten — wird gerade von einer PARALLELEN Session bearbeitet), danach Freigabe-Gate für Merge nach `main` stellen (noch nicht gestellt).
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
- Parallele Session mutiert `docs/LESSONS-LEARNED.md` + `docs/okf-retrieval-architecture/` + `docs/okf-revision/*.yaml` im selben Haupt-Workdir — bewusst nicht angefasst/committet (gehört der anderen Session). Sobald sie fertig ist: ihre Ergebnisse in Q03 einarbeiten.
