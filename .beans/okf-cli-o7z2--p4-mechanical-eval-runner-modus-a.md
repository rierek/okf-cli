---
# okf-cli-o7z2
title: P4 — Mechanical eval runner (Modus A)
status: completed
type: task
priority: normal
created_at: 2026-07-25T18:13:10Z
updated_at: 2026-07-25T19:05:40Z
parent: okf-cli-2lpu
blocked_by:
    - okf-cli-ez6f
    - okf-cli-n9l6
---

## Objective (User Story)
As the maturity gate, I want a deterministic runner that scores golden queries and emits a metric table so that keyword vs hybrid retrieval can be compared numerically.

## EARS Acceptance
- WHEN `run()` executes against a seeded catalogue, THE runner SHALL emit all eight metrics (recall_at_1, recall_at_5, mrr, zero_hit_rate_literal, zero_hit_rate_paraphrase, mean_score_ratio, location_correct_rate, metadata_hit_rate) and a per-row rank for every golden query.
- WHEN scoring a `list` row, THE runner SHALL compare actual hit/miss against the row's `expect` field and fold it into location_correct_rate (S2) or metadata_hit_rate (Ziel-3, EVAL-DESIGN.md:31,41-42).
- THE runner SHALL record the catalogue git rev into the result blob.
- WHEN a query returns zero hits, THE runner SHALL record rank=inf and count toward the class zero-hit-rate (never crash).

## Success Criteria
- SC-001: S1 literal row scores rank 1, recall_at_1 > 0.
- SC-002: result blob carries all eight metrics + catalogue_rev.
- SC-003: invokes find/list/index via subprocess against okf-cli.py.

## Affected code
- Create `cli/eval/runner.py`: `run(catalogue_root, golden_path) -> dict`, `main()` CLI `--root --golden [--out]`.
- Test: `cli/test_eval_runner.py`
Consumes P2 (seed/teardown), P3 (golden.json). Produces run()-shape consumed by P5,P12. Full steps: PLAN.md Task 4.
Commit: `feat(eval): mechanical golden-file eval runner (Modus A)`

## Prelude 2026-07-25 (from P2 completion, okf-cli-ez6f)

- EVAL-DESIGN.md EXISTS at ~/Obsidian/Vault/okf-revision/EVAL-DESIGN.md (P2 bean's original deviation note claiming otherwise was wrong; corrected).
- Fixtures are TRANSIENT by design (reviewer-confirmed conformant): the eval runner must call cli/eval/fixtures.py seed()/teardown() around its own runs and leave the real catalogue clean.

## Prelude 2026-07-25 — from P3 review (okf-cli-n9l6, non-blocking F01)

The s4-index-walk golden row only holds when the runner invokes 'index agent-memory --json' (live iter_concepts scan). The plain 'index agent-memory' reads the bundle's static cached index.md block, which does NOT list freshly seeded fixtures — the human-facing TOC surface stays unmeasured. Open design question flagged to PO (Q01 in supervisor status report): should index-walk also assert against the rendered index.md, or is --json the sole measurement surface? Until PO answers: build the runner on --json (as P3's Notes for T(n+1) already prescribe); do NOT silently add an index.md assertion.


## Summary

Implemented cli/eval/runner.py: run(catalogue_root, golden_path) -> dict and a
main() CLI (--root/--golden/--out). For every cli/eval/golden.json row it
invokes find/list/index against okf-cli.py via subprocess (same boundary
mcp/okf_mcp.py uses), parses the `------`-delimited find blocks or --json
output, locates the row's expected_path, records a per-row rank (rank=inf on
zero-hit, never crashes), and aggregates the eight metrics: recall_at_1,
recall_at_5, mrr, zero_hit_rate_literal, zero_hit_rate_paraphrase,
mean_score_ratio (all from find rows, literal/paraphrase split),
location_correct_rate (S2 list --scope rows), metadata_hit_rate (Ziel-3
list(type,tag) rows). catalogue_rev captured via `git -C <root> rev-parse
--short HEAD`. Fixtures are NOT seeded/torn down inside runner.py itself —
callers (tests, Task 5's baseline freeze) own that window explicitly, per the
P2-completion prelude.

## Test-Output (RED -> GREEN)

RED (runner.py absent, cli/test_eval_runner.py written first):

    FileNotFoundError: [Errno 2] No such file or directory:
    '/Users/erik/Obsidian/tools/okf-tools/cli/eval/runner.py'

GREEN after implementing cli/eval/runner.py (9 new tests, real catalogue):

    Ran 9 tests in 11.773s
    OK

Full test-substrate delta:
    BEFORE: python3 -m unittest cli.test_okf_cli cli.test_okf_mcp cli.test_eval_fixtures
            -> Ran 116 tests, FAILED (failures=19, errors=2)
    AFTER:  python3 -m unittest cli.test_okf_cli cli.test_okf_mcp cli.test_eval_fixtures cli.test_eval_runner
            -> Ran 125 tests, FAILED (failures=19, errors=2)
    Delta: +9 tests, all new tests green, 0 new failures/errors (pre-existing
    19F/2E unchanged, matches P2/P3 baseline note).

## Smoke

Real eval run against the live catalogue (seed -> run -> teardown, all via
the actual CLIs, not the test harness):

    python3 cli/eval/fixtures.py --root ~/Obsidian/Knowledge-Catalogue --seed
    python3 cli/eval/runner.py --root ~/Obsidian/Knowledge-Catalogue \
        --golden cli/eval/golden.json --out <scratch>/smoke-result.json
    python3 cli/eval/fixtures.py --root ~/Obsidian/Knowledge-Catalogue --teardown

Result metrics (keyword baseline, catalogue_rev f0714b2):

    recall_at_1                0.750
    recall_at_5                1.000
    mrr                        0.812
    zero_hit_rate_literal      0.000
    zero_hit_rate_paraphrase   1.000
    mean_score_ratio           0.396
    location_correct_rate      1.000
    metadata_hit_rate          1.000

All 12 golden rows scored `correct=true` (each row's actual outcome matched
its designed expect), including S3-literal at rank 4 (field-weighting gap,
by design) and S2/S4 metadata/location rows. Catalogue end-state confirmed
clean: `find ~/Obsidian/Knowledge-Catalogue -iname "_okfeval-*"` returns
nothing; `git -C ~/Obsidian/Knowledge-Catalogue status --short` shows only
the pre-existing unrelated `?? .claude/` (not touched by this task).
Smoke artifact NOT committed (Task 5 owns freezing the baseline into
cli/eval/results/ — out of this task's scope).

## Deviations/ERRATA

- FIRST commit title landed at 56 chars ("feat(eval): mechanical golden-file
  eval runner (Modus A)"), violating the ≤50-char rule; amended in-place to
  "feat(eval): mechanical eval runner (Modus A)" (44 chars) before any
  push/review — same-turn self-correction, not a silent late edit.
- No other deviation from PLAN.md Task 4 / bean AC. index-walk rows are
  scored and carry a per-row rank but intentionally fold into no aggregate
  metric (the bean names exactly eight; per the P3-review prelude, index-walk
  stays --json-only, no index.md assertion added).

## Notes for T(n+1)

- Task 5 (freeze baseline) can reuse this exact smoke recipe verbatim:
  seed -> `runner.py --out cli/eval/results/baseline-<rev>.json` -> record
  headline metrics in PLAN.md -> teardown -> commit the frozen file. The
  smoke run above already shows the numbers that freeze would capture
  (catalogue_rev f0714b2) — re-run at freeze time in case catalogue state
  drifted.
- `_score_list_row`/`_score_index_row` treat "found at all" as rank=1 (list/
  index aren't ranked outputs) — if a future task needs finer-grained
  list-ranking (e.g. position within list's alphabetical sort), that is not
  implemented; only hit/miss is scored today, matching the bean's AC2.
- FIND_LIMIT is hardcoded to 50 in runner.py (vs okf-cli's own default 10)
  so a golden row's true rank is never truncated. If golden.json ever adds a
  fixture whose designed rank exceeds 50, bump this constant.
