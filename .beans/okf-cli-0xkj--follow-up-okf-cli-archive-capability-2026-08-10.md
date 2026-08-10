---
# okf-cli-0xkj
title: Follow-up okf-cli archive capability 2026-08-10
status: todo
type: epic
priority: normal
created_at: 2026-08-10T06:45:07Z
updated_at: 2026-08-10T11:21:08Z
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


## D02 2026-08-10 — PO decision on Q02: `rename` out of the archive is refused

The PO answered Q02 the same day, verbatim:

> ein rename, dessen Quelle unter _archive/ liegt, verweigert und verweist auf archive --restore

That is reading 3 of the three put forward. Interpretation: a `rename` whose resolved source lies under `_archive/` exits non-zero and names `archive --restore`; every other `rename` path stays untouched. The residue of `okf-cli-gqss` becomes unreachable through `rename` without any pruning logic entering the shared `perform_rename` — so R-04/A15 (`rename` byte-identical, provable by the unchanged `rename` test set) survives intact, which is what ruled out reading 2.

Readings 1 (leave it) and 2 (extend the prune into `cmd_rename`) are hereby closed, not deferred.

**Operationalized as a sixth leaf: `okf-cli-tk33`.** The epic grows from five leaves to six. The guard goes in `cmd_rename`, not in `perform_rename` — `archive --restore` legitimately moves a source out of `_archive/` through that same shared function, so a guard placed there would refuse the very operation the PO is pointing users at. Same placement rule as the three direction guards and the `okf-cli-5436` counterpart check, per SPEC section 2.

No open question remains from Q02.


## Q03 2026-08-10 — SC-03 of `okf-cli-yixf` is unsatisfiable as written, for the PO

Raised by the implementer of `okf-cli-yixf` as a disclosed deviation, independently confirmed by the `ce-specs-reviewer` (verdict APPROVED — explicitly not a reason to withhold approval).

SC-03 of that bean reads: "Both new edge cases fail when the precedence rule is removed from the code path they exercise."

For AC3 (a `collisions` set holding an archived namesake next to an active candidate) this holds and was proven. For AC2 (an existing-but-empty `_archive/` directory) it cannot hold, and the reason is arithmetic rather than a gap in the work: an empty archive tier yields zero archived candidates, so the active/archived split in `_apply_archive_precedence` is a no-op for that fixture under ANY mutation of that function. The reviewer traced this himself against the fixture and agrees the criterion is unsatisfiable as written.

The test was written to the bean's literal wording as a geometry pin. The reviewer then probed whether it is pure decoration and found it is not, but only just: replacing `for b in list_bundles(archive_root):` (`cli/okf-cli.py:3436`) with `for b in [list_bundles(archive_root)[0]]:` raises `IndexError` and turns it red. Every natural mutation of the guard itself — deleting the `os.path.isdir` check, inverting it — leaves it green, because an empty archive tier contributes nothing however the branch falls.

**What the test therefore is:** a cheap crash-guard against an "assumes non-empty" indexing bug. **What it is not:** evidence that the precedence rule is exercised, which is what SC-03's wording promises.

**Open for the PO — the leaf is approved either way; this is about wording, not rework:**

1. Accept as shipped and amend SC-03 in the bean to name AC2's coverage as crash-safety rather than precedence-sensitivity. My recommendation — it costs one appended sentence and stops the criterion from reading as a guarantee it never had.
2. Drop the AC2 test. Not recommended: it is cheap, it does kill one real bug class, and the epic's own lesson is that removing a weak guard is only right when it protects nothing at all.
3. Replace AC2's fixture with one that has archived content, so precedence genuinely applies. That is a different edge case than the one `okf-cli-yixf` was written to pin, and would be a new leaf rather than a correction.

Independent of the choice: the phrase "both edge cases fail when X is removed" should not be reused in this epic without checking that each named case can actually fail that way.
