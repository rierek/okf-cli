---
title: "Conformance checks"
description: "Scan a catalogue against the OKF v0.2 hard rules and local invariants."
---

## Purpose

Describe `okf check` and `okf verify`: what is checked, how findings are reported, what the exit code means.

## Audience

A catalogue owner or CI author who wants to keep a catalogue valid.

## Visual elements

Code block with a real finding; table of rule groups.

## Search terms

validate markdown frontmatter; OKF conformance check; link checker wikilinks; okf check

## Required sections

### Result sentence

- Bold sentence, one or two lines: what the reader can do after reading this page. Source: FACTS §okf check.

### How it looks

- Real output of `okf check` with one finding. Source: FACTS §okf check.

### Why it matters

- Bold sentence: a single command tells you which concepts break the rules. Source: FACTS §okf check.

### What you get

- Findings per rule, `--json` envelope for CI. Source: FACTS §okf check; FACTS §Topic: `--json` envelope.
- `okf verify` records a verification date in frontmatter. Source: FACTS §okf verify.
- `okf wikilinks` reports Obsidian wikilinks and their resolution. Source: FACTS §okf wikilinks.

### Details

- Hard rules versus local invariants. Source: FACTS §okf check.
- Provenance fields `generated`, `sources`, `verified`, `stale_after`. Source: FACTS §Topic: catalogue, bundle, concept and type model.
- Exit code for findings is 4 (NonConformant). Source: FACTS §Topic: exit-code classes.

### Limits

- v0.2 rules apply only to bundles that declare `okf_version: "0.2"`. TODO: verify

### Reference

- Links to `okf check`, `okf verify`, `okf wikilinks`, exit codes. Source: FACTS §Section index of commands.
