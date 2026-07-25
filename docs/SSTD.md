# okf-tools — Session State Transfer (Pointer-File)

> SSTD hält kein Wissen — nur Sink-Registry + Entry-Point (D01). Decisions/durables Wissen → OKF-Bundle, Work-State → beans, Code-Historie → git.

## Sink-Registry

| Sink | Hält | Lesen | Fundstelle |
|---|---|---|---|
| **OKF-Bundle** | Konzepte, Decisions, Patterns | `okf-cli find\|read\|toc\|index` | `docs/okf-tools-okf` |
| **beans** | Work-State, nächster Schritt | `beans list --ready` / `beans roadmap` | `.beans/` |
| **git** | Code-/Change-Verlauf | `git log` / `git diff` | dieses Repo |
| **SSTD.md** | Continuity/Entry-Point (dieses File) | Read | `docs/SSTD.md` |

## Entry-Point (Stand 2026-07-26, PO-Review + Grilling abgeschlossen)

- **Milestone `okf-cli-wuiv`: PO-Review durch, alle drei Epics `accepted`** (`okf-cli-2lpu`, `okf-cli-5hg4`, `okf-cli-oka0`). 10 User-Stories geprüft, 9 direkt accepted, 1 rejected (US-04 — Tags wurden nie automatisch embedded) → inline reworked (TDD, RED→GREEN, 2/2 Mutationsproben, commit `cc2696e`) → re-accepted.
- **Q01/Q02/Q04 entschieden** (`/ce-grilling`, D01/D02/D04 im Milestone-bean): D01 Eval bleibt `--json`-only · D02 `--bundle`-Alias bei `find` entfernt (commit `4a72755`, Test-Cleanup in `test_okf_cli.py`+`test_okf_mcp.py`) · D04 P15 gescrappt (`okf-cli-cfgj` → `scrapped`).
- **Nächster Schritt:** Q03 abwarten (siehe unten — wird gerade von einer PARALLELEN Session bearbeitet), danach Freigabe-Gate für Merge nach `main` stellen (noch nicht gestellt).
- **Q03 — einzige noch offene Frage, AKTIV in Bearbeitung durch eine andere Session** (Think-Partner, Thema "okf-cli-wuiv (Q03)", 2026-07-26): Chunk- vs. Dokument-Embedding für `concept_emb`. Diese Session experimentiert live (`docs/okf-retrieval-architecture/`, `embed_arms.py --arm chunk` gegen Macmini/Tailscale) und hat bereits `docs/LESSONS-LEARNED.md` erweitert (LL-08 Ollama-Crash ohne Retry/Resume, LL-09 Ollama 10–35× langsamer als Voyage-Batch). **Vor jeder Q03-Aktion zuerst prüfen, ob diese Session fertig+committet hat** — nicht parallel gegenarbeiten (LL-05-Disziplin).
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
