---
# OKFT-wsne
title: Nothing triggers the concept_emb producer
status: draft
type: bug
priority: high
created_at: 2026-08-10T13:11:08Z
updated_at: 2026-08-10T13:16:58Z
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


## Partially addressed 2026-08-10

Two of three halves are done; the trigger itself is not.

Done — the gap was closed once: the producer ran over 166 concepts (`--target concepts --model voyage-3-large --produce`), live coverage is now 2590 of 2590. The R1 query that found nothing returns its target at rank 1.

Done — the gap is no longer silent (commit b7d43a9): `prime` reports `semantic index: complete | partial — N of M | absent`, mirroring what `fts index:` already stated. Counted by comparing PATH SETS rather than row totals, because the 74 orphan rows for deleted concepts would otherwise let a row count mask a real gap — a guard that passes at the moment it matters is not a guard. Three tests, RED before the change, including a counter-mutation asserting a complete index is NOT reported as partial.

Open — nothing still triggers the producer. SC-001 is only half met: staleness is observable through `prime`, not yet at `find` time, and no mechanism updates the index when concepts are added. The FTS analogue is a Stop hook (OKFT-iaxj); the equivalent here needs a network call and an API key, which is why it is a decision rather than a copy. That decision is what remains in this bean.
