---
# okf-cli-iwx4
title: share archive-aware scope resolution between the substring arm and list
status: in-progress
type: task
priority: normal
created_at: 2026-08-09T19:15:04Z
updated_at: 2026-08-09T21:41:23Z
parent: okf-cli-scd5
blocked_by:
    - okf-cli-pn72
---

`_substring_ranking` (cli/okf-cli.py:969) and `cmd_list` (:582) both traverse via `resolve_scopes` (:2940). One shared function adds the archive scopes when the flag is set. The path prefix of a hit stays its position under root — B04 must hold, an `okf-cli read` on the printed path has to resolve.

### Requirement 1: The scan arms reach the archive too

**Objective:** As a searcher, I want `list` and the substring fallback to honour the flag, so that the answer does not depend on which arm happened to serve the query.

#### Acceptance Criteria

1. THE okf-cli SHALL resolve search scopes through one shared function used by both `cmd_list` and the substring ranking.
2. WHEN `include_archive` is set THE okf-cli SHALL add the archive scopes to the traversal.
3. THE okf-cli SHALL emit each hit under its position below the catalogue root, so that `_archive/<bundle>/<cid>` is what `read` receives.
4. THE okf-cli SHALL keep applying the loaded-file predicate to every substring hit, so that a change of traversal shape cannot reopen the I01 gap.

#### Success Criteria

- SC-01: `list --type X` returns no archived concept without the flag and returns it with the flag.
- SC-02: `read` on a path printed by an archive hit resolves to the file.

_Requirements: R-12_

## Recommended Skills

- `superpowers:test-driven-development`
