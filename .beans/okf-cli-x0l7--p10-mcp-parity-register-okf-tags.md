---
# okf-cli-x0l7
title: 'P10 — MCP parity: register okf_tags'
status: todo
type: task
priority: normal
created_at: 2026-07-25T18:13:10Z
updated_at: 2026-07-25T18:13:10Z
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
