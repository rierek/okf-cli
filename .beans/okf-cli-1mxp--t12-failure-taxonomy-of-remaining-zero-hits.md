---
# okf-cli-1mxp
title: T12 Failure taxonomy of remaining zero-hits
status: in-progress
type: task
priority: normal
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-26T09:17:39Z
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


## Prelude from the T10/T11 reviews (2026-07-26, supervisor)

T10 (`okf-cli-snxj`) and T11 (`okf-cli-ftri`) are closed and approved. Six things carry into the taxonomy work:

1. **Baseline moved.** The suite is now **259 tests**, still exactly **19 failures / 2 errors** — all pre-existing in the crosslink suites.
2. **The failure set is flag-independent.** Expansion changed zero outcomes: `shipped_expand.json` is identical to `shipped_v2.json` on every per-file metric. Build the taxonomy from either file; `--expand-tags` does not move a single one of the 8 residual zero-hits.
3. **Per-query diagnostics were not persisted.** T11 measured top-tag cosines per query in-process and did not write them out. If the taxonomy wants a synonymy-closeness split, those numbers must be regenerated.
4. **One taxonomy class is already established and must not be re-derived as an open question.** For the R12 family, tag-vector expansion cannot close the gap *in principle* — not because of the floor, not because of granularity, but because the terms are not neighbours in tag-slug space (tags are embedded slug-only, R06). Concept embedding, which sees the running text, is what solves that class. Measured evidence: `"mockup tailscale"` → `tailscale` at 0.595 (a word already in the query, so zero information gain); `"mockup"` → `mockups` at 0.6693 (morphological variant, not a synonym); `excalidraw` at rank 105/650 for `"mockup"`, absent from any plausible neighbourhood. See Q05/Q06 in QUESTIONS.md.
5. **Do not conflate zero-hits with squeeze-outs.** `okf-cli-uumj` tracks a different failure: there the target IS a hit and is merely truncated out of the result window under handover. Those cases are not in the zero-hit set and belong to a separate taxonomy branch, if they are mentioned at all. Affected concepts recorded there: tailscale-subnet-routing, data-ui-convention, replikations-playbook, ai-operating-system, immich.
6. **A bound on the suggestion feature exists.** `_zero_hit_suggestions()` reaches typos and synonyms ONLY; truncated or partially typed terms never arrive there, because both lexical procedures catch any prefix first by construction.

Two standing quality rules from this chain:

- **PF-5:** a sentence whose function is to end review is the sentence that gets checked. Claims of the form "verified" / "behaviour-identical" / "reverted byte-identically" must name the command and quote its observed output, or not be written.
- **Prove the mechanism fired before comparing outputs.** A silently swallowed flag produces bit-identical output to an honest null result — from the artefact alone the two are indistinguishable. Count the calls first (a counting stub), then compare.
