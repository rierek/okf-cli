---
# okf-cli-9e2b
title: pass include_archive through the MCP layer
status: todo
type: task
priority: normal
created_at: 2026-08-09T19:15:18Z
updated_at: 2026-08-09T19:15:51Z
parent: okf-cli-scd5
blocked_by:
    - okf-cli-iwx4
---

`_BOOL_FLAGS` (mcp/okf_mcp.py:27) is shared across all commands, so the tool signature is where the decision is made: a command that does not know the flag answers with an argparse error.

### Requirement 1: The flag reaches MCP callers

**Objective:** As an agent using okf-MCP, I want the archive flag on find and list, so that the MCP surface can answer the same questions as the CLI.

#### Acceptance Criteria

1. THE okf-MCP SHALL accept `include_archive` as a parameter of `okf_find` and `okf_list`.
2. WHEN that parameter is truthy THE okf-MCP SHALL emit `--include-archive` in the argv it builds.
3. THE okf-MCP SHALL emit the flag for no other command.

#### Success Criteria

- SC-01: `build_argv` for find and list carries the flag when set and omits it when unset.
- SC-02: `build_argv` for every other command omits the flag regardless of the parameters passed.

_Requirements: R-14_

## Recommended Skills

- `superpowers:test-driven-development`
