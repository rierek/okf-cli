---
# okf-cli-snxj
title: T10 Informative zero-hit for agent consumers
status: in-progress
type: task
priority: normal
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-26T08:19:04Z
parent: okf-cli-cskz
blocked_by:
    - okf-cli-uagv
---

Plan: `docs/okf-retrieval-architecture/PLAN.md` → **Task 10**. Follow it step by step; it carries the literal code and tests.

The consumer of `find` is usually an agent over MCP, and an agent can reformulate if it learns *why* nothing matched (Q13). Only the zero-hit branch changes (`cli/okf-cli.py:881-883`) — a query with hits prints exactly as before.

### Requirement 1: A zero hit hands back something to reformulate with

**Objective:** As an agent whose query returned nothing, I want the nearest registered tags, so that I can reformulate instead of giving up.

#### Acceptance Criteria

1. WHEN a query yields no hits THE CLI SHALL print the registered tag slugs closest to the query's terms, and a concrete retry suggestion.
2. IF no tag is close enough THEN THE CLI SHALL print the plain no-match line without suggestions.
3. THE suggestion lookup SHALL use fuzzy string matching only, so that it also works on the fully degraded path with no index, no cache and no network.
4. THE output for a query WITH hits SHALL be unchanged.

#### Success Criteria

- SC-01: `_zero_hit_suggestions(root, "tailscal")` contains `tailscale`.
- SC-02: `_zero_hit_suggestions(root, "zzzzqqqq")` returns `[]`.
- SC-03: `find tailscal` prints `(no matches for: tailscal)` and names `tailscale`.
- SC-04: the fixture gate still prints `GATE: PASS` — `cli/eval/runner.py:64` only parses `score:`/`path:` lines, so the extra lines cannot confuse it. Verify, do not assume.
- SC-05: `python3 -m unittest discover -s cli -p 'test_*.py'` stays at exactly 19 failures / 2 errors.

_Requirements: PLAN.md Task 10 · QUESTIONS Q13 · TASKS.md T07_

## Steps

- [ ] Write the failing `ZeroHitSuggestions` tests
- [ ] Run them, confirm they fail for the stated reason
- [ ] Add `_zero_hit_suggestions()` using `difflib`; extend the zero-hit branch
- [ ] Tests pass; suite still 19F/2E
- [ ] Re-run the gate command from the measurement task, confirm `GATE: PASS`
- [ ] Commit `feat(cli): suggest nearest tags on zero hit`

## Recommended Skills

- `superpowers:test-driven-development`



## PRELUDE 2026-07-26 — carried over from T09 (measured facts, not estimates)

**The residual zero-hit set you are writing output for: 8 of 48 queries (0.1667 combined)** —
7 of 40 in `queries_v2.json`, 1 of 8 in `queries_real.json`. Down from 0.979. Identify the
exact rows via `docs/okf-retrieval-architecture/eval/remeasure.py` and
`docs/okf-retrieval-architecture/eval/shipped_v2.json`.

**Do NOT assume your `(no matches ...)` branch covers the `okf-cli-uumj` squeeze-out cases.**
It does not, by construction: in those cases the target IS a hit — it is merely truncated out
of the output window. A zero-hit message will never fire for them. Measured by T09 and
independently reproduced by the reviewer: 5 of 48 queries (10.4%) reach the mechanism at all,
and of those **5 of 5 (100%)** lose their target from the window if that one concept has no
`concept_emb` row. Affected concepts: tailscale-subnet-routing, data-ui-convention,
replikations-playbook, ai-operating-system, immich.

Gate state entering T10 (all four criteria passed, no retune, reviewer-reconfirmed):
zero-hit 0.1667 (<= 0.30) · MRR 0.4519 (>= 0.35) · real-query zero-hit 0.125 (<= 0.25) ·
p50 0.621 s (<= 2.0 s). Baseline: 248 tests, exactly 19 failures / 2 errors BOTH with
`VOYAGE_API_KEY` set and with `env -u VOYAGE_API_KEY`.
