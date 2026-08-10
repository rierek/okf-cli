---
# OKFT-wsne
title: Nothing triggers the concept_emb producer
status: draft
type: bug
priority: high
created_at: 2026-08-10T13:11:08Z
updated_at: 2026-08-10T13:11:08Z
parent: OKFT-hkze
---

## Objective (User Story)
As a catalogue user, I want every concept to be reachable by the semantic arm, so that retrieval quality does not silently decay as the catalogue grows.

## Evidence (MODUS-B-REPORT, Nachtrag 2026-08-10)
On 2026-08-10 the live `.tagvec` was missing vectors for 115 of 2589 concepts (4.4 %). Every one of them was added to the catalogue after the one-shot productive population — the earliest creation date among them is 2026-08-05. The producer knows its own delta (`build_tagvec.py` dry-run reported 166 concepts needing embedding, missing plus content-changed) and nothing invokes it. `.fts` has a rebuild trigger and a staleness notice; `.tagvec` has neither.

The cost is not theoretical: the R1 miss of the Modus-B run was exactly such a concept. Its paraphrase found nothing; after the fill it returns at rank 1.

## EARS Acceptance
- WHEN concepts are added or changed, THE semantic index SHALL be brought up to date without a human remembering to do it, by the same mechanism class that already keeps `.fts` current.
- WHERE the index cannot be updated (no API key, no network), THE degradation SHALL be announced, not silent — same shape as the existing `lexical index is stale` notice.
- THE trigger SHALL NOT embed on every find call; the network dependency stays out of the query path (D13/D16).

## Success Criteria
- SC-001: a catalogue change makes the semantic index stale and the staleness is observable to a CLI and an MCP consumer.
- SC-002: after the trigger runs, coverage is complete — asserted by a test that compares concept paths on disk against `concept_emb` rows.
- SC-003: `just test` green.

## Note
Related but distinct: OKFT-3520 (stale rows on content change — after the 2026-08-10 run no duplicate-per-path rows remain, verify there) and OKFT-uumj (make a stale concept_emb visible, the announcement half of SC-002). The 74 orphan rows for deleted files were NOT cleaned by the producer run and belong to OKFT-3520.
