---
# okf-cli-3geg
title: 'P7 — .tagvec provenance: pull producer into repo'
status: todo
type: task
priority: normal
created_at: 2026-07-25T18:13:10Z
updated_at: 2026-07-25T18:13:10Z
parent: okf-cli-5hg4
blocked_by:
    - okf-cli-5qmn
---

## Objective (User Story)
As a maintainer, I want the `.tagvec` embedding producer in-repo and its embedded scope documented so that the semantic backstop design (P8) rests on a known, reproducible asset.

## EARS Acceptance
- THE producer script SHALL live in-repo and regenerate a `tag_vectors.sqlite` with the `emb(key,tag,model,dim,vec)` schema (RET10) from a catalogue root.
- THE README SHALL document embedded scope (tags only, `emb.tag`) and state that `find` reads this cache at runtime but never produces it.
- THE task SHALL record a written finding: tag-embeddings only vs. body-embeddings needed — this decides P8's fallback surface.

## Success Criteria
- SC-001: `cli/embeddings/build_tagvec.py` regenerates the emb schema.
- SC-002: `cli/embeddings/README.md` states tags-only scope + runtime-read/offline-produce split.
- SC-003: tags-vs-body decision recorded for P8.

## Grounding
Live cache `~/Obsidian/Knowledge-Catalogue/.tagvec/tag_vectors.sqlite` (627 bge-m3 + 650 voyage rows, RET10). Producer SOP: `Knowledge-Catalogue/okf-meta-wiki/extensions/embedding-based-tag-consolidation.md` (RET11).
GATES P8. Full steps: PLAN.md Task 7.
Commit: `feat(embeddings): bring tagvec producer + provenance into repo`
