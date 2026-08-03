---
# okf-cli-kgt2
title: Migrate the catalogue's remaining legacy crosslinks
status: draft
type: task
created_at: 2026-08-03T18:26:10Z
updated_at: 2026-08-03T18:26:10Z
---

The catalogue still carries both link forms side by side. Sampling `home-lab-wiki` shows canonical `](/home-lab-wiki/services/authelia.md)` next to legacy bundle-relative `](/services/...)`, `](/context/...)`, `](/decisions/...)`.

Legacy links are not cosmetic debt: `check_crosslink_format` flags a leading-`/` link that does not resolve from the catalogue root as dangling (the phantom-orphan class), and such a link orphans in Obsidian. `fix-crosslinks` migrates them — `resolve_crosslink_target` tries the legacy bundle-root reading first precisely so this works, and the rewrite is idempotent on already-canonical links.

Deliberately left undone in the session that found this (2026-08-03): the run WRITES into the Obsidian store, which needs explicit confirmation. Draft until the PO releases it.

- [ ] `okf-cli --root <kc> fix-crosslinks --check` per bundle, record the scope (how many files, how many links, any unresolved targets)
- [ ] present the unresolved list to the PO first — an unresolvable target is a broken reference, not a format issue, and must not be silently left behind
- [ ] confirm, then run without `--check`
- [ ] `okf-cli --root <kc> check` afterwards: zero `crosslink-format` violations
- [ ] spot-check a migrated note in Obsidian: links resolve, graph edges intact

## Context

Verified during the I01/I02 work: the canonical form is catalogue-root-absolute (`/bundle/subdir/concept.md`, leading `/` = catalogue root = Obsidian vault root). Sources of truth for that: `resolve_crosslink_target` docstring, the `bundle_graph` and `build_ref_matrix` comments, and the `fix-crosslinks` help text. The CLI test suite was migrated onto this form in the same session — before that, 21 tests still asserted the superseded bundle-relative form.
