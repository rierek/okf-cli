---
# OKFT-uctf
title: Arm the wikilink guard for okf-tools' own docs
status: completed
type: task
priority: normal
created_at: 2026-08-13T12:10:53Z
updated_at: 2026-08-13T17:37:27Z
---

Found while reviewing OKFT-glon, 2026-08-13. Two related gaps, both in the guard rather than in the code it guards.

## 1. `check` cannot see wikilink breakage in this repo

`docs/.okf.toml` carries no `wikilink_checked_bundles` key. Verified mechanically: `wikilink_checked_bundles(config, root)` returns `set()`, so `wl_checked` in `run_checks` is empty and `check_wikilink_resolvable` (okf-cli.py:3797-3815) returns `[]` for every file no matter what state its links are in. A deliberately dead link left `okf-cli --root docs check` sitting at its usual 33 violations, unmoved.

That is why the OKFT-glon break-test had to assert over `okf-cli wikilinks --unresolved` instead of `check` as its own text prescribed. The substitute is mechanism-equivalent — both paths run `resolve_wikilink_records` → `resolve_wikilink` → `build_concept_basename_index` — but it means the repo's own default integrity command is blind to the failure class this epic spent two review rounds guarding against.

Proposal: add `wikilink_checked_bundles = ["okf-tools-okf"]` to `docs/.okf.toml`. The catalogue precedent is deliberate about this — its own `.okf.toml` opts bundles in one at a time and explicitly keeps `qm-wiki` and `general-knowledge-wiki` out because their unresolved counts would drown the gate. So the first step is to measure: how many unresolved links does `okf-tools-okf` carry today? Arm the gate only if that number is zero or small enough that any warning is a real regression rather than pre-existing debt.

## 2. Direction 1 of the break-test is pinned by argument, not by a test

The OKFT-glon probe ran a wikilink from a topic folder into a bundle concept and one in reverse. The reverse direction breaks visibly under a narrowing mutation; the forward direction cannot break under **any** bundle-narrowing mutation of `build_concept_basename_index`, because its target lives inside the declared bundle by construction. Its real risk is a narrowed *source* traversal, which `CheckAndWikilinksStayWideWithDeclaredBundle` covers — the reviewer hunted for a mutation that slips past both existing guards and found none.

So the coverage is real, but it rests on a structural argument. A direct test — source outside the declared bundle, target inside, assert it still resolves — would pin the same property where a future refactor would trip over it. Suggested name: `test_wikilink_from_outside_the_declared_bundle_resolves`.

Neither item blocks anything. Both are hardening on top of a guard that currently holds.
