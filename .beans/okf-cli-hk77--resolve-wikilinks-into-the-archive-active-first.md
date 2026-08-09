---
# okf-cli-hk77
title: resolve wikilinks into the archive, active first
status: in-progress
type: task
priority: normal
created_at: 2026-08-09T19:14:21Z
updated_at: 2026-08-09T20:04:15Z
parent: okf-cli-xlck
---

Without this, archiving a concept turns every inbound `[[x]]` into an unresolved target and `check` reports it in the five opted-in bundles — in files the archiver never touched. The precedence rule is what keeps archive-then-recreate from making the same link ambiguous instead.

### Requirement 1: Archive as a resolution target

**Objective:** As a catalogue maintainer, I want archived concepts to stay wikilink-resolvable, so that archiving one concept does not break links in unrelated files.

#### Acceptance Criteria

1. THE okf-cli SHALL include `_archive/<bundle>/**` in the basename index built by `build_concept_basename_index`.
2. WHEN a basename has at least one active candidate THE okf-cli SHALL resolve it against the active candidates only.
3. WHEN a basename has no active candidate THE okf-cli SHALL resolve it against the archived candidates.
4. WHEN a basename has two or more active candidates THE okf-cli SHALL report it as ambiguous, unchanged from today.

#### Success Criteria

- SC-01: After archiving a concept that an active concept links to, `check` over the five opted-in bundles reports zero violations.
- SC-02: With an active and an archived concept sharing a basename, the link resolves to the active one rather than reporting ambiguity.
- SC-03: Removing the precedence rule from the index turns SC-02's test red — the guard is proven by its own reversal, and the test stays in the repo.

_Requirements: R-05, R-06_

## Recommended Skills

- `superpowers:test-driven-development`


## 2026-08-09 — Prelude from Gate B (ce-verify-operationalization, finding F01)

AC4 ("WHEN a basename has two or more active candidates THE okf-cli SHALL report it as ambiguous, unchanged from today", spec A07, `docs/okf-archive-lifecycle/SPEC.md:159`) carries no success criterion. SC-01 … SC-03 only cover AC1 … AC3.

Do this first, in this task, not in a follow-up: add an SC-04 that asserts a basename with two active candidates is still reported as ambiguous once archive resolution is in place, and cover it with a named test. Adding a test that secures an existing acceptance criterion is not a plan deviation and needs no escalation.
