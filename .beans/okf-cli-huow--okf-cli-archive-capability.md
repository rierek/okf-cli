---
# okf-cli-huow
title: okf-cli archive capability
status: todo
type: milestone
created_at: 2026-08-09T19:13:36Z
updated_at: 2026-08-09T19:13:36Z
---

Give the CLI the archive half of the knowledge lifecycle: move a concept out of the active catalogue without losing it, keep every inbound link working, and let `find`/`list` reach back into the archive on request.

Spec: `docs/okf-archive-lifecycle/SPEC.md` (R-01 … R-15). The convention it implements was decided upstream in `lean-stack/docs/okf-knowledge-lifecycle/taxonomy-and-lifecycle/DESIGN.md` (D05, D06, D07, D08, D13, D14, D21) and is not renegotiated here.

Three technical strands, one per child feature:

1. The `archive` command itself — a thin wrapper over `rename`, which already carries the git-aware move, the link rewrite and the reversibility.
2. Wikilink resolution into the archive — without it, archiving turns inbound `[[x]]` links into check violations in files nobody touched.
3. Archive-aware retrieval — `--include-archive` as a fourth `FindFilters` dimension, plus the index work that makes the flag more than a decoration.

Out of scope and tracked separately: `okf-cli-oe8t` (iter_concepts does not prune `_`-prefixed dirs). That blind spot concerns in-bundle staging and is independent of the catalogue-level archive.
