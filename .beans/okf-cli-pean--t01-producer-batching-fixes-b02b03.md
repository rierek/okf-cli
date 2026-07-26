---
# okf-cli-pean
title: T01 Producer batching (fixes B02/B03)
status: in-progress
type: task
priority: high
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-26T05:00:54Z
parent: okf-cli-cskz
---

Plan: `docs/okf-retrieval-architecture/PLAN.md` → **Task 1**. Follow it step by step; it carries the literal code and tests.

Fixes findings B02 and B03: `embed_voyage()` sends *every* text in one request and `main()` writes rows only after a whole model pass returns (`cli/embeddings/build_tagvec.py:223-245, 343-351`), while `embed_bge_m3()` loops one HTTP call per text although `/api/embed` accepts a list (`:208-220`, measured 10-35x slower, LL-09). A 2437-concept run is structurally undoable today.

### Requirement 1: Batched embedding requests

**Objective:** As the catalogue maintainer, I want the embedding producer to send API-sized batches and persist each one, so that a full 2437-concept run is physically completable and resumable.

#### Acceptance Criteria

1. THE producer SHALL cut pending work into batches bounded by BOTH a per-model item count AND a per-model payload character budget.
2. THE producer SHALL send all texts of one bge-m3 batch in a single `/api/embed` request.
3. WHEN a batch completes THE producer SHALL write its rows to sqlite before starting the next batch.
4. IF a single item exceeds the character budget THEN THE producer SHALL emit it as its own batch rather than dropping it.
5. THE producer SHALL perform no network call and no write unless `--produce` is passed.

#### Success Criteria

- SC-01: `batches()` splits 5 items at `max_items=2` into `[2,2,1]`, and four 40-char items at `max_chars=100` into `[2,2]`.
- SC-02: `embed_bge_m3(["a","b","c"])` issues exactly 1 HTTP request whose `input` is `["a","b","c"]`, proven with a faked `urlopen` — no real network in any test.
- SC-03: the dry-run against the live catalogue prints `2437 concept(s) need title+body embedding` and writes nothing.
- SC-04: `python3 -m unittest discover -s cli -p 'test_*.py'` stays at exactly 19 failures / 2 errors.

_Requirements: PLAN.md Task 1 · findings B02/B03 · TASKS.md T11 · LESSONS-LEARNED LL-09_

## Steps

- [ ] Write the failing tests (`Batches`, `BgeBatchPayload`) in `cli/test_embeddings_tagvec.py`
- [ ] Run them, confirm they fail for the stated reason
- [ ] Add `BATCH_LIMITS` and `batches()`, rewrite `embed_bge_m3()` to send a list
- [ ] Wire both production blocks in `main()` to batch and write per batch
- [ ] Tests pass; suite still 19F/2E
- [ ] Verify the dry-run stays offline
- [ ] Commit `perf(embeddings): batch calls, write per batch`

## Recommended Skills

- `superpowers:test-driven-development`


## Additional success criterion (global constraint, network)

- SC-NET: no unit test added or touched by this task performs a real network call. Every embedding call under test is exercised through a faked `urlopen` or a patched module attribute. The producer's test module is network-free by construction and must stay that way.
