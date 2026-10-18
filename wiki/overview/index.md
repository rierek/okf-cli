---
title: "okf in brief"
description: "What okf is, who it is for and where to go next."
---

## Purpose

Introduce okf in one screen: a CLI and MCP server that searches, navigates, validates and refactors a catalogue of OKF v0.2 bundles.

## Audience

Someone who has heard of okf, or an agent picking it up, who needs to decide in a minute whether okf fits and where to read next.

## Visual elements

CardGrid with one card per chapter; one callout stating that okf follows the specification.

## Search terms

okf CLI overview; Open Knowledge Format; context management for AI agents; markdown knowledge base

## Required sections

### Result sentence

- Bold sentence: after reading, the reader knows what okf does and which chapter to open. Source: README intro; FACTS §Topic: catalogue, bundle, concept and type model.

### Specification-first

- Prominent statement in the result block: okf follows the OKF specification and is updated when the specification changes; this separates it from CLIs that do not anchor to a specification. Commitment (Q01, PO 2026-10-18): okf-cli follows the OKF specification and is adapted when it changes; no release date or per-version release is promised.
- Bound to OKF v0.2; v0.2 rules run only in bundles whose root index declares `okf_version: "0.2"`. Source: FACTS §Topic: catalogue, bundle, concept and type model.

### What okf is

- A single static Go binary named `okf`, no Python or `uv` at run time; `uv` is needed only by the MCP server that `okf install` registers. Source: FACTS §Topic: install; FACTS §Topic: MCP server and `OKF_BIN`.
- Works on a catalogue: a directory whose subdirectories are OKF bundles of Markdown files with YAML frontmatter. Source: FACTS §Topic: catalogue, bundle, concept and type model.

### What you can do

- Four groups of commands: navigation, search, tags, maintenance, as in `okf --help`. Source: FACTS §Section index of commands.
- One link per feature page (search, context bundles, conformance checks, safe edits, tags and registry, canon blocks). Source: page list of the Features chapter.

### Where to go next

- Links to Installation, First steps, Concepts, Agent onboarding and the command reference. Source: CONCEPT D05.

### Reference

- Link to the command reference. Source: FACTS §Section index of commands.
