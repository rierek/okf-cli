---
# okf-cli-8uaf
title: 'P8 — Hybrid find: semantic backstop + filters + score breakdown'
status: in-progress
type: task
priority: normal
tags:
    - to-review
created_at: 2026-07-25T18:13:10Z
updated_at: 2026-07-25T20:09:29Z
parent: okf-cli-5hg4
blocked_by:
    - okf-cli-3geg
---

## Objective (User Story)
As an agent, I want `find` to rescue paraphrase queries semantically, be scopeable by type/tag/bundle, and expose a score breakdown so that retrieval is precise and trustworthy — while staying keyword-first and degrading gracefully.

## EARS Acceptance
- WHEN `find <q> --type T --tag G --scope B` runs, THE CLI SHALL keyword-rank only concepts matching the exact type/tag within scope B (resolve_scopes okf-cli.py:514, extract_tags :519); WITHOUT filters, behavior unchanged.
- WHEN `find <q> --breakdown` runs, THE CLI SHALL emit per-hit contributing field(s)/term(s); WITHOUT it, output byte-identical to today (okf-cli.py:568).
- WHEN a paraphrase query (keyword zero-hit per baseline) for S3 is issued AND an embedding backend is available, THE CLI SHALL surface the expected concept within top-5.
- WHEN the `.tagvec` cache OR embedding backend is absent, THE CLI SHALL return keyword-only results without error.
- THE semantic pass SHALL run only as a backstop (below-threshold/zero keyword), never replacing a strong keyword top-hit (S1 literal stays Top-1).

## Success Criteria
- SC-001: scoped find excludes non-matching types (unit test).
- SC-002: --breakdown lists contributing fields; default output unchanged.
- SC-003: semantic fallback rescues S3 paraphrase (backend-guarded/xfail); graceful keyword-only when cache removed.
- SC-004: `okf_find` MCP tool exposes type/tag/scope/bundle; `_FLAGS` (okf_mcp.py:19) registers scope/bundle so build_argv marshals them (subprocess test).

## Affected code
- `cli/okf-cli.py:538-574` cmd_find + argparse `pf` (:1894-1896)
- `mcp/okf_mcp.py:67-69` okf_find tool + `:18-19` _FLAGS (`"scope":"--scope","bundle":"--bundle"`)
- sqlite3 (stdlib) reader for `.tagvec`; threshold const `SEMANTIC_FALLBACK_RATIO`
- Tests: `cli/test_okf_cli.py`, `cli/test_okf_mcp.py`
Design keyed on P7's tags-vs-body finding. Full 8a/8b/8c steps: PLAN.md Task 8.
Commit: `feat(cli): hybrid find — semantic backstop, filters, score breakdown`

## Prelude 2026-07-25 — non-blocking finding from P1 review (okf-cli-83vq)

F02 (style): cmd_index JSON branch (cli/okf-cli.py ~485-501) duplicates the concept-building loop between the args.bundle and no-bundle cases. Deduplicate opportunistically when touching okf-cli.py in this task. Source: ce-specs-reviewer verdict on okf-cli-83vq.

## Prelude 2026-07-25 — P7 gating finding (okf-cli-3geg, CORRECTED post-review)

BINDING for 8c scope: tag-embeddings are INSUFFICIENT to satisfy 8c's S3 acceptance as specified (98% concept-tag coverage, but S3 is tags=[]/body-only — structurally unreachable by a tag-keyed backstop). Per PLAN's contingency clause: 8c SHALL extend the offline producer (cli/embeddings/build_tagvec.py) to also embed titles/bodies, and the semantic pass reads those vectors. Full finding + data: bean okf-cli-3geg section 'Finding for Task 8 — CORRECTED 2026-07-25' and cli/embeddings/README.md. PO was informed (D01), default path (i) producer extension stands unless PO overrides. Follow LL-01 (docs/LESSONS-LEARNED.md): module-attr pinning + mutation self-test for any boundary test you add.


## Summary

Shipped hybrid `find`: exact-match filter composition (`--type/--tag/--scope/
--bundle`), a `--breakdown` score-transparency flag, and a best-effort
semantic backstop that reads title+body embeddings from an extended
`.tagvec` producer. Kept keyword as the unconditional first pass; the
semantic pass fires ONLY when the keyword top hit is zero or weak
(`SEMANTIC_FALLBACK_RATIO = 0.5`), and its results are score-interleaved with
keyword hits (not blindly appended — see Deviations) so a strong semantic
candidate is not crowded out by weak keyword noise in a ~4000-concept real
catalogue. Per the corrected Task-7 finding (bean okf-cli-3geg), extended
`cli/embeddings/build_tagvec.py` with a `--target concepts` pass that embeds
concept title+body into a NEW `concept_emb` table (existing `emb` tags-only
table/rows untouched) — this is what makes S3-class (tags=[], body-only
token) concepts reachable at all. Opportunistically fixed prelude F02
(cmd_index JSON loop dedup) as its own first commit.

## Test-Output (per subtask, RED -> GREEN)

- Prelude F02: pure refactor, validated by re-running the existing
  `CmdIndexJson`/`CmdListJson` suites unchanged (no new RED needed for a
  style-only dedup) — all green after the refactor.
- 8a (filter composition, CLI + MCP): RED —
  `cli.test_okf_cli.FindFilterComposition` 6/7 failing (scope/tag/type/
  bundle-alias filters not implemented) and
  `cli.test_okf_mcp.McpFindFilterBoundary` 2/4 failing (scope/bundle
  silently dropped — proven via a second bundle sharing the query token, not
  a same-bundle false-green). GREEN after implementing `--type/--tag/--scope/
  --bundle` in `pf` + `cmd_find`, and `_FLAGS`/`okf_find` in `mcp/okf_mcp.py`.
- 8b (score breakdown): RED — `FindScoreBreakdown.
  test_breakdown_lists_contributing_fields` failing (no `contrib:` line).
  GREEN after adding the per-field `contrib` dict + `--breakdown` print path;
  `test_default_output_unchanged_without_breakdown` pins byte-identical
  default output.
- 8c producer (`build_tagvec.py`): RED — 8 errors (`AttributeError` for
  `concept_text`/`concept_cache_key`/`plan_concept_delta`/`write_concept_rows`,
  and `--target`/`--concept-path-prefix`/`--concept-limit` unknown to
  argparse). GREEN after adding the `concept_emb` schema + functions +
  `--target {tags,concepts,both}` (default `tags`, regression-safe).
- 8c CLI (semantic backstop): RED — 7 errors
  (`AttributeError: module 'okf_cli' has no attribute '_embed_query_bge_m3'`
  in every `SemanticBackstop` test's `setUp`). GREEN after adding
  `_tagvec_db_path`/`_load_concept_vectors`/`_embed_query_bge_m3`/`_cosine`/
  `semantic_backstop`/`_semantic_hit_dicts` and wiring the fallback into
  `cmd_find`.
- Full-suite delta, every subtask: 145 tests (19F/2E baseline, per Task-5
  freeze) -> 177 tests (19F/2E) — zero new failures/errors; the 19F/2E are
  the exact pre-existing crosslink-suite set (unrelated to this task).

## Mutation self-test (fusion/ranking logic)

`SemanticBackstop.test_mutation_self_test_inverted_cosine_breaks_ranking`:
monkeypatches `okf._cosine` to `-orig_cosine(a, b)` (inverted), re-runs the
same near/far ranking assertion inside `assertRaises(AssertionError)` to
prove the ordering check actually detects a broken fusion, then restores
`okf._cosine` in a `finally` block. Lives permanently in the suite (not a
one-shot manual check) — re-verified green after restore in the same run.

A second, real-catalogue-driven mutation was found via manual smoke (not
planned upfront): appending semantic hits strictly after ALL keyword hits
let weak keyword noise crowd out a strong semantic candidate before
`--limit`. Proof: temporarily replaced the interleave-sort with `if False:`
(scratch, not committed) — `test_strong_semantic_hit_is_not_crowded_out_by_
weak_keyword_noise` failed (`'b/near' not found in ['b/noise2', 'b/noise6',
'b/noise7']`); reverted via `git checkout -- cli/okf-cli.py` and reapplied
the interleave fix (commit `1350b69`), confirmed green again.

## Smoke

- **(a) filter composition, real catalogue:**
  `python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue find "git
  worktree" --type Concept --scope dev-wiki --limit 3` — 3 hits, all
  `type: Concept` under `dev-wiki/...` (no `--root`-outside-scope leakage).
- **(b) score breakdown:** `find "git worktree" --breakdown --limit 2` ->
  `contrib: title=[git]; body=[git,worktree]` /
  `contrib: title=[worktree]; body=[git,worktree]` per hit.
- **(c) graceful degradation:** both (a) and (b) runs printed `note:
  semantic backstop skipped (.tagvec cache/concept embeddings absent) —
  keyword-only results` on stderr (real live cache has no `concept_emb` rows
  yet outside this manual smoke window) — zero exception, keyword results
  unaffected. Backend-unreachable and empty-table paths additionally covered
  by unit tests (`test_embedding_backend_failure_degrades_gracefully`,
  `test_empty_concept_emb_table_degrades_gracefully`).
- **(d) S3 paraphrase rescue — REAL (Ollama bge-m3, local, reachable this
  session):**
  1. Backed up live `.tagvec/tag_vectors.sqlite` to scratch
     (`tag_vectors.sqlite.pristine-backup`, md5 `0ad92871cfc0a13cdb5baadefdc21ce2`).
  2. `python3 cli/eval/fixtures.py --root ~/Obsidian/Knowledge-Catalogue
     --seed` (S1-S4 into `agent-memory`/`ai-wiki`).
  3. Ran `build_tagvec.py --target concepts --concept-path-prefix
     "agent-memory/_okfeval-" --produce` against a SCRATCH COPY of the cache
     (never the live file directly) — real Ollama call, 3 rows written;
     verified the `emb` (tags) table row count identical before/after
     (1277 == 1277).
  4. Copied the scratch working copy into the live `.tagvec` path (temporary,
     for the smoke window only), ran `find "unmarked item lacking
     classification" --limit 5` against the real catalogue:
     rank 2/5 = `agent-memory/_okfeval-s3` (`provenance: semantic
     (cosine=0.44)`) — the exact fixture golden.json's `s3-paraphrase` row
     expects as a keyword zero/weak-hit rescue. S4 also rescued (rank 1),
     S1 rescued (rank 3) — all three concept-embedded fixtures recovered.
  5. Restored the live cache from the pristine backup (md5 verified
     identical again), tore down the fixtures
     (`fixtures.py --teardown`), verified `git -C
     ~/Obsidian/Knowledge-Catalogue status --short` clean (0 lines).
  6. Re-ran the full suite post-cleanup: 177 tests, 19F/2E (no
     `test_eval_runner` pollution from the smoke window — this was caught
     once mid-session, exactly as an example of why the restore/teardown
     order matters, see Deviations).

## Catalogue / tagvec state

- Real Knowledge-Catalogue: clean (`git status --short` = 0 lines after
  smoke teardown).
- Live `.tagvec/tag_vectors.sqlite`: byte-identical to pre-task state (md5
  `0ad92871cfc0a13cdb5baadefdc21ce2` before and after) — the `concept_emb`
  table exists only in the transient scratch copies used for the smoke, not
  in the live file.

## Deviations/ERRATA

- **Multiple commits per subtask, not one Task-8 commit.** PLAN.md's Task 8
  narrative says "committed as one Task-8 deliverable... hold commit until
  8c"; this session's explicit dispatch instructions said the opposite
  ("Mehrere Commits erwünscht (Preludes, 8a, 8b, 8c, bean)"). Followed the
  session's explicit instruction: 6 commits (`e61c113` F02 prelude,
  `ed53a58` 8a, `7287df5` 8b, `f5f38a2` producer 8c, `f23297f` CLI 8c,
  `1350b69` crowding fix).
- **`build_argv`'s shared `_FLAGS` dict:** the bean/PLAN's literal
  instruction to add `"bundle": "--bundle"` would, by itself, have broken
  `okf_index` — `_FLAGS` is applied uniformly across ALL commands, and
  `"bundle"` is ALSO `index`'s positional param name; a non-empty
  `params["bundle"]` would then have been marshaled a SECOND time as an
  unrecognized `--bundle` flag for `index`'s subparser (which only has the
  positional), causing `argparse` to exit non-zero and `run_okf` to raise
  for every `okf_index(..., bundle="...")` call. Fixed by making
  `build_argv` skip a `_FLAGS` key when it is also in the current command's
  `positional` list; added a regression test
  (`McpFindFilterBoundary.test_index_with_bundle_still_works_after_flags_
  change`) plus a direct `build_argv` unit test
  (`BuildArgvBundlePositionalGuard`). Caught by writing the RED test with a
  SECOND bundle sharing the query token (LL-01-style diligence) instead of
  trusting a same-content false-green.
- **`--bundle` implemented as a `--scope` alias**, not a fully independent
  filter dimension. EARS Acceptance for 8a names only `--scope`; the
  Interfaces line additionally lists `--bundle`, and SC-004 requires both to
  reach the CLI via MCP. No prior codebase pattern defines a distinct
  `--bundle` semantics for `find` (unlike `cmd_index`'s positional
  `bundle`), so I resolved the ambiguity as: `--bundle` narrows via the same
  `resolve_scopes()` call as `--scope`; `--scope` wins if both are given.
  Documented, tested (`test_bundle_alias_behaves_like_scope`,
  `test_scope_and_bundle_both_set_scope_wins`), not silently assumed.
  Flagging for PO/T12 in case a distinct semantics was actually intended.
- **Fusion is score-interleaved, not append-only** — see the Mutation
  self-test section above for the real-catalogue finding that forced this;
  `PLAN.md`'s own fusion clause explicitly allows "appended/interleaved",
  so this is within the stated design space, not outside it.
- **Query-time semantic embedding uses ONLY `bge-m3` (local Ollama)**, never
  `voyage-3-large`, even though the producer can embed concepts with either
  model. Rationale: `voyage-3-large` requires `VOYAGE_API_KEY` and a paid
  network call at QUERY time in production use, which conflicts with
  "best-effort, no hard dependency, no cost" graceful degradation; `bge-m3`
  via local Ollama has neither cost nor a required secret. This is a
  narrower runtime surface than the producer supports — intentional, not an
  oversight.
- **Mid-session test pollution, caught and corrected in-session:** after the
  first (pre-crowding-fix) real smoke run, the live `.tagvec` cache was left
  swapped and fixtures left seeded while the full suite was re-run once —
  `cli.test_eval_runner.RunnerAgainstRealCatalogueTest.
  test_zero_hit_paraphrase_rows_get_rank_inf_never_crash` failed (20F
  instead of 19F) because the semantic backstop was now live against the
  real catalogue mid-eval-fixture-window. Root-caused immediately (not a
  code regression), live cache restored from the pristine backup and
  fixtures torn down before proceeding; the suite returned to the exact
  19F/2E baseline. Recorded per LL-03's forward-guard (residue-check
  discipline) even though the actual residue here was cache-state, not
  files.
- **F02 prelude:** deduplicated `cmd_index`'s JSON concept-building loop
  into `_concepts_json()`; pure refactor, output-preserving (validated by
  the pre-existing `CmdIndexJson` suite, no new test added since it's
  style-only).

## Notes for T(n+1) (P12 re-measurement)

- **What changed in `find`'s behavior and why golden-rows should move:**
  - `s3-paraphrase` (currently `expect: "miss"` in `golden.json`) should now
    resolve to a HIT within top-5 whenever a `.tagvec` cache with
    `concept_emb` rows for the query's catalogue exists — per the real
    smoke above, `agent-memory/_okfeval-s3` landed at rank 2/5. **P12 must
    first run `build_tagvec.py --target concepts --produce` (real, against
    the live catalogue, gated by `--produce` as always) to populate
    `concept_emb` for the real 2435-concept catalogue** — the semantic
    backstop is a no-op (keyword-only, with a stderr note) until that cache
    exists; it does NOT run automatically as part of `find`.
  - `s1-paraphrase`/`s4-paraphrase` may ALSO flip from miss to hit once
    `concept_emb` is populated for their bundles (S1/S4 fixtures were also
    successfully rescued in the smoke — ranks 3 and 1 respectively) even
    though they are NOT the fixture 8c's acceptance specifically named (only
    S3 is EARS-named) — this is an expected side-benefit, not a defect;
    `golden.json`'s `expect: "miss"` for s1/s4-paraphrase may need PO review
    as part of P12, since a real capability improvement changes what
    "expected" should mean for those rows.
  - `s2-paraphrase` should NOT flip (S2 is a location-sensitivity fixture,
    not indexed differently by the semantic pass; find remains
    location-blind by design either way).
  - Literal S1-S4 (`min_rank`/`min_score_ratio` rows) are UNCHANGED — the
    semantic pass never fires when the keyword top hit is strong (ratio
    >= 0.5), which is true for every literal-class golden row by
    construction.
  - `mean_score_ratio` (literal-class only) is unaffected (semantic pass
    doesn't touch literal rows).
- **Cache-population is now part of the P12 runbook, not automatic.** The
  real `concept_emb` production run for the full ~2435-concept catalogue
  was deliberately NOT done in this task (only the 3 fixture concepts,
  scoped via `--concept-path-prefix`, to keep the real network call small
  and the live cache pristine per the hard constraints) — P12 needs its own
  `--produce` pass (real Ollama, no `VOYAGE_API_KEY` needed since query-time
  only uses `bge-m3`) before re-measuring, and should budget for that
  runtime (roughly 2435 local-Ollama calls, unless already warm from a prior
  producer run for other purposes).
- `SEMANTIC_FALLBACK_RATIO = 0.5` and `OLLAMA_EMBED_TIMEOUT = 5` are the two
  tunables (`cli/okf-cli.py`) if P12's delta table suggests the threshold or
  timeout needs adjustment.


## ERRATA — concurrent-commit collision during commit-title cleanup (2026-07-25, post-hoc)

After the original 6 P8 commits landed, I found 3 titles exceeded the
repo's strict 50-char limit (51/52/56 chars) and corrected them via
`git reset --soft`/`--hard` + `git cherry-pick` (no `rebase -i`, per the
harness's flag ban). Mid-sequence, the supervisor concurrently committed
`bc4feda` ("docs(beans): anchor PF-1 inline-mode from P12") directly on top
of my intermediate `ed53a58` reset-point in the SAME shared working
directory — the exact shared-HEAD collision the worktree-isolation rule
exists to prevent (main-workdir, no worktree, both of us writing at once).
My subsequent `git reset --hard ed53a58` then orphaned that commit from
`main`'s branch pointer (object stayed reachable only via reflog).

Caught immediately by diffing the orphaned commit against my rebuilt HEAD
before calling the task done: only ONE file differed —
`.beans/okf-cli-wuiv--okf-climcp-maturity-revision.md` (the supervisor's PF-1
PO-directive anchor, 8 lines) — everything else (all P8 code/test/bean
content) was already byte-identical between the orphaned commit and my
rebuilt history, since both derived from the same diffs. Recovered via
`git checkout bc4feda -- <that file>` + a new commit (`358ba01`,
`docs(beans): anchor PF-1 inline-mode from P12`, same message, correct
content, now on `main`). Verified with a full `git diff bc4feda HEAD` across
every file (empty) before proceeding. `backup-before-title-fix` safety
branch (created before the reset sequence) deleted after parity was
confirmed. No supervisor content was lost; the P8 deliverable itself was
never at risk (rebuilt from the original, correctly-scoped commits via
`git cherry-pick`, not reconstructed from memory).
