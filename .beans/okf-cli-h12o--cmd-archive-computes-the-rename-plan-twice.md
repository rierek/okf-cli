---
# okf-cli-h12o
title: cmd_archive computes the rename plan twice
status: todo
type: task
priority: low
created_at: 2026-08-09T20:04:06Z
updated_at: 2026-08-10T10:46:23Z
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
