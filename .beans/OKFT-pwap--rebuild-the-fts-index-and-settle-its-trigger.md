---
# OKFT-pwap
title: Rebuild the FTS index and settle its trigger
status: completed
type: task
priority: normal
created_at: 2026-08-13T11:07:31Z
updated_at: 2026-08-13T13:10:29Z
parent: OKFT-wmbu
blocked_by:
    - OKFT-n8xz
---

docs/.fts/fts.sqlite in lean-stack was last built 2026-07-29 - 15 days stale at time of measurement. Two topic folders created since (25 and 4 files) are absent from it, so every measurement taken against it understates the current state.

Settle what triggers a rebuild (Stop hook exists per OKFT-iaxj) and rebuild once the corpus scoping from OKFT-n8xz has landed, so the new baseline measures the fixed behaviour.


## Research prelude 2026-08-13 (ce-research, dispatched by the supervisor)

The "Stop hook exists per OKFT-iaxj" hint in this bean is **outdated in two ways**. Verified findings:

**The event is `SessionStart`, not `Stop`.** OKFT-iaxj D01 (PO decision 2026-08-03) rejected `Stop` because it fires per turn, not per session, and rejected `SessionEnd` because it cannot see out-of-band edits (Obsidian) made between sessions.

**The hook deliberately does not cover this index.** OKFT-iaxj D03 scopes the hook to the `kc_root` from `.okf.toml` — the Knowledge Catalogue — and explicitly excludes repo-local `docs/*-okf` bundles. Two hooks exist and both carry that limit:

- `~/.claude/hooks/fts-rebuild-if-stale.sh:38` runs `python3 $OKF_CLI_PY --root $kc_root build-index --if-stale`, registered under `hooks.SessionStart` in `~/.claude/settings.json` (timeout 5).
- `~/.claude/hooks/tagvec-rebuild-if-stale.sh:41` does the same for `build-semantic-index --if-stale`.

`$kc_root` is read from `/Users/erik/dev/okf-tools/docs/.okf.toml:3` and is therefore always `/Users/erik/Obsidian/Knowledge-Catalogue`. `lean-stack/docs/.fts/fts.sqlite` has no automatic trigger at all.

**No other trigger exists.** Checked and empty: no `build-index` recipe in either justfile (okf-tools :1-22, lean-stack :1-125); the lean-stack `.githooks/pre-commit` (:33,65,89) only runs `okf-cli check`, never `build-index`; okf-tools uses the global `~/.claude/git-hooks` with no fts reference; crontab and launchd carry nothing related.

**Machinery that already exists** in `cli/okf-cli.py`: `build_fts_index` (:695), `_fts_index_stale` (:760, stat-only — concept counts active/archived plus `newest_mtime` against `fts_meta`, unreadable meta counts as stale), `cmd_build_index` (:803) with `--if-stale` registered at :4743; semantic arm `cmd_build_semantic_index` (:825) with `--if-stale` at :4750, backed by `semantic_coverage` (:1845, content-hash via `plan_concept_delta`).

**No OKF concept fixes this policy** — it lives only in bean OKFT-iaxj. Nearest neighbour `okf-tools-okf/archive-lifecycle/include-archive-as-a-retrieval-dimension` describes the staleness counters but not the trigger.

**No duplicate bean.** OKFT-uumj and OKFT-3520 touch the semantic arm, not this trigger; lean-stack `LES-we5q` and `LES-plor` are completed.

### Consequence for this task

The rebuild itself is unblocked work: run `build-index` against `lean-stack/docs` once OKFT-n8xz has landed, and quote the resulting document count (expected 41, down from 197).

Settling the trigger is **not** open engineering — D03 already settled it as "kc_root only". What is open is whether that exclusion should stand now that this epic's own measurement was distorted by a 15-day-stale repo-local index. That is a new decision, not a re-run of D03. Raised to the PO as Q01 on the epic; do not decide it inside this task.


## Summary

Trigger question (half 1) was already settled by the research prelude — recorded here as closed, not re-decided: OKFT-iaxj D01/D03 scope the SessionStart rebuild hooks to \`kc_root\` only, so \`lean-stack/docs/.fts/fts.sqlite\` has no automatic trigger of any kind. That gap is real and is epic Q01, owned by the PO; not decided in this task.

Half 2 — the rebuild — is done. Preconditions verified: \`docs/.fts/\` is gitignored in lean-stack (\`.gitignore:12\`), so the rebuild write cannot create a commit there. Old index: 197 documents, \`n_concepts=197\`, file mtime 2026-07-29 20:40:09 (15 days stale at measurement time). Ran \`python3 cli/okf-cli.py --root /Users/erik/dev/lean-stack/docs build-index\` from okf-tools (the \`okf-cli\` shell alias hardcodes \`--root ~/Obsidian/Knowledge-Catalogue\`, so it cannot be used for a cross-repo target — invoked the script directly instead). Output: \`indexed 52 concept(s) -> /Users/erik/dev/lean-stack/docs/.fts/fts.sqlite\`. New index: 52 documents (\`n_concepts=52\`, \`n_archived=0\`), mtime 2026-08-13 15:03:37.

52, not ~52-rounds-to-41: matches OKFT-n8xz's own re-measurement (52/245, Q02 there), not the epic's original 41/197 baseline. Investigated per the task's instruction to treat any deviation as a finding, not a footnote: OKFT-n8xz's Summary and Q02 already traced this — the repo grew organically (24 commits touching \`lean-stack-okf/\` since 2026-08-01) between the epic's baseline capture and every task that ran after it, including this one. The reduction ratio is what matters and holds: 52/245 = 21.2% narrowed vs. the epic's own 41/197 = 20.8%, same ~79% cut. No new discrepancy introduced by this task — this run simply reproduces OKFT-n8xz's already-explained number.

Qualitative check against the rebuilt index, unscoped \`find\` (R34's exact example plus one more):

- \`dev-CLI Kanon Entrypoint Wrapper Shims\`: rank 1 is now \`lean-stack-okf/dev-cli-canon\` (was rank 4 out of 9, with 8/9 hits from \`dev-cli-canon/\`, \`dev-cli-layering/\`, \`obs-hygiene/\` scaffolding per R34). All 10 returned hits are \`lean-stack-okf/*\` — zero scaffolding, because scaffolding is no longer in the index at all, not merely re-ranked.
- \`capability\`: top 4 hits are all \`lean-stack-okf/*\` canon concepts (\`plan-quality-determines-model-floor\`, \`four-discipline-model\`, \`ce-read-path\`, \`tpic-document-chain\`) — same pattern.

\`just test\` in okf-tools: 701 tests, exactly the three pre-existing \`RunnerAgainstRealCatalogueTest\` failures, no fourth — repo-local production code is unchanged by this task, this is a control run.

\`git -C /Users/erik/dev/lean-stack status --porcelain\` is byte-identical before and after the rebuild (confirms the gitignore held and nothing else was touched). \`LES-zr4r\` was not read or touched.

## Test-Output

\`just test\` (okf-tools, before and after the rebuild — no production code changed, this is a control):

\`\`\`
FAIL: test_index_walk_row_present_with_rank_no_dedicated_metric (test_eval_runner.RunnerAgainstRealCatalogueTest.test_index_walk_row_present_with_rank_no_dedicated_metric)
FAIL: test_metadata_hit_and_miss_rows_scored_correct (test_eval_runner.RunnerAgainstRealCatalogueTest.test_metadata_hit_and_miss_rows_scored_correct)
FAIL: test_runner_scores_literal_s1_top1 (test_eval_runner.RunnerAgainstRealCatalogueTest.test_runner_scores_literal_s1_top1)
Ran 701 tests in 29.110s
FAILED (failures=3)
\`\`\`

## Smoke

check-ignore:

\`\`\`
$ git -C /Users/erik/dev/lean-stack check-ignore -v docs/.fts/fts.sqlite
.gitignore:12:docs/.fts/	docs/.fts/fts.sqlite
\`\`\`

Before (old index, direct sqlite query against \`docs\` table and \`fts_meta\`):

\`\`\`
docs row count: (197,)
n_concepts 197
newest_mtime 1785350324.0100436
mtime (fs): Jul 29 20:40:09 2026
\`\`\`

build-index run:

\`\`\`
$ python3 cli/okf-cli.py --root /Users/erik/dev/lean-stack/docs build-index
indexed 52 concept(s) -> /Users/erik/dev/lean-stack/docs/.fts/fts.sqlite
\`\`\`

After:

\`\`\`
docs row count: (52,)
n_concepts 52
n_archived 0
newest_mtime 1786621451.182199
mtime (fs): Aug 13 15:03:37 2026
\`\`\`

find query 1 (R34's example, top hit):

\`\`\`
$ python3 cli/okf-cli.py --root /Users/erik/dev/lean-stack/docs find "dev-CLI Kanon Entrypoint Wrapper Shims"
rank: 1
title: dev-cli-canon — projekt-lokale just-CLI als Determinismus-Kontrakt
type: Concept
path: lean-stack-okf/dev-cli-canon
provenance: lexical
\`\`\`
(all 10 returned hits are \`lean-stack-okf/*\`, none from \`dev-cli-layering/\` or \`obs-hygiene/\` — those directories are simply not in the index anymore)

find query 2:

\`\`\`
$ python3 cli/okf-cli.py --root /Users/erik/dev/lean-stack/docs find "capability"
rank: 1  lean-stack-okf/plan-quality-determines-model-floor
rank: 2  lean-stack-okf/four-discipline-model
rank: 3  lean-stack-okf/ce-read-path
rank: 4  lean-stack-okf/tpic-document-chain
\`\`\`

\`git -C /Users/erik/dev/lean-stack status --porcelain\` — identical before and after the rebuild:

\`\`\`
 M architecture/aca/capabilities.yaml
 M architecture/aca/cli.py
 M architecture/layer0/discovery.py
 M docs/aca_agentic-capability-architecture/DECISIONS.md
 M docs/aca_agentic-capability-architecture/TASKS.md
 M docs/aca_agentic-capability-architecture/TPIC-CHAIN.md
 M docs/aca_agentic-capability-architecture/eriks-notes/eriks-task-list.md
?? architecture/aca/tests/test_tpic_mapping.py
?? architecture/aca/tpic.py
?? docs/aca_agentic-capability-architecture/tpic-mapping.yaml
\`\`\`
Note: this pre-existing working-tree state is broader than the task brief's single named file (\`eriks-task-list.md\`) — six more tracked files and three untracked files also sit modified/untracked, none of it caused by this task and none of it touched by it. Flagging so the owning session isn't surprised if it diffs against an assumption of one dirty file.

## Deviations/ERRATA

- The \`okf-cli\` shell alias hardcodes \`--root ~/Obsidian/Knowledge-Catalogue\` and cannot target another repo; invoked \`python3 cli/okf-cli.py --root <path>\` directly instead, per the task's own instruction text (which already used the script form).
- New document count is 52, not the epic's original ~52-expectation-matching-41-scaled figure — matches OKFT-n8xz's own re-measurement exactly (52/245), not a new discrepancy. See Summary.
- The lean-stack working tree carries six more pre-existing dirty/untracked entries beyond the one file named in the task brief. None touched, none caused by this task, flagged above for visibility.
- \`build-semantic-index\` was NOT run, per explicit instruction — recommendation only, below.

## Notes for T(n+1)

Recommendation on \`build-semantic-index\`: **do not run it yet, and route the decision through Q01, not around it.** Reasoning: if the PO answers Q01 "yes, extend the SessionStart hooks to repo-local docs roots," both the FTS and the semantic-coverage rebuild become automatic on the next session start for lean-stack, and a manual semantic rebuild done now would just be redone by the hook shortly after — wasted Voyage-API spend. If the PO answers "no, leave D03 standing," a manual semantic rebuild is still worth doing once, but it should happen as the first step of whichever future task actually runs a semantic-arm remeasurement (R33/R34-style), not speculatively here — this task's scope was the lexical FTS index per the epic's own baseline framing, and \`build-semantic-index\` is unbudgeted work with a real cost (Voyage API calls) that the bean did not ask for. Net: hold, let Q01 resolve first, then let the semantic remeasurement task pay for its own rebuild.


## Review 2026-08-13 — APPROVED (ce-specs-reviewer)

- **Neighbour repo clean.** `docs/.fts/` independently confirmed ignored (`.gitignore:12`). The six extra dirty files were absorbed by lean-stack commit `0cfa3f0 feat(aca): map TPIC execution` at 15:06:17, three minutes after the `fts.sqlite` mtime of 15:03:37; their own mtimes run 14:25-15:01, all before that commit. A parallel session working the `aca_agentic-capability-architecture` epic, not us. `git status --porcelain` there now shows only the one pre-existing modified file.
- **52 confirmed without rebuilding**: `select count(*) from docs` → 52; `fts_meta` → `n_concepts 52`, `n_archived 0`. Path aggregation → 52 under `lean-stack-okf`, not a single topic-folder document. Matches the independent OKFT-n8xz measurement exactly.
- **The epic's headline claim reproduced.** `find "dev-CLI Kanon Entrypoint Wrapper Shims"` → rank 1 `lean-stack-okf/dev-cli-canon`, and all ten returned paths are `lean-stack-okf/*`. R34 read in the original (`REFERENCES.md:91`) and the before-state is quoted correctly: "8 von 9 Treffern aus `dev-cli-canon/`, `dev-cli-layering/`, `obs-hygiene/`; der kanonische `lean-stack-okf/dev-cli-canon` steht auf Rang 4."
- **No trigger decision smuggled in.** Both SessionStart hook scripts unchanged since before this session (mtimes 3 Aug and 10 Aug). No `.tagvec*` in `lean-stack/docs` — `build-semantic-index` was not run, no Voyage spend. Q01 left open on the epic.

`just test`: `Ran 701 tests in 27.782s`, `FAILED (failures=3)`, the three baseline failures, no fourth.

One observation, not a finding: this bean carries no formal acceptance-criteria list the way OKFT-n8xz does. Its prose objective was unambiguous enough to judge against, but the asymmetry is worth noticing for the next planner.
