---
# OKFT-gpcx
title: Superseded decisions are not marked
status: draft
type: task
priority: normal
created_at: 2026-08-10T12:59:09Z
updated_at: 2026-08-10T12:59:09Z
parent: OKFT-hkze
---

## Objective (User Story)
As an agent answering from the catalogue, I want to see that a decision has been superseded, so that I do not report an overturned decision as current.

## Evidence (MODUS-B-REPORT Q01)
Run R4 retrieved a decision to consolidate the memory layer onto one database. A later concept in the same bundle, `decisions/memory-db-layer-teardown`, tears that layer down again. Nothing in the retrieved document says so; the agent noticed only because it had walked the bundle index first. Modus A cannot see this failure mode at all — the retrieval was formally correct and the answer was stale.

## Open question (Q01)
Should supersession become explicit in the catalogue — a frontmatter relation or a status field on decision-type concepts — and should `find`/`read` surface it?

## Note
Draft on purpose: this is a catalogue-schema decision (OKF properties), not an okf-tools change. It needs a PO decision before it is an implementable task. Scope guard: whatever the answer, it must not turn every concept into a workflow-state machine.
