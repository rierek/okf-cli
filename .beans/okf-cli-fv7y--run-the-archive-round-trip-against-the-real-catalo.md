---
# okf-cli-fv7y
title: run the archive round trip against the real catalogue
status: todo
type: task
priority: normal
created_at: 2026-08-09T19:15:18Z
updated_at: 2026-08-09T19:25:42Z
parent: okf-cli-huow
blocked_by:
    - okf-cli-16rg
    - okf-cli-pnyf
    - okf-cli-fu7o
    - okf-cli-iwx4
    - okf-cli-6dsl
---

A green suite proves the fixtures. This proves the catalogue. `~/Obsidian/Knowledge-Catalogue` has no `_archive/` today — this run creates it and removes it again.

### Requirement 1: Proof on the real store

**Objective:** As the product owner, I want the archive path exercised once against the real catalogue, so that the feature is accepted on evidence rather than on fixtures.

#### Acceptance Criteria

1. THE operator SHALL archive one concept in `~/Obsidian/Knowledge-Catalogue` and record the command output.
2. THE operator SHALL run `check` over the five bundles opted into the wikilink rule and record the result.
3. THE operator SHALL run the same `find` query with and without `--include-archive` and record both results.
4. THE operator SHALL run `find --scope <bundle> --include-archive` against the concept's own bundle while it is archived and record the result.
5. THE operator SHALL restore the concept and confirm that the working tree is clean afterwards.

#### Success Criteria

- SC-01: `check` reports zero violations across the five opted-in bundles while the concept is archived.
- SC-02: The query without the flag omits the archived concept and the query with the flag returns it.
- SC-03: `find --scope <bundle> --include-archive` returns only archived concepts of that bundle — the archived concept under test appears, and no archived concept from a foreign bundle appears.
- SC-04: `git status` in the catalogue is clean after the restore.

_Requirements: R-15_

## Recommended Skills

- `superpowers:verification-before-completion`


## 2026-08-09 — Prelude from Gate B (ce-verify-operationalization, finding F02)

`docs/okf-archive-lifecycle/SPEC.md:181` asks the real-catalogue run to replay A05 and A08 through A10. The acceptance criteria above cover A08 and A09; the scoped run A10 is missing.

Do this first, in this task: add an acceptance criterion and a success criterion for `find --scope <bundle> --include-archive` against `~/Obsidian/Knowledge-Catalogue`, proving that only that bundle's archived concepts come back. Record the command and its output like the other runs.
