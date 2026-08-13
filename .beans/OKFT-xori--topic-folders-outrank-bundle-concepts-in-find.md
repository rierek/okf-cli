---
# OKFT-xori
title: Topic folders outrank bundle concepts in find
status: todo
type: bug
priority: high
created_at: 2026-07-27T06:36:10Z
updated_at: 2026-08-13T11:24:39Z
parent: OKFT-wmbu
blocked_by:
    - OKFT-n8xz
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


## Verdict 2026-08-13 — the question is settled, this bean now waits on the fix

The "Question to settle" above is **answered**. Erik signed D16 and D17 on 2026-08-13 in `lean-stack/docs/aca_capability-mcp/DECISIONS.md:31-32`.

All four candidate mechanisms listed above are **rejected**, verbatim from D16: "Keiner der vier Kandidaten ist mehr nötig." Do not implement a bundle boost, a topic-folder exclusion heuristic, an opt-in flag or an `*-inbox` rule off the back of this bean.

The chosen mechanism instead honours a declaration that already exists: `.okf.toml` names its bundle in every repo docs root (`bundle = "lean-stack-okf"`, `bundle = "okf-tools-okf"`), and `okf-cli` already parses that file via `load_okf_config` for `types_source` and `wikilink_checked_bundles` without ever reading the `bundle` key. Where the key is present it defines the indexable set; where it is absent the existing name filter stands, which is correct for the catalogue. D17 confines the narrowing to the index/search corpus only — `is_bundle_dir` is not touched, and resolution, rename and wikilink integrity keep the wide set.

Both defects reported above are covered:

1. *Working notes outrank canon* — the corpus drops from 197 to 41 in `lean-stack/docs`, so 79% of the search space disappears rather than being re-weighted (R37: a ranking boost alone would leave the corpus share untouched).
2. *Un-drained inbox competes with canon* — `docs/lean-stack-okf-inbox/` and `docs/okf-tools-okf-inbox/` are not the declared bundle and fall out of the corpus with everything else.

**Dependency corrected the same day.** This bean previously blocked OKFT-n8xz, which was circular: the only way to resolve this bug is for OKFT-n8xz to land. The edge is reversed — this bean is now `blocked_by: OKFT-n8xz` and closes once the fix has landed and OKFT-glon has proved it did not strand wikilinks.
