---
# OKFT-e9hm
title: 'P13 — Modus B: agentic realism check (SEPARATE session)'
status: completed
type: task
priority: normal
tags:
    - separate-session
created_at: 2026-07-25T18:13:10Z
updated_at: 2026-08-10T12:49:55Z
parent: OKFT-s3ee
blocked_by:
    - OKFT-6gq6
---

## Objective (User Story)
As the PO, I want an agentic realism check of the whole retrieval loop, run by a separate agent session, so that real query-formulation success is sanity-checked beyond the mechanical metric.

## EARS Acceptance
- THE bean SHALL be executed in a SEPARATE agentic session (NOT ce-implementer) — D12.
- THE task set SHALL cover >=1 paraphrase-style retrieval per scenario S1-S4 and record agent success/failure as qualitative sanity, explicitly excluded from the gate metric.

## Success Criteria
- SC-001: `cli/eval/modus-b-tasks.md` authored (task prompts + rubric).
- SC-002: outcomes recorded, marked non-gating sanity.

## Note
Author the task set (this bean); the agentic run happens in a separate session with only okf MCP tools. Full steps: PLAN.md Task 13.
Commit: `docs(eval): Modus B agentic realism task set`

## Prelude 2026-07-25 — Steps 1-2 done inline (PF-1), Step 3 stays SEPARATE

cli/eval/modus-b-tasks.md authored + committed: 5 task prompts (>=1 paraphrase per S1-S4 + 1 literal control), rubric (outcome/calls/verbatim query/provenance/friction), preconditions (seed + concept_emb swap-in + teardown/restore), reporting format. Execution (Step 3) MUST run in a separate agentic session with only mcp__okf__* tools — this bean stays open until that session records outcomes here. Watch item from P12: S2/S4 paraphrase not mechanically rescued — agent reformulation/browsing success there is the key Modus-B signal.


## Pointer update 2026-08-10

The task set moved out of `cli/` (repo convention: all markdown lives under /docs) and is now `docs/okf-revision/modus-b-tasks.md`. Content unchanged, git rename, frontmatter added.


## Step 3 executed 2026-08-10 (separate session, five fresh agents)

Report: `docs/okf-revision/MODUS-B-REPORT.md`. Task set revised first — PO decision 2026-08-10 replaced the seeded S1-S4 fixtures with five real catalogue concepts (`modus-b-tasks.md`, section "Revision 2026-08-10"), because a faithful fixture run would now require rebuilding the live `.fts` index and producing embeddings for the fixtures, three mutations of live state that `okf-tools/CLAUDE.md` rule 1 forbids.

Outcome 5/5 success, four of them on a single search call. R2 closes the PO's own zero-hit counter-test from 2026-07-25: the paraphrase hits rank 1 through the semantic arm, and the literal original query `find "mockup tailscale"` now returns the target at rank 2 instead of not at all. R4 succeeded purely by index-walk without any search. Catalogue and both indices bitwise unchanged across the run (git status empty, md5 of `.tagvec/tag_vectors.sqlite` and `.fts/fts.sqlite` identical before and after).

Findings carried out of the run: B01 the `semantic arm owns this ranking` banner spans the whole list while the carrying hit may be lexical, attributable only by a missing marker; B02 catalogue duplicates (`ralph-wiggum-loop` threefold, `integration` twofold) plausibly steal the BM25 margin; I01 the semantic arm missed its own core case in R1 (user-language paraphrase failed to surface a concept whose title carries the term literally, rescued only by jargon reformulation); I02 two incompatible score scales in one list, reported independently by three agents; I03 catalogue-level `okf_index` is expensive for budgeted browse; I04 `type: Decision` filed outside `decisions/`; Q01 superseded decisions are not marked as such.

Non-gating by contract (D12) — qualitative sanity only, excluded from the P12 gate metric.
