---
# OKFT-6361
title: T03 Document --limit, correct the --expand-tags promise
status: scrapped
type: task
priority: normal
created_at: 2026-07-26T13:02:30Z
updated_at: 2026-07-26T13:23:29Z
---

Plan: `docs/okf-cli-capability-surface/PLAN.md` → **Task 3**.

Two option texts on `find`. The second is the finding the PO did not raise.

### Requirement 1: `--limit` describes itself

**Objective:** As a user of `find`, I want every option to carry a description, so that no option renders with an empty help column.

#### Acceptance Criteria

1. THE `--limit` option of `find` SHALL carry help text naming its default (`cli/okf-cli.py:2598`, empty today).

### Requirement 2: `--expand-tags` states the measurement instead of promising one

**Objective:** As a reader of the help, I want a flag to tell me the state of the decision it depends on, so that I do not wait for a measurement that already happened.

#### Acceptance Criteria

1. THE `--expand-tags` help SHALL NOT contain the phrase `until measured`.
2. THE `--expand-tags` help SHALL state that the expansion was measured, found ineffective for the vocabulary-mismatch class it was built for, and therefore stays off (Q05/D17 of `docs/okf-retrieval-architecture/`).

#### Success Criteria

- SC-01: `find`'s `--limit` action help contains `default 10`.
- SC-02: `find`'s `--expand-tags` action help contains `measured` and not `until measured`.
- SC-03: full suite at `Ran 267 tests`, exactly 19 failures / 2 errors.

**Files:** `cli/okf-cli.py:2598` and `:2606-2609` · `cli/test_okf_cli.py` (append class `FindOptionHelp`)

## Steps

- [ ] Write the failing `FindOptionHelp` tests
- [ ] Run them, confirm both fail for the stated reason
- [ ] Fix both help strings with the literal text from the plan
- [ ] Full suite; commit `fix(cli): document --limit, correct --expand-tags`

## Recommended Skills

- superpowers:test-driven-development



Scrapped 2026-07-26: orphaned duplicate of OKFT-2ljd (same operationalization run, no parent, no blocked_by). The canonical leaf under epic OKFT-5uog is OKFT-2ljd.
