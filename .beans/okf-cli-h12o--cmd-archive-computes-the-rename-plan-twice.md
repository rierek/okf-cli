---
# okf-cli-h12o
title: cmd_archive computes the rename plan twice
status: draft
type: task
priority: low
created_at: 2026-08-09T20:04:06Z
updated_at: 2026-08-09T20:04:06Z
---

Found by the review of `okf-cli-16rg` (2026-08-09, finding I01) — non-blocking, deliberately not fixed inside that leaf.

`cmd_archive` calls `plan_rename(root, src_abs, dest_abs)` to print the AC7 report line ("N active concept(s) still link to this concept"), and `perform_rename` then computes the same plan again internally, because it does not return one. See `cli/okf-cli.py:4037-4042`.

The duplication is a known consequence of the signature fixed in `docs/okf-archive-lifecycle/SPEC.md` §2, recorded in the `## Notes for T(n+1)` section of `okf-cli-2lj0` — it was not overlooked. The cost is a second `build_ref_matrix` scan per `archive` invocation, which grows with catalogue size.

Possible fix for a later iteration: let `perform_rename` accept or return an already-computed plan. That touches a spec-fixed signature, so it is a PO/planner decision, not an implementer one.

Deliberately parentless: not part of milestone `okf-cli-huow`, and attaching it there would keep the milestone from going terminal.
