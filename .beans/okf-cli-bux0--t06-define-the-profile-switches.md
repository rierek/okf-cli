---
# okf-cli-bux0
title: T06 — define the profile switches
status: todo
type: task
priority: high
created_at: 2026-08-09T20:44:41Z
updated_at: 2026-08-09T20:44:41Z
parent: okf-cli-03o1
---

Name the switches for the ten extension rules and assign them to the `okf` and `catalogue` profiles.

Deliberately deferred during the spec phase. None of the 26 spec files names a switch; they say "bound to a switch" and defer here. Grep for "T06" across `docs/okf-cli-rust-rewrite/spec/` to collect every deferred question.

Candidate set is the ten non-normative rules in `spec/check.md`, section "Zuordnung zur Norm": type-registered, tag-registered, english-keys, crosslink-format, wikilink-resolvable, tags-block-form, xml-like-tags, filename-chars, asset-placement, entry-file-description.

Open sub-question carried over: whether `wikilink-resolvable` keeps its bundle-granular opt-in list (`wikilink_checked_bundles`) or collapses to a plain switch. The granularity has a reason — it keeps the gate quiet while two large bundles are unclean — and the profile model must not lose it.
