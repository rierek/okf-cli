---
# okf-cli-uumj
title: Make a stale concept_emb visible, like .fts
status: todo
type: task
priority: normal
created_at: 2026-07-26T07:34:54Z
updated_at: 2026-07-26T07:34:54Z
parent: okf-cli-wuiv
---

Surfaced in T08 (`okf-cli-kc9x`), 2026-07-26, while diagnosing a baseline failure.

Under conditional handover (D12), when the lexical arm is not confident the semantic arm owns
the ranking and lexical hits are appended behind it — then truncated at `--limit`. A concept
that exists in the file tree but has **no `concept_emb` row** can therefore be displaced out of
the result entirely, even when it is the correct lexical answer.

This is not a defect in D12: R43 measured exactly this rule. But it measured it on a catalogue
where **every** concept was embedded. A curated, written store does not stay in that state — new
notes appear continuously and the producer runs occasionally. For the newest content, handover
is therefore worse than the pre-plan pin rule, and it fails **silently**: the user sees results,
just not the right ones.

`.fts` already got staleness detection for exactly this class of problem (D15). `concept_emb`
did not.

### Requirement 1: A stale embedding cache is visible, not silent

**Objective:** As someone searching a catalogue I have just written into, I want to be told when
the semantic index does not yet cover my newest notes, so that a missing result is explained
rather than mysterious.

#### Acceptance Criteria

1. THE CLI SHALL detect WHEN the catalogue contains concepts that have no `concept_emb` row for
   the active model.
2. WHEN such concepts exist THE CLI SHALL print one stderr note naming the count and the
   producer command that fixes it.
3. THE detection SHALL use file metadata and a row count, and SHALL NOT read concept bodies.
4. THE note SHALL NOT change ranking — visibility only, no scoring change.

#### Success Criteria

- SC-01: a catalogue with N unembedded concepts produces exactly one stderr note naming N.
- SC-02: a fully embedded catalogue produces no note.
- SC-03: `find` stdout is byte-identical with and without the note.

## Open design question for the PO — do NOT decide unilaterally

Visibility is the cheap half. The open half: should a confident-but-unembedded lexical hit be
guaranteed a slot when the semantic index is known stale? That would soften D12 and must be
measured, not argued — the eval harness from `okf-cli-uagv` can answer it. Raise it with the PO
once the numbers from T09 exist.

_Requirements: surfaced by okf-cli-kc9x · relates to D12, D15 · measurement base R43_
