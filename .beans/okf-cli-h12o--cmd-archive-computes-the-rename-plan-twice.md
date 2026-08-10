---
# okf-cli-h12o
title: cmd_archive computes the rename plan twice
status: completed
type: task
priority: low
created_at: 2026-08-09T20:04:06Z
updated_at: 2026-08-10T11:29:22Z
parent: okf-cli-0xkj
---

Found by the review of `okf-cli-16rg` (2026-08-09, finding I01) — non-blocking, deliberately not fixed inside that leaf.

`cmd_archive` calls `plan_rename(root, src_abs, dest_abs)` to print the AC7 report line ("N active concept(s) still link to this concept"), and `perform_rename` then computes the same plan again internally, because it does not return one. See `cli/okf-cli.py:4037-4042`.

The duplication is a known consequence of the signature fixed in `docs/okf-archive-lifecycle/SPEC.md` §2, recorded in the `## Notes for T(n+1)` section of `okf-cli-2lj0` — it was not overlooked. The cost is a second `build_ref_matrix` scan per `archive` invocation, which grows with catalogue size.

Possible fix for a later iteration: let `perform_rename` accept or return an already-computed plan. That touches a spec-fixed signature, so it is a PO/planner decision, not an implementer one.

Deliberately parentless: not part of milestone `okf-cli-huow`, and attaching it there would keep the milestone from going terminal.


### Requirement 1: One plan computation per archive invocation

**Objective:** As a catalogue maintainer working on a large store, I want `archive` to scan the reference matrix once rather than twice, so that the command's cost does not grow at double rate with the catalogue.

#### Acceptance Criteria

1. THE okf-cli SHALL compute the rename plan at most once per `archive` invocation.
2. THE okf-cli SHALL keep the inbound-concept report line of `cmd_archive` byte-identical to its current output.
3. THE okf-cli SHALL keep the existing `rename` behaviour and its test set unchanged.

#### Success Criteria

- SC-01: A single `archive` run performs exactly one `build_ref_matrix` scan, asserted by counting calls rather than by timing.
- SC-02: The pre-existing `rename` and `archive` test sets stay green without modification.
- SC-03: Restoring the second computation turns SC-01 red.

_Requirements: review of `okf-cli-16rg` 2026-08-09, finding I01_

## Note on authority

The duplication follows from the `perform_rename` signature fixed in `docs/okf-archive-lifecycle/SPEC.md` section 2. Letting that function accept or return an already-computed plan changes a spec-fixed signature, so the shape of the fix is a planner decision, not an implementer one. An implementer who reaches this leaf without that decision having been taken should stop and say so rather than pick a shape.

## Recommended Skills

- `superpowers:test-driven-development` — SC-01 needs a call-counting assertion that exists before the refactor, otherwise there is nothing to prove the second scan is gone.


## D01 — PO decision 2026-08-10: optional `plan` parameter

The bean states that the shape of this fix is a planner/PO decision because it touches the `perform_rename` signature fixed in `docs/okf-archive-lifecycle/SPEC.md` section 2. The PO decided on 2026-08-10, before any implementer was dispatched.

**Decision:** `perform_rename` gains a trailing optional parameter and recomputes only when it is absent.

```python
def perform_rename(root, old_abs, new_abs, apply, force,
                   verb="rename", plan=None):
    if plan is None:
        plan = plan_rename(root, old_abs, new_abs)
    ...
```

`cmd_archive` passes the plan it already computed for the AC7 report line:

```python
plan = plan_rename(root, src_abs, dest_abs)
print(f"{len(plan.inbound)} active concept(s) still link ...")
perform_rename(root, src_abs, dest_abs, args.apply,
               args.force, verb="archive", plan=plan)
```

`cmd_rename` keeps its call site unchanged, which is what keeps AC3 ("rename behaviour and its test set unchanged") cheap to satisfy.

**Rejected alternative:** splitting `perform_rename` into a planning and an applying half. Cleaner separation, but a larger cut into a function that `rename` and `archive` share — too much regression surface for a low-priority scan-count optimization.

**Spec obligation:** the implementer of this leaf appends a dated section to `docs/okf-archive-lifecycle/SPEC.md` section 2 recording the widened signature. Append, do not rewrite the existing paragraph — the original signature stays readable as what the milestone shipped.


## Prelude 2026-08-10 — carried over from the review of `okf-cli-tk33`

**I01 — the "is this path under that directory" idiom is now duplicated verbatim.** The `ce-specs-reviewer` flagged it as non-blocking on `okf-cli-tk33` (verdict APPROVED) and routed it here, because this is the leaf that touches code structure rather than tests.

Two places now compute the same boundary the same way:

- `cli/okf-cli.py:4288` — the new `rename` refusal guard
- `cli/okf-cli.py:4313` — `_prune_empty_archive_dirs`

both as `archive_root = os.path.realpath(os.path.join(root, "_archive"))` followed by `x == archive_root or x.startswith(archive_root + os.sep)`. A third, structurally similar instance sits in `_git_mv`, comparing against `root` instead. The reviewer was explicit that this leaf extended a pre-existing pattern rather than introducing it, and that the implementer named the precedent in a code comment instead of hiding it.

**This is an invitation, not an instruction.** A helper such as `_is_under(path, boundary)` or `_archive_root(root)` would remove the duplication, and the segment-boundary correctness that `okf-cli-tk33`'s review probed (a bundle named `my_archive` must NOT match) would then live in one place instead of three. But it is NOT part of this bean's acceptance, and AC3 of this bean requires the existing `rename` behaviour and its test set to stay unchanged. If you fold it in, it is a separate commit with its own mutation proof, and any doubt means you leave it and note it in `## Notes for T(n+1)` instead.

Still in force from the earlier reviews: `Refs: okf-cli-h12o` footer on EVERY commit including the bean-closing one, the 50-byte subject soft target counted on every subject, and mutation proofs citing `file:line` plus the mutated expression verbatim.


## Prelude addendum 2026-08-10 — from the review of `okf-cli-yixf`

**I02 — the 50-byte subject soft target was missed a fourth time**, on BOTH commits of that leaf (65 and 54 bytes), in the leaf whose own prelude names this exact recurrence. The 72-byte hard limit is hook-enforced and held every time, so nothing ever fails mechanically — which is precisely why the soft target keeps slipping. You are the last leaf of this epic. Count both subjects.



## Summary — closed 2026-08-10

Implemented D01: `perform_rename` (`cli/okf-cli.py:4106`) gained a trailing optional `plan` parameter, defaulting to `None`, recomputing via `plan_rename` only when absent (`cli/okf-cli.py:4174`). `cmd_archive` (`cli/okf-cli.py:4327`) now passes the plan it already built for its AC7 inbound-count report line through `plan=plan` (`cli/okf-cli.py:4392`), so a single `archive` invocation performs exactly one `build_ref_matrix` scan instead of two. `cmd_rename` (`cli/okf-cli.py:4267`) is untouched — no diff hunk touches it — which is what keeps AC3/R-04 (rename byte-identical) cheap to satisfy: `plan` stays `None` on that path and the function falls back to its old recompute-every-time behaviour exactly as before.

Two tests added in `cli/test_okf_cli.py:5715` (class `ArchiveComputesPlanOnce`): `test_sc01_single_archive_run_scans_the_ref_matrix_once` (SC-01, call-counting via `mock.patch.object(okf, "build_ref_matrix", wraps=...)`, exercised through `cmd_archive`) and `test_ac2_inbound_report_line_is_byte_identical` (AC2, literal-string pin on the full report line, not the pre-existing substring checks).

Commits: `e0b785a fix(archive): compute rename plan once` (code + tests), `d697d1e docs(archive): note perform_rename's plan param` (SPEC.md §2 addendum, appended not rewritten).

## Test-Output

RED (before the fix, `just test`):

```
FAIL: test_sc01_single_archive_run_scans_the_ref_matrix_once (test_okf_cli.ArchiveComputesPlanOnce.test_sc01_single_archive_run_scans_the_ref_matrix_once)
Exercised through cmd_archive, not a direct perform_rename call —
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/Users/erik/dev/okf-tools/cli/test_okf_cli.py", line 5744, in test_sc01_single_archive_run_scans_the_ref_matrix_once
    self.assertEqual(spy.call_count, 1)
AssertionError: 2 != 1
----------------------------------------------------------------------
Ran 634 tests in 32.703s
FAILED (failures=1)
```

GREEN (after the fix, `just test`):

```
Ran 635 tests in 26.305s
OK
```

635 = the declared 633-test baseline at HEAD `60c0617` + the 2 new tests in `ArchiveComputesPlanOnce`. Run through the declared substrate (`just test`, `python3 --version` → `Python 3.14.6`, Homebrew), not a substitute interpreter.

## Mutation proofs (gate item 5, cited `file:line` + mutated expression verbatim)

- **SC-03** (restore the second computation): `cli/okf-cli.py:4392` `perform_rename(root, src_abs, dest_abs, args.apply, args.force, verb=verb)` (dropped `plan=plan`) → SC-01 test red, `AssertionError: 2 != 1`. Reverted; `git diff --stat cli/okf-cli.py` unchanged before/after (`18 ++++++++++++++----`).
- **AC1** (compute at most once): same mutation as SC-03 — dropping the passed plan is exactly what makes the count go to 2, so SC-03's proof is AC1's proof.
- **AC2** (byte-identical report line): `cli/okf-cli.py:4392` (post-fix line) `print("{} active concept(s) still link to this thing".format(n_concepts))` (mutated `"concept"` → `"thing"`) → the new `test_ac2_inbound_report_line_is_byte_identical` went red (`AssertionError`, exact string not found in captured stdout). Reverted.
- **AC3** (rename behaviour/test set unchanged, no edits to pre-existing tests): `cli/okf-cli.py:4174` `if plan is None:` mutated to `if False:` → 43 pre-existing tests in `test_okf_cli.RenameWikilinks` (and the wider rename suite) went red with `TypeError: 'NoneType' object is not subscriptable` at `cli/okf-cli.py:4179` (`wl_rewrite = [r for r in plan["wikilinks"] ...]`). Reverted. No pre-existing test was edited to reach green (SC-02) — verified by `git diff` touching only `cli/okf-cli.py` (production) and the new `ArchiveComputesPlanOnce` class in `cli/test_okf_cli.py`; every pre-existing test body is byte-identical.

## Smoke

Throwaway layout under `mktemp -d` (not `~/Obsidian/Knowledge-Catalogue`): one bundle `a/old.md`, one inbound linker `b/src.md`. `archive a/old.md` (dry-run then `--apply`) printed `1 active concept(s) still link to this concept`, moved the file to `_archive/a/old.md`, rewrote the inbound link — byte-for-byte the same report shape as before this leaf. `archive _archive/a/old.md --restore --apply` moved it back to `a/old.md`, printed the same `1 active concept(s) still link to this concept` line (plan recomputed for the restore direction, unaffected by this change), and the empty `_archive/` tree was pruned (`okf-cli-gqss` behaviour intact). Final `find` listing showed only `a/old.md` and `b/src.md` — round trip clean.

## Deviations/ERRATA

None from D01's prescribed shape. Two additions beyond the bean's literal SC list, both within the gate's own instructions rather than scope creep: the AC2 literal-string test (gate item 3 explicitly required it, and the pre-existing `assertIn("N active concept(s)", ...)` checks only pin the prefix, not the full line) and treating SC-03's mutation as also serving AC1 (gate item 5 permits naming one test per criterion; the two criteria are the same fact from two angles — "at most once" and "restoring the second call turns it red" — so a second, differently-mutated test would have been redundant, not additional evidence). Did not touch the I01 helper-extraction invitation (duplicated "is this path under that directory" idiom, `cli/okf-cli.py:4288`/`4313`) — explicitly optional, left alone per instructions, noted below.

## Notes for T(n+1)

I01 from the `okf-cli-tk33` review (duplicated path-boundary idiom at `cli/okf-cli.py:4288` and `4313`, structurally echoed a third time in `_git_mv`) remains unaddressed — still an invitation, not an instruction, and this leaf's diff stayed minimal on purpose. This closes the last leaf of epic `okf-cli-0xkj`; the epic itself is not touched by this commit (container close is a PO/tag action, not an implementer status change).
