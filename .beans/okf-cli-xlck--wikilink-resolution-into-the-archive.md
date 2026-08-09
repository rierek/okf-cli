---
# okf-cli-xlck
title: wikilink resolution into the archive
status: todo
type: feature
created_at: 2026-08-09T19:13:45Z
updated_at: 2026-08-09T19:13:45Z
parent: okf-cli-huow
---

`build_concept_basename_index` (cli/okf-cli.py:3208) walks `list_bundles(root)`, and `is_bundle_dir` (:69) excludes `_`-prefixed names. An archived concept therefore stops being a wikilink target, every inbound `[[x]]` goes unresolved, and `check_wikilink_resolvable` (:3326) reports it in the five bundles opted in via `.okf.toml` — whose comment declares any warning from them a real regression.

Covers R-05 … R-07 of `docs/okf-archive-lifecycle/SPEC.md`.
