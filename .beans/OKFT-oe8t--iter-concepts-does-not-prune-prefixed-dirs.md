---
# OKFT-oe8t
title: iter_concepts does not prune _-prefixed dirs
status: in-progress
type: bug
priority: normal
created_at: 2026-08-09T19:09:25Z
updated_at: 2026-08-13T12:10:58Z
parent: OKFT-wmbu
---

Measured in lean-stack/docs/okf-knowledge-lifecycle/taxonomy-and-lifecycle (R09, reproducible via `just okf-archive-exclusion`).

`iter_concepts` (cli/okf-cli.py:81) prunes only dot-dirs and `assets`, while `iter_all_md` (:2582) additionally prunes `_`-prefixed staging dirs. In-bundle `_` content is therefore retrievable via index/list/find and skipped by check — the worst combination: reachable but unverified.

Really affected today: `general-knowledge-wiki/_intake/` and `qm-wiki/_intake/`.

Independent of the archive work in docs/okf-archive-lifecycle: that archive lives at catalogue level (`_archive/<bundle>/`), where the exclusion already holds. Tracked there as T15, deliberately kept out of that scope.

Note the outward coupling: fixing this makes `just okf-archive-exclusion` in lean-stack exit 1, which is intended — the guard then reports that DESIGN section 4 needs re-reading.


## ERRATA 2026-08-13 — line number for iter_all_md

The body above cites `iter_all_md` at `okf-cli.py:2582`. That is wrong: line 2582 holds the unrelated `render_recent_lines`. `iter_all_md` is defined at **okf-cli.py:2883**, and the pruning clause this bean compares against (`not d.startswith("_")`) sits at **2888-2890**. The function name is correct and greppable; only the line reference was off. Verified 2026-08-13 by ce-verify-operationalization.

`iter_concepts` at :81 is correct as written.
