---
title: "Known limitations"
description: "Open defects and limits of okf, by short ID, with effect and workaround."
---

## Purpose

List every open finding with symptom, effect and workaround, so a user can check a problem against it first.

## Audience

A user who hits unexpected behaviour; a maintainer who plans fixes.

## Required sections

### How to read an ID

- `[abcd]` is the short ID of the tracker item; the list is maintained by hand; each row shows its status. Source: canon limitations/known-limitations-page.

### Measured on

- `Measured on okf <version>, <date>.` (checkout `df4c194`, 2026-10-18 for the fact base). Source: FACTS §Source of truth.

### Open limitations

- [irxe] `okf tags --validate` exits 4, help says 1. Workaround: test for non-zero. Source: FACTS §Defect list a.
- [jh7t] zsh completion script comments name argcomplete and `okf-cli.py`; no behaviour change. Source: FACTS §Defect list b.
- [71rn] Homebrew formula is head-only and builds from source. Workaround: `brew install --HEAD okf-cli`, or the release binary. Source: FACTS §Defect list c.
- [i2ws] No `--version` flag. Workaround: file hash or `brew info`. Source: FACTS §Defect list d.
- [dqq5] Release binaries are not run before upload. Workaround: run the downloaded asset. Source: FACTS §Defect list e.
- [c0mc] No statement whether macOS binaries are signed or notarised. Source: FACTS §Defect list f.
- [vf2r] `ctx show`, `read`, `check`, `edit` exit 4 for a dead entry, help says 1. Workaround: test for non-zero. Source: FACTS §Defect list g.
- [erpf] `tags --register` and `prime` name `build_tagvec.py`, which a Go install lacks. Workaround: ignore, or `okf build-tagvec --produce`. Source: FACTS §Defect list h.
- [l2j0] `okf --help` describes the Python script. Workaround: ignore. Source: FACTS §Defect list i.
- [fs8c] A blocked `install` plan exits 1 with a generic message. Workaround: read the plan, or use `--json`. Source: FACTS §Defect list j.
- [zs6t] README, `docs/install.md`, `pyproject.toml` and the Homebrew formula still name the old GitHub owner `xRiErOS`; the repo and this site live under `rierek`. Workaround: use `rierek/okf-cli`; check the tap and release URLs before you copy a command. Source: FACTS §Topic: Homebrew formula; FACTS §Topic: install.

### Fixed

- Empty until the first fix release. Source: canon limitations/finding-traceability, step 7.

### Decisions pending

- Deviations from the Python CLI that await the product owner (D-03 to D-60 of the acceptance report) appear here only after the decision (CONCEPT D10). Source: FACTS Nicht bestimmbar part 2.
