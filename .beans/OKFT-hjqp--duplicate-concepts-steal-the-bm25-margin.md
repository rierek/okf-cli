---
# OKFT-hjqp
title: Duplicate concepts steal the BM25 margin
status: draft
type: bug
priority: normal
created_at: 2026-08-10T12:58:43Z
updated_at: 2026-08-10T12:58:43Z
parent: OKFT-hkze
---

## Objective (User Story)
As the catalogue owner, I want a concept to exist once, so that a literal query does not lose its lexical top-1 margin to its own copies.

## Evidence (MODUS-B-REPORT B02)
`ralph-wiggum-loop` exists three times (`ai-wiki/`, `general-knowledge-wiki/ai-agentic-coding/`, `claude-code-wiki/sessions-workflow/`, three distinct md5), `integration` twice (`ai-wiki/`, `general-knowledge-wiki/ai-agentic-coding/`). In run R5 the query `ralph wiggum loop` matched three titles verbatim and STILL fell through to the semantic arm — the agent's hypothesis is that the copies split the margin the conditional-handover rule tests for.

## EARS Acceptance
- THE margin hypothesis SHALL be measured before any merge — `find` over the affected queries with and without the duplicates present, on a catalogue copy, never on the live one.
- WHERE the measurement confirms it, THE duplicates SHALL be merged through the `ce-okf` skill, keeping the richest copy and redirecting crosslinks.

## Success Criteria
- SC-001: measurement recorded, hypothesis confirmed or refuted in writing.
- SC-002: on confirmation, one canonical concept per topic and no dangling wikilinks (`okf-cli check` clean).

## Note
Whether more duplicates exist beyond these two is unknown — a catalogue-wide near-duplicate scan is part of the measurement, not a separate task.
