---
# OKFT-wsne
title: Nothing triggers the concept_emb producer
status: completed
type: bug
priority: high
created_at: 2026-08-10T13:11:08Z
updated_at: 2026-08-10T14:52:36Z
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

## Done 2026-08-10 (commit 9417bce)

Built the trigger, the last of the three halves. PO decision executed as given: a SessionStart hook, exact mirror of the FTS hook, running detached and always exit 0.

New CLI verb `build-semantic-index [--if-stale]` (`cli/okf-cli.py`, category `search`, next to `build-index`). Without the flag it fills `plan_concept_delta()`'s delta unconditionally, same as before any flag existed. With `--if-stale` it skips the network call when `semantic_coverage()`'s PATH-SET probe already reports every on-disk concept embedded — absent or partial still gets the full run, mirroring `cmd_build_index`'s D02 shape exactly, deliberately probing paths rather than row counts because `concept_emb` carries orphan rows for deleted concepts (OKFT-3520) that a row-count check would let mask a real gap. Output names the count embedded and the database path.

Degradation instead of a crash: a missing `VOYAGE_API_KEY` or an exhausted-retries network failure both print a `note: ...` to stderr (same shape as the existing lexical-index notices) and return cleanly — no traceback, verified by a test that removes the key and one that forces every `embed_voyage` call to raise. The query path is untouched: `find` still never calls this producer itself (D13/D16).

MCP: `okf_build_semantic_index` in `mcp/okf_mcp.py`, wired straight to `run_okf(root, "build-semantic-index", {})`, docstring names the network dependency and that `--if-stale` is CLI-only (mirrors `okf_build_index`, which also does not expose FTS's `--if-stale`).

Hook `~/.claude/hooks/tagvec-rebuild-if-stale.sh` (outside this repo, not committed here) is a line-for-line mirror of `fts-rebuild-if-stale.sh`, differing only in the CLI verb it backgrounds. Its own missing-`VOYAGE_API_KEY` no-op comes from the CLI's own degradation, not a separate hook-level check — the hook discards stdout/stderr on the backgrounded call either way. Test script `~/.claude/hooks/tagvec-rebuild-if-stale.test.sh` (mirror of the FTS test, 6 cases) passes: all four guard cases stop the fork before it happens, the happy path invokes `--root <kc_root> build-semantic-index --if-stale`, and a non-zero exit from the backgrounded CLI still leaves the hook silent and exit 0. Registered in `~/.claude/settings.json` under `hooks.SessionStart` (new entry, `timeout: 5`, same shape as the FTS entry) — file read before editing, only this one entry added, `python3 -c "import json; json.load(...)"` confirmed valid JSON afterward.

TDD: 9 new tests in `cli/test_okf_cli.py` (class `CmdBuildSemanticIndex`) plus 4 new tests in `cli/test_okf_mcp.py`, all RED before the implementation (`AttributeError: module 'okf_cli' has no attribute 'cmd_build_semantic_index'` / `KeyError: 'build-semantic-index'`), GREEN after. SC-002 verbatim: `test_sc002_disk_paths_match_concept_emb_rows_after_run` compares the on-disk concept path set against `concept_emb` rows with `embed_voyage` replaced by a fixed-vector fake — no network. Two guard mutations shown red and rolled back: `cov[0] >= cov[1]` → `cov[0] > cov[1]` turned `test_if_stale_skips_when_coverage_is_complete` red (it ran the network fill instead of skipping); `if not os.environ.get("VOYAGE_API_KEY")` → `if False` turned `test_missing_api_key_degrades_without_raising` red (it fell through to a real, slow retry-and-fail path instead of the fast stderr note). `just test`: 662 tests, OK (was 650 before this bean).

Live proof against the real catalogue (`~/Obsidian/Knowledge-Catalogue`), a genuine Voyage AI network call:
- before: `semantic index: partial — 2587 of 2590 concept(s) embedded; the rest is invisible to the semantic arm (rebuild: cli/embeddings/build_tagvec.py --target concepts)`
- `build-semantic-index --if-stale` → `embedded 3 concept(s) -> /Users/erik/Obsidian/Knowledge-Catalogue/.tagvec/tag_vectors.sqlite`
- after: `semantic index: complete — all 2590 concept(s) embedded`
- second `--if-stale` run: `semantic index is current, skipping rebuild -> ...tag_vectors.sqlite` — no second network call.
- `git -C ~/Obsidian/Knowledge-Catalogue status --porcelain`: clean; `.tagvec/` is listed in that repo's `.gitignore`, so no catalogue-side commit was needed.

Boundary held: this bean built and registered the trigger only. It did NOT touch content-changed staleness (the content-hash delta belongs to the producer itself, unaffected here) or clean the 74 orphan rows for deleted concepts — both stay OKFT-3520. It did NOT add a `find`-time staleness display — that stays OKFT-uumj; `find` still never calls this producer (D13/D16, re-verified by the untouched query-path tests).
