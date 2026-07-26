---
# okf-cli-c922
title: T03 Fill concept_emb with voyage-3-large (2437)
status: completed
type: task
priority: high
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-26T06:32:46Z
parent: okf-cli-cskz
blocked_by:
    - okf-cli-2a1w
---

Plan: `docs/okf-retrieval-architecture/PLAN.md` → **Task 3**. Follow it step by step.

This is the original Q03 question, now answered by measurement: `concept_emb` is empty in production (R10), so the semantic arm is inert. D13 makes `voyage-3-large` the productive model (MRR 0.452 vs 0.150 for bge-m3, zero-hit 0.167 vs 0.646 — R42).

**This task spends money and mutates a catalogue outside this repo.** Estimated ~$0.71. Get the PO's go-ahead in chat before producing, and report the outcome afterwards. `~/Obsidian/Knowledge-Catalogue` is a separate git repo — nothing is committed there.

### Requirement 1: Populate the production concept embeddings

**Objective:** As an agent searching the catalogue, I want every concept to carry a voyage-3-large document vector, so that the semantic arm can rank against the whole corpus instead of nothing.

#### Acceptance Criteria

1. THE producer SHALL write exactly one `concept_emb` row per catalogue concept for model `voyage-3-large`.
2. THE producer SHALL NOT modify any row of the `emb` (tag-scope) table.
3. IF a run is interrupted THEN THE producer SHALL embed only concepts still missing on its next invocation.
4. THE embedding unit SHALL be `title + "\n\n" + body` — not chunks, not title-only (D11).

#### Success Criteria

- SC-01: `SELECT model, COUNT(*), MIN(dim), MAX(dim) FROM concept_emb GROUP BY model` returns exactly one group: `voyage-3-large`, 2437, 1024, 1024.
- SC-02: the `emb` table's per-model counts are byte-identical to the values recorded before the run (~752 bge-m3, ~650 voyage-3-large).
- SC-03: nothing is committed in the catalogue repo.

_Requirements: PLAN.md Task 3 · DECISIONS D13, D11 · TASKS.md T14 · REFERENCES R10, R42_

## Steps

- [ ] Record the starting row counts of `concept_emb` and `emb`
- [ ] Dry-run the plan, confirm 2437 pending and no writes
- [ ] Get the PO's go-ahead in chat (cost)
- [ ] Produce with `--target concepts --model voyage-3-large --produce` (needs `VOYAGE_API_KEY`; a context-mode sandbox does not inherit it, a plain bash subprocess does)
- [ ] Verify the end state; re-run if the count is below 2437 (the delta plan is resumable)
- [ ] Report rows written, retries logged and actual cost to the PO — no commit in this repo

## Recommended Skills

- none (operational run)



## PO approval 2026-07-26 (supervisor, realization session)

Verbatim (PO, chat): "Jetzt freigeben" — in response to: fill concept_emb for 2437
concepts via voyage-3-large, real API call, ~$0.71.

Interpretation: the full run is authorised. Execute without asking again. No dry run
required. Still applies: never commit inside ~/Obsidian/Knowledge-Catalogue (separate repo);
report any intended catalogue change to the PO instead.


## Summary

Filled `concept_emb` on the live catalogue (`~/Obsidian/Knowledge-Catalogue`)
with `voyage-3-large` document vectors (`title + "\n\n" + body`, D11), using
the T01/T02-hardened producer (batched, per-batch commit, resilient retry).
Single pass, no interruption, no auth failure. `emb` (tag scope) is
byte-identical to the pre-run baseline — untouched, as required (SC-02).

## Test-Output

Live producer run (`--target concepts --model voyage-3-large --produce`),
one pass:

```
voyage-3-large: wrote 2443/2443 concept row(s)
```

- SKIPPED batches: 0
- retries logged: 0
- HTTP 401/403 (auth failure): none observed

End state (`sqlite3 ~/Obsidian/Knowledge-Catalogue/.tagvec/tag_vectors.sqlite`):

```
SELECT model, COUNT(*), MIN(dim), MAX(dim) FROM concept_emb GROUP BY model;
voyage-3-large|2443|1024|1024

SELECT model, COUNT(*) FROM emb GROUP BY model;
bge-m3|752
voyage-3-large|650
```

Both match the pre-run baseline for `emb` exactly (752 / 650, recorded before
Step 3). `concept_emb` now holds exactly one group as required by SC-01,
except the count is 2443 not 2437 — the live catalogue grew between plan
authoring and realization (already logged as `LL-pending-02` on the parent
epic bean; not a defect, count mismatch accepted and carried forward per the
supervisor's dispatch).

Repo test gate (unrelated to this task's data-only change, run per dispatch
instruction to prove nothing broke):

```
python3 -m unittest discover -s cli -p 'test_*.py'
Ran 229 tests in 13.588s
FAILED (failures=19, errors=2)
```

Matches the required baseline exactly (229 tests, 19F/2E, all pre-existing).

## Smoke

Sampled 3 random rows from `concept_emb` (not just 2, for extra confidence)
and unpacked each vector with `struct`:

```
key=c1b2b85072292b0b8c2c3a56fe532173f8040e3f path=obsidian-vault-mgmt-wiki/skripts/commands-hotkeys-dataviewjs-audit
  dim_col=1024 unpacked_floats=1024 nonzero=1024 sample=(-0.0036, -0.0067, 0.0387, 0.0394, 0.0272)
key=5f738dd9560d61eb7aa78302d307384bc32b9000 path=home-lab-wiki/context/services/cloudflare-tunnel
  dim_col=1024 unpacked_floats=1024 nonzero=1024 sample=(-0.0511, 0.0169, 0.0245, -0.0142, 0.0323)
key=8525bc7678a4f0b302918e39e5e89c54b4643709 path=qm-wiki/qmb-training/knowledge-blocks/aufgaben-von-qualitaetsmanagement-werkzeugen
  dim_col=1024 unpacked_floats=1024 nonzero=1024 sample=(-0.0109, 0.0474, -0.0163, 0.0318, 0.0003)
```

All three: 1024 floats (voyage-3-large's dimensionality), all non-zero, no
truncation, plausible small-magnitude cosine-space values — real vectors,
not placeholders.

Catalogue repo state after the run (must show only untracked/ignored, never
staged/committed):

```
git -C ~/Obsidian/Knowledge-Catalogue status --porcelain            -> (empty)
git -C ~/Obsidian/Knowledge-Catalogue status --porcelain --ignored  -> !! .tagvec/
```

Confirmed clean — `.tagvec/` is gitignored there, nothing was committed in
the catalogue repo (SC-03).

Cost/token count: the producer does not surface Voyage's `usage` field from
the API response (out of this task's scope to add — would be a code change,
not a data-fill run), so no per-run billed figure is available from the tool
itself. Computed offline (no network) from the same `title+body` text the
producer sent: 2443 concepts, 7,398,051 characters total, ≈1.85M tokens by a
4-chars/token approximation. That is in the same order of magnitude as the
plan's own $0.71 estimate for 2437 concepts (measured in the prior eval
session, R42) scaled to 2443 — consistent, not independently re-verified
against the Voyage billing dashboard (no dashboard access from this
session).

## Deviations/ERRATA

- Row count is 2443, not the 2437 named in the plan/bean's SC-01 and title.
  Root cause: the live catalogue is a separate, actively-growing repo; 6
  concepts were added between plan authoring and this realization. Per the
  dispatch instructions this is accepted growth, already logged as
  `LL-pending-02` on the parent epic bean (okf-cli-cskz) with its own
  forward-guard (state success criteria as `>= N` or as an invariant, not a
  literal count, when they quote a number from a separate live repo). No
  action taken here beyond reporting — re-running is unnecessary, the run
  already covers 100% of the current catalogue (2443/2443).
- No SKIPPED batches occurred, so the "second pass to pick up the remainder"
  contingency in the dispatch was not needed.
- Exact API cost was not obtainable from the tool (producer doesn't log
  Voyage's usage/cost fields); reported an offline token estimate instead,
  as the dispatch allowed ("token count if not [cost]").

## Notes for T07

T07 (`okf-cli-8j7l`, semantic arm on voyage-3-large) can now rely on:

- `concept_emb` in `~/Obsidian/Knowledge-Catalogue/.tagvec/tag_vectors.sqlite`
  holds exactly one model group, `voyage-3-large`, 2443 rows, dim 1024 for
  every row — full catalogue coverage, no partial/mixed-model state to guard
  against on this catalogue.
- Embedding unit is `title + "\n\n" + body` per `concept_text()` in
  `cli/embeddings/build_tagvec.py:140-145` — matches D11, matches what the
  query-side semantic arm must embed the query text as reference against.
  `concept_cache_key()` (same file, :148-155) is path+content-scoped; T07's
  reader just needs `SELECT path, vec, dim FROM concept_emb WHERE model =
  'voyage-3-large'` and to unpack with `struct` (4-byte little-endian
  floats, as verified in the Smoke section above) — no numpy needed.
- The `emb` (tag-scope) table is untouched (752 bge-m3 / 650 voyage-3-large,
  unchanged before/after) — T07 must not accidentally read tag-scope rows
  out of `emb` when it means `concept_emb`; the two tables are intentionally
  separate (D16).
- This run used `voyage-3-large` exclusively; `bge-m3` is confirmed NOT a
  runtime fallback anywhere in `concept_emb` (D16) — only one model group
  exists in that table, so T07's query path can assume a single model
  without a model-selection branch.
- Growth watch: the catalogue is live and growing (2437 at plan time -> 2443
  at this run). `plan_concept_delta()` is idempotent/resumable by design, so
  a future top-up run for newly-added concepts is a plain re-run of Step 3
  with `--produce` — no manual bookkeeping, no need to re-embed existing
  rows (their cache key is unchanged unless content or path changes).
