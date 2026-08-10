---
# OKFT-xori
title: Topic folders outrank bundle concepts in find
status: todo
type: bug
priority: high
created_at: 2026-07-27T06:36:10Z
updated_at: 2026-08-03T19:37:57Z
---

## Context

Field observation from the lean-stack `dev-cli-layering` think session (2026-07-27),
running `okf-cli --root docs` against the lean-stack repo.

`is_bundle_dir` treats every non-`.`/`_` directory under `docs/` as a bundle. This is
already known for `check` — the lean-stack `docs/CLAUDE.md` documents the workaround
(always pass a positional bundle target, otherwise ~36 foreign violations from
topic-slug folders). The same root cause produces a second, undocumented symptom in
`build-index` / `find`: topic-slug think folders are indexed as first-class concepts
and outrank the canonical bundle.

## Evidence

`okf-cli --root docs build-index` indexed 133 concepts.
`okf-cli --root docs find "just dev-cli"`:

| rank | hit | score |
|------|-----|-------|
| 1-3 | `dev-cli-layering/DECISIONS`, `/REFERENCES`, an imported kickoff note | 100/100 |
| 4 | `lean-stack-okf/dev-cli-canon` (the canonical concept) | 99/100 |
| 5 | `lean-stack-okf-inbox/dev-cli-canon` (an un-drained ingest duplicate) | 99/100 |
| - | `lean-stack-okf/dev-cli-audit-checklist` | absent from top 8 |

Two distinct defects surface here:

1. **Working notes outrank canon.** A live think session's DECISIONS/QUESTIONS/REFERENCES
   files rank above the ingested concept they were derived from. The store applies no
   weighting between durable bundle knowledge and in-flight scaffolding. This degrades
   monotonically: every new think session adds noise on top of the same canon.
2. **Un-drained inbox competes with canon.** `docs/lean-stack-okf-inbox/` still holds
   `dev-cli-canon.md` and `dev-cli-conformance.md` as duplicates of already-ingested
   concepts, indexed at near-identical scores.

## Question to settle

Should `find` weight canonical bundle concepts over topic-folder notes? Candidate
mechanisms: bundle boost in ranking; exclude non-bundle topic dirs from `build-index`
by default; require an explicit opt-in flag to include them; treat `*-inbox/` as
never-indexable.

Relates to the scoping workaround documented in lean-stack `docs/CLAUDE.md`, and to the
`--root` safety work in OKFT-1617.
