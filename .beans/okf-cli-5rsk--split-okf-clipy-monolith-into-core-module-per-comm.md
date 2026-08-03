---
# okf-cli-5rsk
title: Split okf-cli.py monolith into core module + per-command files
status: todo
type: task
priority: deferred
created_at: 2026-07-26T12:47:21Z
updated_at: 2026-08-03T19:37:56Z
---

## Context
cli/okf-cli.py is a single-file monolith (~2715 lines): all cmd_* functions
(cmd_find, cmd_read, cmd_tags, cmd_rename, cmd_check, ...) plus shared helpers
(read_file, meta_of, fuzzy_matches, _fts_ranking, embeddings loading) live in
one file, with argparse subparsers wired at the bottom in main(). mcp/okf_mcp.py
is a thin subprocess wrapper around it and needs no change.

Raised during a discussion about whether splitting commands into separate
files would help context economy (Read tool loads the whole file when editing
one command). Not urgent — deferred as backlog/tech-debt.

## Objective
THE cli/okf-cli.py module SHALL be restructured so that shared retrieval/IO
logic lives in a small number of core modules, separate from per-command
entry points, WITHOUT changing CLI behavior or MCP wrapper contracts.

## Acceptance Criteria (EARS)
- WHEN a shared core module (e.g. core/fts.py, core/frontmatter.py,
  core/embeddings.py) is extracted, THE existing cmd_* functions SHALL import
  from it instead of duplicating logic.
- WHEN the refactor is complete, THE full existing test suite (cli/test_*.py)
  SHALL pass unchanged (behavior-preserving refactor, no test rewrites beyond
  import path updates).
- IF per-command files are also split out (e.g. commands/find.py,
  commands/tags.py), THEN THE argparse wiring in main() SHALL continue to
  dispatch to them without changing any CLI flag/argument surface.
- THE mcp/okf_mcp.py subprocess wrapper SHALL require no changes (it only
  shells out to python3 okf-cli.py <args>).

## Success Criteria
- okf-cli.py line count meaningfully reduced (target: no single file >~800
  lines) without behavior change.
- All cli/test_*.py tests green.
- No change to CLI argument surface or --json output shapes.

## Notes
- Full per-command split is NOT recommended as a first step: helpers
  (read_file, meta_of, _fts_ranking, fuzzy_matches) are heavily shared across
  cmd_find/cmd_tags/cmd_list — extracting shared core first avoids import
  cycles. Per-command file split can follow once core is stable.
- Low priority / no urgency — defer until okf-cli.py growth or edit friction
  makes it worth the refactor cost.
