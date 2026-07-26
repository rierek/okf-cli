---
# okf-cli-kc9x
title: T08 Conditional handover fusion
status: in-progress
type: task
priority: critical
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-26T07:15:15Z
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


## Inherited obligation from T07 (okf-cli-8j7l) — remove the compatibility shim

T07 changed `semantic_ranking()` / `_semantic_hit_dicts()` signatures (dropping
`exclude_paths` / `max_score`) while this task owns the `cmd_find` call site. To keep the
tree green in between, T07 applied a **minimal arity-compatible shim** in `cmd_find` that
filters `exclude` locally after the call. It implements no conditional-handover logic.

**This task MUST delete that shim** when it rewires `cmd_find`. Under conditional handover
deduplication happens in `fuse_conditional`, so post-call exclusion is not merely redundant —
it would remove semantic hits before the fusion can decide which arm owns them, silently
re-introducing the defect D12 exists to fix.

- [ ] Locate the shim in `cmd_find` (marked in T07's Deviations/ERRATA section of okf-cli-8j7l)
- [ ] Delete it; `fuse_conditional` handles dedup
- [ ] Confirm no caller passes `exclude_paths` any more

### Additional success criterion

- SC-SHIM: the T07 compatibility shim no longer exists in `cmd_find`; `grep` for it returns
  nothing, and no code path filters semantic hits before `fuse_conditional` runs.



## PRELUDE 2026-07-26 — two rulings from the plan author, read before implementing

**(1) SC-06 says "appears", NOT "rank 1". Do not optimise toward rank 1.**

Independently re-run by the plan author against the live catalogue, matching T07's numbers
exactly: the R12 target `dev-wiki/testsystem-vite-tailscale/serve-excalidraw-drafts` comes back
at **rank 3, cosine 0.5484**; a second real query "service home-lab photos" returns
`home-lab-wiki/services/immich` at rank 1.

The five hits span **0.5569 down to 0.5407** — the top two are generic tailscale concepts. That
narrow band is **R34 in the field: cosine is a RANK signal, not a confidence signal.** SC-06 is
worded "appears" precisely because of it. If your smoke run has the target anywhere in the
result set, the criterion is met — rank 3 included. Resist tuning toward rank 1.

This sharpens rather than softens the standing HARD STOP recorded earlier in this bean: if
`find "mockup tailscale"` does NOT return the target at all, stop and report — and never move
`SEMANTIC_MARGIN_RATIO` to make a number look better. The ratio is measured
(`eval/hybrid_eval.py:151`), not a tuning knob.

**(2) SC-SHIM is binding — the `cmd_find` shim MUST be deleted here.**

T07 (`91e2604`) added a minimal arity-compatible shim in `cmd_find` as a deliberate bridge
across the T07/T08 signature change. Removing it is your duty, criterion `SC-SHIM` (pinned in
commit `b7b236d`).

Reason, so it is not treated as cosmetic: under conditional handover the dedup happens INSIDE
`fuse_conditional`. A post-hoc exclude-filter would strip semantic hits BEFORE the fusion can
decide which arm owns the ranking — reinstating exactly the defect D12 exists to prevent
(normalised BM25 at ranks 2-10 sits near 0.9 while a good cosine sits near 0.6, R36, so the
lexical arm ranks good semantic hits away).

**Verified ground entering T08:** `semantic_ranking()` and `_semantic_hit_dicts()` are on their
final signatures — no further renaming needed. Live vectors are proven reachable for the SC-06
counter-probe (`concept_emb`, 2443/2443, voyage-3-large, dim 1024). `VOYAGE_API_KEY` is live
and functional; rotation is scheduled after T09, so do not print it and abort on any 401/403
instead of retrying. Baseline entering T08: 233 tests, exactly 19 failures / 2 errors.



## PRELUDE 2026-07-26 — carried over from the T07 re-review

**Awareness item (latent, do NOT fix here — filed as `okf-cli-3520`).** `concept_emb` can hold
more than one row per concept path: the `PRIMARY KEY` is `key` (content+path hash), not
`path`, and the producer never deletes the superseded row when a concept's content changes.
Anything that sizes a candidate window by path count is then undersized — the same failure
class as T07's blocker B01, different trigger. `fuse_conditional` reads the same vector list
and inherits the assumption.

Measured right now: 2443 rows, 2443 distinct paths, i.e. **0 duplicates** — the table was
filled in one pass by T03, so nothing manifests today. Do not build a workaround into the
fusion; just do not ASSUME one-row-per-path in a way that would silently drop candidates. If
your design depends on that assumption, say so explicitly in the bean so `okf-cli-3520` knows
what it has to protect.

**T07 final state you inherit:** commits `91e2604` + `be08f8c`, APPROVED after one fix round.
The `cmd_find` shim is now CORRECT (it over-fetches `limit + len(exclude)`, filters, then
slices — verified equivalent to the pre-T07 contract on 7 of 8 constructed edge cases, the 8th
being the duplicate-row case above). It is still your duty to DELETE it (`SC-SHIM`) — a
correct shim is still the wrong place for dedup under conditional handover.
Baseline entering T08: **234 tests, exactly 19 failures / 2 errors**.
