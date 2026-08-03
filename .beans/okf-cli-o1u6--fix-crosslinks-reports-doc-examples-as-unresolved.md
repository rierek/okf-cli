---
# okf-cli-o1u6
title: fix-crosslinks reports doc examples as unresolved
status: draft
type: task
priority: deferred
created_at: 2026-08-03T19:10:30Z
updated_at: 2026-08-03T19:37:56Z
---

## Context

Found while running the kgt2 crosslink migration (2026-08-03). The write run itself was clean: 4 files, 4 links, `check` reports 0 violations, re-run reports `0 file(s) would rewrite`.

What is misleading is the second half of the report. `fix-crosslinks` listed 13 links as `unresolved`, which reads as "13 broken references in the catalogue". Not one of them is.

## Evidence

All 13 sit inside inline code, as format examples in the very documentation that describes the link format:

    okf-meta-wiki/baseline/cross-linking.md
      `[customers table](/tables/customers.md)`
    okf-meta-wiki/extensions/bundle-relative-links-and-cross-bundle-limitation.md
      `[Title](/subdir/concept.md)`
    okf-meta-wiki/examples/minimal-conformant-concept-file.md
      `/pfad/zum/concept.md`

Distribution: okf-meta-wiki 10, memory-layer-wiki 2, claude-code-wiki/skills-commands/okf-skill.md 1.

## Why this is not a rewriter bug

`resolve_crosslink_target` returns None when the target file does not exist, and its docstring names that as deliberate — "the safety anchor that leaves doc examples on non-existent paths untouched". The examples are never rewritten. The behaviour is correct; only the label is wrong.

The cost is that the report cannot distinguish a genuine dangling reference from a placeholder, so a real one would hide in the noise. The same input feeds `check_crosslink_format`'s phantom-orphan class.

## Acceptance

[ ] the link extractor skips inline code spans and fenced blocks, OR the report separates placeholders from genuine dangling targets as its own category

[ ] a real dangling reference still surfaces, with a test that proves it is not swallowed by the new rule

[ ] fix-crosslinks --check against the catalogue reports a placeholder count of 0 in the unresolved category
