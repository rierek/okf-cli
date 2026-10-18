---
title: "Known limitations"
description: "Open defects and limits of okf, by short ID, with effect and workaround."
---

Check an unexpected result against this list first. Each row names one open defect or limit, its effect and, where one exists, a workaround.

Measured on okf 0.2.4, 2026-10-18.

## How to read an ID

`[abcd]` is the short ID of an item in the project tracker. The same ID appears in square brackets on the page that is affected. The list is maintained by hand.

## Open limitations

- [irxe] `okf tags --validate` exits 4, help says 1. Workaround: test for non-zero.
- [jh7t] zsh completion script comments name argcomplete and `okf-cli.py`; no behaviour change.
- [71rn] Homebrew formula is head-only and builds from source. Workaround: `brew install --HEAD okf-cli`, or the release binary.
- [i2ws] No `--version` flag. Workaround: file hash or `brew info`.
- [dqq5] Release binaries are not run before upload. Workaround: run the downloaded asset.
- [c0mc] No statement whether macOS binaries are signed or notarised.
- [vf2r] `ctx show`, `read`, `check`, `edit` exit 4 for a dead entry, help says 1. Workaround: test for non-zero.
- [erpf] `tags --register` and `prime` name `build_tagvec.py`, which a Go install lacks. Workaround: ignore, or `okf build-tagvec --produce`.
- [l2j0] `okf --help` describes the Python script. Workaround: ignore.
- [fs8c] A blocked `install` plan exits 1 with a generic message. Workaround: read the plan, or use `--json`.
- [zs6t] README, `docs/install.md`, `pyproject.toml` and the Homebrew formula still name the old GitHub owner `xRiErOS`; the repo and this site live under `rierek`. Workaround: use `rierek/okf-cli`; check the tap and release URLs before you copy a command.
- [cwyx] The frontmatter writer refuses shapes it cannot patch (lone CR, flow-mapping or null root, anchor/alias/tag on the edited value, comment in a flow list, other shapes, ctx edits, huge ctx positions, non-scalar keys); Python wrote them. Exit 2 with `<path>: <reason>`, file untouched. Workaround: edit the file by hand.
- [n760] One refused file ends the whole run of `merge-tags`, `remove-tags`, `normalize-tags` and `migrate`, a dry run too. Workaround: repair or move the file, then rerun.
- [xhfi] The parser refuses frontmatter that Python reads (`\/` escape, unusual anchor names, empty keys, U+0085, U+2028, U+2029). Workaround: replace the character or form.
- [4752] Frontmatter is validated less strictly than in Python (equal duplicate keys, invalid tag values, merge-key misuse, impossible dates such as `2026-02-30`). Workaround: `okf check` and an external YAML linter.
- [6xot] A TOML integer above int64 in a config file aborts every command that reads the config. Workaround: remove the number.
- [lazz] `okf recent` prints UTC when `TZ` is a POSIX rule string. Workaround: set `TZ` to an IANA name.
- [3hfd] Cherokee text: case folding is not idempotent, so a heading in the other case is not found. Workaround: type the stored case.
- [qo6x] Timeouts limit the whole request, not each socket wait as in Python. Workaround: retry.
- [6peo] After `rename --apply` of a canon owner, consumers keep the old path in the `> [!quote]` line and `sync-status` still says `synced`. Workaround: run `sync-update --apply`.
- [gnnc] The substring fallback of `find` prints `provenance: lexical`, help says `substring`. Workaround: none needed, cosmetic.
- [oyw7] `okf --help` does not say that `--json` is a per-command flag. Workaround: see the command pages.

## Fixed

Empty until the first fix release.
