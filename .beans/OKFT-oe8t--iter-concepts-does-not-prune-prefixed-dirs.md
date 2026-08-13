---
# OKFT-oe8t
title: iter_concepts does not prune _-prefixed dirs
status: todo
type: bug
priority: normal
created_at: 2026-08-09T19:09:25Z
updated_at: 2026-08-13T11:07:18Z
parent: OKFT-wmbu
---

Measured in lean-stack/docs/okf-knowledge-lifecycle/taxonomy-and-lifecycle (R09, reproducible via `just okf-archive-exclusion`).

`iter_concepts` (cli/okf-cli.py:81) prunes only dot-dirs and `assets`, while `iter_all_md` (:2582) additionally prunes `_`-prefixed staging dirs. In-bundle `_` content is therefore retrievable via index/list/find and skipped by check — the worst combination: reachable but unverified.

Really affected today: `general-knowledge-wiki/_intake/` and `qm-wiki/_intake/`.

Independent of the archive work in docs/okf-archive-lifecycle: that archive lives at catalogue level (`_archive/<bundle>/`), where the exclusion already holds. Tracked there as T15, deliberately kept out of that scope.

Note the outward coupling: fixing this makes `just okf-archive-exclusion` in lean-stack exit 1, which is intended — the guard then reports that DESIGN section 4 needs re-reading.
