---
# okf-cli-ftri
title: T11 Tag query expansion behind --expand-tags
status: todo
type: task
priority: normal
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-25T23:32:42Z
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

- [ ] Write the failing `ExpandQueryTags` tests (with `okf._QUERY_VEC_CACHE.clear()` in `setUp`)
- [ ] Run them, confirm they fail for the stated reason
- [ ] Add `_QUERY_VEC_CACHE` / `_query_vector`; reroute `semantic_ranking()` through it
- [ ] Add `_load_tag_vectors()` and `_expand_query_tags()`
- [ ] Wire expansion as a rescue path after the first lexical pass; register `--expand-tags`
- [ ] Tests pass; suite still 19F/2E
- [ ] Commit `feat(cli): add --expand-tags query expansion`
- [ ] Add the `--find-arg` passthrough to `remeasure.py`; measure with and without
- [ ] Resolve Q05/Q06 in `QUESTIONS.md`; commit `test(eval): measure tag expansion, answer Q05/Q06`
- [ ] Report the comparison to the PO; do not change the default unilaterally

## Recommended Skills

- `superpowers:test-driven-development`


## Additional success criterion (global constraint, network)

- SC-NET: no unit test added or touched by this task performs a real network call. Every embedding call under test is exercised through a faked `urlopen` or a patched module attribute. The producer's test module is network-free by construction and must stay that way.
