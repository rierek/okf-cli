---
# okf-cli-3520
title: Producer leaves stale concept_emb rows on content change
status: todo
type: bug
priority: normal
created_at: 2026-07-26T07:14:42Z
updated_at: 2026-07-26T07:14:58Z
parent: okf-cli-wuiv
---

Found by ce-specs-reviewer during the T07 re-review (`okf-cli-8j7l`), 2026-07-26. Latent
today, not manifesting — filed so it is not rediscovered as a mystery later.

## Defect

`concept_emb` can accumulate MORE THAN ONE row per concept path.

- Schema: `PRIMARY KEY` is `key` = hash of content + path, NOT `path`
  (`cli/embeddings/build_tagvec.py:82-83`).
- Producer: `INSERT OR REPLACE` keys on `key` and never deletes the previous row
  (`cli/embeddings/build_tagvec.py:253`).
- Consequence: every time a concept's CONTENT changes, its `key` changes, a new row is
  inserted, and the stale row for the same `path` stays behind forever.

## Why it matters

Consumers that size a candidate window by path count are then undersized. Concretely,
`cmd_find`'s shim over-fetches `limit + len(exclude)` candidates on the assumption of at most
one row per excluded path (`cli/okf-cli.py:1126-1140`). With duplicates, a genuinely eligible
candidate can be dropped — the same failure class as the T07 blocker B01, reached by a
different trigger. `fuse_conditional` (T08) reads the same vector list and inherits the
assumption.

Note the predecessor `semantic_backstop(exclude_paths=...)` was only ACCIDENTALLY robust here:
its unconditional generator-side filter strips every matching row regardless of count. It
likewise never deduped a non-excluded duplicate path in its output. So this is pre-existing
debt, not a regression introduced by T07.

## Current state (measured)

`~/Obsidian/Knowledge-Catalogue/.tagvec/tag_vectors.sqlite` holds **0 duplicate-path rows**
right now — `concept_emb` has 2443 rows and 2443 distinct paths after the T03 full fill. The
defect is latent because the table was filled in one pass; it will start manifesting as
concepts get edited and re-embedded.

## Suggested fix (not scoped here)

Producer-side prune: after writing a batch, delete rows whose `path` matches a just-written
row but whose `key` differs. Alternatively add a uniqueness constraint on `path` per model, or
have the consumer dedupe by path when loading vectors. Decide deliberately — the consumer-side
fix hides the storage growth, the producer-side one prevents it.

## Verification when fixed

Edit a concept, re-run `--produce`, and assert `select count(*) from concept_emb` equals
`select count(distinct path) from concept_emb` for the model.
