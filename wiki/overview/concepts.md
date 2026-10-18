---
title: "Concepts"
description: "Catalogue, bundle, concept, type, frontmatter and the provenance fields okf checks."
---

## Purpose

Define the vocabulary of okf once, so every other page can use the terms without explaining them.

## Audience

A user or agent who runs okf commands and needs the model behind the output.

## Visual elements

Mermaid diagram of catalogue, bundle and concept; table of frontmatter fields; callout for specification-first.

## Search terms

OKF catalogue bundle concept; Open Knowledge Format frontmatter; okf_version; knowledge base structure

## Required sections

### Result sentence

- Bold sentence: after reading, the reader can tell a catalogue from a bundle from a concept. Source: FACTS §Topic: catalogue, bundle, concept and type model.

### Catalogue, bundle, concept

- Definitions and one directory tree example. Source: FACTS §Topic: catalogue, bundle, concept and type model.

### Specification-first

- okf implements the OKF specification and follows it when it changes. Commitment (Q01, PO 2026-10-18): okf-cli follows the OKF specification and is adapted when it changes; no release date or per-version release is promised.
- Version binding: `okf_version` in the root index selects the rules; link to the specification repository. Source: FACTS §Topic: catalogue, bundle, concept and type model; FACTS Nicht bestimmbar part 1.

### Types and frontmatter

- Frontmatter fields and the `type` vocabulary of the catalogue (`TYPES.md`, `PROPERTIES.md`). Source: FACTS §Topic: catalogue, bundle, concept and type model; FACTS §okf info.

### Provenance and freshness

- OKF v0.2 fields `generated`, `sources`, `verified`, `stale_after`; `check` reports, `verify` records. Source: FACTS §Topic: catalogue, bundle, concept and type model; FACTS §okf check; FACTS §okf verify.
- v0.2 rules run only in bundles whose root index declares `okf_version: "0.2"`. TODO: verify with a bundle lacking the key

### Context bundles, tags, canon blocks

- One paragraph each, with links to the feature pages. Source: FACTS §Topic: ctx bundles; FACTS §Topic: tag registry (TAGS.md) and `okf registry`; FACTS §Topic: canon blocks (`sync-*`).

### Search and index artefacts

- `.fts/fts.sqlite` and `.tagvec/tag_vectors.sqlite`: what they hold and when they are built. Source: FACTS §Topic: index and search artefacts.

### Reference

- Links to the glossary and the frontmatter reference. Source: reference/glossary.
