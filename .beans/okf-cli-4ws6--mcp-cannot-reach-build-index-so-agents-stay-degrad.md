---
# okf-cli-4ws6
title: MCP cannot reach build-index, so agents stay degraded
status: todo
type: bug
priority: normal
created_at: 2026-07-26T12:25:37Z
updated_at: 2026-07-26T13:03:40Z
parent: okf-cli-5uog
blocked_by:
    - okf-cli-g0gi
---

## Origin

PO review 2026-07-26, raised by the PO after the US-07 reject with two direct questions: is `--help` documented in the MCP, and is `prime`? Both answers are no, and checking them surfaced a structural gap.

## Verified

`mcp/okf_mcp.py` exposes a hand-maintained whitelist `_COMMANDS` of **10** tools (`find`, `read`, `toc`, `index`, `list`, `check`, `reindex`, `refs`, `rename`, `tags`). The CLI ships **21** subcommands. Missing from the MCP surface:

`prime`, `info`, `visualize`, `rewrite-path`, `build-index`, `log`, `merge-tags`, `remove-tags`, `normalize-tags`, `fix-crosslinks`, `fix-xml-tags`

## The defect, precisely

A selective MCP surface is a legitimate design choice — most of the missing eleven are write/maintenance commands that arguably do not belong in an agent's hands. **One entry is not a choice but a defect:**

**`build-index` is unreachable over MCP.** `find` degrades gracefully when the FTS5 index is absent or stale and says so on stderr: `note: lexical index is stale (catalogue changed since build) — run \`okf-cli build-index\``. An agent working through MCP receives that instruction and **cannot follow it**. It is told to run a command its interface does not offer, so it stays permanently on the degraded path with no way out. The degradation note — accepted as correct behaviour in US-08 of this review — becomes a dead end rather than a remedy for exactly the audience it was written for ("informative zero-hit for agent consumers" is the title of T10).

Two smaller findings from the same check:

- **`prime` is absent**, although the CLI documents it as "one-shot agent onboarding: CLAUDE.md guide + catalogue TOC (start here in a new session)". The command built for agents is missing from the agent interface.
- **The MCP tool docstrings predate this feature.** `okf_find` is described as "Ranked keyword search across a catalogue/repo root, composable with exact-match type/tag filters and a bundle/subdir scope" — no mention of the semantic arm, `provenance:` lines, the degradation notes, or `--expand-tags`. An MCP consumer cannot learn from its tool description that results may come from either of two arms.

## Root cause, shared with okf-cli-3suc

There is no single place that establishes what the CLI can do and projects it outward. The capability surface is described three times by hand — the `Commands:` prose block in the module docstring, argparse's `add_parser(help=...)` registrations, and `_COMMANDS`/docstrings in `mcp/okf_mcp.py`. All three have already drifted apart: `find` is documented in the first, missing from the second, and described pre-feature in the third.

## Fix

Minimum: add `build-index` to `_COMMANDS` with a tool wrapper, so the remedy the tool itself prescribes is reachable by the audience it addresses. Then refresh `okf_find`'s docstring to describe what `find` now does.

## Deliberately NOT decided here

Which of the remaining ten commands belong on the MCP surface at all. That is a design decision for the PO — `visualize`, `log` and `info` are read-only and harmless; `merge-tags`, `remove-tags`, `normalize-tags`, `rewrite-path`, `rename` and the two `fix-*` commands mutate the catalogue, and putting them in an agent's hands is a question about blast radius, not about completeness. The PO asked for this to be raised as a defect, not for the wider surface to be settled.
