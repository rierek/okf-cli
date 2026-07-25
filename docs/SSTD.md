# okf-tools — Session State Transfer (Pointer-File)

> SSTD hält kein Wissen — nur Sink-Registry + Entry-Point (D01). Decisions/durables Wissen → OKF-Bundle, Work-State → beans, Code-Historie → git.

## Sink-Registry

| Sink | Hält | Lesen | Fundstelle |
|---|---|---|---|
| **OKF-Bundle** | Konzepte, Decisions, Patterns | `okf-cli find\|read\|toc\|index` | `docs/okf-tools-okf` |
| **beans** | Work-State, nächster Schritt | `beans list --ready` / `beans roadmap` | `.beans/` |
| **git** | Code-/Change-Verlauf | `git log` / `git diff` | dieses Repo |
| **SSTD.md** | Continuity/Entry-Point (dieses File) | Read | `docs/SSTD.md` |

## Entry-Point (Stand 2026-07-25)

- **Aktives Milestone: `okf-cli-wuiv` — okf-cli/mcp maturity revision** (4 Epics, 14 Tasks, operationalisiert aus `docs/okf-revision/PLAN.md`; ce-plan-reviewer GRÜN, PO-approved, Gate-B verify GRÜN).
- **Nächster Schritt (Realisierung startklar):** `cc --implement "/ce-implement-beans okf-cli-wuiv"`. Ready ohne Blocker: **P1 `okf-cli-83vq`** (B01 --json-fix) · **P2 `okf-cli-ez6f`** (seed golden fixtures S1-S4). Rest blockiert bis Baseline-Freeze `okf-cli-5qmn` (hartes Gate vor Phase 2).
- Reihenfolge/Deps: `beans roadmap` / `beans list --ready`. Plan-Detail je Task: `docs/okf-revision/PLAN.md`.
- Repo-Konvention (nicht verhandelbar pro Session, s. `/tools/CLAUDE.md`): **Worktree-Weiche = main-direkt erlaubt** (Solo-Repo, ein Repo für `cli/`+`mcp/`+`plugin/`).

## Attention (noch nicht in kanonischer Senke)

- `plugin/`-Zweck/Scope offen (Platzhalter, keine Klasse-B-Substanz) — Entscheidung noch zu treffen, dann per `/okf-p` als Decision ins Bundle.
- `cli/test_okf_cli.py`: 19 Failures/2 Errors sind verifiziert pre-existing (vor der Extraktion aus der Knowledge-Catalogue identisch) — kein neuer Bug, aber noch nicht als `known-issue`/`dead_end`-Konzept im OKF-Bundle festgehalten.
