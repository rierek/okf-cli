---
title: "Define canon knowledge and use it in projects"
description: "Write a rule once as a canon block and materialise it in project concepts."
---

## Purpose

Show defining a canon and keeping consumers in sync.

## Audience

A catalogue owner who repeats rules across projects.

## Visual elements

Steps; Mermaid of owner and consumers; code blocks with sync output.

## Search terms

canon knowledge markdown; reusable rules across projects; okf sync; architecture canon

## Required sections

### Result sentence

- Bold sentence: define a rule once and every project carries the same text. Source: FACTS §Topic: canon blocks (`sync-*`).

### Set it up

- Mark a canon block in its owner concept. Source: FACTS §Topic: canon blocks (`sync-*`).

### Work through it

- `okf sync-export` prints the payload. Source: FACTS §okf sync-export.
- `okf sync-insert` materialises it; `okf sync-update` refreshes outdated copies; both preview first. Source: FACTS §okf sync-insert; FACTS §okf sync-update.
- `okf sync-status` lists drift. Source: FACTS §okf sync-status.

### What you get

- Projects that read the same canon and show drift when it changes. Source: FACTS §okf sync-status.

### Limits

- Error-path exit codes of `sync-insert` and `sync-update` are not verified. TODO: verify

### Reference

- Links to Canon blocks and the blog post "Canon in the catalogue". Source: DESIGN D27.
