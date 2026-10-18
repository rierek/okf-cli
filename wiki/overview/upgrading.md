---
title: "Upgrading"
description: "Move from the Python okf CLI to the Go binary and between releases."
---

## Purpose

Say what changes for a user of the Python CLI and how to switch without surprises.

## Audience

An existing user of `okf-cli` 0.2.x (Python script, wheel, pipx or `uv tool`).

## Required sections

### What changed

- One static binary, no Python at run time; the Python CLI is still published. Source: FACTS §Topic: upgrade from the Python CLI.
- Frontmatter edits patch only the edited lines instead of re-serialising. Source: FACTS §Topic: upgrade from the Python CLI.
- Deviations from the Python CLI that await a product-owner decision are listed on Known limitations only after the decision (CONCEPT D10). Source: FACTS Nicht bestimmbar part 2.

### Switch steps

- Install the new binary, make it the first `okf` on PATH (`type -a okf`), run `okf install --apply` again, restart agent sessions. Source: FACTS §Topic: install; FACTS §Topic: upgrade from the Python CLI.
- No `--version` to confirm which binary runs; use `file "$(command -v okf)"` [i2ws]. Source: FACTS §Defect list d.

### Existing indexes

- `.fts/fts.sqlite` and `.tagvec/tag_vectors.sqlite` from the Python CLI keep working. Source: FACTS §Topic: index and search artefacts; FACTS §Topic: upgrade from the Python CLI.

### Exit codes and help text

- Exit-code classes 0-5 as in the reference; help text of some commands still names exit 1 where the code exits 4 [irxe] [vf2r]. Source: FACTS §Topic: exit-code classes.

### Reference

- Links to Installation and the exit-code reference. Source: FACTS §Topic: exit-code classes.
