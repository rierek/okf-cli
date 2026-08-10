---
# okf-cli-0xkj
title: Follow-up okf-cli archive capability 2026-08-10
status: todo
type: epic
priority: normal
created_at: 2026-08-10T06:45:07Z
updated_at: 2026-08-10T10:11:46Z
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


## Q02 2026-08-10 — the residue is still reachable through `rename`, for the PO

Raised by the `ce-specs-reviewer` on `okf-cli-gqss` as decision D01 of that review, status 🟡 — needs a PO decision. The leaf itself was APPROVED; this is about whether a further leaf follows.

`okf-cli-gqss` prunes the emptied `_archive/<bundle>/` and `_archive/` directories, but the prune lives in `cmd_archive` only. The reviewer verified by his own smoke run that a direct call reproduces the original defect:

```
okf-cli.py rename _archive/<bundle>/old.md <bundle>/old.md --apply
```

leaves `_archive/<bundle>/` and `_archive/` standing — the same invisible residue, reached through a different command.

**Why it was left alone, and why that was right.** `docs/okf-archive-lifecycle/SPEC.md` section 2 requires (R-04/A15) that `rename` stay byte-identical, and section 1 makes `archive --restore` the only documented restore interface. Moving the prune into `perform_rename` would have broken an explicit, separate spec requirement in order to close a gap that lies outside the documented interface. Both the implementer and the reviewer took the same position, independently.

**Open for the PO — three readings, no default:**

1. Leave it. The guarantee is scoped to the documented restore interface, and `rename` out of `_archive/` is an operator going around the front door.
2. Extend the guarantee to be command-independent: `cmd_rename` gets the same prune. Costs the byte-identical-`rename` promise and needs a SPEC section 2 amendment.
3. Refuse the path: a `rename` whose source lies under `_archive/` errors and names `archive --restore`. Keeps `rename` semantics for every other path and turns the bypass into a signpost — shape-wise a sibling of `okf-cli-5436`.

Reading 3 is the one I would put first if the PO wants the gap closed at all: it fixes the surprise without touching what R-04/A15 protects.
