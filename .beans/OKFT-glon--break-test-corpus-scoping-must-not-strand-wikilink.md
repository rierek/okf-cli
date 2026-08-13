---
# OKFT-glon
title: 'Break-test: corpus scoping must not strand wikilinks'
status: completed
type: task
priority: high
created_at: 2026-08-13T11:07:31Z
updated_at: 2026-08-13T12:10:58Z
parent: OKFT-wmbu
blocked_by:
    - OKFT-n8xz
---

Proof obligation for the corpus/resolution split, per lean-stack-okf/guard-form-vs-mechanismus: a guard nobody deliberately tried to break is a hypothesis.

Procedure: add a wikilink from a topic-folder file to a bundle concept and one in the reverse direction, run okf-cli check on the bundle, and quote the observed output. Assert that no new unresolved entries appear. Roll the manipulation back afterwards.

A passing run without this probe does not close the task.



## Summary

Ran the break-test the bean requires — a wikilink in each direction across the `okf-tools-okf` bundle boundary, `okf-cli check`/`wikilinks` before and after, and a counter-probe that deliberately narrows `build_concept_basename_index` to prove the assertion can fail. All against the real `/Users/erik/dev/okf-tools/docs` (`bundle = "okf-tools-okf"`), manipulated and rolled back per direction, never committed.

Result: both directions resolve cleanly with the guard intact (no new unresolved entries); the counter-probe shows the guard is real — narrowing `build_concept_basename_index` to `list_indexable_bundles` breaks direction 2 (bundle → topic-folder) but *not* direction 1 (topic-folder → bundle), and that asymmetry is explained below, not just observed.

One correction to the bean's own procedure: `okf-cli check` on this repo is silent on wikilinks regardless of resolution, because `docs/.okf.toml` carries no `wikilink_checked_bundles` key — `check`'s violation list never includes unresolved-wikilink findings here. `check`'s 33-violation total is therefore *not* the discriminating signal the bean's step 3/4 implies; `okf-cli wikilinks --unresolved` is. Both are quoted below; `check` is included because the bean names it explicitly, but the assertion in step 5 rests on `wikilinks`.

## Test-Output

`just test` gate, clean tree, no code change committed:

```
FAIL: test_index_walk_row_present_with_rank_no_dedicated_metric (test_eval_runner.RunnerAgainstRealCatalogueTest.test_index_walk_row_present_with_rank_no_dedicated_metric)
FAIL: test_metadata_hit_and_miss_rows_scored_correct (test_eval_runner.RunnerAgainstRealCatalogueTest.test_metadata_hit_and_miss_rows_scored_correct)
FAIL: test_runner_scores_literal_s1_top1 (test_eval_runner.RunnerAgainstRealCatalogueTest.test_runner_scores_literal_s1_top1)
Ran 685 tests in 26.145s
FAILED (failures=3)
```

Exactly the three pre-existing `RunnerAgainstRealCatalogueTest` failures from the epic baseline, no fourth. `git status --porcelain` empty before and after this run.

## Smoke

All four runs below are against `/Users/erik/dev/okf-tools/docs` via `python3 cli/okf-cli.py --root docs <cmd>` (no `.fts/` rebuild involved — `check`/`wikilinks` read markdown directly). Manipulated files were reverted with `git checkout --` immediately after each capture; `git status --porcelain` and `git diff` were empty before the next step and after the last one.

### Baseline (before any manipulation)

`check`:

```
ERROR    reserved-no-type     okf-retrieval-architecture/eval/README.md  (reserved file must not carry `type`)
ERROR    asset-placement      okf-retrieval-architecture/eval/queries_generated.json  (non-md file outside assets/)
ERROR    asset-placement      okf-retrieval-architecture/eval/eval_v2.json  (non-md file outside assets/)
ERROR    asset-placement      okf-retrieval-architecture/eval/hybrid_v1c.json  (non-md file outside assets/)
ERROR    asset-placement      okf-retrieval-architecture/eval/queries_negative.json  (non-md file outside assets/)
ERROR    asset-placement      okf-retrieval-architecture/eval/queries_i01.json  (non-md file outside assets/)
ERROR    asset-placement      okf-retrieval-architecture/eval/shipped_expand.json  (non-md file outside assets/)
ERROR    asset-placement      okf-retrieval-architecture/eval/remeasure.py  (non-md file outside assets/)
ERROR    asset-placement      okf-retrieval-architecture/eval/eval_full6.json  (non-md file outside assets/)
ERROR    asset-placement      okf-retrieval-architecture/eval/hybrid_v2c.json  (non-md file outside assets/)
ERROR    asset-placement      okf-retrieval-architecture/eval/gen_queries.py  (non-md file outside assets/)
ERROR    asset-placement      okf-retrieval-architecture/eval/i01_jargon.json  (non-md file outside assets/)
ERROR    asset-placement      okf-retrieval-architecture/eval/queries_v2.json  (non-md file outside assets/)
ERROR    asset-placement      okf-retrieval-architecture/eval/hybrid_eval.py  (non-md file outside assets/)
ERROR    asset-placement      okf-retrieval-architecture/eval/measure_negative.py  (non-md file outside assets/)
ERROR    asset-placement      okf-retrieval-architecture/eval/eval_arms.py  (non-md file outside assets/)
ERROR    asset-placement      okf-retrieval-architecture/eval/queries_real.json  (non-md file outside assets/)
ERROR    asset-placement      okf-retrieval-architecture/eval/negative_v1.json  (non-md file outside assets/)
ERROR    asset-placement      okf-retrieval-architecture/eval/i01_jargon_after.json  (non-md file outside assets/)
ERROR    asset-placement      okf-retrieval-architecture/eval/fts_arm.py  (non-md file outside assets/)
ERROR    asset-placement      okf-retrieval-architecture/eval/embed_arms.py  (non-md file outside assets/)
ERROR    asset-placement      okf-retrieval-architecture/eval/shipped_2026-08-10.json  (non-md file outside assets/)
ERROR    asset-placement      okf-retrieval-architecture/eval/shipped_v2.json  (non-md file outside assets/)
ERROR    asset-placement      okf-revision/06-retrieval-quality.yaml  (non-md file outside assets/)
ERROR    asset-placement      okf-revision/08-retrieval-flow.yaml  (non-md file outside assets/)
ERROR    asset-placement      okf-revision/05-cli-docs.yaml  (non-md file outside assets/)
ERROR    asset-placement      okf-revision/04-skills.yaml  (non-md file outside assets/)
ERROR    asset-placement      okf-revision/00-synthesis.yaml  (non-md file outside assets/)
ERROR    asset-placement      okf-revision/02-verbs.yaml  (non-md file outside assets/)
ERROR    asset-placement      okf-revision/03-mcp-config.yaml  (non-md file outside assets/)
ERROR    asset-placement      okf-revision/01-storage.yaml  (non-md file outside assets/)
ERROR    asset-placement      okf-revision/07-tests-and-usage.yaml  (non-md file outside assets/)
ERROR    asset-placement      wikilink-awareness/mutants.py  (non-md file outside assets/)
WARNING  entry-file-description okf-cli-capability-surface  (no entry file (INDEX-MAP.md/index.md) found)
WARNING  entry-file-description okf-retrieval-architecture  (no entry file (INDEX-MAP.md/index.md) found)
WARNING  entry-file-description okf-revision  (no entry file (INDEX-MAP.md/index.md) found)
WARNING  entry-file-description okf-tools-okf-inbox  (no entry file (INDEX-MAP.md/index.md) found)
WARNING  entry-file-description plans  (no entry file (INDEX-MAP.md/index.md) found)
WARNING  entry-file-description wikilink-awareness  (no entry file (INDEX-MAP.md/index.md) found)
33 VIOLATIONS
```

23 `okf-retrieval-architecture/`, 9 `okf-revision/`, 1 `wikilink-awareness/` (per-directory `asset-placement`/`reserved-no-type` count), matching the reviewer's earlier figure exactly.

`wikilinks --unresolved`:

```
unresolved body        okf-tools-okf/archive-lifecycle/index.md  [[x]]
unresolved frontmatter okf-tools-okf/archive-lifecycle/active-beats-archived-in-wikilink-resolution.md  [[x]]
unresolved body        okf-tools-okf/archive-lifecycle/active-beats-archived-in-wikilink-resolution.md  [[autonome-agent-kette]]
wikilinks: 3 link(s), 0 resolved, 0 ambiguous, 3 unresolved
```

(The three baseline-unresolved links are pre-existing illustrative `[[x]]` placeholders and one cross-repo reference to a lean-stack concept — none touched by this probe.)

### Probe Richtung 1 — topic folder → bundle

Appended `Probe OKFT-glon direction 1: [[find-score-formula-drift]].` to `docs/wikilink-awareness/NSP.md` (topic folder `wikilink-awareness`, outside the declared bundle) linking to `okf-tools-okf/capability-surface/find-score-formula-drift.md` (inside the declared bundle).

`check`: `diff` against the baseline capture above is empty (byte-identical, still `33 VIOLATIONS`).

`wikilinks --unresolved`:

```
unresolved body        okf-tools-okf/archive-lifecycle/index.md  [[x]]
unresolved frontmatter okf-tools-okf/archive-lifecycle/active-beats-archived-in-wikilink-resolution.md  [[x]]
unresolved body        okf-tools-okf/archive-lifecycle/active-beats-archived-in-wikilink-resolution.md  [[autonome-agent-kette]]
wikilinks: 4 link(s), 1 resolved, 0 ambiguous, 3 unresolved
```

Assertion holds: 4 links now (was 3), 1 newly resolved, **unresolved count unchanged at 3** — no new unresolved entries. Reverted with `git checkout -- docs/wikilink-awareness/NSP.md`; `git status --porcelain` empty.

### Probe Richtung 2 — bundle → topic folder

Appended `Probe OKFT-glon direction 2: [[NSP]].` to `docs/okf-tools-okf/capability-surface/find-score-formula-drift.md` (inside the declared bundle) linking to `docs/wikilink-awareness/NSP.md` (topic folder, outside the declared bundle).

`check`: `diff` against baseline empty, still `33 VIOLATIONS`.

`wikilinks --unresolved`:

```
unresolved body        okf-tools-okf/archive-lifecycle/index.md  [[x]]
unresolved frontmatter okf-tools-okf/archive-lifecycle/active-beats-archived-in-wikilink-resolution.md  [[x]]
unresolved body        okf-tools-okf/archive-lifecycle/active-beats-archived-in-wikilink-resolution.md  [[autonome-agent-kette]]
wikilinks: 4 link(s), 1 resolved, 0 ambiguous, 3 unresolved
```

Same result: unresolved count stays at 3. Reverted with `git checkout -- docs/okf-tools-okf/capability-surface/find-score-formula-drift.md`; `git status --porcelain` empty.

### Gegenprobe — guard deliberately broken

Mutated `cli/okf-cli.py:3695` inside `build_concept_basename_index`, `for b in list_bundles(root):` → `for b in list_indexable_bundles(root):` — the exact mutation the bean's task description names. Repeated both directions with this mutation live.

Richtung 1 replayed (topic folder → bundle, `NSP.md` → `find-score-formula-drift`): `check` diff still empty (`33 VIOLATIONS`); `wikilinks --unresolved` still `4 link(s), 1 resolved, 0 ambiguous, 3 unresolved` — **the counter-probe does NOT catch direction 1**, because the target (`find-score-formula-drift`) is itself inside the declared bundle, so it stays in the index even when the index is narrowed to `list_indexable_bundles`. This is a real, mechanism-level fact, not a probe weakness — see Deviations below.

Richtung 2 replayed (bundle → topic folder, `find-score-formula-drift` → `NSP.md`) with the same mutation live:

```
unresolved body        okf-tools-okf/capability-surface/find-score-formula-drift.md  [[NSP]]
unresolved body        okf-tools-okf/archive-lifecycle/index.md  [[x]]
unresolved frontmatter okf-tools-okf/archive-lifecycle/active-beats-archived-in-wikilink-resolution.md  [[x]]
unresolved body        okf-tools-okf/archive-lifecycle/active-beats-archived-in-wikilink-resolution.md  [[autonome-agent-kette]]
wikilinks: 4 link(s), 0 resolved, 0 ambiguous, 4 unresolved
```

`check` stays silent even here (diff against baseline still empty, `33 VIOLATIONS`) — confirming the D02 finding above independently: on this repo's config, `check` cannot see this regression at all, only `wikilinks` can. The counter-probe **does** catch direction 2: unresolved count rises from 3 to 4, exactly the failure `okf-tools-okf/archive-lifecycle/active-beats-archived-in-wikilink-resolution` predicts — narrowing the corpus strands an inbound link and turns a loud defect (missing target) into a silent one (target exists, index no longer sees it).

Reverted both files: `git checkout -- docs/okf-tools-okf/capability-surface/find-score-formula-drift.md cli/okf-cli.py`. `git status --porcelain` and `git diff` empty — verified clean before writing this report.

## Deviations/ERRATA

- **The bean's step 3/4 ("run `okf-cli check`, quote the output") is not the discriminating signal on this repo.** `docs/.okf.toml` carries no `wikilink_checked_bundles` key, so `run_checks`'s wikilink pass never runs here and `check`'s violation list cannot show an unresolved wikilink regardless of resolution correctness — verified directly: appending an unambiguously-dead `[[does-not-exist-anywhere-zz]]` link left `check`'s `33 VIOLATIONS` unchanged. `okf-cli wikilinks --unresolved` is what actually carries the assertion in this repo; both are quoted above, but the pass/fail judgment rests on `wikilinks`, not `check`. Flagging this rather than silently substituting commands, per instruction 4 (deviations need a stated reason, not a silent swap).
- **The counter-probe only breaks one of the two directions, and that is expected, not a gap.** `build_concept_basename_index`'s narrowing removes bundles *other than* the declared one from the resolution-target index. Richtung 1's target (`find-score-formula-drift`) lives inside the declared bundle, so it stays indexed under `list_indexable_bundles` too — no mutation of this function can break that direction. Richtung 2's target (`NSP`) lives outside the declared bundle, so narrowing removes it from the index — this is the direction the archive-lifecycle concept's failure mode actually predicts, and it is the one that broke.
- No file under `~/Obsidian/Knowledge-Catalogue` or `/Users/erik/dev/lean-stack` was touched. All manipulation was against `/Users/erik/dev/okf-tools/docs` and `/Users/erik/dev/okf-tools/cli/okf-cli.py`, reverted via `git checkout --` after each step, verified via `git status --porcelain`/`git diff` before proceeding.

## Test coverage decision — no new test added

Checked both `BundleKeyDoesNotNarrowResolution` and `CheckAndWikilinksStayWideWithDeclaredBundle` (`cli/test_okf_cli.py`) against the two failure modes this probe exercises, not just against the bean's two directions:

- **Failure mode A — resolution-target index narrowed** (what my counter-probe mutation triggers, `build_concept_basename_index` line 3695): `BundleKeyDoesNotNarrowResolution` already pins this exactly — a concept inside a declared bundle linking to one outside it, asserting `resolve_wikilink` still returns `resolved`. This is Richtung 2's failure mode. Covered.
- **Failure mode B — source traversal narrowed** (a hypothetical mutation of `scan_wikilinks`/`run_checks`'s own directory walk to `list_indexable_bundles`, which would make a scaffolding source file invisible to `wikilinks`/`check` entirely, never mind whether its links resolve): `CheckAndWikilinksStayWideWithDeclaredBundle` already pins this — its `other-scaffolding/bad.md` file sits outside the declared bundle and the test asserts the unscoped `run_checks`/`scan_wikilinks` still reports it. This is Richtung 1's failure mode (a wikilink whose *source* sits outside the bundle must still be scanned) — Richtung 1's target happening to be inside the bundle only means Richtung 1 cannot additionally test failure mode A, not that it goes uncovered.

Both directions' actual failure modes are therefore already guarded by existing, independently red-turning tests. Adding a third test that repeats either mutation against a real-vs-real-bundle-concept fixture would be the guard-form-vs-mechanismus violation the source concept itself warns against — a duplicate assertion against the same mechanism, not a new one. No test added.

## Notes for T(n+1)

- If a future task wants `check` itself to be the discriminating signal for wikilink regressions in this repo, `docs/.okf.toml` needs a `wikilink_checked_bundles` entry naming `okf-tools-okf` — currently absent, so `check`'s 33-violation count is entirely `asset-placement`/`reserved-no-type`/`entry-file-description` and never wikilinks, independent of any corpus-scoping change.
- The asymmetry documented above (Richtung 2 breakable by index-narrowing, Richtung 1 not) is a property of `build_concept_basename_index`'s specific narrowing mutation, not a general claim that inbound links from scaffolding are safe from every possible future narrowing — see failure mode B, which a *different* mutation (of the source-traversal call sites, still on OKFT-n8xz's negative list) would trigger, and which is already guarded.


## Review 2026-08-13 — APPROVED (ce-specs-reviewer)

The reviewer re-ran the whole probe rather than reading it, and confirmed the asymmetry with a stronger argument than the implementer gave.

**The `check` substitution holds.** Verified mechanically, not taken on trust: `docs/.okf.toml` carries no `wikilink_checked_bundles`, so `wikilink_checked_bundles(config, root)` returns `set()`, `wl_checked` in `run_checks` is empty, and `check_wikilink_resolvable` (:3797-3815) returns `[]` for every file regardless of resolution state. The substitute is not a workaround but the same mechanism: `check_wikilink_resolvable` and `scan_wikilinks` both go through `resolve_wikilink_records` → `resolve_wikilink` → `build_concept_basename_index`. Only the opt-in gate and file-wise vs link-wise aggregation differ. `wikilinks --unresolved` exercises exactly the path `check` would exercise if the gate were armed.

**The inert direction is inert by construction, not by accident.** Reproduced: with `build_concept_basename_index` narrowed, direction 2 gives `4 link(s), 0 resolved, 0 ambiguous, 4 unresolved`, direction 1 gives `4 link(s), 1 resolved, 0 ambiguous, 3 unresolved`. The reviewer's addition: such a mutation can only remove targets *outside* the declared bundle from the index, and direction 1's target is by definition *inside* it. Direction 1 is therefore unbreakable by **any** bundle-narrowing mutation of that function — not just by the one that was tried.

**Direction 1's real risk is a different mutation, and it is covered.** The risk is narrowing the *source* traversal, so the link is never seen at all. The reviewer wrote a second, different mutation for that (`scan_wikilinks` building a bundle-scoped index) and found both existing guards still green while the real direction-1 probe still resolved — i.e. it hunted for a gap and did not find one.

**Rollback clean.** `git status --porcelain` and `git diff HEAD` empty before and after the reviewer's own runs; `git show ac66bfd --stat` is one file, 164 insertions, the bean alone; both manipulated docs files byte-identical to origin; `cli/okf-cli.py` byte-identical to a pre-review backup.

`just test`: `Ran 685 tests in 26.692s`, `FAILED (failures=3)`, the three baseline failures, no fourth.

### Non-blocking, carried forward

- **D01** — the bean said `check` **on the bundle**; the run was unscoped against the whole docs root. Correct as executed: a bundle-scoped run would never have scanned direction 1's source file, which lives outside the bundle, and would have voided the probe. Deviation is right, but it is a deviation.
- **Q01 / I01** — filed as OKFT-uctf: arm `wikilink_checked_bundles` for this repo, and add a test that pins direction 1 directly instead of relying on a structural argument.
- **Q02** — the gap hunt in prüfpunkt 5 was targeted, not exhaustive. No impossibility proof was attempted, and none is claimed.
