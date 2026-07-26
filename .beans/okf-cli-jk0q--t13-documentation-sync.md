---
# okf-cli-jk0q
title: T13 Documentation sync
status: in-progress
type: task
priority: normal
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-26T09:48:27Z
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
