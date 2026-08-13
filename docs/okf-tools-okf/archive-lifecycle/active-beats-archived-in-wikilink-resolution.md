---
type: Concept
title: Active beats archived when a wikilink resolves, and the move simulation must agree
description: Archiving a concept would strand every inbound ``[[x]]`` as unresolved, so the basename index includes _archive/ — but with a precedence rule, otherwise archive-then-recreate makes every such link ambiguous. The same rule has to run in the dry-run's index simulation.
tags:
  - okf-cli
  - archive
  - wikilinks
timestamp: 2026-08-10T12:10:00Z
---

# Active beats archived when a wikilink resolves, and the move simulation must agree

`build_concept_basename_index` traverses `list_bundles(root)`, and `is_bundle_dir` excludes `_`-prefixed directories. An archived concept was therefore no longer a resolution target: every inbound ``[[x]]`` went unresolved, and in the bundles that opt into wikilink checking via `.okf.toml`, `check_wikilink_resolvable` reported violations **in files the archiver never touched**. The catalogue's own `.okf.toml` comment declares every warning from there a real regression, so this was not cosmetic.

So the index includes `_archive/<bundle>/**`. On its own that trades one defect for another, which is why it comes with a rule:

> If at least one **active** candidate exists for a basename, only the active candidates count. Only when no active one exists does the link resolve to the archived one or ones.

Without it, archiving a concept and creating a new one under the same name would make every ``[[x]]`` ambiguous — the single most likely thing to happen after an archive. The existing ambiguity semantics among active concepts are untouched: two active candidates stay `ambiguous`, and two archived ones with no active counterpart do too.

## The simulation is a second implementation of the same rule

`_index_after_move` simulates the index *after* the move to determine `turns_ambiguous` for the dry run. It must apply the identical precedence rule. Without it the dry run reports ambiguity that would not arise, and — because the guard is honest — refuses to proceed without `--force`. A correct implementation plus a stale simulation is indistinguishable from a broken implementation, from where the user stands.

Markdown crosslinks need nothing: `plan_rename` rewrites them to the `_archive/` path, the target exists, the link stays valid.

## Two side effects, checked and harmless

Recorded so nobody re-derives them under time pressure:

- `bundle_of` returns `_archive` for an archive path, so the move counts as cross-bundle and the outbound pass runs. It changes nothing, because `link_expr` emits catalogue-root-absolute links, which are location-independent.
- `plan["bundles"]` contains `_archive` alongside the origin bundle, so `reindex_tree` runs over both. Under `_archive/` it finds no `index.md` and does nothing, while the origin bundle's `index.md` correctly loses the entry.

## Why the guard on this rule needs a resolution assertion

The test protecting the precedence rule originally asserted only `assertNotIn("turns-ambiguous", out)`. Under the inverted mutation — archived winning over active — the result stays a *single* candidate, just the wrong one, so no ambiguity line is printed and the test stays green while the link resolves into `_archive/`. Absence of a warning has more than one cause; the assertion has to name the resolved target:

```python
after_index = okf.build_concept_basename_index(root)
self.assertEqual(okf.resolve_wikilink(after_index, "a/other.md", "old"),
                 ("resolved", ["/d/old.md"]))
```

Generalized in the OKF playbook ``[[autonome-agent-kette]]`` as one of three blind spots of the mutation probe. The cross-catalogue reference is shown as code because cross-catalogue wikilink resolution is out of scope.
