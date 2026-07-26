---
# okf-cli-2ljd
title: T03 Document --limit, correct the --expand-tags promise
status: in-progress
type: task
priority: normal
created_at: 2026-07-26T13:02:45Z
updated_at: 2026-07-26T13:40:43Z
parent: okf-cli-5uog
blocked_by:
    - okf-cli-lbh1
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



## Prelude from the T01/T02 reviews (2026-07-26, non-blocking)

1. The 50-character subject cap applies to EVERY commit, including the bean-close meta commit. T02's close commit `1fb3463` ("chore(beans): close lbh1, commands registered via _sub") was 54 characters and nothing caught it: there is no `commit-msg` hook in `.git/hooks/`, so the cap is a discipline, not a guard. Count the subject before committing.
2. For any before/after proof, snapshot with `git show <rev>:<path> > /tmp/<x>.py` and diff against the working tree. Do not use `git stash` — it is a shared-tree operation and this repo sees concurrent activity.
