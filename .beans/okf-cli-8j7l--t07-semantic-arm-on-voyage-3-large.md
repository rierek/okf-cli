---
# okf-cli-8j7l
title: T07 Semantic arm on voyage-3-large
status: in-progress
type: task
priority: high
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-26T06:33:56Z
parent: okf-cli-cskz
blocked_by:
    - okf-cli-c922
    - okf-cli-17y7
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
