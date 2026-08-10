---
# OKFT-8j7l
title: T07 Semantic arm on voyage-3-large
status: completed
type: task
priority: high
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-26T07:07:51Z
parent: OKFT-cskz
blocked_by:
    - OKFT-c922
    - OKFT-17y7
---

Plan: `docs/okf-retrieval-architecture/PLAN.md` → **Task 7**. Follow it step by step; it carries the literal code and tests.

The query path still embeds locally with bge-m3 (`cli/okf-cli.py:673-675, 704-716`) even though D13 made `voyage-3-large` productive. D16 keeps the degradation two-stage: voyage, then lexical only — bge-m3 is NOT a runtime fallback, and `concept_emb` holds voyage rows only.

Renaming matters here: under conditional handover this arm is no longer a *backstop* that fills gaps. On a paraphrase query it owns the ranking.

### Requirement 1: Voyage-backed semantic arm with two-stage degradation

**Objective:** As an agent issuing a paraphrase query, I want the semantic arm to use the model that was measured as usable, so that I get the concept I meant instead of nothing.

#### Acceptance Criteria

1. THE query embedding call SHALL use model `voyage-3-large` with `input_type` `query` and bearer authentication.
2. IF `VOYAGE_API_KEY` is unset THEN THE embedding call SHALL raise, so that the caller degrades rather than sending an unauthenticated request.
3. IF the embedding cache, its table, the API key or the backend is unavailable THEN THE semantic arm SHALL return no results and SHALL print exactly one stderr note, and SHALL NOT raise.
4. THE semantic arm SHALL NOT fall back to a local model.
5. THE semantic arm SHALL score each hit as `round(100 * cosine)` and SHALL mark it with semantic provenance and its cosine.
6. THE semantic arm SHALL NOT take an exclusion list — deduplication happens during fusion, after the owning arm is decided.

#### Success Criteria

- SC-01: with a faked `urlopen`, the request payload is `{"model": "voyage-3-large", "input": ["<query>"], "input_type": "query"}` and the `Authorization` header is `Bearer <key>`.
- SC-02: an unset `VOYAGE_API_KEY` raises `RuntimeError`.
- SC-03: an absent cache and an unreachable backend each yield `[]`, not an exception.
- SC-04: the renamed pre-existing semantic suite (`cli/test_okf_cli.py:1487-1690`) passes with `voyage-3-large` rows, the `_embed_query_voyage` patch point and the new `semantic arm skipped` wording — with no assertion weakened.
- SC-05: `python3 -m unittest discover -s cli -p 'test_*.py'` stays at exactly 19 failures / 2 errors.

_Requirements: PLAN.md Task 7 · DECISIONS D13, D16 · REFERENCES R05, R42_

## Steps

- [ ] Write the failing `VoyageQueryEmbedding` and `SemanticRankingDegradation` tests
- [ ] Run them, confirm they fail for the stated reason
- [ ] Replace the model constants; replace `_embed_query_bge_m3` with `_embed_query_voyage`
- [ ] Rename `semantic_backstop` to `semantic_ranking`, drop `exclude_paths`
- [ ] Rewrite `_semantic_hit_dicts` onto `_hydrate_hit` and the 0..100 scale
- [ ] Rename the pre-existing semantic suite (model, patch point, note wording) and add `okf._QUERY_VEC_CACHE.clear()` to its `setUp` — six of its methods share one query string with different mocks, and only alphabetical ordering hides the leak today
- [ ] Tests pass; suite still 19F/2E
- [ ] Commit `feat(cli): semantic arm on voyage-3-large`

## Recommended Skills

- `superpowers:test-driven-development`


## Additional success criterion (global constraint, network)

- SC-NET: no unit test added or touched by this task performs a real network call. Every embedding call under test is exercised through a faked `urlopen` or a patched module attribute. The producer's test module is network-free by construction and must stay that way.


## Summary

Query-time semantic arm now speaks the productive model, matching D13/D16:
`voyage-3-large`, `input_type=query`, bearer auth from `VOYAGE_API_KEY`,
scored `round(100*cosine)`, two-stage degradation (voyage -> lexical-only,
never a bge-m3 fallback), no `exclude_paths` (dedup deferred to fusion,
T08). `semantic_backstop()` -> `semantic_ranking()`, `_embed_query_bge_m3()`
-> `_embed_query_voyage()`. Pre-existing semantic suite renamed in place
(patch point, model rows, note wording) with the T11 cache-clear line added
per plan Step 5.

## Test-Output

RED (Step 2, confirms failing for the stated reason):

```
AttributeError: module 'okf_cli' has no attribute '_embed_query_voyage'. Did you mean: '_embed_query_bge_m3'?
AttributeError: module 'okf_cli' has no attribute 'semantic_ranking'. Did you mean: 'semantic_backstop'?
Ran 4 tests in 0.003s
FAILED (errors=4)
```

GREEN (new + renamed suite, 15 tests):

```
Ran 15 tests in 0.023s
OK
```

Mutation probe (input_type, RED->fix->GREEN, byte-identical revert verified
via git diff before/after):

```
AssertionError: 'document' != 'query'
- document
+ query
```
reverted, `cli.test_okf_cli.VoyageQueryEmbedding` green again (2/2).

Full suite at commit point (before AND after the test_eval_fixtures fix,
same result): `python3 -m unittest discover -s cli -p 'test_*.py'`

```
Ran 233 tests in 40.337s
FAILED (failures=19, errors=2)
```

FAIL/ERROR set diffed byte-identical against the pre-task baseline
(`diff` empty) — no new failure, no fixed-by-accident failure. 229 tests
baseline -> 233 (4 new: 2x VoyageQueryEmbedding, 2x
SemanticRankingDegradation), all green.

## Smoke

Direct call against the live catalogue (`~/Obsidian/Knowledge-Catalogue`),
`okf.semantic_ranking(root, "mockup tailscale", 5)`, real Voyage API call,
no key printed:

```
0.5569 home-lab-wiki/services/tailscale
0.5566 home-lab-wiki/context/services/tailscale
0.5484 dev-wiki/testsystem-vite-tailscale/serve-excalidraw-drafts
0.5421 home-lab-wiki/manuals/admin/tailscale-einrichten
0.5407 bew_BeWiki-Python-Download-okf/general/portal-remote-review-via-tailscale-serve
```

Rank 3 is exactly the target concept named in T08's SC-06 — the arm is
live and functioning; no 401/403 observed. `okf-cli find "mockup
tailscale"` end-to-end still shows 0 `provenance: semantic` lines, as
expected: cmd_find's gate/fusion is untouched OLD pin+interleave code
(Task 8's job), so a strong keyword top-1 still suppresses the arm at the
CLI layer even though the arm itself is proven live above.

## Deviations/ERRATA

1. **cmd_find compatibility shim (bounded; CORRECTED in Fix round 1 after
   review round 1, B01).** T07's own signature change (`semantic_ranking()`
   / `_semantic_hit_dicts()` drop `exclude_paths`/`max_score`) breaks
   `cmd_find`'s call site, which PLAN.md assigns to Task 8
   ("replace the gate at :853-861 and the fusion at :863-879"). The FIRST
   version of this shim called `_semantic_hit_dicts(root, query, limit)`
   and filtered the keyword-owned paths out of the result AFTER the fetch.
   **That claimed "preserving 100% prior observable behaviour... verified"
   — that claim was FALSE.** `_semantic_hit_dicts()` ranks by cosine and
   slices to `limit` before any exclusion can happen, so filtering after a
   plain `limit`-sized fetch silently starves the pool whenever an excluded
   (keyword-owned) path ranks inside that window: an eligible,
   lower-ranked candidate never even enters the fetch and a weaker
   candidate (or a weaker second keyword hit) wins its slot instead. The
   reviewer reproduced this live and it is now covered by
   `cli/test_okf_cli.py::SemanticBackstop::test_shim_backfills_when_excluded_paths_rank_inside_the_window`
   (quoted RED/GREEN in `## Fix round 1` below). **Corrected implementation
   (Fix round 1):** request `limit + len(exclude)` candidates from
   `_semantic_hit_dicts()`, filter excluded paths from that widened window,
   then slice to `limit` — since each excluded path can consume at most one
   slot in the widened window, at least `limit` eligible candidates survive
   whenever that many exist, which IS behaviourally equivalent to the
   pre-T07 `semantic_backstop(exclude_paths=...)` contract (exclude, then
   rank, then slice). The plan author's original approval of "the right
   bridge" rested on the false premise above; the bridge itself (a
   temporary, arity-compatible stand-in for Task 8's `fuse_conditional`)
   is still the right shape — only its internal correctness needed fixing.
   Its removal remains a hard duty with its own criterion **SC-SHIM** on
   `OKFT-kc9x` (T08), commit `b7b236d` — post-hoc exclude-filtering must
   not survive into conditional handover, because dedup there belongs
   inside `fuse_conditional`, after the owning arm is decided.
2. **`_QUERY_VEC_CACHE = {}` forward-declared early.** PLAN.md Task 7 Step
   5 literally instructs adding `okf._QUERY_VEC_CACHE.clear()` to the
   pre-existing suite's `setUp` now, but the dict itself is only defined in
   Task 11. Added the empty dict now (placed exactly where Task 11 places
   it, "above `_embed_query_voyage`"), not wired into `semantic_ranking()`
   — that wiring stays Task 11's job. Idempotent: Task 11 re-declaring it
   is harmless.
3. **`cli/test_eval_fixtures.py` fixed inside T07, file not on T07's
   stated file list.** `SeedThenTeardownIsClean.test_token_absent_before_seed`
   runs `okf.cmd_find` against the LIVE catalogue and, once
   `SEMANTIC_MODEL=voyage-3-large` matched what `concept_emb` actually
   holds (post-T03), started (a) making a real Voyage network call under
   test and (b) failing (semantic search legitimately returns 50
   nearest-neighbours for a nonsense token, which does not refute the
   test's lexical claim). Escalated live via `herdr pane run w2B:pG`;
   plan author ruled fix-now (not scope creep — falls under this bean's
   own SC-NET / the plan's global "no network under test" constraint) and
   specified the exact fix: patch `okf._embed_query_voyage` to raise
   inside that one test, forcing the documented degradation path instead
   of weakening the assertion. Applied verbatim, try/finally-restored.
   Full suite reconfirmed at exactly 19F/2E, FAIL/ERROR set byte-identical
   to the pre-task baseline. The deeper structural issue (a unit test
   driving `cmd_find` against `fixtures.DEFAULT_ROOT`, the live repo) is
   explicitly NOT this task's — the plan author is filing a separate
   follow-up bean for it.

None of these touch DESIGN.md/DECISIONS.md/REFERENCES.md or change any
EARS acceptance criterion; all three are call-site/test-harness glue
required to keep the tree buildable and the baseline exact at this
sequencing point, reviewed live by the plan author before this bean
closed.

## Notes for T08

- **SC-SHIM is binding**: delete the `cmd_find` compatibility shim
  (`_semantic_hit_dicts(root, query, limit)` + local exclude-filter) when
  wiring `fuse_conditional` — do not just leave it alongside the new
  fusion. Dedup must happen inside `fuse_conditional`, after ownership is
  decided, not before.
- `semantic_ranking()` / `_semantic_hit_dicts()` are already on the
  final signature T08 needs — no further renames required, only the
  `cmd_find` gate/fusion block changes.
- `_QUERY_VEC_CACHE = {}` already exists (empty, unused) directly above
  `_embed_query_voyage()` for Task 11 — do not redeclare in a different
  location; Task 11 can just add `_query_vector()` next to it.
- Live smoke already proves the arm surfaces
  `dev-wiki/testsystem-vite-tailscale/serve-excalidraw-drafts` (T08's
  SC-06 target) at cosine 0.5484, rank 3 of 5 — the hard counter-probe in
  T08 has real vectors to work with; if it still doesn't surface with
  `provenance: semantic` after fusion is wired, that is a fusion-logic
  finding per T08's HARD STOP, not a data problem.
- `VOYAGE_API_KEY` is confirmed live and functional (no 401/403
  encountered); rotation is scheduled after T09 per the plan author.



## REVIEW ROUND 1 — CHANGES_REQUIRED 2026-07-26 (ce-specs-reviewer)

Status flipped back to `in-progress` by the supervisor per PF-2. Fix in THIS bean.

**B01 (high, BLOCKING) — the `cmd_find` shim is NOT dedup-inert.**
`cli/okf-cli.py:1122-1131` ranks and slices the semantic candidates to `limit` BEFORE excluding
paths already returned lexically. The pre-T07 `semantic_backstop(exclude_paths=...)` excluded
BEFORE ranking/slicing. Reproduced live by the reviewer: `limit=2`, excluded path `b/x1` at
cosine rank 1, candidates `b/x2` (rank 2) and `b/x3` (rank 3) — old code returns `[x2, x3]`,
the shim returns only `[x2]`. `x3` is silently dropped because it never enters the
pre-exclusion top-`limit` window.

This fires whenever a lexical hit's path also ranks inside the semantic top-`limit` — the
common case, since a keyword-matching document is usually also semantically close. It is a
live behaviour change on `main`, and no test in the added or renamed suites covers the
overlap-with-backfill scenario.

It also contradicts this bean's own `## Deviations/ERRATA` #1, which claims "preserving 100%
prior observable behaviour... verified". That claim is false as written. **The plan author
approved the shim on the strength of that description** — the approval rested on a wrong
premise and has been corrected accordingly (see below).

**I01 (low).** Stale module comment at `cli/okf-cli.py:925-930` still describes the arm as a
"semantic backstop" using "a LOCAL Ollama bge-m3 call" — wrong after this commit's rename to
`semantic_ranking`/`voyage-3-large`, and inconsistent with the accurate docstrings added
directly below it in the same commit.

**I02 (info, no action).** The still-untouched pin+interleave block
(`cli/okf-cli.py:1143-1147`) numerically compares semantic `round(100*cosine)` against lexical
scores that are 0..100 on the FTS path but only `6*len(terms)` on the substring fallback — a
real scale mismatch. Pre-existing debt, out of T07 scope, replaced by T08's `fuse_conditional`.
The reviewer checked the planned T08 design (PLAN.md:1373-1434) and confirmed it never compares
cross-arm scores for ownership or ordering, so the mismatch does not propagate — it is live
only during this transient window.

**Confirmed clean (no action) — strong evidence:**
- SC-NET proven by execution, three ways: invalid key (`233 tests, 19F/2E`), unset key
  (identical), and a socket-level guard patching `socket.socket.connect` to raise on any
  non-localhost address across the full run under all three env conditions — **0 real connect()
  calls in every run**. No test phones home regardless of key validity.
- `test_token_absent_before_seed`: a spy confirmed the local monkeypatch is what runs (0 calls
  reached the real function), the note fires exactly once, and the assertion text is
  byte-identical to the pre-task version — the lexical claim was not weakened.
- PF-4 degradation: missing `concept_emb`, missing key, unreachable backend each yield `[]`
  plus exactly one note; combined missing-key + absent-FTS yields exactly 2 notes, one per
  independent event, which is coherent. `bge-m3` appears only in the unrelated tag-auto-embed
  path, never in the query path (D16 holds).
- Baseline: 229 -> 233 tests, both 19F/2E, sorted FAIL/ERROR name lists diffed byte-identical
  against pre-task commit `ea23f50` — nothing new, nothing silenced.
- Key hygiene: no key material in the diff, the bean, or the commit message.
- Live artefacts intact: `.fts/fts.sqlite` 13,164,544 bytes; `concept_emb` 2443 rows, all
  voyage-3-large; both repos clean after review.


## Fix round 1 (2026-07-26, addresses REVIEW ROUND 1)

**B01 fixed.** Root cause: the shim requested exactly `limit` semantic
candidates and filtered `exclude` afterward, so an excluded path ranking
inside that window silently starved the pool (reviewer repro: `limit=2`,
excluded `b/x1` at rank 1, `[x2,x3]` expected, `[x2]` returned).

Regression test added:
`cli/test_okf_cli.py::SemanticBackstop::test_shim_backfills_when_excluded_paths_rank_inside_the_window`
— two keyword hits (`a`, `b`) both rank inside the semantic top-`limit`
window for the same query, alongside two genuinely eligible semantic-only
candidates (`x2`, `x3`); `args.limit=3` gives 1 pinned + 2 rest slots.

RED, quoted, against the pre-fix shim:

```
AssertionError: 'b/x3' not found in ['b/a', 'b/x2', 'b/b'] : x3 must
surface: it is the 3rd-best ELIGIBLE semantic candidate, and excluding
a/b before windowing (not after) must not let a weaker keyword hit
occupy its slot instead. Got: ['b/a', 'b/x2', 'b/b']
```

Fix applied: `cmd_find` now requests `limit + len(exclude)` candidates from
`_semantic_hit_dicts()`, filters `exclude` from that widened window, then
slices to `limit` — each excluded path can consume at most one slot in the
widened window, so at least `limit` eligible candidates survive whenever
that many exist. Behaviourally equivalent to the pre-T07
`semantic_backstop(exclude_paths=...)` contract (exclude, then rank, then
slice).

GREEN, quoted, after the fix (full `SemanticBackstop` suite, 12 tests):

```
Ran 12 tests in 0.027s
OK
```

Mutation probe (reverted the over-fetch back to plain `args.limit`, i.e.
reintroduced the exact bug): the new regression test failed with the
IDENTICAL RED output quoted above (`['b/a', 'b/x2', 'b/b']`), confirming
the test detects precisely this defect and nothing else. Reverted
byte-identically (verified via the same replace/revert string round-trip);
`SemanticBackstop` green again (12/12).

**I01 fixed.** `cli/okf-cli.py:925-930` module comment corrected: no
longer calls the arm a "semantic backstop" using "a LOCAL Ollama bge-m3
call" — now describes the renamed `semantic_ranking()` arm, `voyage-3-large`
via the Voyage HTTP API (D13), and that bge-m3 is not a runtime fallback
(D16), consistent with the docstrings added directly below it.

Full suite at this commit point:

```
Ran 234 tests in 40.666s
FAILED (failures=19, errors=2)
```

FAIL/ERROR set re-diffed byte-identical against the pre-task baseline
(229-test commit `ea23f50`) — still nothing new, nothing silenced. 233 -> 234
tests (the one new regression test), all green.

Commit: `be08f8c` (fix(cli): shim excludes before slicing).
