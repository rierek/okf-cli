---
# OKFT-8l96
title: Lexical margin condition effectively never fires
status: draft
type: bug
priority: high
created_at: 2026-08-10T14:21:48Z
updated_at: 2026-08-10T14:21:48Z
parent: OKFT-hkze
---

## Objective (User Story)
As the owner of the retrieval mechanism, I want the conditional-handover rule to be calibrated against the real corpus, so that the shipped hybrid is a hybrid and not the semantic arm wearing a fusion rule.

## Evidence (docs/okf-revision/B02-DUPLICATE-MARGIN.md, B01/Q01)
Measured on the live catalogue while investigating `OKFT-hjqp`: over all 48 canonical eval queries the lexical arm owns the ranking exactly ONCE, and only because that query has a single hit (`len(hits) == 1`). The smallest `top2` ever observed across every multi-hit query is 69; `_keyword_top1_is_confident` requires `top2 <= 66` on the 0..100 scale. The margin branch therefore never fires on this corpus.

The obvious suspicion — a scale mismatch between raw BM25 scores in the eval harness and the 0..100 normalised scores in production — was checked and rejected: the test is a pure ratio test and thus scale-invariant.

## Open question (Q01)
If the condition never fired in `eval/hybrid_eval.py` either, then the measured R43 quality of 0.437 was in fact "semantic arm alone", and `SEMANTIC_MARGIN_RATIO = 0.5` was never calibrated as a compromise between the arms. Verify that against the harness before changing the constant — the constant may be wrong, or the measurement it was derived from may have been measuring something else.

## EARS Acceptance
- THE claim SHALL be verified inside `eval/hybrid_eval.py` itself, not only against the shipped CLI, before any constant is touched.
- WHERE the constant is re-calibrated, THE change SHALL be measured as a delta against the recorded baseline on the canonical query set, per the P12 gate discipline.

## Success Criteria
- SC-001: written verdict on whether the R43 measurement was effectively single-arm.
- SC-002: any change to `SEMANTIC_MARGIN_RATIO` carries a before/after metric table on the canonical 48-query set.

## Note
Do not "fix" this by loosening the threshold until SC-001 is answered. A rule that never fires may be a defect or may be the honest outcome of a corpus where BM25 rarely separates its top hit; those need different answers.
