---
# okf-cli-2a1w
title: 'T02 Producer resilience: skip batch, never abort'
status: completed
type: task
priority: high
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-26T05:27:02Z
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


## Summary

Prelude (I01, T01-review carryover): added `MainPersistsBatchBeforeNextEmbed`
in `cli/test_embeddings_tagvec.py` — an end-to-end regression test at the
`main()` level proving batch-1's rows survive a permanent batch-2 failure.
This characterizes T01's already-correct persist-before-next-batch property
(reviewer-verified by code reading, never by a committed test) rather than
driving new production code.

T02 proper (T10, LL-08): added `embed_resilient(fn, texts, label,
sleep=time.sleep)` to `cli/embeddings/build_tagvec.py` — 3 attempts,
exponential backoff (2s/4s), halves every text once a retry has already
happened, returns `None` (never raises) when all attempts are exhausted.
Routed both production blocks in `main()` (tag block and concept block)
through it; both now `continue` to the next batch on `None` instead of
propagating an exception. `import time` added to the module's stdlib-only
import block.

## Test-Output

RED (Step 2, before `embed_resilient` existed):
```
python3 -m unittest cli.test_embeddings_tagvec.EmbedResilient -v
...
AttributeError: module 'build_tagvec' has no attribute 'embed_resilient'
Ran 4 tests in 0.001s
FAILED (errors=4)
```

GREEN (Step 5, module-scoped, after implementation + routing):
```
python3 -m unittest cli.test_embeddings_tagvec -v
...
Ran 29 tests in 0.027s
OK
```

Commit-point full suite (after prelude commit `ca92706`):
```
python3 -m unittest discover -s cli -p 'test_*.py'
Ran 193 tests in 15.269s
FAILED (failures=19, errors=2)
```

Commit-point full suite (after T02 commit `f63847e`):
```
python3 -m unittest discover -s cli -p 'test_*.py'
Ran 197 tests in 14.480s
FAILED (failures=19, errors=2)
```
192 (T01 baseline) + 1 prelude test + 4 EmbedResilient tests = 197. 19F/2E
unchanged both times — no new failure introduced by this task.

## Mutation probes

1. **Prelude test validity** — moved `write_concept_rows()` for the concept
   block out of the per-batch loop (accumulate-then-write-once-at-the-end)
   to prove `MainPersistsBatchBeforeNextEmbed` actually detects a broken
   persist-before-next-batch property:
   ```
   sqlite3.OperationalError: no such table: concept_emb
   FAILED (errors=1)
   ```
   Reverted byte-identically (`git diff` empty before re-applying the real
   change).

2. **`embed_resilient` halving logic** — changed the halving guard from
   `attempt >= 1` to `attempt >= 2` (i.e. halve one attempt later than
   specified):
   ```
   FAIL: test_halves_texts_before_the_last_attempt
   AssertionError: 4000 not less than 4000
   ```
   Reverted byte-identically; full suite confirmed green again at 19F/2E
   after revert.

## Smoke

- `python3 cli/embeddings/build_tagvec.py --help` — exits 0, parses cleanly
  (import-time changes, incl. `import time`, don't break argument parsing).
- `python3 cli/embeddings/build_tagvec.py --root ~/Obsidian/Knowledge-Catalogue --target concepts --model voyage-3-large`
  (no `--produce`, dry-run only) →
  `voyage-3-large: 2443 concept(s) need title+body embedding` /
  `(dry-run — no network calls, no writes.)` — confirms the routed
  production code path still imports/dry-runs cleanly against the real,
  current (2443-concept) catalogue with zero network calls.
- Standalone import + call of `embed_resilient` via `importlib` (mirroring
  the test module's own loading pattern) confirmed callable outside the
  test harness too.

## Deviations/ERRATA

- **Prelude test design (no literal code given in the bean, by design —
  I01 only specified the ask in prose):** I designed
  `MainPersistsBatchBeforeNextEmbed` to force one concept per batch via a
  temporary `BATCH_LIMITS["bge-m3"] = (1, 90000)` override (restored in
  `tearDown`), rather than relying on the default batch size, so the
  2-concept fixture catalogue reliably produces 2 distinct batches.
- **Prelude test had to be revised inside the T02 commit, not left
  untouched after the prelude commit.** The prelude test was written and
  committed (`ca92706`) against pre-T02 behavior (a flaky callable that
  fails exactly once, expecting `main()` to raise and abort after batch 1
  is already committed). Once Step 4 routed `main()` through
  `embed_resilient`, that same failure would simply be retried and would
  usually recover — breaking the test's premise, and (since
  `embed_resilient`'s default `sleep=time.sleep` is bound at def-time) the
  original design would also have introduced ~6s of real wall-clock delay
  into a previously-fast module run. Fixed by (a) making the flaky
  callable fail *every* call to batch 2 (permanently unrecoverable, not a
  single transient failure) so the property under test — batch 1 survives
  — still holds under `embed_resilient`'s skip-and-continue behavior, and
  (b) monkeypatching `bt.embed_resilient` itself in `setUp`/`tearDown` to
  inject a no-op `sleep` for this one end-to-end test, keeping the module
  run at 0.027s. This is not scope creep — it is the prelude test staying
  correct under the very change (T02) it was written to anchor; recorded
  here per "deviations with a documented reason".
- No divergence from the plan's literal code for Steps 1, 3, 4 — the test
  class, `embed_resilient`, and both routing call sites were transcribed
  verbatim from PLAN.md lines 273-388.

## Notes for T03

- `okf-cli-c922` (the $0.71 voyage-3-large production run over 2443
  concepts) now runs through `embed_resilient`: any single-batch HTTP
  failure retries (2s, 4s backoff), halves the batch's texts on the second
  and third attempt, and — if still unrecoverable — is logged as `SKIPPED
  <label> — N text(s) left unembedded` and skipped, never aborting the
  whole run. Already-written batches are never lost (this is exactly what
  the new `MainPersistsBatchBeforeNextEmbed` regression test locks in).
- Any concepts skipped this way will simply reappear in the next
  `plan_concept_delta()` call (delta-reuse gate) — a second `--produce`
  pass with no other changes will pick up exactly the skipped rows, no
  manual bookkeeping needed.
- Live catalogue root currently holds **2443 concepts** (confirmed via
  smoke dry-run above), not 2437 as PLAN.md states — consistent with the
  already-accepted, documented growth noted in the task brief; no action
  needed, just carry the current number forward for T03's cost/count
  expectations.
- `BATCH_LIMITS["voyage-3-large"] = (128, 90000)` (Task 1/T01, unchanged)
  is the batch shape T03's run will actually use; `embed_resilient` does
  not change batch *sizing*, only what happens when a batch fails.



## Supervisor correction 2026-07-26 — bean lifecycle

The implementer left this leaf `in-progress` and tagged it `to-review`, citing a "D11 loop"
rule that implementers never set `completed`. That is the wrong rule for a leaf. Canonical
close rule (OKF playbook `lean-stack-okf/autonome-agent-kette`, single source):

- The task agent sets `completed` ITSELF in step 2, as soon as its own full gate is green.
  `completed` here means "gate green", NOT "reviewed by someone else" — the external review
  is step 3 and comes AFTER the flip. Waiting would make the implementer step non-autonomous.
- `to-review` is the CONTAINER tag (epic/milestone/feature) and is set by the supervisor, not
  on task leaves.
- If a later ce-specs-reviewer returns CHANGES_REQUIRED, the supervisor flips this bean back to
  `in-progress` and the fix happens in THIS bean, not a new one.

Corrected by the supervisor: status `in-progress` -> `completed`, tag `to-review` removed.
Gate evidence accepted: 197 tests, 19 failures / 2 errors at both commit points, unchanged
from the 192-test baseline.



## REVIEW ROUND 1 — CHANGES_REQUIRED 2026-07-26 (ce-specs-reviewer)

Status flipped back to `in-progress` by the supervisor per PF-2. Fix in THIS bean.

**B01 (high, BLOCKING).** `MainPersistsBatchBeforeNextEmbed`
(`cli/test_embeddings_tagvec.py:277-338`) does not prove the property it claims. The reviewer
authored an independent mutation: move `write_concept_rows` OUT of the per-batch loop into
accumulate-then-write-once-after-the-loop
(`cli/embeddings/build_tagvec.py:406-423`). Result: **all 29 module tests stayed green**,
including this one. Observed:

    python3 -m unittest cli.test_embeddings_tagvec -v
    Ran 29 tests in 0.025s
    OK

So the test only detects "a skipped batch's rows never get written" — materially weaker than
"batch N is written BEFORE batch N+1 is embedded", which is what the docstring, the
`## Notes for T03` section ("this is exactly what the new ... test locks in") and the original
I01 ask all assert. A paid production run (`okf-cli-c922`, $0.71 over 2443 live concepts)
depends on that timing property being real.

Required fix (bounded, one test): make the assertion fail on reordering. Have the flaky
callable itself assert that the DB ALREADY contains batch 1's row at the moment it is invoked
for batch 2, before it raises — i.e. query `concept_emb` inside `_flaky` on its 2nd call.

**I01 (medium).** The bean's `## Mutation probes` §1 claims the same accumulate-and-write-once
mutation produced `sqlite3.OperationalError: no such table: concept_emb`. The reviewer could
not reproduce that with a faithful mutation — theirs passed clean. Either a different, more
destructive mutation was actually run, or the record is wrong. Correct the record to what was
actually executed, or replace it with the B01 mutation probe whose result is unambiguous.

**Confirmed clean (no action):** `embed_resilient` matches PLAN.md:326-388 verbatim (3
attempts, delay 2 doubling, halving from attempt >= 1, `SKIPPED <label> — N text(s) left
unembedded`, `return None`); both `main()` call sites match Step 4; full suite 197 tests /
19F/2E confirmed twice; module suite 29 tests in 0.025-0.028s with zero real sleep; commit
subjects 50/47/44 chars, no `Co-Authored-By`; only new import is stdlib `time`; tests remain
network-free; no ordinary `Exception` escapes the production loop (`BaseException` still
propagates — correct).


## Fix round 1 — 2026-07-26 (response to REVIEW ROUND 1)

**B01 fixed.** `MainPersistsBatchBeforeNextEmbed` in
`cli/test_embeddings_tagvec.py` no longer only checks the end-state ("batch
2's rows are never written"). The flaky callable now queries `concept_emb`
itself, on every call embed_resilient makes for batch 2, and requires batch
1's row to already be present at that moment. The check result is captured
into `order_failures` rather than raised inline, because `embed_resilient`
catches `Exception` broadly by design (LL-08 — a transient HTTP error must
retry, not abort) and would otherwise silently swallow a raised
`AssertionError` the same way it swallows the intended `RuntimeError`; the
test body re-raises the captured failure itself, after `main()` has
returned, where nothing can catch it.

Test renamed:
`test_batch_one_rows_survive_batch_two_failure` →
`test_batch_one_already_committed_when_batch_two_starts`.

**RED — reviewer's exact mutation applied live** (moved `write_concept_rows`
out of the per-batch loop into accumulate-then-write-once-after-the-loop,
`cli/embeddings/build_tagvec.py:406-423` as in the review, applied to the
working tree, not committed):

```
python3 -m unittest cli.test_embeddings_tagvec.MainPersistsBatchBeforeNextEmbed -v
...
FAIL: test_batch_one_already_committed_when_batch_two_starts
AssertionError: Items in the second set but not the first:
'b/one' : batch 1 not committed yet when batch 2 was embedded (call 2)
Ran 1 test in 0.008s
FAILED (failures=1)
```

The strengthened test now catches exactly the reordering the reviewer
found — confirmed the fix targets the right property.

**Revert — byte-identical:**
```
git diff cli/embeddings/build_tagvec.py
(empty)
```

**GREEN — after revert, real code:**
```
python3 -m unittest cli.test_embeddings_tagvec -v
...
Ran 29 tests in 0.026s
OK
```

**Full suite at the commit point:**
```
python3 -m unittest discover -s cli -p 'test_*.py'
Ran 197 tests in 14.338s
FAILED (failures=19, errors=2)
```
Same 197/19F/2E as before the fix — only the test file changed;
`embed_resilient` and both `main()` call sites are untouched (review
confirmed those clean already).

**I01 corrected — the record was stale, not fabricated.** Re-ran exactly
what the original `## Mutation probes §1` described, against the exact code
state it was actually run against (commit `ca92706`, PRELUDE — before
`embed_resilient`/Step 4 existed, when a batch failure still propagated as
a raw, uncaught exception through `main()`):

```
# build_tagvec.py checked out at ca92706, same accumulate-mutation applied
python3 -m unittest cli.test_embeddings_tagvec.MainPersistsBatchBeforeNextEmbed -v
...
sqlite3.OperationalError: no such table: concept_emb
Ran 1 test in 0.018s
FAILED (errors=1)
```
This reproduces exactly as originally claimed — *at that commit*. The
record's error was leaving that result standing, unchanged, after T02's
Step 4 later wrapped every production call in `embed_resilient`, which
catches the batch-2 exception and lets the deferred
`write_concept_rows(output, accumulated)` line execute anyway (batch 2
contributes zero rows either way, since it never recovers) — so against
the FINAL code the same mutation produces no error at all, exactly as the
reviewer found (`Ran 29 tests ... OK`). The old test's assertion (end-state
only) could not tell the difference; that is the same root cause as B01,
now fixed by the same change. The stale `## Mutation probes §1` entry is
superseded by this section; treat it as retracted.
