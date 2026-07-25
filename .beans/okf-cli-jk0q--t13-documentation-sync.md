---
# okf-cli-jk0q
title: T13 Documentation sync
status: todo
type: task
priority: normal
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-25T23:32:25Z
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
