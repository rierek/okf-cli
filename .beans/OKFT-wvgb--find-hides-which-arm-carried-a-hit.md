---
# OKFT-wvgb
title: find hides which arm carried a hit
status: draft
type: bug
priority: normal
created_at: 2026-08-10T12:58:43Z
updated_at: 2026-08-10T12:58:43Z
parent: OKFT-hkze
---

## Objective (User Story)
As an agent consuming `find` output, I want every result line to state which retrieval arm produced it, so that I can tell a lexical hit from a semantic one without inferring it from a missing marker.

## Evidence (MODUS-B-REPORT B01)
`find` prints one banner for the whole list — `note: semantic arm owns this ranking (lexical top-1 lacked a clear margin)` — while the hit that actually answered the question may come from the lexical arm. In run R1 the answer sat at rank 5 with `score: 100/100` and NO `provenance:` line, four semantically ranked hits above it. Provenance was only derivable from the absence of a marker.

## EARS Acceptance
- WHEN `find` prints a result line, THE tool SHALL print a `provenance:` value for that line naming its arm, including the lexical one.
- THE banner SHALL keep describing who owns the ranking, not who produced an individual hit.

## Success Criteria
- SC-001: a mixed-arm result set prints an explicit arm on every line; asserted by a test over a query that provably mixes both arms.
- SC-002: `just test` green; the eval runner's `path:` parsing (docs/okf-retrieval-architecture/eval/remeasure.py:33) still works unchanged.
