---
# okf-cli-6dsl
title: announce that the semantic arm does not cover the archive
status: todo
type: task
created_at: 2026-08-09T19:15:04Z
updated_at: 2026-08-09T19:15:04Z
parent: okf-cli-scd5
blocked_by:
    - okf-cli-pn72
---

The embedding build (`cli/embeddings/build_tagvec.py:174`) stays on the active catalogue: embeddings cost API calls for material that is hidden by default. That is a deliberate limit, and an unannounced limit is a trap — the user would search an archive the answering arm never saw and read the empty result as an answer. One note per arm per invocation, following the existing degradation notes (PF-4).

### Requirement 1: A named limit instead of a silent one

**Objective:** As a searcher, I want to be told when my archive flag did not reach the arm that answered, so that an empty result is not mistaken for an absence.

#### Acceptance Criteria

1. WHEN `--include-archive` is set AND the semantic arm contributes hits THE okf-cli SHALL write exactly one note to stderr stating that the flag covers the lexical arm only.
2. WHILE `--include-archive` is not set THE okf-cli SHALL write no such note.
3. THE okf-cli SHALL write the note at most once per invocation.

#### Success Criteria

- SC-01: A `find --include-archive` whose answer contains semantic hits carries the note on stderr.
- SC-02: The same query without the flag carries no note.

_Requirements: R-13_

## Recommended Skills

- `superpowers:test-driven-development`
