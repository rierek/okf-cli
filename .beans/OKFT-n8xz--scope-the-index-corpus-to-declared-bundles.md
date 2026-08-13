---
# OKFT-n8xz
title: Scope the index corpus to declared bundles
status: todo
type: task
priority: high
created_at: 2026-08-13T11:07:18Z
updated_at: 2026-08-13T11:08:04Z
parent: OKFT-wmbu
blocked_by:
    - OKFT-xori
blocking_external: lean-stack:LES-zr4r
---

Add a second, narrower bundle set beside list_bundles - e.g. list_indexable_bundles(root) - derived from the .okf.toml bundle key, falling back to the existing name filter when the key is absent (catalogue behaviour, correct there).

Use it ONLY at the index and search call sites: okf-cli.py:740 (build-index), 785 (freshness stats), 851 (semantic coverage / --if-stale), 3312 and 3317 (resolve_scopes -> find).

Do NOT touch is_bundle_dir, and do NOT narrow these call sites: 3627 and 3636 (build_concept_basename_index), 3721 (wikilink_checked_bundles validation), 3765 (wikilinks target validation), 3964 (symlink traversal), nor the presentation sites 166, 560, 585, 588, 1909, 1962.

Reason for the split: okf-tools-okf/archive-lifecycle/active-beats-archived-in-wikilink-resolution documents what narrowing list_bundles costs - every inbound [[x]] went unresolved and check reported violations in files the archiver never touched. Narrowing the corpus must not narrow resolution, or a loud defect is traded for a silent one.

Expected effect: corpus drops from 197 to 41 documents in lean-stack/docs.
