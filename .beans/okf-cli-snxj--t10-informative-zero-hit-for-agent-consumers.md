---
# okf-cli-snxj
title: T10 Informative zero-hit for agent consumers
status: todo
type: task
priority: normal
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-25T23:25:11Z
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
