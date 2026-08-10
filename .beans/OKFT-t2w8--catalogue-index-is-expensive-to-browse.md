---
# OKFT-t2w8
title: Catalogue index is expensive to browse
status: completed
type: task
priority: low
created_at: 2026-08-10T12:59:09Z
updated_at: 2026-08-10T14:16:15Z
parent: OKFT-hkze
---

## Objective (User Story)
As an agent with a small tool budget, I want the catalogue-level index to cost one cheap call, so that navigating is a viable path next to searching.

## Evidence (MODUS-B-REPORT I03)
`okf_index` at catalogue level returns 22 bundles with full descriptions. In run R4 exactly one of those lines carried the answer; a wrong bundle guess (both `home-lab-wiki/decisions` and `general-knowledge-wiki/home-lab-and-hosting` were plausible) would have left almost no budget for a second index call.

## EARS Acceptance
- THE catalogue-level index SHALL default to a compact form — bundle name plus a one-line description.
- THE full description SHALL remain reachable on explicit request.

## Success Criteria
- SC-001: default output shrinks measurably (assert on line count or bytes for the real catalogue), full form still available behind a flag.
- SC-002: MCP surface exposes the same distinction; `just test` green.


## Done 2026-08-10 (commit 3382cd4)

Changed:
- `cli/okf-cli.py`: new `render_bundle_compact(root, b)` (`"{bundle}: {one-line description}"`); `cmd_index`'s catalogue-wide branch (no `bundle` arg) now defaults to it, one line per bundle, no separators. `--full` restores the old structured block (`render_bundle_block(..., full=True)`, always including types/tags now — see decision below). `_bundle_summary_json(root, b, full=False)` gained a `full` param: default returns `{bundle, description}`, `full=True` adds `concepts`/`directories` (previously always present). `cmd_index`'s `--json` branch without a bundle now passes `full=args.full` through. Argparse help for `index --full` rewritten to describe the new split. Per-bundle form (`index <bundle>`, with or without `--json`) untouched.
- `mcp/okf_mcp.py`: `okf_index(root, bundle="", full=False)` gained the `full` param, passed through `run_okf`; `_BOOL_FLAGS["full"] = "--full"`, scoped via `_BOOL_FLAG_COMMANDS["full"] = {"index"}` (mirrors the existing `include_archive` scoping pattern) so no other command's argv is affected.
- `cli/test_okf_cli.py`: new `RenderBundleCompact` (2 tests), new `CmdIndexCatalogueCompactDefault` (2 tests); `CmdIndexJson` gained `test_json_without_bundle_defaults_to_compact_fields` and had its two existing default-JSON tests (`test_json_without_bundle_reports_a_concept_count_not_the_list`, `test_json_without_bundle_carries_description_and_directories`) rewritten to assert under `full=True` instead of the old always-on default — see deviation below.
- `cli/test_okf_mcp.py`: new `BuildArgvIndexFullFlag` (2 tests) plus 2 new tests in `McpIndexListBoundary` for the compact/full split over the real subprocess boundary.

Design decisions:
- `--full` on the catalogue-wide `index` now does double duty: it both restores the full block (description/concepts/directories) *and* keeps adding types/tags, instead of introducing a third flag. Rationale: a reader asking for "full" wants the whole structured view; the previous in-between state (block shown, types/tags withheld) was only reachable because the block used to be the unconditional default, not because anyone asked for exactly that combination. Collapsing to one flag keeps the CLI surface small and matches how `--full` already behaves on the per-bundle form (`index <bundle> --full`), which is untouched.
- The `--json` catalogue-wide form is NOT left unchanged, despite the task's default assumption — it now defaults to `{bundle, description}` and needs `--full` for `concepts`/`directories`, deliberately deviating because SC-002 requires the MCP surface (which always calls the CLI with `--json`) to expose the same compact/full distinction; leaving JSON always-full would have made SC-002 unsatisfiable for `okf_index`. Two pre-existing tests were updated accordingly (see Changed above) rather than left contradicting the new default.
- Per-bundle `index <bundle>` (text and `--json`) is unchanged, as the task allowed by default.

Tests RED before implementation (confirmed by running each in isolation against the unmodified code):
- `RenderBundleCompact.*` — `AttributeError: module 'okf' has no attribute 'render_bundle_compact'`
- `CmdIndexCatalogueCompactDefault.test_default_text_is_one_line_name_plus_description` — asserted compact text, got the old block+`-----` output
- `CmdIndexJson.test_json_without_bundle_defaults_to_compact_fields` — asserted `{bundle, description}` only, got `concepts`/`directories` present
- `test_okf_mcp.BuildArgvIndexFullFlag.test_full_true_adds_the_flag` — `--full` absent from `build_argv` output
- `test_okf_mcp.McpIndexListBoundary.test_index_json_over_subprocess_no_bundle_defaults_to_compact` — `concepts` key present over the real subprocess

Mutation-guard proof (each mutated, confirmed red, then reverted):
- `cli/okf-cli.py` `cmd_index`: `if not args.full:` → `if False:` turned `CmdIndexCatalogueCompactDefault.test_default_text_is_one_line_name_plus_description` red (full block printed instead of the compact line).
- `cli/okf-cli.py` `_bundle_summary_json`: `if full:` → `if True:` turned `CmdIndexJson.test_json_without_bundle_defaults_to_compact_fields` red (`concepts`/`directories` leaked into the compact-default entry).
- `mcp/okf_mcp.py` `_BOOL_FLAGS`: removing the `"full": "--full"` entry turned `test_okf_mcp.BuildArgvIndexFullFlag.test_full_true_adds_the_flag` and `test_okf_mcp.McpIndexListBoundary.test_index_json_over_subprocess_no_bundle_full_includes_concepts` red.

SC-001 measurement, real catalogue (`~/Obsidian/Knowledge-Catalogue`, read-only, `index` command, ~22 bundles):
- Before: 201 lines / 6620 bytes
- After: 21 lines / 3937 bytes (≈90% fewer lines, ≈41% fewer bytes)

`just test`: 649 tests, OK (baseline 637/640 + 9 new).
