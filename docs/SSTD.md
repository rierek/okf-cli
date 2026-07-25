# okf-tools — Session State Transfer (Pointer-File)

> SSTD hält kein Wissen — nur Sink-Registry + Entry-Point (D01). Decisions/durables Wissen → OKF-Bundle, Work-State → beans, Code-Historie → git.

## Sink-Registry

| Sink | Hält | Lesen | Fundstelle |
|---|---|---|---|
| **OKF-Bundle** | Konzepte, Decisions, Patterns | `okf-cli find\|read\|toc\|index` | `docs/okf-tools-okf` |
| **beans** | Work-State, nächster Schritt | `beans list --ready` / `beans roadmap` | `.beans/` |
| **git** | Code-/Change-Verlauf | `git log` / `git diff` | dieses Repo |
| **SSTD.md** | Continuity/Entry-Point (dieses File) | Read | `docs/SSTD.md` |

## Entry-Point (Stand 2026-07-25, PO-Review abgeschlossen)

- **Milestone `okf-cli-wuiv`: PO-Review durch für Epics Phase 1/2/4 — alle drei `accepted`** (`okf-cli-2lpu`, `okf-cli-5hg4`, `okf-cli-oka0`). 10 User-Stories geprüft, 9 direkt accepted, 1 rejected (US-04 — Tags wurden nie automatisch embedded) → inline reworked (TDD, RED→GREEN, 2/2 Mutationsproben, commit `cc2696e`) → re-accepted. Epic `okf-cli-5hg4` von `rejected` zurück auf `accepted` retagged.
- **Nächster Schritt:** Q01/Q02/Q03/Q04 mit PO klären (siehe unten), dann Freigabe-Gate für Merge nach `main` (Skill-Phase 4.3, noch nicht gestellt).
- **Bewusst offen:** P13 (`okf-cli-e9hm`) Step 3 — Modus-B-Lauf in SEPARATER Agent-Session (Task-Set fertig: `cli/eval/modus-b-tasks.md`); P15 (`okf-cli-cfgj`) draft, Q04-gated.
- **Beweislage:** Suite 191 Tests, exakt 19F/2E pre-existing (Crosslink-Suiten), 0 neue (+2 Tests aus dem US-04-Rework). Baseline `cli/eval/results/baseline-f0714b2.json` (frozen) vs `hybrid-39d6c0a.json`: Gate PASS, Paraphrase-Zero-Hit 1.000→0.500, keine Literal-Regression. Katalog + Live-`.tagvec` pristine (Tag-Embeddings zwischenzeitlich produktiv vervollständigt: 752 bge-m3-Zeilen, 0 offen; `concept_emb` bewusst weiter 0 — Q03).
- **Offene PO-Fragen (im Milestone-bean `okf-cli-wuiv` verankert, mit Live-Review-Evidenz angereichert):** Q01 index.md-vs-`--json`-Mess-Surface · Q02 `--bundle`-als-`--scope`-Alias · **Q03 stark erweitert** — Design-Root-Cause (Dokument- vs. Chunk-Embedding, Option d neu, Option e Tag-Vektor-Expansion neu), Live-Gegenprobe bestätigt Embedding-Notwendigkeit (Zero-Hit-Beispiel `mockup tailscale`) · Q04 P15 go/no-go.
- Lessons: `docs/LESSONS-LEARNED.md` LL-01…LL-07 (je mit Forward-Guard).
- Repo-Konvention (s. `/tools/CLAUDE.md`): **Worktree-Weiche = main-direkt erlaubt** (Solo); bei parallelen Implementern in DIESEM Repo: Worktrees Pflicht + Supervisor committet währenddessen nie im Haupt-Workdir (LL-05).

## Attention (noch nicht in kanonischer Senke)

- `plugin/`-Zweck/Scope offen (Platzhalter, keine Klasse-B-Substanz) — Entscheidung noch zu treffen, dann per `/okf-p` als Decision ins Bundle.
- `cli/test_okf_cli.py`: 19 Failures/2 Errors sind verifiziert pre-existing (vor der Extraktion aus der Knowledge-Catalogue identisch) — kein neuer Bug, aber noch nicht als `known-issue`/`dead_end`-Konzept im OKF-Bundle festgehalten.
