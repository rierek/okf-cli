---
# okf-cli-bux0
title: T06 — define the profile switches
status: completed
type: task
priority: high
created_at: 2026-08-09T20:44:41Z
updated_at: 2026-08-11T19:47:24Z
parent: okf-cli-03o1
---

Name the switches for the ten extension rules and assign them to the `okf` and `catalogue` profiles.

Deliberately deferred during the spec phase. None of the 26 spec files names a switch; they say "bound to a switch" and defer here. Grep for "T06" across `docs/okf-cli-rust-rewrite/spec/` to collect every deferred question.

Candidate set is the ten non-normative rules in `spec/check.md`, section "Zuordnung zur Norm": type-registered, tag-registered, english-keys, crosslink-format, wikilink-resolvable, tags-block-form, xml-like-tags, filename-chars, asset-placement, entry-file-description.

Open sub-question carried over: whether `wikilink-resolvable` keeps its bundle-granular opt-in list (`wikilink_checked_bundles`) or collapses to a plain switch. The granularity has a reason — it keeps the gate quiet while two large bundles are unclean — and the profile model must not lose it.

## PO decision 2026-08-11
D09, D12 and D13 are confirmed: provide `okf` and `catalogue` profiles, permit individual extension overrides, default semantic retrieval on only in `catalogue`, and apply CLI/MCP argument > config override > profile > built-in default. This task still names the individual extension switches and maps the ten extension rules.

## Completion 2026-08-11
D15-D20 are now encoded in `spec/_common.md`: eleven named Boolean switches, profile defaults, `--profile`, MCP precedence and the top-level Wikilink positive-list contract. `just spec-check` passed with 356 requirements and zero violations.
