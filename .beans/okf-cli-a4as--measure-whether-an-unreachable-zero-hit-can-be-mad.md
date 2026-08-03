---
# okf-cli-a4as
title: Measure whether an unreachable zero-hit can be made reachable
status: completed
type: task
priority: high
created_at: 2026-07-26T13:04:17Z
updated_at: 2026-08-03T19:27:49Z
parent: okf-cli-wuiv
---

## Origin

PO review 2026-07-26, reject of US-06. `okf-cli-snxj` shipped a zero-hit suggestion branch that is **unreachable in the live catalogue**: `cmd_find` enters it only on an empty result list, and against a populated `concept_emb` the semantic arm sorts all 2443 candidates and cuts to `--limit` with no absolute cosine floor (R05b, recorded before that feature began). Reproduced live at planning time, own hands:

```
$ python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue find "zzzzqqqq" --limit 3
note: semantic arm owns this ranking (lexical top-1 lacked a clear margin)
score: 46/100  title: QMunity  ...  provenance: semantic (cosine=0.46)
score: 45/100  title: QMS des U  ...
```

The PO decided on 2026-07-26 that this bean carries a **measurement only**. No threshold is to be chosen here. Three retrieval intuitions of this project (chunking, an absolute cosine floor, "lexical is the biggest lever") were all measured and all three were wrong; a floor set freehand by a plan author would be exactly the overfitting that was avoided three times. `SEMANTIC_MARGIN_RATIO` and the expansion floor have likewise never been retuned by hand in this chain, and this measurement changes nothing about that.

## The correction this bean exists to carry

**R34 is not the answer to this question, and must not be cited as closing it.** R34 rejected the absolute cosine floor (Q12/T06, status "verworfen") on the evidence that correct rank-1 targets and best false hits overlap completely: `voyage+titlebody` correct median 0.604 / min 0.494, best false hit 0.644. That was measured **exclusively on queries that have a target in the catalogue**. The population here is the opposite one — queries with no target at all — and its top-1 cosine distribution has never been measured, because all 48 evaluation queries have targets.

Both directions have concrete, cheap evidence pointing at them, which is precisely why this needs measuring rather than arguing:

- *For separation:* the nonsense query above tops out at 0.46, while the minimum correct target sits at 0.494 (R34). n=1.
- *Against a suppressing floor:* the two `synonymy` zero-hits in `docs/okf-retrieval-architecture/eval/taxonomy.md` sit at cosine 0.395 and 0.35 (verbatim from `eval/taxonomy.md`, rank 90/2443 and 736/2443). A floor around 0.47 would destroy exactly the cases the zero-hit feature exists to rescue.

### Requirement 1: A negative query set exists as a versioned eval asset

**Objective:** As whoever decides this threshold, I want a query population with no valid target in the catalogue, so that the "nothing convincing" case can be measured instead of assumed.

#### Acceptance Criteria

1. THE repository SHALL contain `docs/okf-retrieval-architecture/eval/queries_negative.json` with 40 queries, matching `queries_v2.json`'s size so the two distributions are directly comparable.
2. THE set SHALL contain two labelled sub-populations: *hard negatives* (well-formed questions about topics demonstrably outside the catalogue's twelve bundles) and *nonsense* (strings with no lexical or semantic content).
3. THE eval set SHALL record, for each hard negative, why no concept answers it, adjudicated against that query's own top-10 semantic hits.
4. WHERE a hard negative's target turns out to exist in the catalogue, THE eval set SHALL exclude that query.
5. THE generation SHALL follow the method that produced `queries_v2.json` (subagent-written, machine-checked, R41/D10), not hand-authoring by the measuring agent.

### Requirement 2: The separating statistic is measured, not chosen

**Objective:** As the decision-maker, I want the cost of every candidate threshold quantified in both directions, so that the value is read off data rather than picked.

#### Acceptance Criteria

1. THE measurement SHALL report, for candidate cosine floors from 0.30 to 0.65 in steps of 0.01: how many negatives are suppressed, and how many correct targets of the 48 positive queries are lost.
2. THE measurement SHALL evaluate BOTH candidate mechanisms against the same data: (a) a suppressing floor below which a candidate is not a hit at all, and (b) a confidence bar that keeps the results and additionally prints the suggestion line. Their cost functions differ — a false trigger of (b) costs one noisy line, a false trigger of (a) costs a result.
3. THE measurement SHALL prove the mechanism ran before concluding anything from a null result — count the invocations, not the diffs (LL-14).
4. THE bean SHALL end with a recommendation and the table behind it. It SHALL NOT ship a threshold, a code change to `cmd_find`, or a change to `SEMANTIC_MARGIN_RATIO`.

#### Success Criteria

- SC-01: `queries_negative.json` exists, 40 entries, both sub-populations labelled, committed.
- SC-02: the trade-off table above is in the bean, with the literal command that produced it.
- SC-03: the recommendation names which mechanism the data supports, or states explicitly that the data supports neither — that is a legitimate outcome and closes the bean just as well.
- SC-04: `~/Obsidian/Knowledge-Catalogue` is left pristine: no `_okfeval-*` files, no stray rows, `git status --short` empty in that repo. Never commit there.

## Cost and operational notes

**Embedding cost is one query vector per query per run** — 88 queries (48 positive + 40 negative), a few dozen tokens each, one `voyage-3-large` call per query via `_query_vector()`. **No catalogue re-embedding is needed**: `concept_emb` already covers 2443/2443 concepts (R44), and that pass — the expensive one — is already paid for. Re-running the measurement is therefore cheap enough to repeat freely.

**`VOYAGE_API_KEY` rotation is pending.** The key lives in the shell. If it rotates before or during this work, re-export it and re-run; the measurement is idempotent and no partial state survives a failed run. A missing key degrades `find` to the lexical arm with a stderr note rather than failing, so a silently unset key would produce a measurement of the wrong thing — check the key is live before trusting any number.

## Related, deliberately not merged into this bean

`okf-cli-uumj` asks whether the binary ownership decision of conditional handover is too absolute in both directions, and its open half needs the same eval harness. Whoever picks this up should read it first — the two may share a measurement run, but they are separate decisions.

## Measurement 2026-08-03 — result: the data supports NEITHER mechanism

Run against the live catalogue, 2947 concept vectors, 88 query embeddings (48 positive, 40 negative).

    python3 docs/okf-retrieval-architecture/eval/measure_negative.py \
        --root ~/Obsidian/Knowledge-Catalogue --out negative_v1.json

Harness: `docs/okf-retrieval-architecture/eval/measure_negative.py`. Raw result: `docs/okf-retrieval-architecture/eval/negative_v1.json`.

### The distributions overlap completely

| population | n | min | p25 | median | p75 | max |
|---|---|---|---|---|---|---|
| negative top-1 (all) | 40 | 0.294 | 0.413 | 0.470 | 0.516 | 0.566 |
| hard negatives | 20 | 0.369 | 0.416 | 0.469 | 0.497 | 0.564 |
| nonsense | 20 | 0.294 | 0.413 | 0.493 | 0.520 | 0.566 |
| positive top-1 | 48 | 0.346 | 0.478 | 0.535 | 0.578 | 0.721 |
| positive target | 48 | 0.289 | 0.452 | 0.521 | 0.560 | 0.721 |

The negative maximum (0.566) sits above the positive-target median (0.521), and the positive-target minimum (0.289) sits below the negative minimum (0.294). There is no value anywhere in the range that separates the two populations.

AUC of top-1 cosine as a classifier, target versus negative: **0.641**. Against nonsense alone it is **0.611**, against hard negatives **0.670**.

### The trade-off table

`suppressed` is the benefit both mechanisms share. `targets_lost` is mechanism (a)'s cost, a result the user no longer gets. `noisy_lines` is mechanism (b)'s cost, a suggestion line printed at a query that was legitimate.

| floor | suppressed /40 | targets_lost /48 | noisy_lines /48 |
|---|---|---|---|
| 0.30 | 1 (2%) | 1 (2%) | 0 (0%) |
| 0.36 | 3 (8%) | 2 (4%) | 1 (2%) |
| 0.40 | 8 (20%) | 7 (15%) | 1 (2%) |
| 0.42 | 12 (30%) | 8 (17%) | 3 (6%) |
| 0.44 | 16 (40%) | 11 (23%) | 5 (10%) |
| 0.46 | 17 (42%) | 15 (31%) | 8 (17%) |
| 0.47 | 21 (52%) | 17 (35%) | 12 (25%) |
| 0.50 | 27 (68%) | 24 (50%) | 15 (31%) |
| 0.52 | 32 (80%) | 24 (50%) | 19 (40%) |
| 0.56 | 37 (92%) | 35 (73%) | 27 (56%) |
| 0.58 | 40 (100%) | 39 (81%) | 36 (75%) |

Full 36-row table at 0.01 resolution in `negative_v1.json` under `tradeoff`.

### Recommendation

**Ship neither.** SC-03 admits this outcome, and the data forces it.

Mechanism (a), a suppressing floor, is not viable at any value. Its best Youden index over the whole range is J = 0.300 at floor 0.52, where it catches 32 of 40 negatives and destroys 24 of 48 correct targets. A retrieval feature that discards half the correct answers to silence four fifths of the nonsense is worse than the noise it removes. R34 rejected the floor on the positive population; this measurement rejects it on the negative one as well, so the rejection is now two-sided and no longer open.

Mechanism (b), a confidence bar, is cheaper but still not worth its cost. Best J = 0.404, also at 0.52, where it flags 32 of 40 negatives and mislabels 19 of 48 legitimate queries. At the far gentler 0.42 the ratio looks better (12 of 40 flagged against 3 of 48 mislabelled), but it then reaches under a third of the population it exists for, while telling one in sixteen correct answers that nothing convincing was found. The feature's purpose is to help an agent reformulate; a hint that fires on 30% of the cases that need it and lies in 6% of the cases that do not is not that help.

### Why this is not a tuning problem

Nonsense strings score HIGHER than well-formed questions about absent topics: nonsense median 0.493 against hard-negative median 0.469, and the classifier is measurably worse at separating targets from nonsense (AUC 0.611) than from hard negatives (0.670). A relevance signal that ranks `qwfjzp` above `Terraform remote state locking with DynamoDB` is not measuring relevance in this range. No choice of threshold repairs a statistic that is inverted with respect to the property it would gate on.

This also settles the counter-evidence the bean carried in. The two synonymy zero-hits from `eval/taxonomy.md` at cosine 0.395 and 0.35 do sit inside the region any useful floor would cover, exactly as feared. They are not an edge case to be traded away, they are typical: 17 of 48 correct targets score below the negatives' median.

### What this does NOT decide

The measurement was run on top-1 cosine because that is the statistic both candidate mechanisms would read. It says nothing about a margin-based signal (top-1 against top-2), which is a different statistic on the same vectors and would need its own measurement. `okf-cli-uumj` asks a related question about the binary ownership decision of conditional handover and can reuse this harness; the query embeddings are cached, so a follow-up run costs no API calls.

Nothing was changed in `cmd_find`, no threshold shipped, `SEMANTIC_MARGIN_RATIO` untouched.

### Consequence for okf-cli-snxj

The zero-hit branch stays unreachable in the live catalogue, and this bean does not make it reachable. Whoever picks up `snxj` should treat the reachability as an open question with one answer now ruled out, not as a task waiting on a number from here.

### Verification

Invocation counters (LL-14), asserted before any conclusion was drawn: 88 queries embedded, 0 cache hits, 2947 concept vectors loaded, 259 336 cosine comparisons, 36 floors evaluated. The assertion block earned its keep during development: an ordering mistake left `floors_evaluated` at 0 and the run aborted instead of reporting an empty trade-off table as a null result.

Catalogue left pristine (SC-04): `find ~/Obsidian/Knowledge-Catalogue -name '_okfeval-*'` returns 0, `SELECT COUNT(*) FROM concept_emb WHERE path LIKE '%/_okfeval-%'` returns 0, `git status --short` in that repo is empty. No commit was made there.
