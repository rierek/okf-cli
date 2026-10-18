---
title: "Canon blocks"
description: "Keep one text in sync across many concepts with materialised canonical blocks."
---

## Purpose

Describe the sync-* commands: export, insert, status, update.

## Audience

A catalogue owner who repeats the same rule or table in several concepts.

## Required sections

### Result sentence

- Bold sentence, one or two lines: what the reader can do after reading this page. Source: FACTS §Topic: canon blocks (`sync-*`).

### How it looks

- Real output of `okf sync-status` showing drift. Source: FACTS §okf sync-status.

### Why it matters

- Bold sentence: edit the canon once and every consumer follows. Source: FACTS §Topic: canon blocks (`sync-*`).

### What you get

- `sync-export` prints a canonical payload; `sync-insert` materialises it; `sync-status` reports drift; `sync-update` re-materialises. Source: FACTS §Topic: canon blocks (`sync-*`); FACTS §okf sync-export; FACTS §okf sync-insert; FACTS §okf sync-status; FACTS §okf sync-update.

### Details

- Marker syntax of a canonical block and its owner. Source: FACTS §Topic: canon blocks (`sync-*`).
- `sync-insert` and `sync-update` preview and need `--apply`. Source: FACTS §okf sync-insert; FACTS §okf sync-update.

### Limits

- Exit codes beyond the observed ones are not verified. TODO: verify sync-insert, sync-update error paths

### Reference

- Links to the four sync command pages. Source: FACTS §Section index of commands.
