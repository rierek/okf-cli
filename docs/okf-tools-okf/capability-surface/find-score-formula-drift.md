---
type: LessonLearned
title: find's documented score formula went stale after the FTS arm shipped
description: The deleted docstring's "achieved/max = 6 * number of terms" score explanation only ever described the substring fallback; since the FTS arm shipped, find reports a 0..100 relative scale — the carried-forward prose had to be corrected, not copied.
tags:
  - okf-cli
  - retrieval
  - documentation-drift
timestamp: 2026-07-26T00:00:00Z
---

# find's documented score formula went stale after the FTS arm shipped

Quelle: `docs/okf-cli-capability-surface/PLAN.md`, finding B10 ("Findings this plan
fixes"), Epic `okf-cli-5uog`.

The docstring block being deleted documents `find`'s score as `achieved/max ("4/6") —
3 title-hit + 2 tag-hit + 1 body-hit per term … max = 6 * number of terms`. That is
only true of the **substring fallback**. Since the FTS arm shipped, `_rank_lexically()`
returns a 0..100 scale relative to the run's own top hit, and semantic hits are
`round(100 * cosine)` — which is why a live query prints `score: 46/100`. The prose
carried into `find`'s epilog therefore had to be corrected, not copied.

Location: `cli/okf-cli.py:16-19` (stale prose) vs `:912-928` (`_rank_lexically`),
`:1140-1152` (`_semantic_hit_dicts`).

## Why this is a lesson, not just a bug

The same defect class this whole plan fixes — a capability described by hand in three
places, drifting independently — reached even the one piece of narrative detail
(`find`'s scoring explanation) that the plan's authors deliberately chose to preserve
rather than delete. Preserving prose without re-verifying it against the current code
carries the drift forward instead of fixing it.

## Related

- [Capability-surface decisions D01-D04](/okf-tools-okf/capability-surface/capability-surface-decisions.md) — D02 is the
  fix this finding motivates (argparse becomes the single source of truth).
