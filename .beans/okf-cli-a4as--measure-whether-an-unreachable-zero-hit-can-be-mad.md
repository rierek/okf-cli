---
# okf-cli-a4as
title: Measure whether an unreachable zero-hit can be made reachable
status: todo
type: task
priority: high
created_at: 2026-07-26T13:04:17Z
updated_at: 2026-07-26T13:04:17Z
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
- *Against a suppressing floor:* the two `synonymy` zero-hits in `docs/okf-retrieval-architecture/eval/taxonomy.md` sit at cosine 0.40 and 0.35. A floor around 0.47 would destroy exactly the cases the zero-hit feature exists to rescue.

### Requirement 1: A negative query set exists as a versioned eval asset

**Objective:** As whoever decides this threshold, I want a query population with no valid target in the catalogue, so that the "nothing convincing" case can be measured instead of assumed.

#### Acceptance Criteria

1. THE repository SHALL contain `docs/okf-retrieval-architecture/eval/queries_negative.json` with 40 queries, matching `queries_v2.json`'s size so the two distributions are directly comparable.
2. THE set SHALL contain two labelled sub-populations: *hard negatives* (well-formed questions about topics demonstrably outside the catalogue's twelve bundles) and *nonsense* (strings with no lexical or semantic content).
3. EACH hard negative SHALL record why no concept answers it, adjudicated against its own top-10 semantic hits — a query whose target turns out to exist is not a negative and SHALL be removed from the set.
4. THE generation SHALL follow the method that produced `queries_v2.json` (subagent-written, machine-checked, R41/D10), not hand-authoring by the measuring agent.

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
