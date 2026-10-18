---
title: "Organize large Bundles"
description: "Keep a big bundle consistent: tags, links and canon drift, each with a preview first."
---

## Purpose

Show the upkeep of a large bundle with tags, link repair and checks.

## Audience

A catalogue owner whose bundle outgrew manual care.

## Visual elements

Steps; Tabs for tags, links and drift; callouts for dry-run rules.

## Search terms

organize large markdown knowledge base; tag cleanup; fix broken links markdown; okf maintenance

## Required sections

### Result sentence

- Bold sentence: tags, links and drift stay under control as a bundle grows. Source: FACTS §okf check.

### Set it up

- Work in a git repository so every change is one reviewable commit. Source: FACTS §okf rename.

### Work through it

- Tags: `okf tags`, `merge-tags`, `normalize-tags`, `tags --validate`. Source: FACTS §okf tags; FACTS §okf merge-tags; FACTS §okf normalize-tags.
- Links: `okf rename` and `archive` move a concept and rewrite links; `fix-crosslinks` repairs absolute form. Source: FACTS §okf rename; FACTS §okf archive; FACTS §okf fix-crosslinks.
- Checks: `okf check`; `okf sync-status` shows canon drift. Source: FACTS §okf check; FACTS §okf sync-status.

### What you get

- A bundle that passes `check` with clean tags and no dangling links. Source: FACTS §okf check.

### Limits

- Dry run is not uniform across commands; read Safe edits first. Source: FACTS §Defect list, observations.
- A file the writer refuses ends a whole tag run. [n760]. Source: ACCEPTANCE-REPORT D-08.

### Reference

- Links to Safe edits, Tags and registry, Conformance checks. Source: FACTS §Section index of commands.
