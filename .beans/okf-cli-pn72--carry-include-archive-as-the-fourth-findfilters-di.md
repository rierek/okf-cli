---
# okf-cli-pn72
title: carry include_archive as the fourth FindFilters dimension
status: todo
type: task
created_at: 2026-08-09T19:14:21Z
updated_at: 2026-08-09T19:14:21Z
parent: okf-cli-scd5
---

`FindFilters` (cli/okf-cli.py:761) documents at its own head why a filter dimension must live in the value object: the same three filters were once implemented three times, travelled as loose arguments through five signatures, and were missing from the semantic arm entirely (I01/B01). The visibility switch follows the same discipline, and the scope rule falls out of the same predicate.

### Requirement 1: Archive visibility as a filter dimension

**Objective:** As a searcher, I want the archive excluded by default and reachable with one flag, so that the default answer describes the active catalogue and nothing is silently lost.

#### Acceptance Criteria

1. THE okf-cli SHALL carry `include_archive` as a field of `FindFilters`, defaulting to excluded.
2. WHILE `include_archive` is not set THE okf-cli SHALL treat every path beginning with `_archive/` as no match.
3. THE okf-cli SHALL compare a scope against the path with its leading `_archive/` segment removed, so that a scoped query reaches the archived concepts of that same bundle.
4. THE okf-cli SHALL escape the underscore in the SQL LIKE predicate so that a bundle named `xarchive` is not excluded by it.

#### Success Criteria

- SC-01: `find <term>` without the flag returns no archived concept even though the concept is present in the index.
- SC-02: `find <term> --include-archive` returns it under its `_archive/<bundle>/<cid>` path.
- SC-03: `find <term> --scope <bundle> --include-archive` returns archived concepts of that bundle and none from another.
- SC-04: A bundle named `xarchive` remains visible without the flag.
- SC-05: Removing the default-exclusion predicate turns SC-01's test red; the test stays in the repo.

_Requirements: R-08, R-09, R-10_

## Recommended Skills

- `superpowers:test-driven-development`
