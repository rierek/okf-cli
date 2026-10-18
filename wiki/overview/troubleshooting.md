---
title: "Troubleshooting"
description: "Symptom-first fixes for common okf problems."
---

## Purpose

Let a stuck user find the fix by the symptom they see.

## Audience

A user whose command fails, prints a note, or whose agent cannot reach okf.

## Visual elements

One heading per symptom; callouts for causes; code blocks with the checks.

## Search terms

okf command not found; okf completion not working; okf MCP server error; okf troubleshooting

## Required sections

### How to read this page

- One entry per symptom: symptom as the heading, cause, fix. Source: page-patterns, Overview pages.

### `command not found: okf` and the old Python CLI first on PATH

- `type -a okf`, `file "$(command -v okf)"`, remove the stale launcher. Source: FACTS §Topic: install; FACTS §Topic: upgrade from the Python CLI.

### TAB completion does not work

- Check the plan, the file, the rc block, a new shell, aliases starting with `okf`, rerun `okf install --apply` after an upgrade. Source: FACTS §Topic: shell completion.
- The comment in the zsh script names argcomplete; behaviour is fine [jh7t]. Source: FACTS §Defect list b.

### `BLOCKED <agent> source not found` and `uv is not on PATH`

- What each means and the fix. Source: FACTS §Topic: install.
- A blocked plan ends with only `install failed with exit code 1` [fs8c]. Source: FACTS §Defect list j.

### The MCP server starts the wrong binary or none

- Set `OKF_BIN`, or put the binary on the agent's PATH. Source: FACTS §Topic: MCP server and `OKF_BIN`.

### `find` prints `note: lexical index absent`

- Run `okf build-index`; `note: semantic arm skipped` is normal without `VOYAGE_API_KEY`. Source: FACTS §okf find; FACTS §okf build-index; FACTS §Topic: index and search artefacts.

### `usage: okf ...` and exit 2 for `okf find git --root ...`

- `--root` and `--global` go before the command. Source: FACTS §Topic: config files and root resolution.

### A tag or `migrate` command exits 2 with `<path>: <reason>`

- The frontmatter line patcher refused a file; nothing was written; edit the file by hand. Source: FACTS §okf migrate; FACTS §okf merge-tags; FACTS Nicht bestimmbar part 2 (D-03 to D-09).

### A tag registration warns about `build_tagvec.py`

- The warning names a script the Go binary does not ship; ignore it or run `okf build-tagvec --produce` [erpf]. Source: FACTS §okf tags; FACTS §Defect list h.
