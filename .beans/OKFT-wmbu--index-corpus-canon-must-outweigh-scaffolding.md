---
# OKFT-wmbu
title: 'Index corpus: canon must outweigh scaffolding'
status: todo
type: epic
priority: high
tags:
    - to-review
created_at: 2026-08-13T11:07:04Z
updated_at: 2026-08-13T13:13:03Z
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


## Gate B 2026-08-13 — verdict OPERATIONALIZATION_GAPS, resolved before dispatch

`ce-verify-operationalization` checked the six child beans against D16/D17 and R33-R42, and re-verified every cited line number against `cli/okf-cli.py`. Textual fidelity to the source was high; the gaps were in the source and in the bean graph, not in the transcription.

Two blocking findings, both resolved by the supervisor before any implementer ran:

- **B01 — the source's own call-site census was incomplete.** Lines 745, 793 and 3326 feed the index/search corpus and appeared in neither of OKFT-n8xz's lists. Each is the `_archive/` sibling of a call site already on the positive list. Resolved in OKFT-n8xz D01: all three join the positive list, which is now 740, 745, 785, 793, 851, 3312, 3317, 3326. Rationale there.
- **B02 — the blocked_by edge was circular.** OKFT-n8xz was blocked by OKFT-xori, whose only possible resolution is OKFT-n8xz landing. Edge reversed: OKFT-xori is now blocked_by OKFT-n8xz and closes once the fix is proven.

Non-blocking findings, all resolved:

- Negative-list line `560` is off by one; the token sits on 561. Corrected in OKFT-n8xz.
- OKFT-oe8t cited `iter_all_md` at :2582; it is at :2883, pruning clause :2888-2890. ERRATA appended there.
- OKFT-xori still read as an open question with four candidate mechanisms that D16 explicitly rejects. Verdict appended so a fresh agent cannot implement a rejected candidate.
- OKFT-0k55 named the defect but no target behaviour. Acceptance and D01 (exit 0) appended.
- OKFT-pwap bundled a design question with a mechanical step. The design half turned out to be already settled by OKFT-iaxj D03; research prelude appended there, remainder raised as Q01.
- This bean cited "R33-R42" as full rationale. R41 (Go-vs-Python latency) and R42 (stdlib dependencies) belong to D21, the Go-rewrite question, not to D16/D17. **Read the citation as R33-R40.**

### Cross-repo note for the PO

B01 is not only a bean defect — `lean-stack/docs/aca_capability-mcp/REFERENCES.md:97` (R40) and `DECISIONS.md:32` (D17) carry the same incomplete census. The think session that owns those files should know that its call-site enumeration missed the three archive branches.

## Q02 — exit status on a broken pipe (2026-08-13, open, PO)

OKFT-0k55 gets exit **0** on a clean early close, so `okf-cli find x | head` does not trip `set -o pipefail`. The competing convention is 141 (128+SIGPIPE), which the CLI-program conformance spec drafted in lean-stack D20 may prefer. Not blocking — one-line change if D20 says otherwise.


## Q03 — does `okf-cli list` belong to the index corpus? (2026-08-13, open, PO)

`cmd_list` (okf-cli.py:641) resolves its scope through `resolve_scopes` and appears in neither of D17's lists — neither index/search nor presentation. It is the third site the source's census missed, after the archive branches (B01 at Gate B).

The argument for narrowing: `list --type Concept` in a repo docs root is a retrieval question, and the eval runner already scores `list(type,tag)` rows under `metadata_hit_rate`. Scaffolding pollutes that answer the same way it pollutes `find`.

The argument against: `list` is also how one sees what is actually on disk, and narrowing it silently shrinks that view.

Left **wide** for now, because wide is the conservative default and because narrowing it is not required by anything this epic promised. One-line change either way.

## Note on the source census, second occurrence

Gate B found D17/R40 missing three archive branches. The review of OKFT-n8xz found the same class again, worse: D17 lists `resolve_scopes` (3312, 3317) as "Index/Suche → find", but ten commands go through that function, including `check` and `wikilinks` — the very integrity paths D17 wants kept wide. Following the list literally produced exactly the silent defect D17 was written to prevent.

The lesson is not that D17 is wrong — its principle held and is what caught this. The lesson is that a call-site census taken by reading is not a census. Both occurrences should go back to the think session that owns `lean-stack/docs/aca_capability-mcp/`.


## Epic complete 2026-08-13 — all six leaves closed, ready for PO review

Full gate on the merged state: `Ran 701 tests in 27.846s`, `FAILED (failures=3)` — exactly the three `RunnerAgainstRealCatalogueTest` failures recorded in the baseline above, no fourth. Test count grew 675 to 701. `beans check` clean, working tree clean.

### What the epic promised and what it delivered

The corpus in `lean-stack/docs` fell from **197 documents to 52**, all 52 under `lean-stack-okf`, not one topic-folder document left — verified by direct SQLite query against the shipped index rather than by re-running the builder. The bean predicted 41; the difference is organic growth of `lean-stack-okf` since the 2026-08-13 measurement, 24 commits touching that directory since 2026-08-01, independently reproduced (Q02).

The behavioural claim was retested on R34's own terms. Query `dev-CLI Kanon Entrypoint Wrapper Shims` returned 8 of 9 hits from topic folders with the canonical `lean-stack-okf/dev-cli-canon` at rank 4. It now returns that concept at **rank 1**, with all ten hits under `lean-stack-okf`.

### Leaves

| bean | what landed |
|---|---|
| OKFT-n8xz | `list_indexable_bundles` from the `.okf.toml` `bundle` key, applied at the index/search sites only; `is_bundle_dir` untouched |
| OKFT-glon | break-test in both directions against the real repo, plus a counter-probe proving the probe can fail |
| OKFT-xori | closed on evidence, both reported defects resolved |
| OKFT-oe8t | `iter_concepts` prunes `_`-prefixed staging; the three tag-mutation commands opt out explicitly |
| OKFT-0k55 | broken-pipe handling at the entry point, exit 0, no traceback, no shutdown noise |
| OKFT-pwap | index rebuilt, trigger question found already settled by OKFT-iaxj D03 |

### Three rounds of the same defect class, and it is the epic's real finding

A narrowing placed in a shared function reached callers nobody had classified — three times, twice from the source document and once from us. Gate B caught the missing `_archive/` branches before dispatch; the first review caught `resolve_scopes` serving ten commands including `check` and `wikilinks`; the third caught `iter_concepts` serving three file-writing tag commands. Both shared functions ended on the same shape: wide by default, narrowing explicit at the caller. Recorded as LL-35 in `docs/LESSONS-LEARNED.md`, with LL-36 on why a green suite of purpose-written fixtures proved nothing here.

**This should go back to the think session that owns `lean-stack/docs/aca_capability-mcp/`.** D17 and R40 carry a call-site census that was incomplete in two distinct ways. The principle in D17 held throughout and is what caught both errors; only its enumeration was wrong.

### Open for the PO

- **Q01** — should the `SessionStart` rebuild hooks cover repo-local docs bundles, or does OKFT-iaxj D03 stand? Blocks the recommendation on `build-semantic-index` in OKFT-pwap.
- **Q02** — 52 documents instead of the bean's 41. Growth-explained and independently reproduced; needs formal sign-off.
- **Q03** — does `okf-cli list` belong to the index corpus? Left wide, which is conservative and required by nothing this epic promised.

### Follow-ups filed, deliberately out of scope

`OKFT-epil` (opt-in flag for topic folders, deferred by D16 itself) · `OKFT-uctf` (arm `wikilink_checked_bundles` for this repo; `check` is currently blind to the failure class this epic guarded) · `OKFT-eyla` (writing commands disagree about `_` staging) · `OKFT-az0k` (broken-pipe handling does not cover stderr).

### Cross-repo

The rebuilt index is the new baseline for the re-measurement tracked as `lean-stack:LES-zr4r`. That measurement belongs to the session that owns it; nothing here touched that bean. `lean-stack` carries unrelated modifications from a parallel session (`0cfa3f0 feat(aca): map TPIC execution`) — not from this work, and the only file written there was the gitignored `docs/.fts/fts.sqlite`.
