---
# OKFT-eyla
title: Settle whether mutation commands should touch _ staging content
status: completed
type: task
priority: low
created_at: 2026-08-13T12:28:21Z
updated_at: 2026-08-13T17:37:27Z
---

Split out of OKFT-oe8t on 2026-08-13 so that bean could stay inside its retrieval-surface mandate.

okf-cli's writing commands disagree with each other about `_`-prefixed staging directories, and always have:

- `fix_crosslinks` (okf-cli.py:3290) and `fix_xml_like_tags` (:3140) walk `iter_all_md`, which prunes `_`. They **skip** staging content.
- `cmd_merge_tags` (:267), `cmd_remove_tags` (:304) and `cmd_normalize_tags` (:357) walk `iter_concepts`. They **repair** staging content.

OKFT-oe8t added a `_` prune to `iter_concepts` for the retrieval surface and would have flipped the second group to match the first as a side effect. That was reverted — the epic's mandate was index/list/find, and silently shrinking what a writing command repairs is not a side effect worth taking unasked. The three tag commands keep the wide walk explicitly.

So the inconsistency is now deliberate and documented rather than accidental, but it is still an inconsistency.

The question: should a writing command repair files in `_intake/`, or leave staging alone until it is drained?

The case for repairing: a tag rename that skips `_intake/` leaves stale tags in files that will later be drained into the bundle proper, carrying the old vocabulary in with them. Nothing reports this.

The case for skipping: staging is by definition not yet part of the bundle, `check` never verified it, and a tool that rewrites files nobody has reviewed is doing work that will be redone at drain time anyway.

Whichever way it goes, both groups should end up on the same rule, and a test should pin it. Today's split is invisible to anyone who does not read the call sites.
