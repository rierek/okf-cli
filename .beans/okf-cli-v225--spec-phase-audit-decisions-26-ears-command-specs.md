---
# okf-cli-v225
title: 'Spec phase: audit, decisions, 26 EARS command specs'
status: completed
type: epic
created_at: 2026-08-09T20:44:41Z
updated_at: 2026-08-09T20:44:41Z
parent: okf-cli-03o1
---

Eleven-axis audit of the Python CLI, decision log D05-D08, and one EARS spec file per command.

Ten subagents wrote the 23 command specs in parallel against a hand-written pilot (`spec/check.md`). 348 requirements across 26 files, gate green.

## What the parallel write bought

Six cross-cutting rules that a single author would not have found, because each surfaced only when several independent authors hit the same hole:

- COM-42 `--json` on write previews; COM-25 had covered read commands only. Reported independently by four tag and structure commands.
- COM-43/COM-44 a disabled switch suppresses the correction, not just the check, and says so.
- COM-45 `--force` carries one meaning across commands: proceed past a safety refusal.
- MCP-13/MCP-14 tool names for subcommands, and no tool for `mcp serve` itself. Reported from opposite sides by `tags.md` and `mcp.md`.

## What the gate did not catch

Five files pointed their argparse grounding reference at a neighbouring `_sub()` block: tags, refs, reindex, rename, wikilinks. All corrected against the registration map. The gate checks EARS form, duplicate IDs and modal verbs — it cannot check whether a line number says what the spec claims.

Norm boundary established: OKF v0.1 §9 names exactly three conformance clauses. Three of the thirteen `check` rules are normative; the other ten are extensions and the candidate set for T06.
