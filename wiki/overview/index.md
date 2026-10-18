---
title: "okf in brief"
description: "What okf is, who it is for and where to go next."
---

## Purpose

Introduce okf in one screen: a CLI and MCP server that searches, navigates, validates and refactors a catalogue of OKF v0.2 bundles.

## Audience

Someone who has heard of okf, or an agent picking it up, who needs to decide in a minute whether okf fits and where to read next.

## Required sections

### Result sentence

- Bold sentence: after reading, the reader knows what okf does and which chapter to open. Source: README intro; FACTS §Topic: catalogue, bundle, concept and type model.

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
