---
# okf-cli-4ws6
title: MCP cannot reach build-index, so agents stay degraded
status: todo
type: bug
priority: normal
created_at: 2026-07-26T12:25:37Z
updated_at: 2026-07-26T14:34:11Z
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



## Resolved by epic okf-cli-5uog (2026-07-26) — awaiting PO acceptance

Left on `todo` deliberately: acceptance record, closing it is the PO's call at the review gate.

Fixed by leaf `okf-cli-g0gi` (T06), commit `826fcbf`, reviewed APPROVED with independent re-verification.

| Finding | Resolution |
|---|---|
| B07 — `find` tells an agent to run `okf-cli build-index`, which the agent cannot reach | `build-index` whitelisted, tool `okf_build_index` added |
| B08 — `prime` ("start here in a new session") missing from the agent interface | `prime` whitelisted, tool `okf_prime` added |
| B09 — `okf_find`'s docstring still described the pre-feature keyword search | Docstring rewritten: two arms, conditional handover, provenance, stderr degradations |

Scope held to D04 exactly — `build-index`, `prime`, `info`, nothing else. Which of the remaining eight CLI commands belong on the agent surface stays open for the PO; `visualize` writes `viz.html` into the catalogue and the tag/fix/rewrite commands mutate catalogue content, so none of them is the read-only addition it appears to be.

**One correction made against the plan, worth the PO's eye.** PLAN.md dictated a docstring sentence claiming every result line names its origin as `provenance: lexical` or `provenance: semantic`. That is false of the code: `cmd_find`'s print loop (`cli/okf-cli.py:1229-1230`) emits the `provenance:` line only for semantic hits — lexical hits carry the field internally and never print it. The implementer caught it and shipped a true sentence instead; the reviewer confirmed it at the code. Shipping the plan's text verbatim would have written a promise into the agent interface that the tool does not keep — the same defect class as B10, which this epic fixed in the CLI's own help.

A regression guard came with it: `McpSurfaceParity` derives from `COMMAND_DISPATCH`, so a command whitelisted on the MCP side but renamed or removed on the CLI side now fails the suite.
