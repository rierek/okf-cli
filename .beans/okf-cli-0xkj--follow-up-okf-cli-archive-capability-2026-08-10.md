---
# okf-cli-0xkj
title: Follow-up okf-cli archive capability 2026-08-10
status: todo
type: epic
priority: normal
created_at: 2026-08-10T06:45:07Z
updated_at: 2026-08-10T09:52:40Z
parent: okf-cli-huow
---

Findings raised by the PO during the 2026-08-10 review of milestone okf-cli-huow. Side findings and rejects that no existing leaf covers land here.


## Scope of this epic — operationalized 2026-08-10

Five leaves, all carrying a Gate-A-validated acceptance block. Three sources feed them: the PO review of 2026-08-10 (`5436`), the R-15 real-catalogue run (`mk7m`, `gqss`), and reviewer findings parked during the milestone realization (`h12o`, `yixf`).

`mk7m`, `h12o` and `yixf` were re-parented into this epic during operationalization. They belonged to milestone `okf-cli-huow`, which is now accepted and terminal; open work below an accepted milestone would be invisible to the roadmap.

Two of the five are blockers for a production recommendation of `archive` on the real catalogue: `mk7m` and `gqss`. Both describe residue that the obvious verification cannot see — one lands writes in an unnamed repository, the other leaves directories git does not track. The other three are quality work with no user-visible defect behind them.

No implementation order is fixed. `mk7m` and `gqss` touch the same code path and would sensibly go to one implementer; `h12o` needs a planner decision on a spec-fixed signature before an implementer can start.


## Q01 2026-08-10 — open reading of AC1 in `okf-cli-mk7m`, for the PO

Raised by the implementer as a disclosed deviation, confirmed as a legitimate open question by the `ce-specs-reviewer` (verdict APPROVED — explicitly not a reason to withhold approval of that leaf).

AC1 of `okf-cli-mk7m` reads: "WHEN `git mv` fails because the path lies beyond a symbolic link THE okf-cli SHALL resolve the real repository of the target and attempt the tracked move there, or state plainly that the move is untracked."

A single `git mv` cannot span two repositories. That is a property of git, not an interpretation. When `archive` moves a concept out of a symlinked bundle, the source resolves into the project repo while the destination `_archive/…` lies under `--root` — two different repositories by construction. The shipped implementation therefore:

- retries a genuinely tracked `git mv` in the foreign repo when BOTH endpoints resolve there (a `rename` fully inside a symlinked bundle), and
- for the cross-repo case falls back to `os.rename` while surfacing git's own reason and naming the repository that received the write.

The stronger reading of AC1 — always manufacture a tracked move via two-sided `git rm --cached` / `git add` staging whenever a real repo is resolvable — was NOT implemented. Neither the bean's real-catalogue narrative nor `docs/okf-archive-lifecycle/SPEC.md` section 2 describes such a mechanism, so building it would have been an implementer-invented scope extension.

**Open for the PO:** is the shipped reading the intended one, or should the cross-repo archive case produce a staged, tracked move on both sides? If the shipped reading stands, this section is the record and no further work follows. If not, it becomes a new leaf — the current leaf stays correct either way, since it reports honestly rather than degrading silently.
