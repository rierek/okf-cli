---
# okf-cli-mk7m
title: archive silently falls back to a non-git move
status: completed
type: bug
priority: high
created_at: 2026-08-09T23:06:24Z
updated_at: 2026-08-10T09:45:29Z
parent: okf-cli-0xkj
---

Found by the real-catalogue run (`okf-cli-fv7y`, R-15) — no fixture could have found it, because fixtures build plain directories.

## What happens

Every project bundle in the real catalogue is a **symlink** into its project repo: `lean-stack-okf`, `vik-okf`, `devd2-okf`, `bew_BeWiki-Python-Download-okf`, `okf-tools-okf`, `vc-search-okf`.

`_git_mv` (cli/okf-cli.py:4048) runs `git -C <root> mv -f`. Git refuses and the code falls back to `os.rename`, reporting `moved (fs)`.

The exact git message was mis-attributed in the first draft of this bean: `fatal: pathspec ... is beyond a symbolic link` comes from `git add`, not from `git mv`. A reviewer rebuilt the layout in a temporary fixture — two repos, the bundle committed into the catalogue as mode `120000` — and got `fatal: not under version control, source=bundle/concept.md, destination=bundle/concept2.md` with exit 128. Do not grep for the wrong string when reproducing this.

Worse than either message: `_git_mv` (cli/okf-cli.py:4048-4059) captures `proc.stderr` and never reads it, so git's explanation never reaches the user at all. The caller (cli/okf-cli.py:4199) prints `moved (fs)` versus `moved (git mv)` — not wordless, but nothing says what `(fs)` costs or which repository actually received the write.

The consequence is that the move — and the crosslink rewrites that go with it — lands **untracked in the target project repo**, not in the catalogue repo. During the run, `git -C ~/Obsidian/Knowledge-Catalogue status` showed only `?? _archive/` while `git -C ~/dev/lean-stack status` showed `D`/`M` on three paths. The round trip restored everything byte-identically, so nothing was lost, but the mechanism is wrong.

## Why it matters

A02/A03 assume a git-tracked move. On the real catalogue that assumption does not hold for any project bundle — which is most of them. Two separate problems:

1. **The fallback is silent.** `moved (fs)` does not tell the user their move left git behind. Someone archiving a concept would reasonably believe it is versioned in the catalogue and could revert it there; it is not, and they cannot.
2. **The write lands in a repo the user did not name.** An operator pointing the tool at `~/Obsidian/Knowledge-Catalogue` gets writes in `~/dev/lean-stack`. That is surprising in a way that matters for any automated or agent-driven use.

### Requirement 1: A move that does not lie about what it did

**Objective:** As a catalogue maintainer, I want to know which repository actually received my move, so that I can revert it where it landed instead of where I assumed.

#### Acceptance Criteria

1. WHEN `git mv` fails because the path lies beyond a symbolic link THE okf-cli SHALL resolve the real repository of the target and attempt the tracked move there, or state plainly that the move is untracked.
2. THE okf-cli SHALL name the repository that received the change in its report, whenever that repository is not the one at `--root`.
3. IF the move was carried out by `os.rename` THEN THE okf-cli SHALL NOT report it in a way that implies version control.

#### Success Criteria

- SC-01: Archiving a concept inside a symlinked bundle either produces a tracked move in the bundle target repository, or an output line that names both the fallback and the repository that received it.
- SC-02: A fixture reproduces the symlinked-bundle layout, so the case is covered without touching the real catalogue.
- SC-03: Removing the enforcement turns SC-01 red.

_Requirements: R-15 real-catalogue run (`okf-cli-fv7y`), 2026-08-09_

## The second finding of this run moved out

`archive` and `archive --restore` also leave an emptied `_archive/<bundle>/` directory behind. Same run, different mechanism, independently fixable — it now lives in `okf-cli-gqss`. Do not fix it here.

## Second sighting of the silent fallback, from the PO review 2026-08-10

The PO hit `moved (fs)` on an ordinary, non-symlinked bundle: the test file was untracked, so `git mv` declined for that reason instead. The two causes are different but the surface is identical, and neither tells the user which one applied. That widens AC3 in practice — the report has to distinguish "git declined and here is why" from "the move is tracked", regardless of why git declined.

## Recommended Skills

- `superpowers:systematic-debugging` — the failing `git mv` has two distinct causes with one surface; separating them is the work.
- `superpowers:test-driven-development` — SC-02 requires the symlinked-bundle fixture to exist before the fix, otherwise there is no way to see the defect fail.

_Blocks a production recommendation of `archive` on the real catalogue._


## Summary

`_git_mv` (cli/okf-cli.py:4048) now resolves the source's real repository when `git -C <root> mv` declines. When the destination also resolves into that same real repository — an ordinary rename that stays inside a symlinked bundle — it retries a tracked `git mv` there and reports `moved (git mv)` plus `tracked in <repo> (repository differs from --root)`. When it does not (archive's destination is always `_archive/<bundle>/…` under `--root`, a different repository from the symlinked bundle's real one), it falls back to `os.rename` and reports `moved (fs)` followed by `untracked — git declined: <git's own stderr, verbatim>`, plus, only when a different repository actually received part of the write, `the untracked change also touches <repo> (repository differs from --root)`. The identical report shape (`untracked — git declined: …`) also now covers the PO's second sighting — a plain untracked file in an ordinary, non-symlinked bundle — without a spurious repo line, since there is no second repository there. `proc.stderr` is read and surfaced in all three branches (point 4 of the gate); no branch implies version control for an `os.rename`-only move (AC3).

Changed: cli/okf-cli.py:4048-4102 (`_git_mv`), cli/okf-cli.py:4224, 4243-4258 (`perform_rename`'s call site and report).

## Test-Output

RED (against the pre-fix `_git_mv`, via `git stash` isolating the test-only diff — new tests, old implementation):

```
FAIL: test_archive_across_repos_states_the_fallback_and_names_the_repo
AssertionError: 'not under version control' not found in
'0 active concept(s) still link to this concept
moved (fs)  proj-okf/concept.md  ->  _archive/proj-okf/concept.md
rewrote 0 inbound link(s) in 0 file(s), 0 outbound link(s)
...'

FAIL: test_untracked_file_in_an_ordinary_bundle_also_states_git_declined
AssertionError: 'not under version control' not found in
'0 active concept(s) still link to this concept
moved (fs)  a/untracked.md  ->  _archive/a/untracked.md
...'

ERROR: test_rename_fully_inside_a_symlinked_bundle_is_tracked_in_the_foreign_repo
TypeError: cannot unpack non-iterable bool object
    moved, repo, reason = okf._git_mv(catalogue, old, new)

Ran 4 tests in 0.579s
FAILED (failures=2, errors=1)
```

`test_fixture_reproduces_the_cited_git_message` was green even in RED — it only pins the real git message via a bare `subprocess.run`, ground truth for point 2 of the gate: `git mv` beyond the symlink says `fatal: not under version control, source=…, destination=…` (exit 128), never the `git add`-only "beyond a symbolic link" pathspec message an earlier bean draft mis-attributed.

GREEN (after the fix):

```
Ran 4 tests in 0.630s
OK
```

Full suite:

```
Ran 616 tests in 25.596s
OK
```

612 baseline + 4 new (`GitMvBeyondSymlink`): the fixture-ground-truth test, one per AC1 branch, and the widened-AC3 untracked-ordinary-bundle case.

## Mutation proof

Made git-recoverable with a WIP commit before mutating; each mutation was reverted and verified byte-identical (`git diff --stat` empty) before the next, then squashed into the final commit with `git reset --soft`.

- **AC1** ("resolve the real repository … and attempt the tracked move there"): disabled the foreign-repo retry branch (`if False and (...)`). Exactly `test_rename_fully_inside_a_symlinked_bundle_is_tracked_in_the_foreign_repo` went red — `AssertionError: False is not true : fatal: not under version control, source=proj-okf/concept.md, destination=proj-okf/renamed.md` — because with the retry disabled, the intra-bundle rename that used to reach a genuine tracked `git mv` now falls back to `os.rename` instead.

- **AC2** ("name the repository that received the change … whenever not `--root`"): removed the "the untracked change also touches …" print. Exactly `test_archive_across_repos_states_the_fallback_and_names_the_repo` went red — the foreign repo's real path was no longer in the output.

- **AC3** (widened): removed the whole `if moved: … else: …` reporting block (`pass`). Both `test_archive_across_repos_states_the_fallback_and_names_the_repo` and `test_untracked_file_in_an_ordinary_bundle_also_states_git_declined` went red — `'not under version control' not found in` the bare `moved (fs)  …` line, for both causes (symlink-beyond and plain untracked), confirming the two share a surface but the enforcement now distinguishes what git actually said in both.

- **SC-03** ("removing the enforcement turns SC-01 red"): removed the whole foreign-repo resolution block (`foreign_repo = None`, no lookup at all). `test_archive_across_repos_states_the_fallback_and_names_the_repo` (which operationalizes SC-01) and the AC1 test both went red — with no repo ever resolved, neither "a tracked move in the bundle target repository" nor "an output line that names … the repository that received it" is possible any more.

All four mutations were reverted; `git diff --stat` against the pre-mutation commit was empty each time.

## Smoke

Real throwaway layout under a temp dir (never `~/Obsidian/Knowledge-Catalogue`): `foreign` (a project repo with a tracked bundle `docs/proj-okf/`) and `catalogue` (tracks only the symlink `catalogue/proj-okf -> foreign/docs/proj-okf`, plus a plain non-symlinked `plain/` bundle with one tracked and one untracked file).

```
=== 1) archive a symlinked-bundle concept (cross-repo) ===
0 active concept(s) still link to this concept
moved (fs)  proj-okf/concept.md  ->  _archive/proj-okf/concept.md
  untracked — git declined: fatal: not under version control, source=proj-okf/concept.md, destination=_archive/proj-okf/concept.md
  the untracked change also touches /…/smoke/foreign (repository differs from --root)
...

=== 2) archive an ordinary UNTRACKED bundle file (PO 2026-08-10 second sighting) ===
0 active concept(s) still link to this concept
moved (fs)  plain/untracked.md  ->  _archive/plain/untracked.md
  untracked — git declined: fatal: not under version control, source=plain/untracked.md, destination=_archive/plain/untracked.md
...

=== 3) archive an ordinary TRACKED bundle file (still real git mv) ===
0 active concept(s) still link to this concept
moved (git mv)  plain/tracked.md  ->  _archive/plain/tracked.md
...

=== git status: catalogue ===
R  plain/tracked.md -> _archive/plain/tracked.md
?? _archive/plain/untracked.md
?? _archive/proj-okf/
=== git status: foreign ===
 D docs/proj-okf/concept.md

=== 4) rename fully inside the symlinked bundle (AC1 first branch: tracked in the foreign repo) ===
moved (git mv)  proj-okf/other.md  ->  proj-okf/renamed.md
  tracked in /…/smoke/foreign (repository differs from --root)
...
=== git status: foreign (expect R, a real tracked rename) ===
R  docs/proj-okf/other.md -> docs/proj-okf/renamed.md
```

Scenario 1 (archive, symlinked bundle, cross-repo) and scenario 2 (archive, plain untracked file) now both name what git actually said and, only for scenario 1, the foreign repository — distinguishing the two causes per the widened AC3, satisfying SC-01's "either … or …" disjunction on its second branch. Scenario 3 (archive, plain tracked file) is unaffected — still a real `git mv`. Scenario 4 (an ordinary `rename` fully inside the symlinked bundle, not `archive`) newly realizes AC1's first branch: a genuine tracked `git mv` in the foreign repo, confirmed by `git status --porcelain` showing `R` there.

## Deviations/ERRATA

- The empty-`_archive/<bundle>/` directory residue (`okf-cli-gqss`) is untouched, as scoped.
- AC1 reads "resolve the real repository of the target and attempt the tracked move there". A single `git mv` cannot span two different git repositories (source's foreign repo vs. `archive`'s destination under `--root`) — no git operation expresses that atomically. I did not implement a two-sided `git rm --cached`/`git add` staging across both repos to manufacture something git-tracked out of a cross-repo move; that would be new mechanism beyond "surface the fallback and name the repo", and the bean's own narrative of the real-catalogue run (`git status` showing a plain `D` in the foreign repo, a plain `??` in the catalogue, nothing staged) does not describe the tool doing any staging either. I read AC1's disjunction ("attempt the tracked move there, OR state plainly untracked") as covering exactly this: attempt succeeds only when both endpoints resolve into the same repository (a genuine same-repo rename that merely crosses the symlink boundary — realized and tested, scenario 4 above); otherwise state plainly. Flagging this reading explicitly rather than presenting it as spec-confirmed — a planner/PO can correct it if the intended fix is the cross-repo staging.
- Added one test (`test_rename_fully_inside_a_symlinked_bundle_is_tracked_in_the_foreign_repo`) that exercises `rename`, not `archive`, because it is the only way to produce a case where both `_git_mv` endpoints resolve into the same foreign repository — the success branch of AC1 that `archive` itself can never reach. This secures acceptance criterion AC1's first branch, which the bean's own `archive`-only fixtures cannot cover; per the task instructions this needs no separate escalation.

## Notes for T(n+1)

- `okf-cli-gqss` (empty `_archive/<bundle>/` residue) is untouched and remains open — separate bean, separate mechanism.
- If a future decision wants archive's cross-repo case to be *actually* git-tracked on both sides (not just plainly reported), that is new scope: `git -C <foreign_repo> rm --cached -f <path>` before the physical move, `git -C <root> add <new_rel>` after — see the Deviations note above for why this leaf did not implement it.
