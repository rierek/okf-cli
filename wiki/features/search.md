---
title: "Search"
description: "Ranked search over a catalogue, narrowed by a single --where filter."
---

## Purpose

Describe the capability of finding concepts: lexical BM25, optional semantic arm, one filter language.

## Audience

A user or agent who needs the right concept among many.

## Visual elements

Code block with real `okf find` output; Mermaid of the lexical and semantic arms.

## Search terms

markdown knowledge base search; BM25 FTS5 CLI; semantic search embeddings Voyage; okf find

## Required sections

### Result sentence

- Bold sentence, one or two lines: what the reader can do after reading this page. Source: FACTS §okf find.

### How it looks

- Real output of `okf find recipe` on the golden catalogue, with rank lines. Source: FACTS §okf find.

### Why it matters

- Bold sentence: you get ranked hits without leaving the shell, and the same filter works for `list`. Source: FACTS §okf find; FACTS §okf list.

### What you get

- Ranked results from SQLite FTS5/BM25 plus an optional Voyage semantic arm. Source: FACTS §okf find; FACTS §Topic: index and search artefacts.
- One `--where` expression narrows by type, tag, scope and more. Source: FACTS §Topic: `--where` filter language.
- `okf list` returns the complete unranked set a `--where` selects. Source: FACTS §okf list.

### Details

- Build and refresh the index with `okf build-index`; `--if-stale` skips unchanged work. Source: FACTS §okf build-index.
- Without the index `find` falls back to a substring scan and says so. Source: FACTS §okf find.
- Semantic arm needs `VOYAGE_API_KEY`; without it the lexical result is complete. Source: FACTS §okf build-semantic-index; FACTS §Topic: index and search artefacts.
- `okf recent` lists the newest concepts. Source: FACTS §okf recent.

- The semantic arm embeds with Voyage (`VOYAGE_API_KEY`); the endpoint and model are not configurable (planned: [76eb]). Source: FACTS §okf build-semantic-index.

### Limits

- `build-semantic-index` without `VOYAGE_API_KEY` exits 0 and writes nothing. Source: FACTS §Defect list, observations.

### Reference

- Links to `okf find`, `okf list`, `okf build-index`, `okf build-semantic-index` and the `--where` reference. Source: FACTS §Section index of commands.
