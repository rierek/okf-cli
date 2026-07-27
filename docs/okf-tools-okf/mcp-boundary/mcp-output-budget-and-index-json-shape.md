---
type: Decision
title: MCP output budget and the shape of index --json
description: Catalogue-wide `index --json` returns a bundle summary (counts, not concept lists) in parity with the text branch, and run_okf caps every MCP result at MAX_OUTPUT_CHARS with an actionable error instead of returning a payload no consumer accepts.
tags:
  - mcp
  - okf-cli
  - cli
  - decision
timestamp: 2026-07-27T17:58:23Z
---

# MCP output budget and the shape of index --json

## The shape

`okf_index` **without** a `bundle` argument returns a bundle summary — the
machine-readable counterpart of the text branch, not a superset of it:

```json
{"bundles":[{"bundle":"…","description":"…","concepts":194,"directories":["…"]}]}
```

`concepts` is a **count**, not a list. Concept listings exist only behind the
`bundle` argument (`okf_index(bundle="…")`), which is unchanged.

## Why it is not the concept dump

The earlier branch enumerated every concept of every bundle. Against the real
catalogue (23 bundles, 2489 concepts) that produced **794 711 bytes**, against
**6 658 bytes** for the text branch of the same verb — one verb meaning two
different things depending on `--json`. The consumer discarded the call with
"exceeds maximum allowed tokens", so the result was lost entirely.

The dump shape was never a requirement. `--json` was added to `index`/`list` to
stop a RuntimeError; the no-argument shape was a by-product of making the output
parseable, never a stated need. Restoring parity with the text branch cost
nothing that anybody had asked for.

## The ceiling

Since 2026-07-27, `run_okf` in `mcp/okf_mcp.py` caps **every** output at
`MAX_OUTPUT_CHARS` (default `120000`, overridable via the environment variable
`OKF_MCP_MAX_CHARS`). Over budget, it raises instead of returning — and the error
names the command, the actual size, the budget, and the way around it.

The cap is a guard, not a fix: it converts an unusable payload into a legible
failure. It does not make the underlying call useful.

## Consequence for agents

`okf_index(bundle="qm-wiki")` is ~240 KB and therefore **fails the ceiling**. For
large bundles, enter through `okf_find` / `okf_list` rather than `okf_index` —
`index` is an orientation verb over bundles, not a retrieval verb over concepts.

## Reference

Bean `okf-cli-7u5z` (`.beans/okf-cli-7u5z--catalogue-wide-index-json-dumps-every-concept.md`),
commit `ab444aa`. Caveat recorded there: the ceiling was verified through unit
tests over the real subprocess boundary, not end-to-end — a long-running MCP
server keeps the pre-fix module until it restarts.
