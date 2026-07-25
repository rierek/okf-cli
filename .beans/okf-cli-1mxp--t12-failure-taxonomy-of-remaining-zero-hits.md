---
# okf-cli-1mxp
title: T12 Failure taxonomy of remaining zero-hits
status: todo
type: task
priority: normal
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-25T23:32:25Z
parent: okf-cli-cskz
blocked_by:
    - okf-cli-uagv
---

Plan: `docs/okf-retrieval-architecture/PLAN.md` → **Task 12**. Follow it step by step.

Analysis, not code. The point is to separate what retrieval design can still fix from what it cannot — a catalogue gap is a writing problem, and no ranking rule heals it.

### Requirement 1: Classify the remaining failures

**Objective:** As the PO deciding where the next lever is, I want every remaining retrieval failure classified, so that effort goes to the class that actually dominates.

#### Acceptance Criteria

1. THE re-measurement SHALL record, per query, the expected path, the achieved rank and the top-3 returned paths, because a failure cannot be classified without what was returned instead.
2. THE taxonomy SHALL assign every query whose target did not reach rank 10 exactly one class from: catalogue-gap, synonymy, ranking, wrong-target.
3. THE taxonomy document SHALL name the measurement it rests on — file, git sha and date.
4. IF catalogue-gap dominates THEN THE document SHALL say so explicitly, because that moves the next lever from retrieval to authoring.

#### Success Criteria

- SC-01: `eval/taxonomy.md` exists with one row per failing query (`query | expected_path | rank | class | note`) and a per-class count summary.
- SC-02: every failing query carries exactly one class — no blanks, no double assignment.
- SC-03: Q03 moves from partially-quantified to resolved with the class split; Q10 resolves with the catalogue-gap count and share.

_Requirements: PLAN.md Task 12 · QUESTIONS Q03, Q10 · TASKS.md T03 · REFERENCES R12_

## Steps

- [ ] Extend `remeasure.py` to emit per-row detail under a `rows` key; re-run it
- [ ] For each failing query, read the expected concept and the top-3 returned concepts, assign one class
- [ ] Write `eval/taxonomy.md` (header naming file + sha + date, the table, the counts — no prose beyond that)
- [ ] Resolve Q03 and Q10 in `QUESTIONS.md`; if catalogue-gap dominates, point it at the follow-up bean `okf-cli-iw0d`
- [ ] Commit `docs(eval): failure taxonomy, answer Q03/Q10`

## Recommended Skills

- none (analysis)
