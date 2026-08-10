---
# OKFT-mac3
title: Consolidate duplicates across ai-wiki and general-knowledge-wiki
status: draft
type: task
priority: normal
created_at: 2026-08-10T14:21:48Z
updated_at: 2026-08-10T15:11:31Z
parent: OKFT-wuiv
---

## Objective (User Story)
As the catalogue owner, I want one canonical concept per topic across `ai-wiki` and `general-knowledge-wiki`, so that a reader does not have to guess which of two copies is current.

## Evidence (docs/okf-revision/B02-DUPLICATE-MARGIN.md)
The near-duplicate scan of 2026-08-10 found 105 duplicate groups — 88 by concept slug, 17 more by identical `title:` — spanning 222 concept files. 66 of those groups (132 files) lie exclusively on the axis `ai-wiki` against `general-knowledge-wiki`. Six groups are `qm-wiki`-internal and deliberate (checklist, norm-reference, story-line, knowledge-blocks as different views of one norm clause); one group (`GLOSSARY`, 5x) is a scan artefact from the repo bundles.

The merge is catalogue hygiene, NOT a retrieval fix. `OKFT-hjqp` measured the margin hypothesis and refuted it: removing copies did not hand the ranking back to the lexical arm, and in the `integration` case it made the margin worse. Any acceptance criterion of the form "after the merge the lexical arm wins" is known to be unreachable and must not be written.

## Open decision (PO)
The 66 cross-bundle groups need ONE direction decision — does `ai-wiki` fold into `general-knowledge-wiki/ai-agentic-coding/`, the other way round, or does each group get judged on its own? 105 individual judgements is not a plan. The richest copy per group is known for the two originally reported cases (`general-knowledge-wiki/ai-agentic-coding/ralph-wiggum-loop.md` with 3 outbound path links against 2 and 0; `general-knowledge-wiki/ai-agentic-coding/integration.md` with 11 against 2), not for the other 103.

## EARS Acceptance
- THE direction decision SHALL be recorded before any concept is moved or deleted.
- WHERE a group is merged, THE surviving concept SHALL be the one carrying the richer body and link set, and every inbound reference SHALL follow through `okf-cli rename` or `reindex`.
- THE deliberate `qm-wiki` groups SHALL be left untouched.

## Success Criteria
- SC-001: direction decision written down.
- SC-002: after the merge, the scan reports no unintended duplicate group; `okf-cli check` clean, no new unresolved wikilinks.

## Note
11 of the 48 canonical eval queries have a target inside a duplicate group — re-measure after the merge, since the surviving path may differ from the recorded target.
