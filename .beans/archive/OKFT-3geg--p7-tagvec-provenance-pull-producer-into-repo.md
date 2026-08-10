---
# OKFT-3geg
title: 'P7 — .tagvec provenance: pull producer into repo'
status: completed
type: task
priority: normal
created_at: 2026-07-25T18:13:10Z
updated_at: 2026-07-25T21:41:53Z
parent: OKFT-5hg4
blocked_by:
    - OKFT-5qmn
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

**[SUPERSEDED 2026-07-25 — post-review F01 (blocking). See "Finding for Task 8
— CORRECTED 2026-07-25 (post-review F01)" below for the current verdict.
Left verbatim, not rewritten, per review instruction.]**

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


## Finding for Task 8 — CORRECTED 2026-07-25 (post-review F01)

**Reviewer defect (F01, blocking):** the original verdict ("tag-embeddings
only suffice") contradicted its own analysis in the same section ("tag-only
structurally CANNOT rescue concepts with zero tags") and PLAN.md Task 8c's
EARS acceptance, which names S3 explicitly: *"WHEN a paraphrase query ... for
fixture S3 AND an embedding backend is available, THE CLI SHALL surface the
expected concept within top-5."* S3 is `tags=[]` by construction, token only
in body — tag-only cannot satisfy that SHALL, by construction, no matter the
coverage percentage. Recommending "ship tag-only, escalate only if P12 shows
it's material" silently dropped a written acceptance criterion; a finding is
not the authority to do that.

**Corrected verdict: tag-embeddings are INSUFFICIENT to satisfy 8c's S3
acceptance as specified.** Coverage is still 98.0% of concepts (2386/2435)
carrying ≥1 tag, but the 2.0% untagged slice (of which S3 is a modeled
instance) is structurally unreachable by a tag-keyed backstop — no vector
exists to match a body-only paraphrase query against.

**Path forward — per PLAN.md's own contingency clause (Task 8c, ~line 395):
"If Task 7 found tag-embeddings insufficient for body-only fixtures (S3
paraphrase), 8c extends the offline producer to also embed titles/bodies and
reads those."** That is now the recorded scope call for Task 8c: it SHALL
extend the offline producer to also embed concept titles/bodies (not tags
only) so S3-class, body-only-token concepts are reachable by the semantic
backstop.

**Alternative path (PO-only):** if extending the producer to titles/bodies is
judged out of proportion to Task 8's remaining scope, the only other
legitimate route is a PO decision to formally revise or drop 8c's S3
acceptance criterion before implementation — not a silent scope-drop inside
a Task-7 finding.

This corrected finding supersedes the "Finding for Task 8" section above in
full; that section is left unmodified (verbatim) and marked superseded, not
rewritten.

## Review 2026-07-25

PO feedback on US-04 (Epic OKFT-5hg4, Round 2), verbatim: "wann werden neue Tags embedded? => das muss automatisch erfolgen sonst haben wir das dilemma, dass dann xxx tags nicht embedded sind. Also rework erforderlich."

**Verdict: r (rejected).** Live-demo during PO-review confirmed the gap directly: 125 of 418 tags in the real catalogue were unembedded at review time (`build_tagvec.py --model bge-m3` dry-run), purely because embedding is a manual, human-triggered offline pass (README.md:11-18) fully decoupled from `okf-cli.py tags --register` (cmd_tags, okf-cli.py:406-409 -> register_tags at :1516). Every newly registered tag silently drifts out of embedding coverage until someone remembers to re-run `--produce` by hand.

**Fix-Prelude:**
- Schwere: medium (silent coverage drift, no crash/data-loss, but defeats the semantic backstop for every tag registered after the last manual run — degrades to keyword-only for those tags without any signal that it happened).
- Fundort: `cmd_tags` / `register_tags()` call site, okf-cli.py:406-409 (register path) + cli/embeddings/build_tagvec.py (producer, currently only invoked manually per README.md).
- Fix-Rezept: after `register_tags()` successfully adds new tag(s) in cmd_tags (okf-cli.py:406-409), auto-invoke the bge-m3 embedding step scoped to just the newly-added tag(s) — e.g. shell out to `build_tagvec.py --produce --model bge-m3` (tags target is already the default) or call its embedding function in-process for `added` only. Must stay best-effort/graceful (Ollama down -> warn on stderr, do NOT fail the `--register` call itself — registering the tag in TAGS.md must still succeed even if embedding fails). Add a regression test asserting: after `tags --register <new-tag>`, the tag is present in `emb` for model bge-m3 without a separate manual `--produce` call.
- Quelle: PO-Review-Session 2026-07-25, Runde 2 (Epic OKFT-5hg4).

## Fix closure 2026-07-25 (inline, no subagent, per PF-1)

**Summary:** tags --register now auto-embeds newly added tag(s) with bge-m3, scoped to just those tags (no full re-embed). Best-effort: embedding failure (Ollama down, network error) prints a stderr warning and does NOT block registration -- TAGS.md write always succeeds.

**Implementation:** okf-cli.py: _load_build_tagvec() (lazy importlib load, cached module-level so tests can monkeypatch the same object's embed_bge_m3, mirroring cli/test_embeddings_tagvec.py's existing pattern) + auto_embed_new_tags(root, tags), called from cmd_tags right after register_tags() succeeds.

**Test-Output (RED->GREEN):**
- RED: AttributeError: module 'okf_cli' has no attribute '_load_build_tagvec' (2 new tests failed before implementation).
- GREEN: both new tests pass (test_register_command_auto_embeds_without_manual_produce, test_embedding_failure_never_blocks_registration).
- Full suite: 191 tests, 19 failures / 2 errors -- byte-identical to the pre-existing baseline (was 189 tests before these 2 additions), 0 new failures.

**Mutation self-test (2/2 caught):**
1. Disabled the auto_embed_new_tags() call site -> test_register_command_auto_embeds_without_manual_produce failed (delta_after non-empty, tag stayed unembedded). Reverted, re-verified GREEN.
2. Removed the try/except around the embed/write call -> test_embedding_failure_never_blocks_registration failed with an uncaught RuntimeError propagating through cmd_tags. Reverted, re-verified GREEN.

**Commit:** cc2696e (fix(cli): auto-embed new tags on register).

**Deviations:** none from the fix-prelude's recipe.

**Notes:** does not touch the separate concept_emb/Q03 question (chunk-vs-document embedding) -- this fix is tag-embedding-only, already-populated infrastructure.
