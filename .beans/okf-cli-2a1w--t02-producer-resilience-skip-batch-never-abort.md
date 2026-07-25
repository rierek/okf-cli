---
# okf-cli-2a1w
title: 'T02 Producer resilience: skip batch, never abort'
status: todo
type: task
priority: high
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-25T23:32:42Z
parent: okf-cli-cskz
blocked_by:
    - okf-cli-pean
---

Plan: `docs/okf-retrieval-architecture/PLAN.md` → **Task 2**. Follow it step by step; it carries the literal code and tests.

LL-08 from the field: an unguarded arm died on a single plain HTTP 400 and threw away ~550 already-embedded concepts. The guarded run logged 4 retries and completed 2437/2437 (R31). Without this, Task 3 is not attemptable.

### Requirement 1: A single failed batch must not abort the run

**Objective:** As the catalogue maintainer, I want an unrecoverable batch to be skipped and logged rather than aborting the pass, so that one transient API error cannot cost a whole embedding run.

#### Acceptance Criteria

1. WHEN an embedding call raises THE producer SHALL retry it with exponential backoff before giving up.
2. IF a retry attempt is not the first THEN THE producer SHALL halve every text in the batch before retrying, because a 400 on these endpoints is usually an over-long input.
3. IF all attempts fail THEN THE producer SHALL log the skipped batch and continue with the next one, and SHALL NOT raise.
4. THE producer SHALL leave every already-written row intact, so that re-running the command re-plans only the missing rows.
5. THE retry ladder SHALL be exercisable without wall-clock delay, via an injected sleep.

#### Success Criteria

- SC-01: a callable that succeeds immediately returns its vectors with no retry logged.
- SC-02: a callable that fails once then succeeds returns vectors after exactly 2 invocations.
- SC-03: after the first retry the texts handed to the callable are strictly shorter than the originals.
- SC-04: a callable that always fails returns `None` — never an exception.
- SC-05: `python3 -m unittest discover -s cli -p 'test_*.py'` stays at exactly 19 failures / 2 errors.

_Requirements: PLAN.md Task 2 · TASKS.md T10 · LESSONS-LEARNED LL-08 · REFERENCES R31_

## Steps

- [ ] Write the failing `EmbedResilient` tests in `cli/test_embeddings_tagvec.py`
- [ ] Run them, confirm they fail for the stated reason
- [ ] Add `embed_resilient(fn, texts, label, sleep=time.sleep)` (retry, halve, skip)
- [ ] Route both production blocks through it, `continue` on `None`
- [ ] Tests pass; suite still 19F/2E
- [ ] Commit `fix(embeddings): skip failed batch, never abort`

## Recommended Skills

- `superpowers:test-driven-development`


## Additional success criterion (global constraint, network)

- SC-NET: no unit test added or touched by this task performs a real network call. Every embedding call under test is exercised through a faked `urlopen` or a patched module attribute. The producer's test module is network-free by construction and must stay that way.
