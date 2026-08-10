---
# OKFT-3rb6
title: One ranking scale in find output
status: completed
type: task
priority: normal
created_at: 2026-08-10T12:59:09Z
updated_at: 2026-08-10T14:37:44Z
parent: OKFT-hkze
blocked_by:
    - OKFT-wvgb
---

## Objective (User Story)
As an agent skimming `find` results, I want a single comparable ranking number per line, so that the numeric order of the list matches its actual order.

## Evidence (MODUS-B-REPORT I02)
A mixed list prints `score: cosine 0.63` next to `score: 100/100`, with the numerically larger BM25 values BELOW the semantic hits. Three of five agents (R1, R2, R5) named this independently as the hardest part of reading the output.

## EARS Acceptance
- THE result list SHALL carry one comparable ranking value per line on a single scale.
- THE per-arm raw value SHALL remain available in the score breakdown, not in the headline number.

## Success Criteria
- SC-001: no result list mixes two scales; asserted by a test over a mixed-arm query.
- SC-002: `docs/okf-retrieval-architecture/eval/remeasure.py` still parses results, and the shipped metrics are re-measured to prove the change is presentation-only (no rank movement).

## Note
Blocked by OKFT-wvgb in practice — both touch the same emission site in `cmd_find`; land the provenance line first, then the scale.


## Done 2026-08-10 (commit b50a7b9)
D01 (PO-set this session): the headline number in every `find` result line is now `rank: N`, the 1-based position in the delivered list — the one scale comparable across a mixed-arm result set, because it IS the list order, not a claim of cross-arm score comparability (D12 stays: handover, never blend). The arm's own raw value moved entirely into `--breakdown`: `score: a/b` for a lexical hit, `score: cosine X.XX` for a semantic one, printed right after `provenance:`, before `contrib:`. `provenance:` is unchanged on every line.

Emission site: `cmd_find` in `cli/okf-cli.py:1566-1596`. Docs updated to match: `_FIND_SCALES_COMPACT` (prime --compact usage text, `cli/okf-cli.py:1739-1749`), `_FIND_EPILOG` (find --help epilog, `cli/okf-cli.py:4559-4579`), and the `okf_prime` MCP docstring (`mcp/okf_mcp.py`) — the only one of the three that literally named "score scales"; `okf_find`'s docstring made no false claim about a score column, so it was left as-is.

TDD: SC-001 RED-before-GREEN test `SemanticBackstop.test_mixed_arm_query_uses_one_rank_scale` — RED failed on `self.assertNotIn("score:", out)` (the pre-change default output still printed `score: cosine 1.00` / `score: 1/6` next to each other). Proof the query is genuinely mixed-arm: b/far is semantic-only, b/noise and b/near are lexical substring hits, all three land in one result set (`provenance: lexical` and `provenance: semantic` both present, verified). GREEN after the emission-site change: `rank: 1`/`rank: 2`/`rank: 3`, no `score:`/`cosine` substring anywhere in the default output.

Gegenmutation 1: replaced `print("rank: {}".format(i))` with a constant `print("rank: 1")` — caught by `test_mixed_arm_query_uses_one_rank_scale` (expected `["rank: 1","rank: 2","rank: 3"]`, got three `"rank: 1"`). Reverted, GREEN confirmed again before proceeding.

Gegenmutation 2: changed `if breakdown:` to `if True:` around the score/contrib block — caught by three tests at once (`test_default_output_unchanged_without_breakdown`, `test_mixed_arm_query_uses_one_rank_scale`, `test_semantic_hit_score_line_uses_its_own_scale_not_a_fraction`), each failing on an unexpected `score:`/`contrib:` substring in the default (non-breakdown) output. Reverted, GREEN confirmed.

Production-code fallout beyond the emission site and docs: `cli/eval/runner.py`'s `_score_find_row` parses `find`'s own `score:` line to compute the `mean_score_ratio` metric — moving that line behind `--breakdown` broke it (KeyError on `h["max_score"]`, 8 test errors in `test_eval_runner.py`). Fixed by passing `--breakdown` through in that one call site; `docs/okf-retrieval-architecture/eval/remeasure.py` needed no change, it only ever parsed `path:` lines.

Also updated in `cli/test_okf_cli.py`: `FindScoreBreakdown.test_default_output_unchanged_without_breakdown` (pinned block now shows `rank: 1`, not `score: 5/6`), `FindScoreBreakdown.test_breakdown_lists_contributing_fields` (added assertion that `score: 5/6` reappears under `--breakdown`), `SemanticBackstop.test_semantic_hit_score_line_uses_its_own_scale_not_a_fraction` (rewritten to assert absence of `score:`/`cosine` in default output and presence under `--breakdown`), `SemanticBackstop.test_ambiguous_lexical_hands_over_but_keeps_its_hits_appended_behind` (now calls `--breakdown` and reads the score line at the new fixed offset from `path:`), `FindDegradesWithoutIndex.test_find_without_index_still_prints_a_hit` (asserts `rank: 1` instead of `score: 3/6`). No other repo location claims the old score-column shape as shipped behavior (grepped `docs/`, `cli/`, `mcp/`) — the remaining hits are historical (beans, LESSONS-LEARNED, completed PLAN.md/SSTD.md entries), left untouched by design.

SC-002 (`docs/okf-retrieval-architecture/eval/remeasure.py`, `--root ~/Obsidian/Knowledge-Catalogue`, `--queries queries_v2.json queries_real.json`, combined n=48): before — recall@1 0.250, recall@5 0.646, recall@10 0.812, mrr 0.4323, zero_hit 0.188; after (identical rounding for recall@1/5/10/zero_hit) — recall@1 0.250, recall@5 0.646, recall@10 0.812, mrr 0.4318, zero_hit 0.188. The 0.0005 mrr delta traces to exactly one query, `"Kollegen Mannschaft Abgrenzung Kriterien"`, whose target sits outside the printed top-3 (rank 8 before, 9 after — no change to what the user sees at recall@5). Investigated, not glossed over: running the identical POST-change code twice in a row reproduces the exact same 8/9 flip and the exact same mrr value the before-run produced (0.41194444444444445 vs 0.4115972222222222 on `queries_v2.json` alone) — this is pre-existing run-to-run tie-break noise at a rank position not visible in the default output, independent of this change, not a regression it introduced. Catalogue verified unchanged after both runs: `git -C ~/Obsidian/Knowledge-Catalogue status --porcelain` empty.

`just test`: 650 tests, OK (was 649; +1 for the new SC-001 test).
