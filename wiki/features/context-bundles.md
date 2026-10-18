---
title: "Context bundles"
description: "Curated, ordered reading lists per topic, stored as ctx files in the catalogue."
---

## Purpose

Describe ctx bundles: what they hold, how to read them, how to curate them.

## Audience

A user or agent who wants the pages a topic needs, in reading order.

## Visual elements

Mermaid flow of a ctx bundle in a session; code block with real `okf ctx show` output.

## Search terms

context management for AI agents; ctx bundle reading list; agent context okf; curated context

## Required sections

### Result sentence

- Bold sentence, one or two lines: what the reader can do after reading this page. Source: FACTS §okf ctx show.

### How it looks

- Real output of `okf ctx show <slug>`. Source: FACTS §okf ctx show.

### Why it matters

- Bold sentence: a session starts with the right pages, in the right order, within a token budget. Source: FACTS §okf ctx show.

### What you get

- Bundles are files `_ctx/<slug>.md` with a table of required and reference entries. Source: FACTS §Topic: ctx bundles.
- `okf ctx <slug>` is short for `okf ctx show <slug>`. Source: FACTS §okf ctx.
- `read`, `toc`, `inbound`, `outbound` run over all entries. Source: FACTS §okf ctx read; FACTS §okf ctx toc; FACTS §okf ctx inbound; FACTS §okf ctx outbound.

### Details

- The write verbs `create`, `add`, `drop`, `move`, `rename`, `remove` write immediately, without preview. Source: FACTS §Defect list, observations; FACTS §okf ctx create.
- `ctx check` validates all bundles. Source: FACTS §okf ctx check.

### Limits

- A dead entry exits 4, while the help says exit 1 [vf2r]. Source: FACTS §Defect list g.

### Reference

- Links to the 14 `okf ctx` verb pages. Source: FACTS §Section index of commands.
