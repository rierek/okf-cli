---
# okf-cli-o7z2
title: P4 — Mechanical eval runner (Modus A)
status: in-progress
type: task
priority: normal
created_at: 2026-07-25T18:13:10Z
updated_at: 2026-07-25T18:53:01Z
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
