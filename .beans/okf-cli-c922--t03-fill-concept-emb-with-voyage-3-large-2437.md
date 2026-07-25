---
# okf-cli-c922
title: T03 Fill concept_emb with voyage-3-large (2437)
status: todo
type: task
priority: high
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-25T23:32:25Z
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
