---
# okf-cli-g0gi
title: T06 Reach build-index, prime and info over MCP
status: todo
type: task
priority: normal
created_at: 2026-07-26T13:03:25Z
updated_at: 2026-07-26T13:10:30Z
parent: okf-cli-5uog
blocked_by:
    - okf-cli-z0tt
---

Plan: `docs/okf-cli-capability-surface/PLAN.md` → **Task 6**. Independent of T01-T05 except for the parity test, which consumes `COMMAND_DISPATCH` from T01.

`find` prints `run 'okf-cli build-index'` on a stale or absent index, and the audience that note was written for cannot execute it. Reproduced live at plan time against `~/Obsidian/Knowledge-Catalogue`: the stale note printed on a real query, while `mcp/okf_mcp.py:7-17` whitelists ten commands without `build-index` among them.

### Requirement 1: The remedy the tool prescribes is reachable by the audience it addresses

**Objective:** As an agent working over MCP, I want to execute the command the degradation note names, so that a note meant as a remedy is not a dead end.

#### Acceptance Criteria

1. THE MCP surface SHALL expose `build-index`, `prime` and `info` — and nothing further; the wider surface question stays open (D04, PO 2026-07-26).
2. THE `okf_build_index` tool SHALL state in its docstring that it is the remedy for the absent/stale note, local only, no network, no change to catalogue content.
3. THE `okf_find` docstring SHALL describe the two arms, the per-query ownership, the `provenance:` lines and the stderr degradations, replacing the pre-feature keyword-search text at `mcp/okf_mcp.py:79-80`.

#### Success Criteria

- SC-01: `run_okf(root, "build-index", {})` creates `<root>/.fts/fts.sqlite` and its output contains `indexed`.
- SC-02: `run_okf(root, "prime", {})` and `run_okf(root, "info", {})` return non-empty output. Both exit 0 on a catalogue lacking `CLAUDE.md`/`TYPES.md` (probed at plan time: they print `(missing: CLAUDE.md)` / `(missing: TYPES.md)`, rc=0), so no fixture seeding is needed.
- SC-03: `set(mcp._COMMANDS) - set(okf.COMMAND_DISPATCH) == set()` — every whitelisted MCP command is a real CLI command.
- SC-04: full suite at `Ran 279 tests`, exactly 19 failures / 2 errors.

**Files:** `mcp/okf_mcp.py:7-17` (`_COMMANDS`), `:79-80` (`okf_find` docstring), `_register()` (three tools) · `cli/test_okf_mcp.py` (append classes `McpAgentRemedyBoundary`, `McpSurfaceParity`)

## Steps

- [ ] Write the failing `McpAgentRemedyBoundary` + `McpSurfaceParity` tests
- [ ] Run them, confirm `ValueError: unsupported okf command: build-index`
- [ ] Add the three `_COMMANDS` entries and the three tool wrappers
- [ ] Rewrite `okf_find`'s docstring
- [ ] Full suite; commit `fix(mcp): expose build-index, prime, info`

## Recommended Skills

- superpowers:test-driven-development

## Sequencing note

`blocked_by: okf-cli-z0tt` is deliberate although the plan calls this task otherwise independent: `McpSurfaceParity` consumes `COMMAND_DISPATCH`, which T01 introduces. The plan permits writing the other three tests first and adding the parity class later; the stricter dependency was chosen so no leaf ever ships with a weakened test. If T01 stalls, relax this and add `McpSurfaceParity` in a follow-up commit — do not replace it with a hardcoded command list.
