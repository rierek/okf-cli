# okf-tools — Session State Transfer (Pointer-File)

> SSTD hält kein Wissen — nur Sink-Registry + Entry-Point (D01). Decisions/durables Wissen → OKF-Bundle, Work-State → beans, Code-Historie → git.

## Sink-Registry

| Sink | Hält | Lesen | Fundstelle |
|---|---|---|---|
| **OKF-Bundle** | Konzepte, Decisions, Patterns | `okf-cli find\|read\|toc\|index` | `docs/okf-tools-okf` |
| **beans** | Work-State, nächster Schritt | `beans list --ready` / `beans roadmap` | `.beans/` |
| **git** | Code-/Change-Verlauf | `git log` / `git diff` | dieses Repo |
| **SSTD.md** | Continuity/Entry-Point (dieses File) | Read | `docs/SSTD.md` |

## Entry-Point (Stand 2026-07-25, Realisierungs-Session abgeschlossen)

- **Milestone `okf-cli-wuiv`: 12/14 Tasks completed** (P1–P8, P10–P12, P14). Epics Phase 1 (`okf-cli-2lpu`), Phase 2 (`okf-cli-5hg4`), Phase 4 (`okf-cli-oka0`) auf Tag `to-review` — **PO-Merge-Gate ist der nächste Schritt:** `/ce-po-review okf-cli-wuiv`.
- **Bewusst offen:** P13 (`okf-cli-e9hm`) Step 3 — Modus-B-Lauf in SEPARATER Agent-Session (Task-Set fertig: `cli/eval/modus-b-tasks.md`); P15 (`okf-cli-cfgj`) draft, Q04-gated.
- **Beweislage:** Suite 189 Tests, exakt 19F/2E pre-existing (Crosslink-Suiten), 0 neue. Baseline `cli/eval/results/baseline-f0714b2.json` (frozen) vs `hybrid-39d6c0a.json`: Gate PASS, Paraphrase-Zero-Hit 1.000→0.500, keine Literal-Regression. Katalog + Live-`.tagvec` pristine.
- **Offene PO-Fragen (im Milestone-bean verankert):** Q01 index.md-vs-`--json`-Mess-Surface · Q02 `--bundle`-als-`--scope`-Alias · Q03 concept_emb produktiv befüllen (Backstop in Produktion bisher dormant) · Q04 P15 go/no-go.
- Lessons: `docs/LESSONS-LEARNED.md` LL-01…LL-07 (je mit Forward-Guard).
- Repo-Konvention (s. `/tools/CLAUDE.md`): **Worktree-Weiche = main-direkt erlaubt** (Solo); bei parallelen Implementern in DIESEM Repo: Worktrees Pflicht + Supervisor committet währenddessen nie im Haupt-Workdir (LL-05).

## Attention (noch nicht in kanonischer Senke)

- `plugin/`-Zweck/Scope offen (Platzhalter, keine Klasse-B-Substanz) — Entscheidung noch zu treffen, dann per `/okf-p` als Decision ins Bundle.
- `cli/test_okf_cli.py`: 19 Failures/2 Errors sind verifiziert pre-existing (vor der Extraktion aus der Knowledge-Catalogue identisch) — kein neuer Bug, aber noch nicht als `known-issue`/`dead_end`-Konzept im OKF-Bundle festgehalten.
