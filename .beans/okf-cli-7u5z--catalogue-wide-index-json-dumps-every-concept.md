---
# okf-cli-7u5z
title: Catalogue-wide index --json dumps every concept
status: completed
type: bug
priority: normal
created_at: 2026-07-27T17:47:29Z
updated_at: 2026-07-27T17:50:48Z
---

## Context

`okf-cli index --json` without a bundle argument enumerates every concept of every
bundle (`cli/okf-cli.py:536-540`), each with id, title, type and description. Against
`~/Obsidian/Knowledge-Catalogue` (23 bundles, 2489 concepts) that is 794.711 bytes.

The text path of the same verb prints compact per-bundle blocks — 6.658 bytes. So one
verb means two different things depending on `--json`:

```
okf-cli index          →   6.658 bytes   (bundle, description, concept count, directories)
okf-cli index --full   →  20.072 bytes
okf-cli index --json   → 794.711 bytes   (all 2489 concepts)
```

`mcp/okf_mcp.py` marks `index` as supports_json and always appends `--json`
(`_COMMANDS["index"] = (["bundle"], True)`). Every MCP call to `okf_index` without a
bundle therefore hits the dump. Observed 2026-07-27: the harness refused the result
("exceeds maximum allowed tokens") and spilled it to a temp file — the call is lost
for the agent.

The `{bundles: [...]}` shape was not a requirement. `okf-cli-83vq` (completed
2026-07-25) added `--json` to `index`/`list` to stop a RuntimeError; the no-argument
shape was a by-product of making the output parseable, never a stated need.

Per-bundle sizes measured the same day — the bundle branch has the same disease:

```
qm-wiki                 240.148 bytes   764 concepts
general-knowledge-wiki  102.807         344
dev-wiki                 69.760         194
km-wiki                  67.255         174
ai-wiki                  60.990         180
(18 more below 40.000)
```

## Objective

THE catalogue-wide `index --json` SHALL return the same information as its text
counterpart, and THE MCP layer SHALL refuse an oversized result with an actionable
message instead of returning a payload no consumer can accept.

## Acceptance

D01 — index --json parity

- [x] `index --json` without a bundle emits `{"bundles":[{"bundle","description","concepts":<int>,"directories":[...]}]}`
- [x] `concepts` is the count, not the list — parity with the text branch
- [x] `index <bundle> --json` is unchanged (still the concept list)
- [x] Text branches byte-identical (no regression)
- [x] Catalogue-wide result for the KC is under 20.000 bytes — 7.256
- [x] `test_okf_cli.py:1279-1280` still valid as written; two new tests pin the shape

D02 — size ceiling in the MCP layer

- [x] `run_okf` rejects stdout above a character budget before parsing/returning
- [x] Error names the command, the actual size, the budget, and how to narrow the call
- [x] Budget overridable per environment variable — `OKF_MCP_MAX_CHARS`, default 120000
- [x] Applies to every verb, not only `index` — the check sits on `proc.stdout`, before the json branch
- [x] Test: an oversized result raises with the guidance, a normal one passes through

## Notes

Not in scope, follow-up: `index <bundle> --json` for `qm-wiki` stays 240 KB and is
rejected by D02 rather than made useful. Making it useful means dropping `description`
from that shape (the bulk of the bytes) or adding a limit — decide on the usage
pattern, since `index <bundle>` serves overview and the description belongs to the hit,
not to the list.


## Summary

D01 — `cmd_index`'s catalogue-wide JSON branch now emits `_bundle_summary_json`
(`bundle`, `description`, `concepts` count, `directories`) instead of every concept of
every bundle. That is the machine-readable twin of `render_bundle_block`, so both
surfaces of the verb finally mean the same thing. `_concepts_json` survives, now used
only by the per-bundle branch.

D02 — `run_okf` checks `len(proc.stdout)` against `MAX_OUTPUT_CHARS` before the json
branch and raises with command, actual size, budget and the remedy. Default 120000,
overridable via `OKF_MCP_MAX_CHARS`. Sized so the largest legitimate bundle listing
(`general-knowledge-wiki`, 102.807 bytes) passes while `qm-wiki` (240.148) does not.

## Test-Output

RED (D01, before the cmd_index change):

```
AssertionError: [{'id': 'one', 'title': 'One', 'type': 'Runbook', 'description': 'first'}] != 1
KeyError: 'description'
Ran 5 tests — FAILED (failures=1, errors=1)
```

RED (D02, before MAX_OUTPUT_CHARS existed):

```
AttributeError: module 'okf_mcp' has no attribute 'MAX_OUTPUT_CHARS'
Ran 2 tests — FAILED (errors=2)
```

GREEN:

```
python3 -m unittest test_okf_mcp   → Ran 21 tests — OK
python3 -m unittest test_okf_cli.CmdIndexJson → Ran 5 tests — OK
```

Full CLI suite: `Ran 204 tests — FAILED (failures=19, errors=2)`. Identical to the
baseline recorded in okf-cli-83vq (2026-07-25: 19 failures, 2 errors). All 21 are
crosslink/rename-plan tests (`test_rewrites_resolvable_same_dir_link`,
`test_plan_cross_bundle_rewrites_inbound_and_outbound`, …) — a different subsystem,
untouched here.

## Smoke

Against `~/Obsidian/Knowledge-Catalogue` (23 bundles, 2489 concepts):

```
index --json   794.711 bytes  →  7.256 bytes
index          6.658 bytes    →  6.658 bytes  (unchanged)
```

Field-level parity spot-checked on `dev-wiki`: text and JSON agree on description,
count (194) and all 18 directories.

Live through MCP: `okf_index(root=KC)` returns the summary shape and is accepted by the
consumer — the same call previously died with "exceeds maximum allowed tokens". D01 is
live immediately because `run_okf` spawns the CLI per call.

## Deviations/ERRATA

D02 is NOT verified live. The ceiling lives in the long-running MCP server process,
which still runs the pre-fix module; it takes effect after a server restart. Covered by
unit tests over the real subprocess boundary, not by an end-to-end MCP call.

## Notes for T(n+1)

- `index <bundle> --json` for `qm-wiki` (240 KB) now fails the ceiling instead of
  flooding the consumer. That is the intended guard, not a fix: the call is still not
  useful. Dropping `description` from the per-bundle shape is the obvious lever — it is
  the bulk of the bytes, and a description belongs to a hit, not to a listing.
- `~/.claude/CLAUDE.md` named 12 bundles by hand; the catalogue has 23. Replaced the
  hardcoded list with the `index` call that produces it.
