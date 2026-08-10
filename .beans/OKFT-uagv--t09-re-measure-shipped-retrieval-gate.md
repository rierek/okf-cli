---
# OKFT-uagv
title: T09 Re-measure shipped retrieval + gate
status: completed
type: task
priority: high
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-26T08:07:42Z
parent: OKFT-cskz
blocked_by:
    - OKFT-kc9x
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



## HARD STOP 2026-07-26 (PO/plan author, realization kickoff)

Verbatim (PO): "Wenn in OKFT-uagv ein Retrieval-Kriterium reisst: stoppen und mit der
JSON melden."

Interpretation: the gate criteria (zero-hit <= 0.30, MRR >= 0.35, real-query zero-hit <= 0.25,
p50 latency <= 2.0 s) are pass/fail, not negotiable. If any one of them fails, do NOT retune,
re-run selectively, or relax a threshold. Stop, attach the full remeasure JSON, and report to
the supervisor.



## PRELUDE 2026-07-26 — mandatory footnote for the R44 line (plan author)

When you write the R44 measurement line, add a footnote recording that the live catalogue held
**2443 concepts at measurement time, not the 2437 named in the plan** — it grew by 6 between
the original measurement and realization.

This is NOT an error and needs no re-run: `concept_emb` covers 2443 of 2443, i.e. 100% of the
current catalogue. But **R42 and R43 were measured against 2437**, so a later reader comparing
R44 to them will see a corpus-size difference and, without the footnote, take it for a bug.
Name it explicitly in the R44 line rather than only in a bean.

Verified state entering the measurement (checked independently by both the supervisor and the
plan author, not implementer-claimed):
- `concept_emb`: 2443 rows, 2443 distinct paths, every vector exactly 4096 bytes
  (1024 float32, no truncation), single model group `voyage-3-large`.
- `emb` (TAG scope): unchanged at 752 bge-m3 + 650 voyage — exactly the R09 values, so the tag
  layer is untouched as AC2/SC-02 require. Do not conflate `emb` with `concept_emb` (D16).
- `~/Obsidian/Knowledge-Catalogue` working tree clean; artefacts `.tagvec/` and `.fts/` are
  both gitignored there. Never commit in that repo.

Related known-drift entry: `LL-pending-02` in the parent bean (success criteria should quote
counts from a live foreign repo as ">= N as of <date>", not as a fixed number).


## Summary

Re-measured the shipped `okf-cli find` (subprocess, no re-implementation) against the unbiased 48-query set and against the golden fixture gate. All four hard-stop retrieval criteria passed on the first run — no retune, no threshold change, `SEMANTIC_MARGIN_RATIO` untouched. Fixture gate: `GATE: PASS`. Live catalogue verified clean afterward (0 `_okfeval-*` files, 0 dangling `concept_emb` rows). Also produced, as requested, a real ablation-based number for the `OKFT-uumj` squeeze-out question.

Commit: `4914650` — `test(eval): re-measure shipped retrieval`.

## Test-Output

Baseline (`python3 -m unittest discover -s cli -p 'test_*.py'`), run twice, before and after the `cli/eval/runner.py` change, both with and without `VOYAGE_API_KEY`:

- With `VOYAGE_API_KEY` set: `Ran 248 tests in ~16-20s` — `FAILED (failures=19, errors=2)` (both before and after the change).
- With `env -u VOYAGE_API_KEY`: `Ran 248 tests in ~13-17s` — `FAILED (failures=19, errors=2)` (both before and after the change).

Exactly the inherited baseline, unchanged, all four runs.

Module-scoped, since `cli/eval/runner.py` was touched (`python3 -m unittest cli.test_eval_runner -v`): `Ran 18 tests` — `OK`, including `RunnerAgainstRealCatalogueTest` (5 tests) which exercises the live catalogue through `runner.run()` with the new `build-index` call inserted. `_park_fts_index()` / `_park_voyage_key()` context managers untouched, both still restoring on every exit path (not modified by this task).

## Smoke

- `python3 docs/okf-retrieval-architecture/eval/remeasure.py --root ~/Obsidian/Knowledge-Catalogue --queries queries_v2.json queries_real.json --out shipped_v2.json` — ran clean, wrote `docs/okf-retrieval-architecture/eval/shipped_v2.json`.
- Bracketed gate sequence executed exactly as PLAN.md Task 9 Step 4 specifies: `fixtures.py --seed` -> `build_tagvec.py --target concepts --model voyage-3-large --produce` (4/4 fixture rows embedded, plain bash subprocess, `VOYAGE_API_KEY` inherited from the real shell — not a context-mode sandbox) -> `runner.py` (now builds the FTS index itself) -> `gate.py` -> `fixtures.py --teardown` -> `DELETE FROM concept_emb WHERE path LIKE '%/_okfeval-%'` -> `build-index`.
- Post-teardown verification commands run and observed directly (not inferred): `find $ROOT -name "_okfeval-*" | wc -l` -> `0`; `SELECT COUNT(*) FROM concept_emb WHERE path LIKE '%/_okfeval-%'` -> `0`; `SELECT COUNT(*) FROM concept_emb WHERE model='voyage-3-large'` -> `2443`; `git -C $ROOT status --short` -> empty (0 lines). Live catalogue repo was never committed to.
- `VOYAGE_API_KEY` presence checked only via `[ -n "$VOYAGE_API_KEY" ] && echo set` (`set`) — never echoed/printed/logged. No 401/403 encountered at any point (all Voyage calls succeeded).

## Measurements

### R44 — shipped-architecture re-measurement (`eval/remeasure.py`, n=48)

```json
{
  "queries_v2.json": {
    "n": 40, "recall@1": 0.25, "recall@5": 0.7, "recall@10": 0.825,
    "mrr": 0.43805555555555553, "zero_hit": 0.175,
    "latency_p50": 0.61971116065979, "latency_max": 0.6599469184875488
  },
  "queries_real.json": {
    "n": 8, "recall@1": 0.375, "recall@5": 0.625, "recall@10": 0.875,
    "mrr": 0.5148809523809523, "zero_hit": 0.125,
    "latency_p50": 0.624352216720581, "latency_max": 0.6667811870574951
  },
  "combined": {
    "n": 48, "recall@1": 0.2708333333333333, "recall@5": 0.6875,
    "recall@10": 0.8333333333333334, "mrr": 0.451901455026455,
    "zero_hit": 0.16666666666666666, "latency_p50": 0.6213710308074951,
    "latency_max": 0.7662489414215088
  }
}
```

Against target (pass/fail, hard stop — none tripped, no retune performed):

| Criterion | Target | Measured | Verdict |
|---|---|---|---|
| combined zero-hit | <= 0.30 (was 0.979) | 0.1667 | PASS |
| combined MRR | >= 0.35 (was 0.021) | 0.4519 | PASS |
| queries_real.json zero-hit | <= 0.25 (was 0.875) | 0.125 | PASS |
| combined latency p50 | <= 2.0 s | 0.621 s | PASS |

**R44 footnote (mandatory, plan-author prelude):** the live catalogue held **2443 concepts** at measurement time, not the 2437 named in the plan — it grew by 6 since R42/R43 (both measured against 2437). This is not an error and needed no re-run: `concept_emb` covers 2443/2443 (100%) of the current catalogue. Recorded verbatim as a footnote on the R44 entry itself in `docs/okf-retrieval-architecture/REFERENCES.md` (not only here), per the plan author's instruction, so a later reader comparing R44 to R42/R43 does not mistake the corpus-size difference for a bug.

### R45 — fixture gate

```
== per-metric delta (baseline -> hybrid) ==
metric                      baseline    hybrid     delta
recall_at_1                    0.750     0.750    +0.000
recall_at_5                    1.000     1.000    +0.000
mrr                            0.812     0.800    -0.012
zero_hit_rate_literal          0.000     0.000    +0.000
zero_hit_rate_paraphrase       1.000     0.500    -0.500
mean_score_ratio               0.396     0.845    +0.449
location_correct_rate          1.000     1.000    +0.000
metadata_hit_rate              1.000     1.000    +0.000

s1-literal rank: baseline 1 -> hybrid 1 (no regression)

GATE: PASS
```

`mean_score_ratio` moved because of the 0..100 scale — expected and ungated, per the plan.

Both R44 and R45 are written into `docs/okf-retrieval-architecture/REFERENCES.md` with the actual numbers (no placeholders), continuing the R-numbering after R43.

### OKFT-uumj squeeze-out measurement

Method (real production functions from `cli/okf-cli.py`, imported in-process — not a reimplementation, not a subprocess re-run of the arms): for each of the 48 queries in `queries_v2.json` + `queries_real.json`, run the real lexical arm; keep only queries where the target concept is itself a lexical hit AND the semantic arm would actually run (mirrors `cmd_find`'s own gate: `not lexical_owned_provisionally or len(hits) < limit`). For each such query, fuse with the target's **real** `concept_emb` row (as it exists today, fully embedded) -> `present_real`; then fuse again with **only that one target's row removed** from the vector set (simulating "this concept is the one freshly-written, not-yet-embedded note" — the other 2442 concepts are untouched) -> `present_ablated`, reusing the same cached query embedding for both runs (no extra network cost). Squeeze-out = `present_real and not present_ablated`.

Result:

```json
{
  "n_total_queries": 48,
  "n_applicable": 5,
  "n_squeezed_out": 5,
  "squeeze_rate_of_applicable": 1.0,
  "squeeze_rate_of_total": 0.10416666666666667
}
```

**5 of 48 queries (10.4%)** hit the mechanism at all (target lexically matching AND semantic arm invoked); of those 5, **all 5 (100%)** would lose their target from the result window if that single concept were unembedded, even though it is present, lexically found, and would otherwise rank — it simply loses the truncation race once enough semantic candidates are ranked ahead of it. Affected targets: `dev-wiki/testsystem-vite-tailscale/tailscale-subnet-routing`, `dev-wiki/debug-interface/data-ui-convention`, `dev-wiki/design-system-replication/replikations-playbook`, `ai-wiki/ai-operating-system`, `home-lab-wiki/services/immich`. In every one of the 5 cases the lexical arm did NOT own the ranking (`owned_real=False`), confirming the mechanism is exactly the one `OKFT-uumj` names: semantic-owns-ranking + unembedded-lexical-hit-appended-behind + truncation at `--limit`.

This is a real, live-code-path number, not an argued one. It is reported for the plan author's decision on `OKFT-uumj` (whether an unembedded confident lexical hit deserves a guaranteed slot) — no slot was implemented here, per instruction. Measurement script kept in the session scratchpad only (not committed — it is not part of the shipped T09 deliverable and reimplements nothing shipped, it only calls shipped functions for ablation).

## Deviations/ERRATA

- ~~REFERENCES.md language~~ — **struck 2026-07-26, supervisor (plan author) ruling.** German in `REFERENCES.md` is not a deviation and needs no declaration: the English-artifact rule covers machine/agent artefacts (commit messages, bean titles/bodies), while `REFERENCES.md` is a thinking document on the human side of that line. R44/R45 stay German as written.
- **Squeeze-out measurement is additive, not in the plan:** PLAN.md Task 9 does not ask for the `OKFT-uumj` number; it was requested directly in this task's dispatch. Implemented as a read-only, in-process ablation script kept outside the repo (scratchpad only) to avoid scope creep into the shipped T09 file set — it calls but does not modify or reimplement any shipped ranking function.
- **`runner.py` build-index call uses `"python3"` literal**, not `sys.executable`, to match the existing convention already used by `_run_cli` in the same module (line 52) — the plan's illustrative snippet used `sys.executable`; changed for internal consistency, functionally identical in this environment.
- No other deviations from PLAN.md Task 9. No retune of `SEMANTIC_MARGIN_RATIO` or any other threshold. No criterion failed, so the HARD STOP path was never entered.

## Notes for T10

T10 (`OKFT-snxj`, informative zero-hit) targets the `(no matches …)` branch at `cli/okf-cli.py:881-883` region (now shifted slightly by this task's edits — re-check line numbers before editing) and should know:

- The zero-hit rate T10 will be working against is now measured at **combined 0.1667** (8 of 48 queries), not the pre-plan 0.979 — a much smaller, harder residual. The 8 remaining zero-hit queries are in `docs/okf-retrieval-architecture/eval/shipped_v2.json` per-file breakdowns (`queries_v2.json` zero_hit 0.175 = 7/40, `queries_real.json` zero_hit 0.125 = 1/8); T10 can identify the exact rows by re-running `remeasure.py` and filtering `paths == []`.
- Separately and NOT T10's scope but worth knowing: `OKFT-uumj` (stale-`concept_emb`-visibility) measured a squeeze-out mechanism affecting 5/48 queries where a target IS found lexically but is NOT reported due to embedding-driven truncation — that is a distinct failure class from zero-hit (the concept is never absent from the *raw* candidate set, only from the *printed* one). T10's informative-zero-hit branch fires only on `all_hits` being empty, so it will not by construction cover the squeeze-out cases (there IS a hit, just not the right one, or not enough slots) — flagging this so it isn't assumed covered.
