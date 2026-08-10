---
# OKFT-1mxp
title: T12 Failure taxonomy of remaining zero-hits
status: completed
type: task
priority: normal
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-26T09:45:37Z
parent: OKFT-cskz
blocked_by:
    - OKFT-uagv
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

- [x] Extend `remeasure.py` to emit per-row detail under a `rows` key; re-run it
- [x] For each failing query, read the expected concept and the top-3 returned concepts, assign one class
- [x] Write `eval/taxonomy.md` (header naming file + sha + date, the table, the counts — no prose beyond that)
- [x] Resolve Q03 and Q10 in `QUESTIONS.md`; catalogue-gap does not dominate (0/8) — no pointer to `OKFT-iw0d` needed
- [x] Commit `docs(eval): failure taxonomy, answer Q03/Q10`

## Recommended Skills

- none (analysis)


## Prelude from the T10/T11 reviews (2026-07-26, supervisor)

T10 (`OKFT-snxj`) and T11 (`OKFT-ftri`) are closed and approved. Six things carry into the taxonomy work:

1. **Baseline moved.** The suite is now **259 tests**, still exactly **19 failures / 2 errors** — all pre-existing in the crosslink suites.
2. **The failure set is flag-independent.** Expansion changed zero outcomes: `shipped_expand.json` is identical to `shipped_v2.json` on every per-file metric. Build the taxonomy from either file; `--expand-tags` does not move a single one of the 8 residual zero-hits.
3. **Per-query diagnostics were not persisted.** T11 measured top-tag cosines per query in-process and did not write them out. If the taxonomy wants a synonymy-closeness split, those numbers must be regenerated.
4. **One taxonomy class is already established and must not be re-derived as an open question.** For the R12 family, tag-vector expansion cannot close the gap *in principle* — not because of the floor, not because of granularity, but because the terms are not neighbours in tag-slug space (tags are embedded slug-only, R06). Concept embedding, which sees the running text, is what solves that class. Measured evidence: `"mockup tailscale"` → `tailscale` at 0.595 (a word already in the query, so zero information gain); `"mockup"` → `mockups` at 0.6693 (morphological variant, not a synonym); `excalidraw` at rank 105/650 for `"mockup"`, absent from any plausible neighbourhood. See Q05/Q06 in QUESTIONS.md.
5. **Do not conflate zero-hits with squeeze-outs.** `OKFT-uumj` tracks a different failure: there the target IS a hit and is merely truncated out of the result window under handover. Those cases are not in the zero-hit set and belong to a separate taxonomy branch, if they are mentioned at all. Affected concepts recorded there: tailscale-subnet-routing, data-ui-convention, replikations-playbook, ai-operating-system, immich.
6. **A bound on the suggestion feature exists.** `_zero_hit_suggestions()` reaches typos and synonyms ONLY; truncated or partially typed terms never arrive there, because both lexical procedures catch any prefix first by construction.

Two standing quality rules from this chain:

- **PF-5:** a sentence whose function is to end review is the sentence that gets checked. Claims of the form "verified" / "behaviour-identical" / "reverted byte-identically" must name the command and quote its observed output, or not be written.
- **Prove the mechanism fired before comparing outputs.** A silently swallowed flag produces bit-identical output to an honest null result — from the artefact alone the two are indistinguishable. Count the calls first (a counting stub), then compare.


## Summary

Extended `docs/okf-retrieval-architecture/eval/remeasure.py`'s `measure()` to
also emit a `"rows"` key (query, expected_path, rank, top3) alongside the
existing aggregate metrics, then re-ran it against the live catalogue
(`~/Obsidian/Knowledge-Catalogue`, read-only) to regenerate `shipped_v2.json`.
Aggregate metrics matched the prior `shipped_v2.json` bit-for-bit **per
constituent query file** (`queries_v2.json` and `queries_real.json`
individually: recall@1/5/10, mrr, zero_hit all unchanged). **`combined.mrr`
did drift**: 0.451901 → 0.450860 (the `combined` block re-runs every query
against the CLI a second time, so it is not a pure re-aggregation of the two
per-file numbers — a query near a lexical/semantic tie can land on the other
side of it between runs). `combined.zero_hit` and recall stayed identical, so
the core claim (same mechanism, same outcome set) is unaffected, but the mrr
point estimate itself moved and is disclosed here rather than only in the
per-file comparison. Per the plan author's ruling (bean, commit `e152b23`):
0.450860 is now twice-reproduced (T09 reviewer's independent check, then this
re-run) and 0.4519 was the outlier; `REFERENCES.md` R44 recast to reflect
that is assigned to T13, not fixed here.

8 of 48 queries are zero-hit at the shipped default (`--limit 10`): 7 of 40
in `queries_v2.json`, 1 of 8 in `queries_real.json`, matching the bean's
stated count exactly.

For each, top-3@10 alone cannot decide `ranking` vs `synonymy` (both classes
mean "not in top 10"), so I ran two companion diagnostics per query, reusing
only shipped code paths — no threshold changed:
1. `okf-cli find "<query>" --root <KC> --limit 50` — same fusion/gating code,
   wider display window only (verified via SQL: `_fts_ranking` truncates with
   `ORDER BY r LIMIT ?`, `_substring_ranking`/`semantic_ranking` sort the full
   set then slice `[:limit]` — raising `--limit` never changes an ordering,
   only how much of it is shown).
2. A standalone `semantic_ranking(root, query, 100000)` call (imported
   `okf-cli.py` as a module) for the full-corpus cosine rank/score, to see
   where the target sits even when the CLI's own margin gate keeps the
   semantic arm from running at all (this happened for one query).

Result: 6/8 (75%) are `ranking` — the target is found at rank 11-40/2443 the
moment the same shipped code is asked for `--limit 50`, i.e. it was already
inside reach, just past the 10-result cutoff (one of the six only reachable
because the standalone semantic call proved the concept sits at a rescuable
rank — the production margin gate itself is what's silently discarding it,
never invoking the semantic arm at any limit because the wrong lexical top-1
holds a "confident" margin). 2/8 (25%) are `synonymy` — not found even at
`--limit 50`; standalone full-corpus semantic rank 90/2443 (cosine 0.395) and
736/2443 (cosine 0.35) respectively, both concepts read directly
(`okf-cli read <path>`) and confirmed to genuinely answer their query, just
sharing no surface vocabulary with the paraphrase. 0/8 `catalogue-gap`, 0/8
`wrong-target` — every one of the 8 expected concepts, read directly, does
answer its query.

Point 4 of the T10/T11 prelude (R12-family, tag-slug-space, concept embedding
is what solves it) was cited, not re-derived — it concerns the `--expand-tags`
tag-vector mechanism specifically, which is a different code path from the
concept-level semantic arm this taxonomy measures (D13's concept_emb already
ran for these 8). Point 5 (OKFT-uumj squeeze-outs) was not folded in —
those queries are hits, not zero-hits, and are absent from `queries_v2.json`/
`queries_real.json`'s zero-hit rows by construction.

One incidental, unactioned observation: every live `find` call in this task
printed `note: lexical index is stale (catalogue changed since build)` to
stderr. This is a pre-existing condition (the re-run's bit-identical
aggregate metrics vs. the prior `shipped_v2.json` prove it was already true
at the T9/T10/T11 baseline, not something this task introduced), out of this
task's scope (a diagnostic, not a fix), and `.fts`/`.tagvec` are git-ignored
in the KC repo so it never touched KC's tracked state. Flagging it for T13/PO
awareness only.

Commits: 81a0368 docs(eval): failure taxonomy, answer Q03/Q10
(docs/okf-retrieval-architecture/eval/taxonomy.md [new],
docs/okf-retrieval-architecture/eval/remeasure.py,
docs/okf-retrieval-architecture/eval/shipped_v2.json,
docs/okf-retrieval-architecture/QUESTIONS.md).

## Test-Output

Baseline, both env directions, before this task's edits (HEAD=cdd7a0b):

    $ python3 -m unittest discover -s cli -p "test_*.py"
    Ran 259 tests in 17.734s
    FAILED (failures=19, errors=2)

    $ env -u VOYAGE_API_KEY python3 -m unittest discover -s cli -p "test_*.py"
    Ran 259 tests in 13.968s
    FAILED (failures=19, errors=2)

After this task's edits (HEAD=81a0368, VOYAGE_API_KEY set) — remeasure.py is
not under `cli/`'s test discovery, so no test-count change is expected and
none occurred:

    $ python3 -m unittest discover -s cli -p "test_*.py"
    Ran 259 tests in 17.129s
    FAILED (failures=19, errors=2)

259 tests, 19 failures / 2 errors — unchanged, as expected for a docs/eval-only
task.

## Smoke

Live re-run of `remeasure.py` against `~/Obsidian/Knowledge-Catalogue`
produced identical per-file aggregate metrics to the pre-existing
`shipped_v2.json` (proving the extended script still runs the same shipped
mechanism):

  queries_v2.json:   recall@1 0.25, recall@5 0.70, recall@10 0.825, zero_hit 0.175
  queries_real.json: recall@1 0.375, recall@5 0.625, recall@10 0.875, zero_hit 0.125

Diagnostic companion run example (one of the 8), showing the mechanism and
its output directly:

    $ python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue find \
        "bots aus hauseigener oberfläche beauftragen" --limit 50
    note: lexical index is stale (catalogue changed since build) — run `okf-cli build-index`
    note: semantic arm owns this ranking (lexical top-1 lacked a clear margin)
    [... path: ai-wiki/claude-dispatch appears at position 27 of 50 ...]

KC repo left clean:

    $ git -C ~/Obsidian/Knowledge-Catalogue status --short
    (empty)

## Deviations/ERRATA

1. **Beyond PLAN.md Step 1's literal scope, but required by Step 3's own
   class table.** The plan's Step 1 only asks `remeasure.py` to persist
   top-3@10; Step 3's `ranking` class is defined as "target was retrieved but
   below rank 10," which is undecidable from top-3@10 alone (that only proves
   *not* in top 10, never *where* beyond it). I added the `--limit 50` /
   standalone `semantic_ranking()` companion diagnostics described above to
   make the `ranking` vs `synonymy` split measured rather than argued, per
   this task's own hard rule ("classify what you measure"). No thresholds
   were changed to produce this — `--limit` is an existing CLI flag, and the
   standalone call reuses the shipped `semantic_ranking()` verbatim.
2. **taxonomy.md carries more than a bare header line.** PLAN.md Step 3 asks
   for "a header naming the measurement ... no prose beyond that." I kept the
   header to file+sha+date plus one short paragraph stating the `--limit 50`/
   standalone-semantic methodology, because the `rank` column is blank on
   every row by construction (all rows are zero-hit) and the classification
   evidence needed a documented source. Judged this the minimum necessary to
   keep the artefact self-supporting under PF-5, not scope creep.

## Notes for T13 (OKFT-jk0q)

- `docs/CLAUDE.md` has no I01-numbered line to fix in this repo (the file
  exists at `docs/CLAUDE.md`, not a root-level `CLAUDE.md` — no root
  `CLAUDE.md` file exists in this repo at all; global tools-level CLAUDE.md
  governs). T13's own bean/PLAN.md Task 13 text should be checked against
  this before editing.
- Q03/Q10 are now 🟢 in `QUESTIONS.md` with the class split and the
  catalogue-gap share (0/8, 0%) respectively — T13 Step 3's TASKS.md/
  QUESTIONS.md sync can point straight at `eval/taxonomy.md`.
- `catalogue-gap` does not dominate (0/8) — no new pointer to
  `OKFT-iw0d` was needed; that bean's existing catalogue-gap case
  ("mockup tailscale" HTML-serving) is unrelated to this task's 8 and is
  already a hit (rank 3), not a zero-hit, in the current measurement.
- Unactioned observation to carry forward or triage: `.fts`/`.tagvec` in the
  live KC catalogue report as stale on every `find` call (pre-existing,
  confirmed not introduced by this task, out of scope to fix here).


## Ruling from the plan author, 2026-07-26 (supervisor-relayed, binding)

### 1. `shipped_v2.json` regeneration — accepted, but R44 is now stale

Verified by the plan author himself: `81a0368` regenerated the file and moved `combined.mrr` from **0.451901 to 0.450860** (latency moved too, expected). `zero_hit` and recall stayed bit-identical. All four gate criteria still hold — no gate break.

Consequence, assigned to **T13**, not to a T12 fix round: R44 in `REFERENCES.md` now cites a number absent from its own raw-data file, and the variance note reads inverted — it names 0.45086 as the deviating re-run while the committed file now says exactly that. **0.45086 is independently reproduced twice** (T09 reviewer, then T12); **0.4519 was the outlier.** R44 to be recast: 0.4509 as the headline number because twice-reproduced, 0.4519 mentioned as the one-off first measurement, cause named as the index-state-dependent near-tie, plus the statement that zero-hit and recall are stable so the core claim is untouched. Pure text work, no new measurement run.

### 2. The fusion-gating case — characterise it, do not fix it

A wrong lexical top-1 with a clear margin keeps the semantic arm from ever firing, although it would have placed the target at **rank 40, cosine 0.46**. This is **not a defect**: it is a priced-in cost of the measured rule. R43 measured exactly this rule and it won in the worst case. It affects **1 of 48** queries. Lowering the threshold on the strength of a single query would be precisely the overfitting this project has avoided three times.

To be recorded in `taxonomy.md` as a **characterised limit of the rule**, with rank and cosine, pointing at `OKFT-uumj` — where the related question already sits: whether the binary ownership decision is too absolute in both directions. Both belong in a future **measured** round, not this one.

### 3. `catalogue-gap` = 0 of 8 belongs up front

The plan author's assessment: this is the strongest substantive finding of T12. It answers Q10 completely and moves the next lever unambiguously to **retrieval design rather than authoring** — contrary to what the older R12 finding might have suggested. It must lead in `taxonomy.md`, not sit in the footnotes.


## Fix round — CHANGES_REQUIRED response, 2026-07-26 (text-only, no re-measurement)

Reviewer verdict: everything measured held (5/8 rank/cosine claims
independently reproduced, gating mechanism verified mechanically at
`_keyword_top1_is_confident` 100 vs 65, `catalogue-gap=0` spot-checked, both
baseline directions and KC hygiene confirmed). Findings were about framing
and disclosure in the shipped artefact, not about any wrong number. Per the
coordinator's instruction and the plan author's ruling (commit `e152b23`,
read first): no measurement re-run, no threshold touched, no JSON
regenerated. All four points addressed as text-only edits:

- **B02** (`eval/taxonomy.md`, fusion-gating row): extended the note to state
  explicitly that this is a *characterised limit of the shipped fusion rule,
  not a defect* — R43 measured this exact margin rule and it won in the worst
  case, it affects 1/48 queries, and tuning on one query would be the
  overfitting this project has already avoided three times. Added the
  `_keyword_top1_is_confident` 100-vs-65 mechanism detail and a pointer to
  `OKFT-uumj`, where the related "is the binary ownership decision too
  absolute" question already sits — both belong in a future *measured* round.
- **B03** (`eval/taxonomy.md`, header/lead): added a lead paragraph stating
  `catalogue-gap = 0/8 (0%)` up front as the strongest substantive finding —
  it answers Q10 completely and moves the next lever unambiguously to
  retrieval design, not authoring.
- **I01** (this bean's Summary, aggregate-metrics claim): corrected "matched
  ... bit-for-bit per file" to explicitly scope that claim to the two
  *constituent* query files only, and disclosed the `combined.mrr` drift
  (0.451901 → 0.450860) that the original wording implied did not exist.
  `combined.zero_hit`/recall are unchanged, so the taxonomy's own conclusions
  are unaffected — but the sentence that read as complete verification did
  not say so, which is exactly what got flagged.
- **I02** (`eval/taxonomy.md`, header sha): now cites two shas, labelled —
  `cdd7a0b` as the logic baseline (the `find`/fusion code being measured,
  unchanged by this task) and `81a0368` as the artefact commit (the `rows`
  key extension plus the file itself).

Not touched: `docs/okf-retrieval-architecture/REFERENCES.md` R44 — assigned
to T13 per the plan author's ruling, left alone.

Baseline re-confirmed after the text edits, both env directions:

    $ python3 -m unittest discover -s cli -p "test_*.py"
    Ran 259 tests in 17.149s
    FAILED (failures=19, errors=2)

    $ env -u VOYAGE_API_KEY python3 -m unittest discover -s cli -p "test_*.py"
    Ran 259 tests in 13.869s
    FAILED (failures=19, errors=2)

Unchanged, as expected for text-only edits. Leaf stays `completed` per the
standing convention (PF-2/PF-5) — this is an inline fix round within the same
bean, not a re-open requiring a fresh implementer cycle.
