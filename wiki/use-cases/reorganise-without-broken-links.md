---
title: "Reorganise without broken links"
description: "Rename and move concepts, and let okf rewrite every link."
---

## Purpose

Show a safe reorganisation: preview, apply, check.

## Audience

A catalogue owner who renames or archives concepts.

## Required sections

### Result sentence

- Bold sentence: problem and solution in one sentence. Source: FACTS §okf rename.

### Set it up

- Start from a clean git working tree in a copy of the golden catalogue. Source: FACTS §okf rename.

### Work through it

- `okf rename a.md b.md` previews; `--apply` writes; `okf check` confirms no broken link; `okf archive` and `--restore` for retirement. Source: FACTS §okf rename; FACTS §okf check; FACTS §okf archive.

### What you get

- A moved concept and zero dangling links in one commit. Source: FACTS §okf rename.

### Limits

- Dry-run is not the default for every command; read the Safe edits page first. Source: FACTS §Defect list, observations.

### Reference

- Links to `rename`, `archive`, `fix-crosslinks`, `check`. Source: FACTS §Section index of commands.
