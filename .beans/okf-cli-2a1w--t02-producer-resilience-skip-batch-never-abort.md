---
# okf-cli-2a1w
title: 'T02 Producer resilience: skip batch, never abort'
status: in-progress
type: task
priority: high
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-26T05:08:52Z
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



## PRELUDE 2026-07-26 — carried over from T01 review (ce-specs-reviewer on okf-cli-pean)

Do this FIRST, as its own commit, before the T02 work proper.

**I01 (low, non-blocking on T01, lands on your seam):** no end-to-end test exercises the
"write rows before starting the next batch" / resumability property at the `main()` level.
Only the pure `batches()` unit and the single-request `embed_bge_m3` payload are covered.
The per-batch-persist property is today verified by code reading and a reviewer probe, not by
a committed test.

Location: `cli/embeddings/build_tagvec.py:349-364` (the two production blocks in `main()`),
test file `cli/test_embeddings_tagvec.py`.

Asked-for test: mock `_embed`/`embed_bge_m3` to raise on batch 2, then assert that batch 1's
rows are already committed in the sqlite output. Reviewer's note: this belongs on T02 because
resilience touches exactly this seam.

**Verified facts from T01 you can build on** (reviewer-confirmed, not just implementer-claimed):
- `write_rows(output, rows)` / `write_concept_rows(output, rows)` are called inside the
  `for batch in batches(...)` loop and each commits via its own sqlite connection BEFORE the
  next batch's `_embed()` call. An abort mid-run keeps all already-committed batches.
- A batch failure today still raises and aborts the run — that is exactly T02's job to change
  (catch per batch, skip, continue, never lose written batches).
- `BATCH_LIMITS[model]` is the single touch point for adding a model or a size override.
- `_embed(model, texts)` resolves `embed_bge_m3`/`embed_voyage` by module-global name at CALL
  time, not at closure-creation time. Existing tests monkeypatch those names — preserve that
  property if you change dispatch.

Source: ce-specs-reviewer verdict on okf-cli-pean, 2026-07-26 (commits 2a07ee9, 3981bd8).
