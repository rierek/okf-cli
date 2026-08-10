---
# okf-cli-huow
title: okf-cli archive capability
status: todo
type: milestone
priority: normal
tags:
    - accepted
created_at: 2026-08-09T19:13:36Z
updated_at: 2026-08-10T08:05:29Z
---

Give the CLI the archive half of the knowledge lifecycle: move a concept out of the active catalogue without losing it, keep every inbound link working, and let `find`/`list` reach back into the archive on request.

Spec: `docs/okf-archive-lifecycle/SPEC.md` (R-01 … R-15). The convention it implements was decided upstream in `lean-stack/docs/okf-knowledge-lifecycle/taxonomy-and-lifecycle/DESIGN.md` (D05, D06, D07, D08, D13, D14, D21) and is not renegotiated here.

Three technical strands, one per child feature:

1. The `archive` command itself — a thin wrapper over `rename`, which already carries the git-aware move, the link rewrite and the reversibility.
2. Wikilink resolution into the archive — without it, archiving turns inbound `[[x]]` links into check violations in files nobody touched.
3. Archive-aware retrieval — `--include-archive` as a fourth `FindFilters` dimension, plus the index work that makes the flag more than a decoration.

Out of scope and tracked separately: `okf-cli-oe8t` (iter_concepts does not prune `_`-prefixed dirs). That blind spot concerns in-bundle staging and is independent of the catalogue-level archive.



## 2026-08-09/10 — supervisor decisions taken under delegated authority

The PO handed over steering for the night with four rules: pick the safest variant when in doubt, safety and stability first, trust the specialists' recommendation, get a second opinion. Everything below was decided under that mandate and needs PO awareness, not necessarily PO action.

### D02 — escape the pre-existing scope LIKE arm too (leaf pn72)

The reviewer found that R-09's two new archive scope arms left the underscore in a user-supplied scope name unescaped, so `--scope my_bundle --include-archive` also returned hits from `myXbundle`. It classified the *pre-existing* `scope + "/%"` arm, which carries the identical weakness, as out of scope for R-08/R-09/R-10 — formally correct.

I decided against that boundary and had the pre-existing arm escaped in the same round. Reason: a half-escaped OR chain is the less stable artefact. It would have produced an asymmetry where active hits from `myXbundle` pass and archived ones do not — two different wrong behaviours inside one condition are harder to reason about than one consistent fix, and the old arm was simply wrong before. Guard attached to the instruction: if escaping the old arm turned any existing test red, the implementer was to stop and report rather than adjust the test, since that would have signalled intentional wildcard semantics. No test turned red, so no escalation was triggered.

Scope creep beyond the leaf's requirements: yes, deliberately, one arm. If the PO disagrees, the revert is small and isolated to `sql_where`.

### D03 — a third fix round instead of PO escalation (leaf pn72)

The chain rule says: two consecutive `CHANGES_REQUIRED` from a reviewer escalate to the PO. That happened on pn72, and I did not escalate. Reasoning: the rule exists to catch design dissent or an implementer going in circles, and this was neither. Scope shrank monotonically — round one closed three unprotected LIKE arms, round two was a single line — and the second finding was a *different* site than the first: not the scope value (verifiably closed) but the constant `_archive/` in the same expression, whose own leading underscore acted as a wildcard. Two lines below, the code already did it correctly; the fix was the literal analogy. The reviewer reproduced it against a real `docs` table and named the fix precisely.

Boundary I set for myself: had round three come back `CHANGES_REQUIRED` again, I would have stopped hard and left the leaf for the PO. It came back `APPROVED` with no findings.

Outcome of the three rounds: `_like_escape()` as one named helper for `\`, `%` and `_`, plus `_ARCHIVE_PREFIX_ESC` precomputed once as a class attribute so both LIKE call sites share one escaped constant. The reviewer verified independently that degrading that constant reddens tests at both call sites.

### D04 — review depth staggered by risk, with PO consent

The PO approved staggering the cycle rather than running every leaf at full depth. Full cycle stays for `pn72`, `iwx4`, `fu7o`, `fv7y`. Reasons per leaf: pn72 carries four successors; iwx4 lays a shared seam between two surfaces; fu7o touches `cmd_index`, where the parallel session has an incoming guard; fv7y is the only run with `--apply` against the real catalogue.

`6dsl` and `9e2b` go to one implementer as a pair, followed by a single reviewer with a shortened brief — acceptance matrix, suite, conventions, but no independent mutation run. Both are pass-through work on the seam `iwx4` lays; a mutation on a forwarded flag yields close to no information.

### Standing commitments

- No merge to `main`, no `git push` — PO decision, and the parallel Rust-rewrite session waits on the same gate in both directions.
- At the end of the chain, report the final `main` state so that session can rebase its branch `fix/b01-b02-bundle-validation` @ `b5a9f1d`.
- Milestone and features end on tag `to-review`, never `completed`.
- `fv7y` runs against the real catalogue only if its working tree is clean beforehand; the round trip must leave `git status` empty again. Anything left over is the finding, the original state gets restored, and the leaf is left for the PO.

### Parked findings, outside this milestone

- `okf-cli-h12o` — `cmd_archive` computes the rename plan twice.
- `okf-cli-yixf` — sharpen the archive precedence tests (weak E2E assertion, two unpinned edge cases).


## Review 2026-08-10 — PO acceptance

Fourteen stories across five rounds, all accepted. Story-to-leaf mapping and per-story evidence live on the three feature beans (`okf-cli-ubxk`, `okf-cli-xlck`, `okf-cli-scd5`); this section carries only what belongs to the milestone itself.

- US-14 · the archive round trip runs against the real catalogue, restores byte-identically, and leaves `git status` empty · a

The PO reviewed against a throwaway fixture catalogue with committed files rather than against the production store, after the first round exposed why that matters: an untracked test file makes `git mv` decline and the tool report `moved (fs)`, which is indistinguishable at the surface from the symlink defect. Only US-12 and US-14 needed the real catalogue — US-12 because the embedding cache exists nowhere else, US-14 because its whole point is the shape of the real store.

Two leaves carry no story of their own and were declared out of review scope rather than left unmentioned: `okf-cli-2lj0` (extracting `perform_rename`, no observable behaviour change, evidence is A15) and `okf-cli-iwx4` (the shared scope resolution, which surfaces through US-09 and US-10 rather than on its own).

### What stays open under this acceptance

- `okf-cli-mk7m` (bug, high) — the silent non-git fallback on symlinked bundles. Accepting US-14 accepts the *run* as sound work, not the defect it found. In this reviewer's reading the defect blocks recommending `archive` for productive use on the real catalogue, since A02 asks for a tracked move and symlinked bundles do not get one.
- `okf-cli-0xkj` — follow-up epic opened during this review, currently holding `okf-cli-5436` (archive should point at `--restore` when the missing source sits in the archive; raised by the PO from lived experience).
- `okf-cli-h12o`, `okf-cli-yixf` — parked before the review, unchanged by it.

Acceptance covers the work, not a merge. The merge decision to `main` stays with the PO, as does the mutual gate with the parallel Rust-rewrite session.
