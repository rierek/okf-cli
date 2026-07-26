---
# okf-cli-kc9x
title: T08 Conditional handover fusion
status: completed
type: task
priority: critical
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-26T07:32:06Z
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

## Summary

Implemented conditional handover fusion (D12/T12) per PLAN.md Task 8, literally:
- `_keyword_top1_is_confident(hits)` rewritten to the measured rule `top1 >= (1 + SEMANTIC_MARGIN_RATIO) * top2` (i.e. 1.5x), handling `len(hits)==0` and `len(hits)==1` itself.
- `SEMANTIC_NOISE_RATIO` deleted (constant + all runtime references); a doc comment records why, no runtime trace remains.
- `fuse_conditional(lexical_hits, semantic_hits, limit) -> (hits, lexical_owned)` added: the owning arm's list first in its own order, the other arm's remainder appended behind, deduplicated by path keeping the owner's entry, truncated to `limit`. Ownership decided from intra-lexical margin only — never a cross-arm score comparison (bean PRELUDE property, preserved).
- `cmd_find`'s old gate+pin+interleave block replaced with the plan's literal gate (`fuse_conditional` called unconditionally; semantic runs when lexical is not confidently owning OR the confident list is shorter than `--limit`) plus the "semantic arm owns this ranking" stderr note.
- T07's `cmd_find` compatibility shim (post-hoc `exclude`-filter with over-fetch backfill) is deleted — SC-SHIM. `grep -n "exclude_paths\|exclude ="` on `cli/okf-cli.py` now returns only a docstring mention (`semantic_ranking` no longer takes `exclude_paths`), no functional code path.

## Test-Output

RED (Step 1/2, `env -u VOYAGE_API_KEY python3 -m unittest cli.test_okf_cli.FuseConditional cli.test_okf_cli.NoiseRatioIsGone -v`), before any implementation, quoted verbatim (tail):

```
ERROR: test_margin_band_matches_the_measured_rule (cli.test_okf_cli.FuseConditional.test_margin_band_matches_the_measured_rule)
The measured rule is top1 >= 1.5*top2 (eval/hybrid_eval.py:151).
----------------------------------------------------------------------
Traceback (most recent call last):
  File ".../cli/test_okf_cli.py", line 1543, in test_margin_band_matches_the_measured_rule
    out, lex_owned = okf.fuse_conditional(lex, sem, 10)
AttributeError: module 'okf_cli' has no attribute 'fuse_conditional'

======================================================================
FAIL: test_constant_removed (cli.test_okf_cli.NoiseRatioIsGone.test_constant_removed)
----------------------------------------------------------------------
Traceback (most recent call last):
  File ".../cli/test_okf_cli.py", line 1559, in test_constant_removed
    self.assertFalse(hasattr(okf, "SEMANTIC_NOISE_RATIO"))
AssertionError: True is not false

----------------------------------------------------------------------
Ran 10 tests in 0.002s

FAILED (failures=1, errors=9)
```

GREEN, commit-point full suite (`env -u VOYAGE_API_KEY python3 -m unittest discover -s cli -p 'test_*.py'`), executed AFTER implementation and AFTER the mutation-probe revert below:

```
Ran 243 tests in 16.052s
FAILED (failures=19, errors=2)
```

The 19F/2E is byte-identical in test-name terms to the pre-T08 baseline (`git stash` diff-checked): same 19 FAIL + 2 ERROR, all in the crosslink suites (`CheckCommand`, `FixCrosslinksCommand`, `RefMatrix`, `RenameConcept`, `ResolveCrosslinkTarget`, `RewriteCrosslinksInBody`) — none of them touched by this task. Count moved 234 -> 243 tests (+10 new `FuseConditional`/`NoiseRatioIsGone` tests, -1 removed `test_shim_backfills_when_excluded_paths_rank_inside_the_window`, net +9).

Mutation probe (LL-01-style, on the ownership rule itself): edited `_keyword_top1_is_confident`'s return line from `top1 >= (1 + SEMANTIC_MARGIN_RATIO) * top2` to `top1 >= 2 * top2` (the pre-plan arithmetic), ran `FuseConditional` alone:

```
test_margin_band_matches_the_measured_rule ... FAIL
  AssertionError: False is not true
Ran 9 tests in 0.001s
FAILED (failures=1)
```

The one test built specifically to pin the 1.5x/2x disagreement band caught the mutation; the other 8 (which don't sit in that band) stayed green, as expected. Reverted the single line via `Edit` back to the literal string `return top1 >= (1 + SEMANTIC_MARGIN_RATIO) * top2`; `git diff cli/okf-cli.py` after the revert shows that exact line as the only occurrence of `top1 >=`, i.e. no residual mutation. Re-ran the full commit-point suite: 19F/2E again (quoted above).

## Smoke

Live counter-probe (SC-06), `VOYAGE_API_KEY` presence-checked only (`[ -n "$VOYAGE_API_KEY" ] && echo set`, printed `set`, never the value), run as `python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue find "mockup tailscale" --limit 5`, verbatim:

```
note: semantic arm owns this ranking (lexical top-1 lacked a clear margin)
------
score: 56/100
title: Tailscale
type: Service
path: home-lab-wiki/services/tailscale
...
provenance: semantic (cosine=0.56)
------
score: 56/100
title: Tailscale — Claude-Kontext
type: Reference
path: home-lab-wiki/context/services/tailscale
...
provenance: semantic (cosine=0.56)
------
score: 55/100
title: Excalidraw-Entwürfe bereitstellen (PNG + Direkt-Öffnen)
type: SOP
path: dev-wiki/testsystem-vite-tailscale/serve-excalidraw-drafts
description: Ein gerendertes Excalidraw-Diagramm dem Nutzer auf einem anderen Tailnet-Gerät zeigen — als PNG-Vorschau UND als editierbare .excalidraw-Datei, über tailscale serve.
...
provenance: semantic (cosine=0.55)
------
score: 54/100
title: Tailscale einrichten
...
------
score: 54/100
title: Portal Remote Review via tailscale serve
...
------
```

Target `dev-wiki/testsystem-vite-tailscale/serve-excalidraw-drafts` appears at rank 3, cosine 0.55, `provenance: semantic` — matches the PRELUDE's independently re-run figure (rank 3, cosine 0.5484) within rounding. SC-06 is "appears", not "rank 1" — met, no tuning applied to reach this. `~/Obsidian/Knowledge-Catalogue` left clean: `.fts/fts.sqlite` present and untouched after the manual reproduction runs below (verified `git status --short` empty in that repo both before and after this session; no commits made there).

## Deviations/ERRATA

1. **Three pre-existing `cli/test_okf_cli.py` tests updated, one deleted — all in-scope, all because the pre-T08 fixtures/assertions encode invariants D12 explicitly removes.** Per plan Step 5 ("check whether it asserts firing behaviour... or a different invariant"):
   - `test_near_threshold_literal_top1_survives_unrelated_semantic` renamed to `test_confident_literal_top1_survives_unrelated_semantic_scale` and its rival fixture's body edited so the lexical top-1 is CONFIDENT under the new 1.5x rule (was deliberately ambiguous under the old rule, relying on the now-deleted absolute pin to still win). The underlying property it protects — a lexical top-1 must never be reordered by an unrelated semantic candidate's inflated raw score, because fusion never compares cross-arm scores — still holds and is still asserted.
   - `test_find_without_index_prints_exactly_one_stderr_note` renamed to `test_find_without_index_prints_exactly_one_note_per_degraded_arm`, now expects 2 stderr lines instead of 1. Cause: SC-05 requires the semantic arm to fire whenever a confident lexical list is shorter than `--limit`, even a single-hit list — the old gate never invoked semantic in that case, so only the lexical-degradation note fired. Both arms are degraded in this fixture (no `.fts`, no `.tagvec`), so two independent PF-4 notes are now correct, not a violation of it (PF-4 is per-branch, not per-command).
   - `test_shim_backfills_when_excluded_paths_rank_inside_the_window` **deleted** (not adapted): it pinned the T07 shim's over-fetch-by-`len(exclude)` backfill guarantee, which SC-SHIM requires removing outright. `fuse_conditional` does not pre-filter or over-fetch by design (D12) — the scenario's premise (a starved semantic window) does not exist in the new architecture, and its score pair (5 vs 3) is additionally CONFIDENT under the measured rule, unlike under the pre-plan rule it was tuned against. No replacement test — the invariant is gone by design, not narrowed to something else.

2. **Ambient `VOYAGE_API_KEY` turns one unrelated integration test into a live-network test — not a T08 defect, but a live finding for T09.** `cli/test_eval_runner.py::RunnerAgainstRealCatalogueTest.test_runner_scores_literal_s1_top1` fails (`row["rank"] == inf`) when `VOYAGE_API_KEY` is exported in the shell, passes when it is not. Root cause, verified by direct reproduction: the S1/S4 golden fixtures (`cli/eval/fixtures.py`) are lexically near-identical by construction (score 5 vs 4, ratio 1.25) — genuinely ambiguous under both the old 2x rule AND the new 1.5x rule. Under the OLD architecture this didn't matter (the absolute pin always kept the lexical top-1 at rank 1 regardless of ambiguity). Under conditional handover, an ambiguous lexical arm hands the ranking to semantic; the eval runner's `FIND_LIMIT=50` then gets filled entirely by 50 real, unrelated `concept_emb` candidates (the fresh fixture is never embedded), squeezing the correct lexical hit out of the window entirely. This is exactly the kind of trade-off D12 accepts at the architecture level (milestone success measure tolerates up to 25% real-query zero-hit), but it makes an integration test's outcome depend on ambient environment state, which contradicts "tests network-free." I did **not** touch `cli/eval/fixtures.py`, `cli/eval/runner.py`, or `cli/test_eval_runner.py` to fix this — those files are outside Task 8's stated scope (`cli/okf-cli.py` + `cli/test_okf_cli.py` only), and Task 9's own file list already includes `cli/eval/runner.py:190-217 "(build the index before scoring)"`, which is plausibly the intended remedy (real FTS BM25 scoring, not the flat substring scan, may resolve the S1/S4 margin differently). All commit-point suite runs in this bean were executed with `env -u VOYAGE_API_KEY` for this reason; SC-07's 19F/2E is verified network-free.

3. **No deviation from the plan's literal code.** `_keyword_top1_is_confident` and `fuse_conditional` are copied verbatim from PLAN.md Task 8 Step 3; the `cmd_find` gate/fusion block is copied verbatim from Step 4. `SEMANTIC_MARGIN_RATIO` was never touched (HARD STOP respected) except transiently during the mutation probe, reverted within the same tool call sequence before any commit.

## Notes for T09 (okf-cli-uagv)

- Baseline entering T09: **243 tests, exactly 19 failures / 2 errors**, verified with `VOYAGE_API_KEY` unset. All 19F/2E are pre-existing crosslink-suite failures, unrelated to retrieval.
- Deviation #2 above is directly relevant to T09's `cli/eval/runner.py` changes ("build the index before scoring"): consider whether the re-measurement path should also pin/unset `VOYAGE_API_KEY` for determinism, or explicitly accept that a live key changes which arm owns ambiguous fixture queries. Building the FTS index before scoring may independently change the S1/S4 margin (BM25 vs. flat substring scoring) — worth checking whether `test_runner_scores_literal_s1_top1` passes cleanly once T09's index-build lands, with the key set.
- `fuse_conditional`'s dedup performance is O(n) over both arms combined per query — no changes needed for T09's re-measurement to see accurate numbers, since Task 9 measures the shipped CLI via subprocess (`_run_cli`), not a re-implementation.
- Live smoke confirms the "mockup tailscale" / R12 query surfaces the target at rank 3 (cosine 0.55) exactly as the PRELUDE predicted — T09's re-measurement should see this reflected in the aggregate MRR/zero-hit numbers for the real-query set.
- `okf-cli-3520` (latent `concept_emb` duplicate-row awareness item, filed by T07) is unaffected by this task — `fuse_conditional` dedups by `path` at the hit-dict level, after `_semantic_hit_dicts` has already flattened `concept_emb` rows; it inherits the same one-row-per-path assumption `semantic_ranking`/`_load_concept_vectors` already carry, nothing new introduced here.
