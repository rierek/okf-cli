---
# okf-cli-kc9x
title: T08 Conditional handover fusion
status: todo
type: task
priority: critical
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-26T05:02:09Z
parent: okf-cli-cskz
blocked_by:
    - okf-cli-8j7l
---

Plan: `docs/okf-retrieval-architecture/PLAN.md` → **Task 8**. Follow it step by step; it carries the literal code and tests.

This is the highest-leverage change in the whole feature. Today's fusion pins the keyword top-1 and interleaves everything else by score (`cli/okf-cli.py:863-879`), which neutralises the semantic arm: it fired on all 8 real queries and the hybrid stayed exactly on the lexical result (R36). In the regime comparison today's rule is the second worst of five (R43).

**Do not re-derive the threshold.** The measured rule is `top1 >= (1 + SEMANTIC_MARGIN_RATIO) * top2`, i.e. 1.5x (`eval/hybrid_eval.py:151`). The pre-plan code computed `(top1-top2)/top1 >= ratio`, i.e. 2x — a stricter bar that hands over less often than what was measured.

`SEMANTIC_NOISE_RATIO` is deleted, not left unused: it was a crutch for the blend rule, and conditional handover subsumes it.

### Requirement 1: Decide which arm owns the ranking

**Objective:** As an agent issuing either a literal or a paraphrase query, I want one arm to own the ranking per query, so that a noisy arm cannot dilute a working one.

#### Acceptance Criteria

1. THE fusion SHALL treat the lexical arm as owner WHEN it has exactly one hit, OR WHEN its top-1 score is at least 1.5 times the runner-up's.
2. IF the lexical arm is not the owner THEN THE semantic arm SHALL own the ranking and the lexical hits SHALL be appended behind it, never in front.
3. THE fusion SHALL emit each concept at most once, keeping the owning arm's entry and therefore its provenance.
4. THE fusion SHALL respect the requested limit.
5. THE CLI SHALL invoke the semantic arm only WHEN the lexical arm is not the owner OR the lexical list is too short to fill the limit, so that a confident query spends no network call.
6. WHEN the semantic arm owns the ranking THE CLI SHALL print one stderr note saying so.

#### Success Criteria

- SC-01: 100 vs 40 → lexical owns, order `a, b, c`; 100 vs 95 → semantic owns, order `c, a, b`.
- SC-02: 100 vs 60 (inside the 1.5x-2x band) → lexical owns. This pins the measured rule against the pre-plan arithmetic; 100 vs 68 → hands over.
- SC-03: a single lexical hit is treated as confident; an empty lexical list hands over.
- SC-04: a concept found by both arms appears once, with the owning arm's provenance.
- SC-05: `okf.SEMANTIC_NOISE_RATIO` no longer exists.
- SC-06: on the live catalogue `find "mockup tailscale"` returns `dev-wiki/testsystem-vite-tailscale/serve-excalidraw-drafts` with `provenance: semantic` — the query from R12 that started the investigation and returns nothing today.
- SC-07: `python3 -m unittest discover -s cli -p 'test_*.py'` stays at exactly 19 failures / 2 errors.

_Requirements: PLAN.md Task 8 · DECISIONS D12, D14 · TASKS.md T12 · REFERENCES R12, R36, R43_

## Steps

- [ ] Write the failing `FuseConditional` and `NoiseRatioIsGone` tests, including both band tests
- [ ] Run them, confirm they fail for the stated reason
- [ ] Rewrite `_keyword_top1_is_confident` to the measured comparison; delete `SEMANTIC_NOISE_RATIO`
- [ ] Add `fuse_conditional(lexical_hits, semantic_hits, limit) -> (hits, lexical_owned)`
- [ ] Rewire `cmd_find`'s gate and fusion blocks
- [ ] Tests pass; suite still 19F/2E. Any pre-existing test whose score pair sits in the 1.5x-2x band flips — update it to the measured rule, or change the pair if it was asserting something else. Never change `SEMANTIC_MARGIN_RATIO`
- [ ] Verify SC-06 on the live catalogue. If it fails, STOP and report — do not tune the margin to make it pass
- [ ] Commit `feat(cli): fuse arms by conditional handover`

## Recommended Skills

- `superpowers:test-driven-development`



## HARD STOP 2026-07-26 (PO/plan author, realization kickoff)

Verbatim (PO): "Wenn in okf-cli-kc9x die Live-Gegenprobe find \"mockup tailscale\" das
Zielkonzept NICHT liefert: stoppen und melden, NIEMALS SEMANTIC_MARGIN_RATIO verstellen,
um die Zahl zu bewegen."

Interpretation: SEMANTIC_MARGIN_RATIO = 1.5 is a MEASURED constant
(eval/hybrid_eval.py:151), not a tuning knob. If the live counter-probe
`okf-cli find "mockup tailscale"` does not return the target concept, that is a finding,
not a calibration task. Stop, report to the supervisor with the observed ranking, and wait.
Touching the ratio to make the probe pass is an explicit protocol violation.
