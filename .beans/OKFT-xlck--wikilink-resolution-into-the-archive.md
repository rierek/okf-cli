---
# OKFT-xlck
title: wikilink resolution into the archive
status: todo
type: feature
priority: normal
tags:
    - accepted
created_at: 2026-08-09T19:13:45Z
updated_at: 2026-08-10T08:05:29Z
parent: OKFT-huow
---

`build_concept_basename_index` (cli/okf-cli.py:3208) walks `list_bundles(root)`, and `is_bundle_dir` (:69) excludes `_`-prefixed names. An archived concept therefore stops being a wikilink target, every inbound `[[x]]` goes unresolved, and `check_wikilink_resolvable` (:3326) reports it in the five bundles opted in via `.okf.toml` — whose comment declares any warning from them a real regression.

Covers R-05 … R-07 of `docs/okf-archive-lifecycle/SPEC.md`.


## Review 2026-08-10

- US-05 · an inbound `[[x]]` still resolves after `x` is archived, `check` stays violation-free · a
- US-06 · with one active and one archived candidate of the same basename the link resolves to the active one; two active candidates stay `ambiguous` · a
- US-07 · the dry run applies the same precedence rule, so it does not warn about ambiguity the move would not create · a

US-05 also surfaced the split between the two link kinds: the markdown link was rewritten to `(/_archive/agent-memory/mein-konzept.md)`, the wikilink stayed `[[mein-konzept]]` in the source and now finds its target through the basename index. Where the basename collided, the rewrite reported `skipped-ambiguous` and declined rather than bending the link to a guessed target.

US-06 was evaluated on a run that showed `1 resolved, 1 ambiguous` before the move and `2 resolved, 0 ambiguous` after — A07 and A06 in one pass. The linking file has to sit in a third bundle for the ambiguity to appear at all: on a collision the linking file's own bundle wins (cli/okf-cli.py:3460), which is pre-existing behaviour unrelated to the archive.

US-07 was first run by the PO on a fixture that had not been reset, where both candidates would have ended up archived; the dry run correctly reported `turns-ambiguous` twice there. On the clean state it stays silent, which is the actual R-07 evidence. The `1 skipped-ambiguous` in the summary line reflects the pre-existing ambiguity of that wikilink, not a consequence of the move.

Considered and deliberately not filed: the dry run prints `wikilink-collision  new basename already taken by …` even when the precedence rule makes the collision inconsequential. The line states something true — the basename is taken — and the absence of `turns-ambiguous` two lines above carries the consequence. PO agreed no bean.
