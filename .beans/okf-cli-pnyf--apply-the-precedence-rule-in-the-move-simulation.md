---
# okf-cli-pnyf
title: apply the precedence rule in the move simulation
status: todo
type: task
created_at: 2026-08-09T19:14:39Z
updated_at: 2026-08-09T19:14:39Z
parent: okf-cli-xlck
blocked_by:
    - okf-cli-hk77
---

`_index_after_move` (cli/okf-cli.py:3670) simulates the basename index after a move in order to decide `turns_ambiguous`. If it does not apply the same active-before-archived rule as the index itself, the dry run of `archive` reports ambiguity that never materialises and refuses to proceed without `--force`.

### Requirement 1: Consistent resolution before and after the move

**Objective:** As a catalogue maintainer, I want the move simulation to resolve links the way the real index does, so that archiving is not blocked by an ambiguity that does not exist.

#### Acceptance Criteria

1. THE okf-cli SHALL apply the active-before-archived precedence rule inside `_index_after_move`.
2. WHEN archiving a concept whose basename is also held by an active concept THE okf-cli SHALL NOT report the inbound links as turning ambiguous.

#### Success Criteria

- SC-01: `archive` of a concept sharing its basename with an active one completes without `--force` and reports no `turns-ambiguous` line.

_Requirements: R-07_

## Recommended Skills

- `superpowers:test-driven-development`
