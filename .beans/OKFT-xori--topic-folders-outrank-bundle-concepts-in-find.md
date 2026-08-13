---
# OKFT-xori
title: Topic folders outrank bundle concepts in find
status: completed
type: bug
priority: high
created_at: 2026-07-27T06:36:10Z
updated_at: 2026-08-13T13:10:29Z
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


## Closed 2026-08-13 — the fix landed and was proven

Both defects reported in this bean are resolved, and the proof is external to the implementer's own word.

**Defect 1, working notes outrank canon.** OKFT-n8xz narrowed the index/search corpus to the bundle declared in `.okf.toml`. Measured against the rebuilt `lean-stack/docs` index (OKFT-pwap): 197 documents down to 52, all 52 under `lean-stack-okf`, not one topic-folder document left. Verified independently by direct SQLite query against the shipped index, not by re-running the builder.

The claim this bean actually made — that scaffolding outranks canon — was retested on its own terms. R34 recorded the query `dev-CLI Kanon Entrypoint Wrapper Shims` returning 8 of 9 hits from topic folders with `lean-stack-okf/dev-cli-canon` at rank 4. The same query now returns `lean-stack-okf/dev-cli-canon` at **rank 1**, with all ten hits under `lean-stack-okf`.

**Defect 2, un-drained inbox competes with canon.** `docs/lean-stack-okf-inbox/` is not the declared bundle and left the corpus with everything else. No special `*-inbox` rule was needed.

**The monotonic degradation this bean predicted is stopped at the source.** It said "every new think session adds noise on top of the same canon". A new think session now adds nothing to the corpus at all, because the corpus is a declaration rather than a leftover of a name filter.

**What it cost, recorded because this bean asked the question that started it.** The four candidate mechanisms proposed here were all rejected by D16 in favour of reading a key that was already being parsed. That was the right call, and it was still not the hard part. The hard part was D17's confinement — narrowing only the corpus, never the resolution — and following D17's own call-site list literally would have broken it twice. See OKFT-wmbu for both occurrences.
