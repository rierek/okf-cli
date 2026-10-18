---
title: "Safe edits"
description: "Preview first, then apply: rename, archive, rewrite, reindex, migrate move concepts and keep links intact."
---

## Purpose

Describe the preview-then-apply model and which commands follow it.

## Audience

A user who reorganises a catalogue and fears broken links.

## Required sections

### Result sentence

- Bold sentence, one or two lines: what the reader can do after reading this page. Source: FACTS §okf rename.

### How it looks

- Real output of `okf rename` as a dry run, then with `--apply`. Source: FACTS §okf rename.

### Why it matters

- Bold sentence: one command moves a concept and rewrites every inbound and outbound link. Source: FACTS §okf rename.

### What you get

- `rename`, `archive` (and `--restore`) move concepts; links are rewritten. Source: FACTS §okf rename; FACTS §okf archive.
- `rewrite-path`, `fix-crosslinks`, `fix-xml-tags`, `reindex`, `migrate` edit in bulk. Source: FACTS §okf rewrite-path; FACTS §okf fix-crosslinks; FACTS §okf fix-xml-tags; FACTS §okf reindex; FACTS §okf migrate.

### Details

- Dry-run is not uniform: `archive`, `rename`, `migrate`, tag commands, `registry convert`, `sync-insert`, `sync-update`, `install` preview and need `--apply`; `fix-crosslinks`, `fix-xml-tags`, `rewrite-path`, `reindex` write by default with `--check` as dry run; `verify`, `tags --register`, `build-index`, `visualize` and the ctx write verbs write immediately. Source: FACTS §Defect list, observations.
- The frontmatter line patcher refuses shapes it cannot patch safely. Source: FACTS Nicht bestimmbar part 2.

### Limits

- Do not say "every mutating command defaults to dry run". Source: FACTS §Defect list, observations.
- Over MCP, `okf_reindex` has no `check` argument. TODO: verify

### Reference

- Links to the command pages. Source: FACTS §Section index of commands.
