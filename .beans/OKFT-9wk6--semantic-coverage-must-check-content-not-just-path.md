---
# OKFT-9wk6
title: semantic_coverage() must check content, not just path presence
status: completed
type: bug
priority: normal
created_at: 2026-08-10T17:12:35Z
updated_at: 2026-08-10T17:17:25Z
---

semantic_coverage(root, paths) in cli/okf-cli.py compares PATH sets against concept_emb only. It ignores concept_cache_key(model, path, text), so a concept whose body changed after embedding still counts as covered because its old row's path matches. Consequence: prime reports "semantic index: complete" and build-semantic-index --if-stale skips a rebuild, even though plan_concept_delta() (the producer's own detector) reports the concept stale. Measured 2026-08-10 against the live catalogue: plan_concept_delta found 40 stale concepts while prime reported 2517/2517 embedded.

Fix: semantic_coverage() must delegate to plan_concept_delta() (content-hash comparison, same concept_cache_key the producer uses) instead of running its own weaker path-set comparison. The full content check costs ~2.2s over 2590 concepts (offline) -- keep that cost out of the default prime path (gate behind a flag), but never dilute the counting method itself.


## Todo
- [x] RED: unit tests for semantic_coverage() content-hash detection (uses concept_cache_key via production functions)
- [x] RED: CmdBuildSemanticIndex reversal test -- changed body without re-embed must trigger --if-stale rebuild
- [x] GREEN: semantic_coverage() delegates to plan_concept_delta()
- [x] Gate the ~2.2s content check out of default prime path (flag), keep --if-stale unconditional/correct
- [x] Update existing prime fixtures/tests to real content-hash keys
- [x] just test green, commit


## Summary of Changes
cli/okf-cli.py: semantic_coverage(root, paths) now delegates to
plan_concept_delta() (content-hash comparison via concept_cache_key over
title+body) instead of comparing PATH sets against concept_emb. This is the
same detector cmd_build_semantic_index's normal run already used to decide
what to embed -- checker and producer now share one scan.

_semantic_coverage_line()/render_catalogue_state() gained a `thorough` flag
(default False). Bare `prime` reports semantic-index PRESENCE only ("semantic
index: present -- staleness not checked by default ..."); the real
content-hash check (~2.2s over ~2600 concepts, offline) runs only with the
new `prime --check-semantic` flag. `build-semantic-index --if-stale` is
unaffected -- it always calls the now-correct semantic_coverage() directly,
unconditionally.

Verified: a body edit with no re-embedding now (a) makes
semantic_coverage() report (0, 1) instead of (1, 1) for that concept, and
(b) makes `build-semantic-index --if-stale` actually re-embed it (previously
skipped with "index is current"). `just test`: 675 tests, OK.
