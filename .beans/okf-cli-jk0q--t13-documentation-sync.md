---
# okf-cli-jk0q
title: T13 Documentation sync
status: completed
type: task
priority: normal
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-26T09:59:30Z
parent: okf-cli-cskz
blocked_by:
    - okf-cli-snxj
    - okf-cli-ftri
    - okf-cli-1mxp
---

Plan: `docs/okf-retrieval-architecture/PLAN.md` → **Task 13**. Follow it step by step.

Documentation trails the shipped end state, and one governance contradiction gets fixed on the way (finding I01): `docs/CLAUDE.md:12` mandates `plans/<beans-id>-<slug>/`, while the governing `/tools/CLAUDE.md` forbids a separate `/plans/` and requires the plan to live beside its think collection. Global wins.

### Requirement 1: The written record matches what shipped

**Objective:** As the next session picking this repo up, I want the docs to describe the shipped behaviour, so that I do not re-derive decisions that were already made and measured.

#### Acceptance Criteria

1. THE producer README SHALL document the batch limits, the retry/halve/skip ladder, the per-batch write and the resulting resumability, and the fact that `concept_emb` holds voyage rows for the whole catalogue, and that `emb` keeps both models for tags.
2. THE repo docs README SHALL describe the topic-folder layout and SHALL NOT mandate a separate plans folder.
3. THE think collection SHALL carry D14 through D17 with their reasoning, and its task and question rows SHALL reflect the measured outcomes.
4. THE SSTD entry point SHALL name the shipped state, the covering bean, the location of the measurement files, and the open merge gate — and SHALL no longer warn about a parallel session owning Q03.
5. IF files still sit under `docs/plans/` THEN THE implementer SHALL leave them in place and report the discrepancy, rather than moving them.

#### Success Criteria

- SC-01: `cli/embeddings/README.md` covers all five producer facts named above.
- SC-02: `docs/CLAUDE.md` no longer contradicts `/tools/CLAUDE.md` on plan location.
- SC-03: `DECISIONS.md` carries D14-D17; T10/T11/T12/T13 are closed with commit shas; T03/T05/T07 are closed with their measured outcome; Q08 and Q09 are resolved.
- SC-04: `docs/SSTD.md` names the bean, the measurement files and the merge gate.
- SC-05: `python3 -m unittest discover -s cli -p 'test_*.py'` stays at exactly 19 failures / 2 errors and the working tree is clean apart from files owned by another session.

_Requirements: PLAN.md Task 13 · finding I01 · QUESTIONS Q08, Q09_

## Steps

- [ ] Update `cli/embeddings/README.md`
- [ ] Fix `docs/CLAUDE.md:12` (I01)
- [ ] Append D14-D17 to `DECISIONS.md`; update `TASKS.md` and `QUESTIONS.md` to the measured outcomes
- [ ] Update the `docs/SSTD.md` entry point
- [ ] Commit `docs: sync retrieval architecture end state`
- [ ] Final verification: suite at 19F/2E, `git status --short` clean

## Recommended Skills

- none (documentation)


## Prelude from the T12 review (2026-07-26, supervisor)

T12 (`okf-cli-1mxp`) is closed and approved. This is the last leaf of the feature; four things carry into it.

### 1. MANDATORY EXTRA SCOPE — recast R44 in `REFERENCES.md`

Assigned to this task by the plan author's ruling (anchored in bean `okf-cli-1mxp`, commit `e152b23`). It is **pure text work — no measurement run, no threshold touched.**

T12 regenerated `docs/okf-retrieval-architecture/eval/shipped_v2.json`. R44 now cites numbers its own raw-data file no longer contains:

- `combined.mrr` moved **0.451901 → 0.450860**. Crucially, **0.45086 is now independently reproduced twice** (the T09 reviewer, then T12) while **0.4519 was the one-off outlier**. R44 currently has this backwards: its table shows 0.452 and its "Reproduzierbarkeit des MRR" paragraph names 0.45086 as the *deviating* re-run. That paragraph must be **rewritten, not appended to.**
- The recast: **0.4509 as the headline number** because twice-reproduced; 0.4519 mentioned as the one-off first measurement; cause named as the index-state-dependent near-tie; plus the explicit statement that zero-hit and all recall values stayed stable, so the core claim is untouched.
- **Latency drifted too and is equally stale**: combined p50 0.6214 → 0.6283 s, combined max 0.7662 → 0.9369 s. Reconcile the WHOLE R44 table against the current `shipped_v2.json`, not only the MRR cell.
- `recall@1/5/10` and `zero_hit` are bit-identical across all three sets — do not change those.
- All four gate criteria still pass on the new numbers (zero-hit 0.1667 ≤ 0.30, MRR 0.4509 ≥ 0.35, real-query zero-hit 0.125 ≤ 0.25, p50 0.628 ≤ 2.0). The gate statement itself does not change; only the cited values do.
- `[^r44]` (the 2443-vs-2437 corpus-size footnote) stays as it is.

### 2. Documentation debt from earlier leaves that must land here

- **The bound on the suggestion feature (T10):** `_zero_hit_suggestions()` reaches typos and synonyms ONLY. Truncated or partially typed terms never arrive there, because the substring scan matches any prefix and the FTS arm matches it via prefix query — both catch it first by construction. This was explicitly marked in bean `okf-cli-snxj` as carrying forward into T13 docs. Someone who does not know this will wonder why suggestions stay absent on a half-typed query.
- **The expansion result (T11):** `--expand-tags` ships **off by default** and stays off. Tag-vector expansion cannot close the R12 gap in principle — not the floor, not granularity, but because the terms are not neighbours in tag-slug space (tags are embedded slug-only, R06). Concept embedding is what solves that class. See Q05/Q06.
- **The taxonomy (T12):** `docs/okf-retrieval-architecture/eval/taxonomy.md`. Point the doc sync straight at it. Headline finding: `catalogue-gap` 0 of 8 — the next lever is retrieval design, not authoring.

### 3. A correction to T13's own file list

`docs/CLAUDE.md` exists in this repo; there is **no root-level `CLAUDE.md` file at all** (only the global `/tools`-level one governs). Re-check T13's I01 line reference against reality before editing anything.

### 4. Standing rules

- **PF-5:** a sentence whose function is to end review is the sentence that gets checked. "Verified" without a named command and its quoted output is a finding. The T12 round produced a textbook case: a Summary sentence read as complete verification while one value it covered had in fact moved.
- **No `to-review` on leaves.** That tag is the PO's, for containers only.


## Summary

All six PLAN.md Task 13 steps done, plus the mandatory extra scope from the T12-review prelude (R44 reconciliation). Documentation now matches the shipped end state of feature `okf-cli-cskz` (all 13 leaves completed); the one remaining step is the PO merge gate.

Files changed (commit `7136c6c`, `docs: sync retrieval architecture end state`):

- `cli/embeddings/README.md` — new section "Batching, resilience and resumability (T01-T03)": `BATCH_LIMITS` per model (bge-m3 32/90000, voyage-3-large 128/90000, `build_tagvec.py:68`), the retry/halve/skip ladder in `embed_resilient()` (`build_tagvec.py:219`, 3 retries with exponential backoff, halving from retry 2, skip-with-report on final failure, skipped batch reappears in next delta plan), per-batch `write_rows()`/`write_concept_rows()` commits = resumability, and `concept_emb`'s current state (2443/2443 voyage-3-large rows, 100% coverage, per bean `okf-cli-c922`) vs. `emb` keeping both models for tags.
- `docs/CLAUDE.md:10` (I01) — replaced the `plans/<beans-id>-<slug>/` line with the `<topic-slug>/` wording PLAN.md Step 2 specified verbatim. `docs/plans/okf-cli-dwcq-cli-okf-prime-optimieren/` still exists under the old layout — left in place per the plan's own contingency clause, not moved.
- `docs/okf-retrieval-architecture/DECISIONS.md` — appended D14-D17 with Warum, verbatim from PLAN.md's "Decisions this plan implements" table.
- `docs/okf-retrieval-architecture/TASKS.md` — T10/T11/T12/T13 (TASKS.md's own Txx numbering, NOT PLAN.md's Task-N numbering, which is a different axis) → 🟢 with commit shas (T10=producer resilience `f63847e`, T11=Ollama batching `2a07ee9`, T12=conditional-handover fusion `4f258d3`/`d6f6175`, T13=FTS5 lexical path `67a8bbb`/`3c3c026`); T03 (taxonomy) → 🟢 `81a0368`/`101522c`; T05 (tag-expansion prototype) → 🟢, measured negative-in-principle, ships flag-gated off; T07 (zero-hit enrichment) → 🟢 `edc2347`/`ee444fb`, plus the T10-prelude's suggestion-bound note (typos/synonyms only, never truncated/partial terms) landed on this row as the natural bean-scoped location. T14/T15/T09 → 🟢 (already true pre-plan, commit `c811b25`).
- `docs/okf-retrieval-architecture/QUESTIONS.md` — Q09 → 🟢 (D15, stdlib-only constraint holds, index artefacts stay optional). Q08 → 🟢 with the reconciled p50/max (0.628s/0.937s combined, from `shipped_v2.json`) — latency is not the binding factor at this catalogue scale.
- `docs/SSTD.md` — new Entry-Point: feature shipped (13/13 leaves completed), measurement location, PO merge gate as the sole open step; removed the stale "parallel session owns Q03" warning from both the historical entry-point paragraph and the Attention section (that session is this one, and it is done); noted the `docs/plans/` discrepancy.
- `docs/okf-retrieval-architecture/REFERENCES.md` R44 — **mandatory extra scope** (prelude §1). Whole table reconciled against the current `shipped_v2.json` (values read via `python3 -c "import json; ..."`, quoted below); "Reproduzierbarkeit des MRR" paragraph rewritten (not appended): 0.4509/0.45086 is now the twice-reproduced number (T09 reviewer + T12 re-run, bean `okf-cli-1mxp` commit `81a0368`, ruling `e152b23`), 0.4519/0.451901 was the one-off outlier. recall@1/5/10 and zero_hit stated as bit-identical (verified); latency drifted too and both p50/max cells were updated for all three rows.

## R44 reconciliation — numbers as read from shipped_v2.json

```
$ python3 -c "
import json
with open('docs/okf-retrieval-architecture/eval/shipped_v2.json') as f:
    d = json.load(f)
for k in ('combined', 'queries_v2.json', 'queries_real.json'):
    r = d[k]
    print(k, {kk: r[kk] for kk in ('n','recall@1','recall@5','recall@10','mrr','zero_hit','latency_p50','latency_max')})
"
combined {'n': 48, 'recall@1': 0.2708333333333333, 'recall@5': 0.6875, 'recall@10': 0.8333333333333334, 'mrr': 0.4508597883597884, 'zero_hit': 0.16666666666666666, 'latency_p50': 0.6283180713653564, 'latency_max': 0.9368741512298584}
queries_v2.json {'n': 40, 'recall@1': 0.25, 'recall@5': 0.7, 'recall@10': 0.825, 'mrr': 0.43805555555555553, 'zero_hit': 0.175, 'latency_p50': 0.6250221729278564, 'latency_max': 0.6558291912078857}
queries_real.json {'n': 8, 'recall@1': 0.375, 'recall@5': 0.625, 'recall@10': 0.875, 'mrr': 0.5148809523809523, 'zero_hit': 0.125, 'latency_p50': 0.6382899284362793, 'latency_max': 0.6490530967712402}
```

recall@1/5/10 and zero_hit at 3dp are unchanged from the prior committed table (verified by direct comparison against the old text before editing); MRR combined moved 0.452→0.451 (0.4509 in prose); latency moved on all three rows (combined p50 0.621s→0.628s, max 0.766s→0.937s; queries_v2 p50 0.620s→0.625s, max 0.660s→0.656s; queries_real p50 0.624s→0.638s, max 0.667s→0.649s). All four gate criteria still pass on the new numbers.

## Test baseline (both runs)

```
$ python3 -m unittest discover -s cli -p "test_*.py" 2>&1 | grep -E "^Ran |^FAILED|^OK"
Ran 259 tests in 17.105s
FAILED (failures=19, errors=2)

$ env -u VOYAGE_API_KEY python3 -m unittest discover -s cli -p "test_*.py" 2>&1 | grep -E "^Ran |^FAILED|^OK"
Ran 259 tests in 13.756s
FAILED (failures=19, errors=2)
```

Both at exactly 19F/2E, matching the pre-existing baseline. Text-only edits, as expected did not move the count.

## Smoke

```
$ git -C ~/Obsidian/Knowledge-Catalogue status --short
(empty)
```
Foreign KC repo confirmed untouched throughout.

```
$ git status --short
(empty, after commit 7136c6c)
```

**Correction (T13 review, B01, supervisor):** the line above was true only for the tracked working tree at the moment `7136c6c` landed, and was written before this bean file's own close edit existed. It was then left standing as if it covered the whole repository state, which it did not — `git status --short` in fact showed `M .beans/okf-cli-jk0q--t13-documentation-sync.md` until the close commit below. This is the PF-5 pattern once more: a sentence whose function is to end review, asserting more than the command behind it had shown. Recording it rather than quietly overwriting it, because it is the third instance in this chain and the pattern is the lesson.

## Deviations from PLAN.md

1. **TASKS.md Txx-vs-PLAN.md-Task-N numbering collision (not asked about, resolved by inspection, not guessed).** PLAN.md Step 3 says "T10, T11, T12, T13 → 🟢 with the commit shas" using TASKS.md's own row codes (T10=producer fault-tolerance/LL-08, T11=Ollama batching/LL-09, T12=fusion rule, T13=FTS5 lexical path) — these are NOT the same axis as the bean titles "T08/T09/T10/T11/T12/T13 <name>" which cite PLAN.md's Task-N step numbers. I resolved this by reading each TASKS.md row's own description/Herkunft and matching it to the bean/commit that actually implemented that content, rather than assuming a 1:1 numeric match. Not escalated because the instruction was unambiguous once TASKS.md's row content was read against git history — no plan contradiction, just two pre-existing overlapping numbering schemes already present before this task.
2. **Commit sha granularity.** Where a PLAN-Task's work spanned several commits (code commit, test commit, review-fix commits, bean-close commit), I cited one representative commit sha per TASKS.md row (typically the core feature/fix commit) rather than the full commit chain, to keep TASKS.md readable. Full chains are recoverable via `git log --oneline` on the relevant bean IDs, which are already named in TASKS.md's Herkunft references and this bean's mapping above.
3. Everything else follows PLAN.md Task 13's steps and the prelude's four numbered items verbatim.

## Anything a later reader would still stumble over

- `docs/plans/okf-cli-dwcq-cli-okf-prime-optimieren/` is a real historical artifact under the now-corrected-as-wrong layout. It was never moved (per the plan's own contingency clause) and now has no home under the corrected `<topic-slug>/` convention — a future cleanup pass could relocate its content into a proper topic folder, but that's out of this task's scope.
- TASKS.md's Txx codes and PLAN.md's "Task N" step numbers are two different, overlapping numbering axes that happen to share the same "T<number>" shape across 13 items each — this collision predates this task and is not fixed here (fixing it would be a TASKS.md/PLAN.md renumbering, out of scope); noted so nobody assumes TASKS.md T13 == PLAN.md Task 13 (bean `okf-cli-jk0q` itself, this task) — it does not; PLAN.md Task 13 is the documentation-sync task, TASKS.md T13 is the FTS5-lexical-path convergence item.
