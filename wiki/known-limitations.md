---
title: "Known limitations"
description: "Open defects and limits of okf, by short ID, with effect and workaround."
---

## Purpose

List every open finding with symptom, effect and workaround, so a user can check a problem against it first.

## Audience

A user who hits unexpected behaviour; a maintainer who plans fixes.

## Visual elements

Table of open limitations; caution callout.

## Search terms

okf known issues; okf limitations; okf bugs

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
- [cwyx] The frontmatter writer refuses shapes it cannot patch (lone CR, flow-mapping or null root, anchor/alias/tag on the edited value, comment in a flow list, other shapes, ctx edits, huge ctx positions, non-scalar keys); Python wrote them. Exit 2 with `<path>: <reason>`, file untouched. Workaround: edit the file by hand. Source: ACCEPTANCE-REPORT D-03 to D-07, D-17, D-18, D-43.
- [n760] One refused file ends the whole run of `merge-tags`, `remove-tags`, `normalize-tags` and `migrate`, a dry run too. Workaround: repair or move the file, then rerun. Source: ACCEPTANCE-REPORT D-08, D-09.
- [xhfi] The parser refuses frontmatter that Python reads (`\/` escape, unusual anchor names, empty keys, U+0085, U+2028, U+2029). Workaround: replace the character or form. Source: ACCEPTANCE-REPORT D-26, D-27.
- [4752] Frontmatter is validated less strictly than in Python (equal duplicate keys, invalid tag values, merge-key misuse, impossible dates such as `2026-02-30`). Workaround: `okf check` and an external YAML linter. Source: ACCEPTANCE-REPORT D-29, D-30.
- [6xot] A TOML integer above int64 in a config file aborts every command that reads the config. Workaround: remove the number. Source: ACCEPTANCE-REPORT D-28.
- [lazz] `okf recent` prints UTC when `TZ` is a POSIX rule string. Workaround: set `TZ` to an IANA name. Source: ACCEPTANCE-REPORT D-52.
- [3hfd] Cherokee text: case folding is not idempotent, so a heading in the other case is not found. Workaround: type the stored case. Source: ACCEPTANCE-REPORT D-59.
- [qo6x] Timeouts limit the whole request, not each socket wait as in Python. Workaround: retry. Source: ACCEPTANCE-REPORT D-60.

### Fixed

- Empty until the first fix release. Source: canon limitations/finding-traceability, step 7.
