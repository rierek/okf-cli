---
# OKFT-l7ko
title: Ship okf-tools as a Claude Code plugin
status: todo
type: feature
priority: deferred
created_at: 2026-07-27T12:46:26Z
updated_at: 2026-08-03T19:37:56Z
---

## Context

okf-tools currently ships as three loose parts that a user wires up by hand:

- `cli/okf-cli.py` — invoked by absolute path or via a shell alias
- `mcp/okf_mcp.py` — registered as a user-scope stdio MCP server in `~/.claude.json`
  (`uv run --with mcp <abs path>`)
- hooks — none yet, but at least one is planned (`OKFT-iaxj`, Stop hook that rebuilds
  the FTS index), and it would land in `~/.claude/hooks/` far away from this repo

`plugin/` exists in the repo but is empty.

Hand-wiring has already cost real breakage. When the repo moved from
`~/Obsidian/tools/okf-tools` to `~/dev/okf-tools` (commit `6bfebf9`), two independent
absolute paths went stale and neither was caught by the test suite:

1. `mcp/okf_mcp.py` had the CLI path baked in as a `~/Obsidian/...` literal — every MCP
   tool died with ENOENT before reaching the CLI. Fixed in `7bd7989` by deriving the path
   from `__file__`.
2. The MCP server definition in `~/.claude.json` still pointed at the old directory;
   `claude mcp list` reported `okf: ✘ Failed to connect`. Fixed by hand with
   `claude mcp remove/add`. The sibling `vikunja-mcp` entry had the identical defect.

A plugin makes the wiring an artifact of the repo instead of hand-maintained machine
state: one manifest declares the MCP server, the hooks, and any commands, all with
plugin-relative paths, and it moves with the repo.

## Objective

THE okf-tools repo SHALL be installable as a single Claude Code plugin that registers the
MCP server, the hooks, and the CLI entry point, so that no absolute path to this repo has
to be maintained in user-level configuration.

## Scope

- MCP server declared by the plugin, replacing the user-scope `okf` entry in `~/.claude.json`
- Hooks shipped by the plugin (first consumer: `OKFT-iaxj`)
- CLI reachable without a hand-written alias
- Migration path: what happens to the existing user-scope entry, and how a user goes from
  the current hand-wired setup to the plugin without a broken window in between

## Open questions

- [ ] Does the plugin manifest carry the catalogue root, or does that stay per-user config?
      The KC root (`~/Obsidian/Knowledge-Catalogue`) is currently passed per call.
- [ ] Distribution: local marketplace entry vs. a git-installable plugin
- [ ] Does the MCP server keep the `uv run --with mcp` launch shape under a plugin, or does
      the plugin declare the dependency itself?

## Acceptance

- [ ] Plugin manifest under `plugin/`, declaring the MCP server with a plugin-relative path
- [ ] Installing the plugin yields a connected `okf` MCP server — verified with `claude mcp list`
- [ ] Hooks ship with the plugin, no manual copy into `~/.claude/hooks/`
- [ ] The user-scope `okf` entry in `~/.claude.json` is retired, with the migration documented
- [ ] Moving the repo to a different directory breaks nothing — verified, not assumed
- [ ] A regression test covers the "repo moved" case for whatever paths remain

## Notes

The regression test added alongside `7bd7989`
(`cli/test_okf_mcp.py::McpDefaultCliPath`) covers the in-repo path only. Config-level path
drift — the second defect above — is still untested and is the more damaging of the two,
because it takes the server down entirely rather than degrading it.
