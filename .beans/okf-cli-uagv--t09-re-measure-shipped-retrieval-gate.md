---
# okf-cli-uagv
title: T09 Re-measure shipped retrieval + gate
status: todo
type: task
priority: high
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-25T23:32:25Z
parent: okf-cli-cskz
blocked_by:
    - okf-cli-kc9x
---

Plan: `docs/okf-retrieval-architecture/PLAN.md` → **Task 9**. Follow it step by step; it carries the literal code.

This is the proof step. A new `remeasure.py` runs the **shipped** CLI as a subprocess, so what is measured is what ships — `hybrid_eval.py` re-implements the arms and measuring it again would measure the eval script.

The fixture gate needs care: `golden.json` targets `_okfeval-*` files that `cli/eval/fixtures.py` seeds into the **live** catalogue and that are absent between runs. Without seeding, every literal row misses and `gate.py:69-79` reports a false regression. And the seeded fixtures are brand-new concepts with no `concept_emb` rows — S3 exists precisely to be rescued semantically, so they must be embedded between seed and scoring.

### Requirement 1: Measure the shipped retrieval

**Objective:** As the PO, I want the shipped CLI measured against the unbiased query set, so that the architecture change is demonstrated rather than asserted.

#### Acceptance Criteria

1. THE re-measurement SHALL invoke the shipped `okf-cli find` as a subprocess and SHALL NOT re-implement any ranking arm.
2. THE re-measurement SHALL report recall@1/5/10, MRR, zero-hit rate and latency, per query file and combined.
3. THE eval runner SHALL build the lexical index before scoring, so that it measures the index-backed arm rather than the degradation path.
4. THE gate run SHALL seed the golden fixtures, embed them, score, gate, tear them down, remove the dangling vectors and rebuild the index.
5. THE live catalogue SHALL end the task with no `_okfeval-*` file and no `_okfeval-%` embedding row.

#### Success Criteria

- SC-01: combined zero-hit ≤ 0.30 (pre-plan: 0.979).
- SC-02: combined MRR ≥ 0.35 (pre-plan: 0.021).
- SC-03: `queries_real.json` zero-hit ≤ 0.25 (pre-plan: 0.875).
- SC-04: combined p50 latency ≤ 2.0 s.
- SC-05: `gate.py` prints `GATE: PASS` against the frozen `baseline-f0714b2.json`.
- SC-06: post-teardown, both verification counts are 0.
- SC-07: R44 and R45 in `REFERENCES.md` carry the actual numbers — a reference containing a placeholder does not count as written.

**If a retrieval criterion fails:** stop and report with the JSON. Do not tune `SEMANTIC_MARGIN_RATIO` to move a number.

**If only latency fails:** that is a known, bounded risk — `_load_concept_vectors` unpacks 2437 x 1024 floats per query in pure Python. Apply the cheapest stdlib remedy that clears the bar, in this order: `array.array('f')` instead of lists; `sum(map(operator.mul, a, b))` for the dot product; L2-normalised vectors stored at produce time. Never add a dependency.

_Requirements: PLAN.md Task 9 · REFERENCES R42, R43 · cli/eval/gate.py:56-81_

## Steps

- [ ] Write `docs/okf-retrieval-architecture/eval/remeasure.py` (rows use the keys `query` / `target` / `source` — verified)
- [ ] Run it against the live catalogue, write `shipped_v2.json`, check SC-01..SC-04
- [ ] Add the index build to `cli/eval/runner.py:run()`
- [ ] Run the bracketed gate sequence (seed, embed, score, gate, teardown, cleanup, rebuild) and verify SC-06
- [ ] Record R44/R45 in `REFERENCES.md` with the real numbers
- [ ] Commit `test(eval): re-measure shipped retrieval`

## Recommended Skills

- `superpowers:verification-before-completion`
