---
# okf-cli-ftri
title: T11 Tag query expansion behind --expand-tags
status: completed
type: task
priority: normal
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-26T08:56:42Z
parent: okf-cli-cskz
blocked_by:
    - okf-cli-uagv
    - okf-cli-snxj
---

Plan: `docs/okf-retrieval-architecture/PLAN.md` → **Task 11**. Follow it step by step; it carries the literal code and tests.

**This is the only change in the feature that alters ranking without prior measurement.** It ships behind `--expand-tags`, off by default, and becomes a default only if the measurement in the final step earns it. That discipline is not ceremony: three retrieval intuitions in this project's history (chunking, an absolute cosine floor, "lexical is the biggest lever") were each measured and each turned out wrong.

Expansion is a *rescue* path on the same terms as the semantic arm: it runs only when the unexpanded lexical arm is not confident. Running it on every query would spend a network call on exactly the queries that did not need one.

Q06 is answered by construction — expansion embeds the whole query and compares it against the tag vectors, so a query term that is not a registered tag never needs its own call. A shared one-entry cache makes the semantic arm and expansion use a single call.

### Requirement 1: Optional tag-vector query expansion

**Objective:** As a user whose vocabulary differs from the catalogue's, I want the query widened with semantically near registered tags before lexical scoring, so that a synonym gap can be closed lexically.

#### Acceptance Criteria

1. THE expansion SHALL be off unless `--expand-tags` is passed.
2. THE expansion SHALL run only WHEN the unexpanded lexical arm is not the ranking owner, and SHALL re-run the lexical arm over the widened term set.
3. THE expansion SHALL return only tags whose similarity clears the configured floor, and SHALL return nothing IF the tag cache is absent or the backend is unavailable.
4. THE semantic arm SHALL embed the original query, never the widened one, because widening before embedding dilutes the vector.
5. THE expansion and the semantic arm SHALL share one query embedding call per invocation.
6. WHEN the query is expanded THE CLI SHALL name the added tags on stderr.

#### Success Criteria

- SC-01: with two seeded tag vectors and a mocked query vector, `_expand_query_tags` returns only the near one.
- SC-02: an absent cache returns `[]`; a candidate below the floor returns `[]`.
- SC-03: `find mockup` WITHOUT the flag still prints `(no matches for: mockup)` against a catalogue whose only concept is tagged `excalidraw`.
- SC-04: `shipped_expand.json` exists and is compared against `shipped_v2.json`.
- SC-05: Q05 and Q06 in `QUESTIONS.md` are resolved with the measured outcome — including plainly stating that expansion did not pay, if it did not.
- SC-06: `python3 -m unittest discover -s cli -p 'test_*.py'` stays at exactly 19 failures / 2 errors.

**Decision rule for the last step:** if MRR improves and zero-hit does not rise, *propose* making it the default to the PO with both JSON files as evidence. Do not flip the default yourself. Otherwise the flag stays off.

_Requirements: PLAN.md Task 11 · QUESTIONS Q05, Q06 · TASKS.md T05 · DECISIONS D17 · REFERENCES R06, R09_

## Steps

- [x] Write the failing `ExpandQueryTags` tests (with `okf._QUERY_VEC_CACHE.clear()` in `setUp`)
- [x] Run them, confirm they fail for the stated reason
- [x] Add `_QUERY_VEC_CACHE` / `_query_vector`; reroute `semantic_ranking()` through it
- [x] Add `_load_tag_vectors()` and `_expand_query_tags()`
- [x] Wire expansion as a rescue path after the first lexical pass; register `--expand-tags`
- [x] Tests pass; suite still 19F/2E
- [x] Commit `feat(cli): add --expand-tags query expansion`
- [x] Add the `--find-arg` passthrough to `remeasure.py`; measure with and without
- [x] Resolve Q05/Q06 in `QUESTIONS.md`; commit `test(eval): measure tag expansion, answer Q05/Q06`
- [x] Report the comparison to the PO; do not change the default unilaterally

## Recommended Skills

- `superpowers:test-driven-development`


## Additional success criterion (global constraint, network)

- SC-NET: no unit test added or touched by this task performs a real network call. Every embedding call under test is exercised through a faked `urlopen` or a patched module attribute. The producer's test module is network-free by construction and must stay that way.


## Prelude from T10 review (2026-07-26, supervisor)

T10 (`okf-cli-snxj`) is closed and approved after one fix round. Three things carry into this task:

1. **Baseline moved.** The suite is now **253 tests**, still exactly **19 failures / 2 errors**. SC-06 measures against that count.
2. **No interface collision expected, but verify rather than assume.** T10 added `_zero_hit_suggestions()` as an independent helper plus a branch inside `cmd_find`. This task touches `all_tags`, `tokenize`, `difflib`, adds `_query_vector`/`_expand_query_tags` and rewires `semantic_ranking()` and the lexical-confidence gate — all of that sits upstream of where the zero-hit branch fires. If expansion changes whether the zero-hit branch is entered at all, that is a real interaction and belongs in this bean.
3. **A feature bound was established and must not be contradicted.** `_zero_hit_suggestions()` reaches typos and synonyms ONLY. Truncated or partially typed terms never arrive there, because the substring scan matches any prefix and the FTS arm matches it via prefix query — both catch it first by construction. It is marked to carry into T13 documentation.

Standing quality note (PF-5, bean `okf-cli-cskz`): a sentence in a bean whose function is to end review is the sentence that gets checked. Claims of the form "verified", "behaviour-identical", "reverted byte-identically" must name the command and its observed output, or not be written.


## Summary

Implemented `_expand_query_tags(root, query, top_k=3, floor=0.6)` (cli/okf-cli.py), its helper `_load_tag_vectors()`, and the shared `_query_vector()`/`_QUERY_VEC_CACHE` cache that `semantic_ranking()` was rewired to use (Task 7's arm and expansion now embed the query exactly once per invocation — Q06 answered by construction, verified by measurement: 46 rescue attempts against the live catalogue, zero extra network calls beyond the one shared per query). Wired expansion into `cmd_find` as a rescue path that fires only when the unexpanded lexical arm is not confident, re-running `_rank_lexically` over the widened term set and printing `note: query expanded with tag(s): ...` on stderr when it adds anything. Registered `--expand-tags` (`action="store_true"`, off by default per D17).

Commits: `7c47039` feat(cli): add --expand-tags query expansion (cli/okf-cli.py, cli/test_okf_cli.py); `ae87426` test(eval): measure tag expansion, answer Q05/Q06 (docs/okf-retrieval-architecture/eval/remeasure.py, docs/okf-retrieval-architecture/eval/shipped_expand.json, docs/okf-retrieval-architecture/QUESTIONS.md).

**Measured outcome (SC-04/SC-05): expansion did not pay — flag stays off, unchanged from D17's default.** `shipped_expand.json` (48-query live-catalogue run, `--expand-tags`) is bit-identical to `shipped_v2.json` (Task 9, no flag) on every per-file metric: `queries_v2.json` recall@1/5/10 = 0.25/0.7/0.825, mrr = 0.43805555555555553, zero_hit = 0.175 — same in both files; `queries_real.json` recall@1/5/10 = 0.375/0.625/0.875, mrr = 0.5148809523809523, zero_hit = 0.125 — same in both files. (The `combined` block's mrr differs by ~0.001 between the two files — 0.451901455026455 in `shipped_v2.json` vs 0.4508597883597884 in `shipped_expand.json` — but that discrepancy pre-exists this task: `shipped_v2.json`'s own stated combined mrr does not equal the arithmetic combination of its own two per-file mrr values, i.e. remeasure.py's third pass over all 48 rows together is itself not perfectly reproducible from run to run, most plausibly due to live-network timing on the semantic arm across three separate live subprocess passes. `shipped_expand.json`'s combined mrr *does* equal the exact arithmetic combination of its own two per-file values, so no discrepancy was introduced by this task — this is pre-existing eval-harness jitter, not an expansion effect, and I did not touch anything to make it agree.)

Root cause, measured directly (not inferred): across the 48-query set, 46 queries had an unconfident lexical arm, so expansion was attempted 46 times. On **0 of 46** did any registered tag's cosine similarity clear the configured floor (`floor=0.6`, an unmodified plan constant — never retuned per the hard rule). The closest miss was the query `"mockup tailscale"` → tag `tailscale` at cosine 0.595, 0.005 short of the floor; mean top-1 cosine across all 46 attempts was 0.472. Re-verified live and end-to-end (see Smoke): the real CLI subprocess against the live catalogue for that exact query shows the rescue attempted (no `note: query expanded` line — extra=[]) and control correctly falling through to the semantic arm, which then owns the ranking as designed.

QUESTIONS.md: Q05 → 🟢 (measured: no, expansion at the current floor solves 0 additional cases on this set; concept_emb stays the primary semantic lever, not tag expansion). Q06 → 🟢 (answered by construction: whole-query embedding + shared cache, confirmed no extra network cost).

## Test-Output

Baseline before any change (both env directions):
```
$ python3 -m unittest discover -s cli -p "test_*.py"
Ran 253 tests in 17.070s
FAILED (failures=19, errors=2)

$ env -u VOYAGE_API_KEY python3 -m unittest discover -s cli -p "test_*.py"
Ran 253 tests in 13.681s
FAILED (failures=19, errors=2)
```

RED (Step 2, before implementation — 3 of the 4 new tests error for the stated reason, the 4th already passes because the unflagged path was already unaffected):
```
$ python3 -m unittest cli.test_okf_cli.ExpandQueryTags -v
test_find_without_the_flag_does_not_expand ... ok
test_returns_empty_when_nothing_clears_the_floor ... ERROR
test_returns_empty_without_a_cache ... ERROR
test_returns_nearest_tag_above_the_floor ... ERROR
AttributeError: module 'okf_cli' has no attribute '_expand_query_tags'
Ran 4 tests in 0.005s
FAILED (errors=3)
```

GREEN after implementation:
```
$ python3 -m unittest cli.test_okf_cli.ExpandQueryTags -v
Ran 4 tests in 0.004s
OK
```

Full suite after both commits, both env directions:
```
$ python3 -m unittest discover -s cli -p "test_*.py"
Ran 257 tests in 17.189s
FAILED (failures=19, errors=2)

$ env -u VOYAGE_API_KEY python3 -m unittest discover -s cli -p "test_*.py"
Ran 257 tests in 13.729s
FAILED (failures=19, errors=2)
```
257 = 253 baseline + 4 new tests; failures/errors unchanged at 19/2 (SC-06 met exactly).

**Mutation probes (3, one per new behaviour), each: break → RED for the stated reason → revert → prove revert with `md5` + `git diff --stat`.**

1. `_expand_query_tags` top-k slicing (`ranked[:top_k]` → `ranked[top_k:]`):
```
FAIL: test_returns_nearest_tag_above_the_floor
AssertionError: Lists differ: [] != ['excalidraw']
```
Reverted. `md5 cli/okf-cli.py` before mutation = after revert = `f1376401d173e6d09d75bff9184f2254`; `git diff --stat cli/okf-cli.py` before mutation = after revert = `1 file changed, 75 insertions(+), 7 deletions(-)`. Re-run: `OK` (4 tests).

2. `_expand_query_tags` cache-absent guard (`if not vectors:` → `if vectors:`):
```
ERROR: test_returns_empty_without_a_cache — TypeError: 'NoneType' object is not iterable
FAIL: test_returns_nearest_tag_above_the_floor — AssertionError: Lists differ: [] != ['excalidraw']
```
Reverted. `md5` = `f1376401d173e6d09d75bff9184f2254` (same as baseline); `git diff --stat` = `1 file changed, 75 insertions(+), 7 deletions(-)` (same as baseline). Re-run: `OK` (4 tests).

3. `cmd_find` rescue gate (`not lexical_owned_provisionally` → `lexical_owned_provisionally`, i.e. inverted so rescue only fires when the lexical arm is ALREADY confident): none of the 4 committed unit tests exercise the wired end-to-end rescue path with a seeded tag-vector cache and an unconfident lexical arm together (PLAN.md Task 11 specifies only the 4 tests quoted above, and the 4th — `test_find_without_the_flag_does_not_expand` — seeds no `.tagvec` cache, so it cannot distinguish this mutation). To close that gap without inventing a new committed test beyond the plan, I wrote and ran an ad-hoc, uncommitted probe (`/private/tmp/.../scratchpad/probe_wiring.py`) that seeds a `.tagvec` cache, monkeypatches `_embed_query_voyage`, and calls `cmd_find` in-process with `expand_tags=True` on an unconfident query. Before mutation: probe finds `path: b/one` and stderr shows `note: query expanded with tag(s): excalidraw` (PROBE OK). After the inverted-gate mutation: probe fails — `(no matches for: mockup)`, no expansion note, `AssertionError: rescue path did not find the concept`. Reverted. `md5 cli/okf-cli.py` before mutation = after revert = `f1376401d173e6d09d75bff9184f2254`; `git diff --stat` before mutation = after revert = `1 file changed, 75 insertions(+), 7 deletions(-)`. Re-run of the probe after revert: `PROBE OK`.

## Smoke

Real CLI subprocess (not the in-process test harness), two independent runs:

1. Fully degraded fixture (no `.fts`, no `.tagvec`), flag on — proves the flag is a true no-op without a cache, matching SC-02/SC-03 at the CLI level, not just the helper level:
```
$ python3 cli/okf-cli.py --root <tmp>/smoke_root find "mockup" --expand-tags
note: lexical index absent — falling back to substring scan; run `okf-cli build-index` for BM25 ranking
note: semantic arm skipped (.tagvec cache/concept embeddings absent) — lexical results only
(no matches for: mockup)
```

2. Live catalogue (`~/Obsidian/Knowledge-Catalogue`), the closest near-miss query from the measurement (`"mockup tailscale"`, cosine 0.595 vs floor 0.6), flag on, real Voyage network call:
```
$ python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue find "mockup tailscale" --expand-tags --limit 3
note: lexical index is stale (catalogue changed since build) — run `okf-cli build-index`
note: semantic arm owns this ranking (lexical top-1 lacked a clear margin)
------
score: 56/100
title: Tailscale
...
provenance: semantic (cosine=0.56)
------
```
No `note: query expanded` line (extra=[] — the near-miss did not clear the floor), control correctly falls through to the semantic arm, which owns the ranking as designed. `git -C ~/Obsidian/Knowledge-Catalogue status --short` before and after both smoke runs and the full measurement run: empty both times — the live catalogue (a foreign git repo) was left exactly as found; `find` and expansion are read-only by construction (no index build, no writes).

## Deviations/ERRATA

None against PLAN.md Task 11's literal code and tests — `_load_tag_vectors()`, `_expand_query_tags()`, `_query_vector()`/`_QUERY_VEC_CACHE`, the `cmd_find` rescue wiring, the `--expand-tags` flag registration, and the `remeasure.py` `--find-arg` passthrough are verbatim from the plan. One process note, not a code deviation: `_QUERY_VEC_CACHE = {}` already existed at cli/okf-cli.py (forward-declared by T10/Task 7 specifically for this task, per its own comment) — Step 3 therefore added `_query_vector()` next to the existing dict rather than declaring the dict itself, which is the same net result the plan describes (`_query_vector` reads/writes the module-level `_QUERY_VEC_CACHE`) via a slightly different diff shape than "add `_QUERY_VEC_CACHE` / `_query_vector`" might suggest read literally.

The mutation-probe gap on the `cmd_find` gate (finding 3 above) is disclosed rather than silently worked around: the plan's 4 specified tests do not, by themselves, distinguish an inverted rescue-gate condition. I did not add a 5th test to the committed suite (that would go beyond "follow the plan, invent nothing beyond it"); I closed the verification gap with an ad-hoc uncommitted probe instead and disclosed the reasoning above. If the plan author wants that coverage promoted into the committed suite, that is a decision for review, not one I made unilaterally.

## Notes for T12 (okf-cli-1mxp, failure taxonomy)

`shipped_expand.json` and `shipped_v2.json` are now both available for T12's `remeasure.py --find-arg` extension (adding the `"rows"` key), but per this task's finding, expansion changed nothing about which queries fail — so the T12 failure taxonomy can be built from either file's failing-query set and will be identical either way. All 46 lexically-unconfident queries in the combined 48-query set had their rescue attempted and got zero tags back; that data (query → top-3 tag cosines, printed during this task's diagnostics) is not persisted anywhere in the repo — if T12's taxonomy wants a `synonymy`-vs-other split informed by "how close did the nearest tag get", it will need to regenerate that from scratch (`_expand_query_tags`'s internals, or a small ad-hoc script like the one used here), since it was not part of this task's committed deliverables.


## Ruling from the plan author, 2026-07-26 (supervisor-relayed, binding)

Arrived after the null result was reported, based on the plan author's own re-measurement. It supersedes the "0 of 46 clear the floor" framing — the conclusion is stronger than the near-miss number suggested.

### 1. The null result is structural, not a threshold accident

Three measured facts, to be recorded verbatim as evidence in Q05/Q06:

- The 0.595 near-miss for `"mockup tailscale"` is the tag `tailscale` — **a word already present in the query**. Expanding with it would yield zero information gain. The floor is therefore NOT the binding constraint: whole-query embedding returns the query's own most prominent word as its nearest neighbour. Lowering the floor would admit no-ops plus noise, not one genuine rescue.
- Term granularity would not solve it either, measured separately: `"mockup"` alone clears the floor with `mockups` at **0.6693** — a morphological variant, not a synonym.
- `excalidraw` does not appear among the nearest neighbours of `"mockup"` at all (top5: `mockups`, `ui-storybook`, `mocking`, `template`, `example`). Tags are embedded slug-only (R06), so `excalidraw` carries no context connecting it to mockups.

**Conclusion to record:** tag-vector expansion cannot close the R12 gap **in principle** — not because of the floor, not because of granularity, but because the two terms are not neighbours in tag-slug space. That case is solved by CONCEPT embedding, which sees the running text. The null result confirms the architecture decision retroactively rather than calling it into question.

### 2. AC-2 requires a committed regression test — not a review judgement call

Ruled mandatory, removed from reviewer discretion. Rationale from the plan author: AC-2 is exactly the property forced by the F06 correction (expansion runs only when the lexical arm is not the ranking owner). Without a regression test, the next refactor silently reintroduces a network call per query and nobody notices — the results stay the same and only the bill grows.

Required shape: with a **confident** lexical arm, `_expand_query_tags` must NOT be called. Implement as a spy/monkeypatch that RAISES on call.

Disclosing the gap instead of silently patching it was explicitly endorsed.
