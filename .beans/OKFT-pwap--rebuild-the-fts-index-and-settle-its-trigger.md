---
# OKFT-pwap
title: Rebuild the FTS index and settle its trigger
status: in-progress
type: task
priority: normal
created_at: 2026-08-13T11:07:31Z
updated_at: 2026-08-13T13:02:24Z
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
