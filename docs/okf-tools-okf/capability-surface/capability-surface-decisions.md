---
type: ADR
title: Capability-surface plan — decisions (D01-D04)
description: argparse becomes the single source of truth for okf-cli's command surface; both a flat and a grouped view render from it; MCP gains build-index, prime and info.
tags:
  - okf-cli
  - mcp
  - architecture
  - decision
timestamp: 2026-07-26T00:00:00Z
---

# Capability-surface plan — decisions (D01-D04)

Quelle: `docs/okf-cli-capability-surface/PLAN.md` ("Decisions this plan implements"),
Epic `okf-cli-5uog`. Nur diese vier Entscheidungen sind hier migriert — die
Task-Scaffolding um sie herum bleibt in der PLAN.md-Datei (Bean `okf-cli-t7jz`, AC1.3).

| Dxx | Decision | Source |
|-----|----------|--------|
| D01 | Strang A (this plan) and Strang B (zero-hit reachability) are separated. Strang B gets a **measurement mandate** as its own bean, no fix plan, because its fix depends on a number nobody has measured. That bean does not exist yet at plan time; `okf-cli-snxj` still carries its original T10 content plus the PO reject | PO 2026-07-26, this session |
| D02 | **argparse is the single source of truth** for the capability surface. The hand-written `Commands:` prose block in the module docstring is replaced by a rendered overview; `find`'s scoring detail — the only non-one-liner in that block — moves into `find`'s own epilog rather than being deleted. A conformance test enforces the invariants | PO 2026-07-26, closes design question 1+2 |
| D03 | **Both layouts, one source.** argparse's own listing stays flat and alphabetical (the PO's literal review request); a purpose-grouped overview is additionally rendered into the epilog. Two views cannot drift because both are generated | PO 2026-07-26, closes design question 3 |
| D04 | MCP gains **`build-index`, `prime`, `info`** and nothing else. All three leave catalogue content untouched (`build-index` writes only its own `.fts` artefact, locally, without network). The wider surface question — which of the remaining eight commands belong in an agent's hands — stays explicitly open | PO 2026-07-26. The PO was offered three bundles (defect minimum only / these three / all non-mutating incl. `visualize`+`log`) and chose this one; `info` is therefore PO-selected, not plan-author bundling |

## Related

- [find's score formula went stale after the FTS arm shipped (B10)](/okf-tools-okf/capability-surface/find-score-formula-drift.md)
- Full plan (task-by-task, stays a file): `docs/okf-cli-capability-surface/PLAN.md`
