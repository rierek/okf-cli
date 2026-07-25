---
# okf-cli-n9l6
title: P3 — Author golden.json query set
status: completed
type: task
priority: normal
created_at: 2026-07-25T18:13:09Z
updated_at: 2026-07-25T18:53:01Z
parent: okf-cli-2lpu
blocked_by:
    - okf-cli-ez6f
---

## Objective (User Story)
As the eval runner, I want a golden file mapping queries to expected concept paths + thresholds so that retrieval can be scored deterministically per scenario and query class.

## EARS Acceptance
- THE golden file SHALL contain >=2 rows per fixture (one `literal`, one `paraphrase`) plus the S4 index-walk and S1/S4 `list`-metadata rows (EVAL-DESIGN.md:27-32).
- THE golden file SHALL contain an explicit S2 location row: `list --scope=<correct-bundle>` expected to MISS the S2 fixture (EVAL-DESIGN.md:12,16-17), with an `expect` (hit/miss) field on `list` rows.
- EACH row SHALL name the verb (find/list/index) and the expected concept path.

## Success Criteria
- SC-001: >=2 rows/fixture with literal+paraphrase classes.
- SC-002: explicit S2 `list --scope` miss row present with `expect:miss`.
- SC-003: JSON (stdlib), no PyYAML dependency.

## Affected code
- Create `cli/eval/golden.json`: rows `{id, verb, query, class, expected_path, min_rank, min_score_ratio, expect}`. `expected_path` matches `bundle/concept-id` (okf-cli.py:560,571).
Consumes `FIXTURES` (P2). Full steps: PLAN.md Task 3.
Commit: `feat(eval): add golden.json query set for S1-S4`

## Prelude 2026-07-25 (from P2 completion, okf-cli-ez6f)

- EVAL-DESIGN.md EXISTS at ~/Obsidian/Vault/okf-revision/EVAL-DESIGN.md (P2 bean's original deviation note claiming otherwise was wrong; corrected). PLAN.md Task 3 line-refs resolve against it.
- S1 and S2 fixtures carry an extra 'tags: [eval-fixture]' (P2 deviation, deliberate) so Task 3 can build a list(type,tag) hit/miss row (S1 hit / S4 miss).
- Fixtures are TRANSIENT: wrap any golden-query validation runs in cli/eval/fixtures.py seed()/teardown() — catalogue must end clean.


## Summary

Authored `cli/eval/golden.json` — 12 rows covering S1-S4: 2 rows per
fixture (literal + paraphrase, 8 rows total), the S4 index-walk row,
and the three Ziel-3/S2 list rows (S1 metadata hit, S4 metadata miss,
S2 location miss). Every query string and filter was empirically
verified by seeding the real fixtures and running find/list/index
against the actual catalogue (not derived from pure reasoning about
scoring) — the tokenize/scoring algorithm has field-weighting subtleties
(body text includes H1/H2 headings, not just prose) that made a few
initially-planned disambiguating query words collide across fixtures
(e.g. "zqxeval sanity" ties S1/S2 because S2's H1 heading also contains
"Sanity"); the empirical pass caught and fixed this before commit.

Row shape: `{id, verb, query, class, expected_path, min_rank,
min_score_ratio, expect}`. `query` is a plain string for `find` rows,
and a dict for `list` (`{type, tag, scope}`) and `index` (`{bundle}`)
rows — see Notes for T(n+1) for exact semantics.

## Test-Output

Baseline (pre-existing, unchanged by this task):
`python3 -m unittest cli.test_okf_cli` → Ran 104 tests, FAILED
(failures=19, errors=2) — identical before and after. No regression
introduced. golden.json is a pure data artifact; no test file was
required per PLAN.md Task 3 ("Test: covered by the runner test (Task 4)").

## Smoke

Seeded S1-S4 fixtures into the real catalogue
(`python3 cli/eval/fixtures.py --root ~/Obsidian/Knowledge-Catalogue --seed`),
ran every one of the 12 golden rows via subprocess against
`okf-cli.py` (find/list/index --json), and asserted observed
hit/miss + rank/score-ratio against each row's thresholds:

| id | verb | observed | expected |
|----|------|----------|----------|
| s1-literal | find | hit, rank 1, ratio 0.417 | hit, rank<=1, ratio>=0.30 |
| s1-paraphrase | find | miss (zero-hit) | miss |
| s2-literal | find | hit, rank 1, ratio 0.333 | hit, rank<=1, ratio>=0.25 |
| s2-paraphrase | find | miss (zero-hit) | miss |
| s3-literal | find | hit, rank 4, ratio 0.167 | hit, rank<=4, ratio>=0.10 |
| s3-paraphrase | find | miss (zero-hit) | miss |
| s4-literal | find | hit, rank 1, ratio 0.667 | hit, rank<=1, ratio>=0.55 |
| s4-paraphrase | find | miss (zero-hit) | miss |
| s4-index-walk | index | hit (listed in agent-memory TOC) | hit |
| s1-list-metadata-hit | list | hit | hit |
| s4-list-metadata-miss | list | miss | miss |
| s2-list-location-miss | list | miss | miss |

Result: 12/12 rows PASS. Teardown ran immediately after
(`--teardown`); catalogue verified clean:
`git -C ~/Obsidian/Knowledge-Catalogue status --short` → only
pre-existing untracked `.claude/` (unrelated, present before this
task started), zero fixture residue.

## Deviations/ERRATA

- The S3 literal query is bare "zqxeval" (no disambiguating word),
  by design: S3's scenario IS the low-rank case (token only in body,
  no matching title/tags), so a maximally-generic literal query is
  the correct probe — its low rank/ratio (4, 0.167) is the expected
  signal, not a defect. All other literal queries add one extra
  literal word from the fixture's own body text to break score-ties
  among S1/S2/S4 (which all embed "zqxeval" in title+body identically)
  — verified empirically these ties are real (bare "zqxeval" 3-way
  ties S1/S4/S2 at 4/6) and would make golden.json's per-fixture rows
  ambiguous without disambiguation.
- Chose `query` as a JSON string for `find` rows but a JSON object for
  `list`/`index` rows (not a uniform string), since PLAN.md's interface
  line names a single `query` field without prescribing its shape, and
  a dict avoids fragile shell-arg parsing in the Task 4 runner. Flagged
  explicitly below for the next implementer.
- No new test file added (`cli/test_eval_runner.py` is Task 4's,
  per PLAN.md: "Test: covered by the runner test (Task 4)"). Validation
  proof for this task is the empirical smoke run above instead of TDD,
  matching the bean's stated "Beweisform" allowance for data artifacts.

## Notes for T(n+1)

- `golden.json` is a bare JSON array (not wrapped in an object), per
  the PLAN.md interface line ("a list of ... rows") — `json.load()`
  gives you the list directly.
- `query` field shape by verb: `find` → plain string (pass straight
  as the CLI `query` positional). `list` → dict with optional keys
  `type`/`tag`/`scope`, map 1:1 to `--type`/`--tag`/`--scope` flags
  (omit the flag if the key is absent — see `s1-list-metadata-hit`
  etc., all three currently share the same query dict but differ in
  `expected_path`/`expect`, which is intentional: one `list` invocation
  answers three separate assertions). `index` → dict with `bundle` key,
  pass as the positional `bundle` arg; use `--json` and read
  `d["concepts"]`, building `"{bundle}/{concept_id}"` for comparison
  against `expected_path`.
- `expected_path` form: `find` → `"{bundle}/{concept_id}"` (matches
  the `path:` line the CLI prints, okf-cli.py:586). `list`/`index` →
  same `bundle/concept_id` form (`list --json` "path" field already
  strips `.md`; index's json only gives `id`, so runner must prefix
  bundle).
- `expect` semantics: for `find` rows, "hit" means the row's
  `expected_path` receives nonzero score (appears in output at all,
  regardless of rank quality — see S3), "miss" means zero-hit
  (expected_path absent from find's hit list entirely). This is
  deliberately reused for the paraphrase rows to encode the
  literal-vs-paraphrase delta as the primary optimization signal
  (EVAL-DESIGN.md:22-23) — a future hybrid-retrieval pass flipping a
  paraphrase row from observed miss to observed hit is the target
  regression-in-the-good-direction to watch for.
- `min_rank`/`min_score_ratio` are `null` for every row where they
  don't apply (all paraphrase rows — zero-hit expected, rank/ratio
  undefined; all `list`/`index` rows — no ranked score exists for
  those verbs). Where non-null, semantics are: `rank <= min_rank` and
  `score_ratio >= min_score_ratio` both must hold for the row to pass
  (validated this exact way in the smoke run above).
- Fixture bundle placement (`correct_bundle`/`wrong_bundle`) is
  resolved dynamically by `fixtures.py::_pick_bundles()` as the first
  two non-symlink bundles in `list_bundles()` order. Against the
  current real catalogue that resolves to `agent-memory` (correct) /
  `ai-wiki` (wrong) — golden.json hardcodes these two bundle names.
  If the catalogue's non-symlink bundle set changes such that
  `agent-memory`/`ai-wiki` are no longer the first two, golden.json's
  `expected_path`s will silently stop matching fixtures.py's actual
  seed locations; Task 4's runner should ideally re-derive
  `correct`/`wrong` bundle names from `fixtures.py._pick_bundles(root)`
  rather than trust golden.json's hardcoded paths blindly, or at least
  assert-fail loudly rather than silently miss. Flagging this as a
  latent coupling, not fixing it here (out of Task 3 scope).
