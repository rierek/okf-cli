---
# okf-cli-pean
title: T01 Producer batching (fixes B02/B03)
status: completed
type: task
priority: high
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-26T05:04:18Z
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

## Summary

Implemented the plan's batching design verbatim: `BATCH_LIMITS` (per-model
`(max_items, max_chars)`), `batches()` cutting `(identity, text, key)` triples
by both count and char budget, `embed_bge_m3()` rewritten to send one
`/api/embed` call with a list `input` instead of one call per text, and
`main()`'s two `--produce` blocks (tag scope, concept scope) rewired to
iterate `batches()` and call `write_rows()`/`write_concept_rows()` per batch
so an interrupted run keeps everything already embedded. `embed_voyage()`
already sent one request per call (B02's "sends every text in one request"
referred to the caller passing the whole delta at once, which the new
per-batch loop now fixes structurally) — no change to its body was required,
only its caller in `main()`.

## Test-Output

RED (before implementation, `cli.test_embeddings_tagvec.Batches` +
`BgeBatchPayload`):

```
ERROR: test_empty_input_yields_nothing (cli.test_embeddings_tagvec.Batches.test_empty_input_yields_nothing)
AttributeError: module 'build_tagvec' has no attribute 'batches'

ERROR: test_single_oversized_item_is_not_dropped (cli.test_embeddings_tagvec.Batches.test_single_oversized_item_is_not_dropped)
AttributeError: module 'build_tagvec' has no attribute 'batches'

ERROR: test_splits_by_char_budget (cli.test_embeddings_tagvec.Batches.test_splits_by_char_budget)
AttributeError: module 'build_tagvec' has no attribute 'batches'

ERROR: test_splits_by_item_count (cli.test_embeddings_tagvec.Batches.test_splits_by_item_count)
AttributeError: module 'build_tagvec' has no attribute 'batches'

FAIL: test_sends_all_texts_in_one_request (cli.test_embeddings_tagvec.BgeBatchPayload.test_sends_all_texts_in_one_request)
AssertionError: 3 != 1

Ran 5 tests in 0.001s
FAILED (failures=1, errors=4)
```

GREEN (after implementation):

```
$ python3 -m unittest cli.test_embeddings_tagvec -v 2>&1 | grep -E "(FAIL|ERROR|^Ran|^OK)"
Ran 24 tests in 0.023s
OK
```

Full suite gate (before task: 187 tests / 19F/2E; after task: 192 tests —
+5 new — / still exactly 19F/2E):

```
$ python3 -m unittest discover -s cli -p 'test_*.py' 2>&1 | grep -E "^(FAILED|Ran|OK)"
Ran 192 tests in 14.885s
FAILED (failures=19, errors=2)
```

Mutation test on the core batching boundary (`len(cur) >= max_items` ->
`len(cur) > max_items`):

```
$ python3 -m unittest cli.test_embeddings_tagvec.Batches -v 2>&1 | grep -E "(FAIL|ERROR|^Ran|^OK)"
test_splits_by_item_count ... FAIL
FAILED (failures=1)
```
Reverted byte-identically (`git diff` clean against the intended patch before
commit); full module re-run back to `OK`.

## Smoke

Dry-run against the live catalogue, no network/writes:

```
$ python3 cli/embeddings/build_tagvec.py --root ~/Obsidian/Knowledge-Catalogue --target concepts --model voyage-3-large
voyage-3-large: 2443 concept(s) need title+body embedding
(dry-run — no network calls, no writes. Re-run with --produce to embed.)
```

## Deviations/ERRATA

- SC-03 states the dry-run prints "2437 concept(s)"; the live run printed
  2443. The catalogue is a separate, actively-edited git repo and grew by 6
  concepts between the plan's grounding and this run — not a code defect.
  Behavior (offline, prints delta count, no writes) matches SC-03's intent
  exactly.
- `embed_voyage()`'s body was left unmodified. B02's finding text ("sends
  every text in one request") described the caller passing the *entire*
  delta to it in one shot, not a per-call defect in `embed_voyage()` itself
  (which already issues exactly one HTTP request per invocation). The plan's
  own fix wires `main()` to call it once per batch via `batches()` — done —
  so no change to `embed_voyage()`'s internals was needed or specified by
  the plan's Step 3 pseudocode (which only replaces `embed_bge_m3`).

## Notes for T02

- T02 (bean okf-cli-2a1w, "Producer resilience", TASKS.md T10, fixes LL-08)
  builds on this batching structure: `main()`'s two `--produce` blocks now
  loop over `batches()` and call `write_rows()`/`write_concept_rows()` once
  per batch — that per-batch write is the resumability seam T02 should hang
  retry/backoff on. A batch failure today still raises and aborts the whole
  run; T02 is expected to catch per-batch and continue/retry rather than
  losing already-embedded batches.
- `BATCH_LIMITS[model]` is looked up inside both `main()` blocks via
  `max_items, max_chars = BATCH_LIMITS[model]` — if T02 adds a third model
  or a CLI override for batch size, this is the single place to touch.
- The `_embed(model, texts)` closure in `main()` is still the resolution
  point between model name and embed function; tests monkeypatch
  `bt.embed_bge_m3`/`bt.embed_voyage` at module level, which still works
  since `_embed` resolves those names at call time, not at closure-creation
  time — keep that property if T02 changes the dispatch.
