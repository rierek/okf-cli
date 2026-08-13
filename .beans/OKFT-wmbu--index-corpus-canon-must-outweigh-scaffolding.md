---
# OKFT-wmbu
title: 'Index corpus: canon must outweigh scaffolding'
status: todo
type: epic
priority: high
created_at: 2026-08-13T11:07:04Z
updated_at: 2026-08-13T11:22:10Z
---

Root cause behind OKFT-xori and OKFT-oe8t: the catalogue has no notion of a topic folder. is_bundle_dir (okf-cli.py:68-69) is a two-clause name filter - anything without a leading dot or underscore is a bundle - and it never opens the directory. Correct at the catalogue root, where every top-level directory really is a bundle; wrong for every directory but one in a repo docs root.

Measured 2026-08-13 against lean-stack/docs: the FTS corpus holds 197 documents, of which 41 are bundle concepts (21%) and 156 are TPIC scaffolding (79%). Over ten real agent queries, 64 of 87 global hits (74%) were scaffolding, and scaffolding held rank 1 in six of ten. Six dispatched agents issued ten find calls, none of them scoped.

The missing distinction is already declared: .okf.toml carries bundle = "<name>" in every repo docs root. okf-cli parses that file through load_okf_config and consumes types_source and wikilink_checked_bundles from it, but never reads the bundle key.

Requirement: honour the declaration for the index and search corpus only. Full rationale in lean-stack docs/aca_capability-mcp/DECISIONS.md D16/D17 and REFERENCES.md R33-R42.


## Baseline 2026-08-13 (Supervisor, before the first change)

`just test` — 675 tests, 26.97 s, **3 pre-existing failures**, all in `cli/test_eval_runner.py::RunnerAgainstRealCatalogueTest`:

- `test_runner_scores_literal_s1_top1` (:375) — `AssertionError: inf != 1`
- `test_metadata_hit_and_miss_rows_scored_correct` (:410) — `AssertionError: False is not true`
- `test_index_walk_row_present_with_rank_no_dedicated_metric` (:420) — `AssertionError: inf != 1`

Runner metrics in the same output: `recall_at_1 0.000`, `recall_at_5 0.000`, `mrr 0.000`, `zero_hit_rate_literal 1.000`, `zero_hit_rate_paraphrase 1.000`, `metadata_hit_rate 0.500`, `catalogue_rev: 685dee9`. `rank: inf` means the golden fixture was not retrieved at all, so the whole runner is measuring a zero-hit catalogue, not a ranking regression.

These three tests measure against the live catalogue `~/Obsidian/Knowledge-Catalogue` (the substrate OKFT-5c2c wants to remove). They are **independent of OKFT-n8xz** by construction: the catalogue `.okf.toml` carries no `bundle` key (verified 2026-08-13; only `wikilink_checked_bundles`), so the declaration rule from D16 falls back to the existing name filter there and the catalogue corpus is unchanged. Whoever lands OKFT-n8xz must show these three still fail identically and no fourth failure joins them.

Do not attribute these three to any commit of this epic.


## Q01 — should the FTS rebuild hook cover repo-local docs bundles? (2026-08-13, open, PO)

OKFT-iaxj D03 (PO, 2026-08-03) scopes the `SessionStart` rebuild hooks to `kc_root` and explicitly excludes repo-local `docs/*-okf` bundles. Verified 2026-08-13: `lean-stack/docs/.fts/fts.sqlite` therefore has no automatic trigger of any kind — not via hook, justfile, git-hook, cron or launchd.

That exclusion is what let the index behind this epic's own measurement go 15 days stale (R37), so every number in R33-R37 was taken against a corpus that understated the current state. The defect is real regardless, but the measurement was distorted by a policy decision, not by an accident.

Question: extend the hooks to repo-local docs roots, or leave D03 standing and accept a manual rebuild after corpus-affecting changes? Not blocking OKFT-pwap — that task rebuilds once by hand either way.
