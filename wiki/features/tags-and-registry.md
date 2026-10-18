---
title: "Tags and registry"
description: "Tag usage, fuzzy search, normalisation, merge, and the TAGS.md registry."
---

## Purpose

Describe tag management and the registry file.

## Audience

A catalogue owner who keeps a tag vocabulary consistent.

## Visual elements

Code blocks with real `okf tags` output; callout on tag hygiene.

## Search terms

tag management markdown frontmatter; TAGS.md registry; merge tags CLI; tag hygiene knowledge base

## Required sections

### Result sentence

- Bold sentence, one or two lines: what the reader can do after reading this page. Source: FACTS §okf tags.

### How it looks

- Real output of `okf tags` and `okf tags --validate`. Source: FACTS §okf tags.

### Why it matters

- Bold sentence: one tag vocabulary, checked and repairable from the shell. Source: FACTS §okf tags; FACTS §Topic: tag registry (TAGS.md) and `okf registry`.

### What you get

- `okf tags` lists usage counts or fuzzy-searches a query; `--validate` checks against `TAGS.md`; `--register` adds tags. Source: FACTS §okf tags; FACTS §Topic: tag registry (TAGS.md) and `okf registry`.
- `merge-tags`, `remove-tags`, `normalize-tags` edit tags across concepts. Source: FACTS §okf merge-tags; FACTS §okf remove-tags; FACTS §okf normalize-tags.
- `okf registry convert` rewrites registry entries between table and block form. Source: FACTS §okf registry convert.

### Details

- The tag commands preview and need `--apply`; `tags --register` writes immediately. Source: FACTS §Defect list, observations.

- Tag hygiene: register tags in `TAGS.md`, run `okf tags --validate` in CI to block unregistered tags (exit 4), merge near-duplicates. Source: FACTS §okf tags; FACTS §Topic: tag registry (TAGS.md) and `okf registry`.
- Semantic tag search embeds with Ollama `bge-m3` on `localhost:11434` or Voyage; the endpoint is fixed today (planned: [76eb]). Source: FACTS §okf tags.

### Limits

- `tags --validate` exits 4, the help says 1 [irxe]. Source: FACTS §Defect list a.
- `tags --register` warns about `build_tagvec.py`, which a Go install does not contain, and calls localhost:11434 [erpf]. Source: FACTS §Defect list h.

### Reference

- Links to the tag command pages. Source: FACTS §Section index of commands.
