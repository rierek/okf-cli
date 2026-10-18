---
title: "Tag hygiene"
description: "Keep a tag vocabulary small: register tags, validate against TAGS.md and block new tags that nobody approved."
date: 2026-10-18
tags: [tags, okf, knowledge-management]
---

## Purpose

Give best practices for tags so they do not grow wild, with the commands that enforce them today.

## Audience

A catalogue owner whose tag list keeps growing.

## Visual elements

Code blocks with `tags --validate`; table of tag commands.

## Search terms

tag hygiene; tag registry markdown; stop tag sprawl; Obsidian tags cleanup

## Required sections

### Result sentence

- Bold sentence: after reading, the reader can stop unregistered tags from entering the catalogue. Source: PO practice (author's experience); TODO: verify examples against the real catalogue before writing.

### Why tags drift

- Short reasoning from experience. Source: PO practice (author's experience); TODO: verify examples against the real catalogue before writing.

### The practice

- Register every tag in `TAGS.md`; `okf tags --validate` reports unregistered tags and exits 4 [irxe]. Source: FACTS §okf tags; FACTS §Defect list a.
- Merge near-duplicates with `merge-tags`, remove with `remove-tags`, normalise the list form with `normalize-tags`. Source: FACTS §okf merge-tags; FACTS §okf remove-tags; FACTS §okf normalize-tags.
- Blocking new tags in CI: run `okf tags --validate` and fail on non-zero. Source: FACTS §okf tags.

### Semantic tag search

- Tag embeddings use a local model (`bge-m3` on Ollama) or Voyage; the endpoint is not configurable today. Source: FACTS §okf tags; FACTS §Topic: index and search artefacts. Planned: [76eb].

### Reference

- Links to Tags and registry and the tag command pages. Source: FACTS §Section index of commands.
