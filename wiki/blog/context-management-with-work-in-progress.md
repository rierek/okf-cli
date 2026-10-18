---
title: "Context management with work-in-progress"
description: "Work in a topic folder, promote what lasts into the catalogue, and let agents read it through ctx."
date: 2026-10-18
tags: [context-management, okf, ai-agents]
---

## Purpose

Tell how project knowledge moves from a `work-in-progress/<topic-slug>` folder into the catalogue and becomes available to every project.

## Audience

A user who runs agent sessions across projects and loses context between them.

## Visual elements

Mermaid loop from topic folder to agent session; callout for the unsupported-symlink caveat.

## Search terms

context management for AI agents; work in progress to knowledge base; Obsidian vault agent context; okf ctx

## Required sections

### Result sentence

- Bold sentence: after reading, the reader has a working loop from topic folder to catalogue to agent context. Source: PO practice (author's experience); TODO: verify examples against the real catalogue before writing.

### The loop

- Mermaid flow: topic folder, review, promote into a bundle, check, ctx bundle, agent session. Source: PO practice (author's experience); TODO: verify examples against the real catalogue before writing.
- Promotion means moving a concept into a bundle and running `okf check`. Source: FACTS §okf check; FACTS §okf rename.

### Making it available elsewhere

- A bundle linked into the catalogue by symlink is available to other projects. Whether okf tells linked bundles from local ones is not documented. TODO: verify symlinked bundles against the binary

### Reading it back

- `okf ctx <slug>` gives an agent the right pages in order; `okf prime` gives the map. Source: FACTS §okf ctx show; FACTS §okf prime.

### Reference

- Links to Context bundles, Work with multiple bundles, `okf rename`. Source: FACTS §Section index of commands.
