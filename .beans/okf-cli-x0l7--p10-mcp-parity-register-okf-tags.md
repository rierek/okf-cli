---
# okf-cli-x0l7
title: 'P10 — MCP parity: register okf_tags'
status: completed
type: task
priority: normal
created_at: 2026-07-25T18:13:10Z
updated_at: 2026-07-25T19:29:40Z
parent: okf-cli-5hg4
blocked_by:
    - okf-cli-5qmn
---

## Objective (User Story)
As an agent, I want the `tags` verb reachable via MCP so that tag discovery is available on the agent-facing surface, while write/admin verbs stay CLI-only by intent.

## EARS Acceptance
- THE MCP surface SHALL expose `okf_tags(root, query="", limit=8)` returning the CLI `tags` output (fuzzy candidate search or full audit dump).
- Write/admin verbs SHALL remain unregistered (parity is deliberate-subset, not 20/20).

## Success Criteria
- SC-001: `okf_tags` registered + runs over subprocess (test).
- SC-002: merge-tags/normalize-tags/fix-*/rename-writes/log/visualize/prime/info remain unregistered.

## Grounding
MCP already has check (okf_mcp.py:91-94) + refs (:101-104); only real gap is `tags` (CLI-only okf-cli.py:1939-1948, RET12/D05). `query` is nargs=* — marshal empty as omitted.
## Affected code
- `mcp/okf_mcp.py:7-17` `_COMMANDS` add `"tags": (["query"], False)`; register tool at :65-115.
- Test: `cli/test_okf_mcp.py`
Full steps: PLAN.md Task 10.
Commit: `feat(mcp): expose okf_tags to close agent-relevant parity gap`


## Summary

Registered `okf_tags(root, query="", limit=8)` on the MCP surface as a thin
subprocess wrapper, closing the only agent-relevant MCP parity gap (D05).
Added `"tags": (["query"], False)` to `_COMMANDS` (mcp/okf_mcp.py:7-17) and
a corresponding `@server.tool()` registration (mcp/okf_mcp.py). Empty query
(default) runs the full audit dump; a non-empty query marshals as a single
fuzzy-search candidate (CLI's `nargs="*"` accepts one value). Write/admin tag
verbs (merge-tags, normalize-tags, --register, --validate) remain
unregistered by intent, per D05/RET12.

## Test-Output

Baseline (before): `python3 -m unittest cli.test_okf_cli cli.test_okf_mcp
cli.test_eval_fixtures cli.test_eval_runner` -> Ran 126 tests, FAILED
(failures=19, errors=2) — pre-existing, matches task brief exactly.

After: same command -> Ran 128 tests, FAILED (failures=19, errors=2) — same
19F/2E, no new failure/error (2 new tests added and passing).

## Smoke

Real MCP path (`mcp.run_okf`) against the real catalogue
(~/Obsidian/Knowledge-Catalogue):

    >>> mcp.run_okf(root, "tags", {"query": "workflow", "limit": 3})
    == searched: workflow ==
      - workflow  (51)
      - agentic-workflow  (7)
      - ai-coding-workflow  (3)

## Deviations/ERRATA

None. Implementation matches PLAN.md Task 10 exactly: `_COMMANDS` entry +
tool registration only, no changes to okf-cli.py itself (tags command was
already fully implemented CLI-side). Scope stayed within
`mcp/okf_mcp.py` + `cli/test_okf_mcp.py` as instructed — no touches to
`cli/okf-cli.py` (parallel P11 territory) or `cli/embeddings/` (parallel P7
territory).

## Notes for T(n+1)

- MCP tool signature intentionally simplifies CLI's `query nargs="*"` (multi-
  candidate) down to a single `query: str` param — matches the bean's
  literal signature `okf_tags(root, query="", limit=8)`. If multi-candidate
  fuzzy search is ever needed via MCP, `_COMMANDS["tags"]` positional
  marshalling would need to accept a list, not just extend `build_argv`'s
  current single-value-per-positional-name assumption.
- Follow `McpBoundaryTestBase` pattern (cli/test_okf_mcp.py) for any further
  MCP boundary tests — patches `mcp.OKF_CLI` as a module attribute, not
  os.environ (LL-01: import-time binding).
