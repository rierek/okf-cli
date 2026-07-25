---
# okf-cli-3geg
title: 'P7 — .tagvec provenance: pull producer into repo'
status: in-progress
type: task
priority: normal
tags:
    - to-review
created_at: 2026-07-25T18:13:10Z
updated_at: 2026-07-25T19:27:09Z
parent: okf-cli-5hg4
blocked_by:
    - okf-cli-5qmn
---

## Objective (User Story)
As a maintainer, I want the `.tagvec` embedding producer in-repo and its embedded scope documented so that the semantic backstop design (P8) rests on a known, reproducible asset.

## EARS Acceptance
- THE producer script SHALL live in-repo and regenerate a `tag_vectors.sqlite` with the `emb(key,tag,model,dim,vec)` schema (RET10) from a catalogue root.
- THE README SHALL document embedded scope (tags only, `emb.tag`) and state that `find` reads this cache at runtime but never produces it.
- THE task SHALL record a written finding: tag-embeddings only vs. body-embeddings needed — this decides P8's fallback surface.

## Success Criteria
- SC-001: `cli/embeddings/build_tagvec.py` regenerates the emb schema.
- SC-002: `cli/embeddings/README.md` states tags-only scope + runtime-read/offline-produce split.
- SC-003: tags-vs-body decision recorded for P8.

## Grounding
Live cache `~/Obsidian/Knowledge-Catalogue/.tagvec/tag_vectors.sqlite` (627 bge-m3 + 650 voyage rows, RET10). Producer SOP: `Knowledge-Catalogue/okf-meta-wiki/extensions/embedding-based-tag-consolidation.md` (RET11).
GATES P8. Full steps: PLAN.md Task 7.
Commit: `feat(embeddings): bring tagvec producer + provenance into repo`


## Summary

Pulled the ad-hoc offline SOP producer for `.tagvec/tag_vectors.sqlite` into
the repo as `cli/embeddings/build_tagvec.py`: parametrized `--root`/`--output`,
reuses `okf-cli.py`'s `catalogue_root`/`all_tags` via the same importlib
pattern as `test_okf_cli.py`, computes the cache-key scheme
(`sha1(model + "\x00slug\x00" + slug_text)`) verified byte-for-byte against a
live cache row, and gates ALL network calls (Ollama bge-m3, Voyage
voyage-3-large) behind an explicit `--produce` flag — import and argument
parsing never touch the network. `cli/embeddings/README.md` documents the
tags-only embedded scope, the offline/runtime-read split, usage, and the
Task-8 gating finding (below).

## Test-Output

Baseline (pre-existing, per Task-5 freeze):
`python3 -m unittest cli.test_okf_cli cli.test_okf_mcp cli.test_eval_fixtures cli.test_eval_runner`
→ Ran 126 tests, FAILED (failures=19, errors=2).

After (baseline suite + new `cli.test_embeddings_tagvec`):
`python3 -m unittest cli.test_okf_cli cli.test_okf_mcp cli.test_eval_fixtures cli.test_eval_runner cli.test_embeddings_tagvec`
→ Ran 136 tests, FAILED (failures=19, errors=2).

Delta: +10 tests, all new tests GREEN, zero new failures/errors — the 19F/2E
are the exact pre-existing crosslink-suite set (unrelated to this task).

## Smoke

- `python3 cli/embeddings/build_tagvec.py --help` — prints usage, exits 0.
- `python3 cli/embeddings/build_tagvec.py --root ~/Obsidian/Knowledge-Catalogue --output ~/Obsidian/Knowledge-Catalogue/.tagvec/tag_vectors.sqlite`
  (no `--produce`, real live cache, read-only path):
  ```
  bge-m3: 126 tag(s) need embedding, 293 already cached
  voyage-3-large: 33 tag(s) need embedding, 386 already cached
  (dry-run — no network calls, no writes. Re-run with --produce to embed.)
  ```
  Live cache untouched (verified via md5 before/after — no write occurred,
  since the `--produce` gate short-circuits before any `write_rows` call).
  `--produce` was never invoked against the real cache/network per the task's
  hard constraint.
- Cache-key scheme cross-checked against a real row:
  `abgeleitetes-artefakt` / `bge-m3` → computed
  `9ed7f0099beeb094eb5bd182c33f1714c0c77b84`, matches the live DB exactly.

## Finding for Task 8

**Verdict: tag-embeddings only suffice as P8's semantic-backstop surface —
body-embeddings are NOT required for this task.**

- Coverage: 98.0% of concepts in the live catalogue (2386/2435) carry ≥1 tag;
  only 2.0% (49/2435) are untagged.
- Tag-only rescues real paraphrase/synonym drift — exactly what the source
  SOP measured during tag consolidation (`sicherheit → security` 0.90,
  `portainer → docker`, `worktree → git`, `jira → issue-tracking`).
- Tag-only structurally CANNOT rescue concepts with zero tags. The eval
  fixtures already encode this on purpose: S3 (`tags=[]`, built to "isolate
  the keyword-vs-semantic gap") and S4 (`tags=[]`, "findable only via
  index-walk or body search") — a tag-keyed backstop has no vector to match
  a paraphrase query against for these. This is the same 2.0%-untagged slice
  quantified above, not a bug.
- Recommendation: ship P8's backstop against `.tagvec` as specified
  (tag-only). Treat the untagged-concept gap as an accepted, documented
  residual outside P8's scope. Escalate to a separate title/body-embedding
  task only if P12's re-measurement shows it's material — that is a larger,
  differently-scoped indexing problem (~2435 concepts vs. 418 tags today).

## Deviations/ERRATA

- Commit title deviates from the bean's suggested exact string
  (`feat(embeddings): bring tagvec producer + provenance into repo`, 62
  chars) — violates the repo's hard 50-char commit-title gate (hook E1).
  Used `feat(embeddings): pull tagvec producer into repo` (48 chars,
  same intent) instead.
- No actual SOP script file existed anywhere on disk to "import" verbatim
  (grepped Knowledge-Catalogue + home dir) — the SOP doc is prose-only
  methodology, not a script. `build_tagvec.py` was written from scratch
  against the SOP's documented method (slug-only embedding, key scheme,
  endpoints, delta-reuse), not literally copied/adapted from a source file.
- No `--produce` run was executed against the real network/cache (hard
  constraint honored); network embed functions (`embed_bge_m3`,
  `embed_voyage`) are therefore untested against real API responses —
  covered only by the dry-run path + monkeypatched-call tests.

## Notes for T(n+1)

- P8 can read `.tagvec/tag_vectors.sqlite` directly via stdlib `sqlite3`
  with a graceful-skip-if-absent guard (per Global Constraints) — no new
  runtime dep needed; `cache_key`/`slug_text` in `build_tagvec.py` are
  reusable if P8 needs to recompute a query-side embedding key, though P8's
  query-time embedding call (if any) is a separate design question this
  task did not scope.
- The live cache currently lags the catalogue's current tag vocabulary
  (126 bge-m3 + 33 voyage-3-large tags need embedding, per the smoke dry-run)
  — likely drift from Phase-1 tag-merge work since the 2026-07-13 SOP pass.
  P8 should not assume the cache is fully up to date; the graceful-skip
  design already tolerates missing keys per-tag.
