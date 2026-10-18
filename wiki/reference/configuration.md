---
title: "Configuration"
description: "Root resolution, config files and environment variables."
---

## Purpose

Specify how okf finds its catalogue and which settings it reads.

## Audience

A user who works with several catalogues or runs okf in CI.

## Required sections

### Root resolution order

- `--root`, then the nearest catalogue above the working directory (`.okf.toml`, or `SPEC.md` plus `TYPES.md`, also in a `docs/` child), then `root` in `~/.config/okf/config.toml`; `--global` skips the search above cwd and excludes `--root`. Source: FACTS §Topic: config files and root resolution.

### Config files

- `.okf.toml` and `~/.config/okf/config.toml`: keys and examples. Source: FACTS §Topic: config files and root resolution.

### Environment variables

- `OKF_BIN` (MCP), `VOYAGE_API_KEY` (semantic arm), `COLUMNS` (help wrapping), `XDG_CONFIG_HOME`. Source: FACTS §Topic: MCP server and `OKF_BIN`; FACTS §okf build-semantic-index; FACTS §Topic: config files and root resolution.

### Files okf writes

- `.fts/fts.sqlite`, `.tagvec/tag_vectors.sqlite`, `_ctx/*.md`, and what `okf install` writes under `$HOME`. Source: FACTS §Topic: index and search artefacts; FACTS §Topic: ctx bundles; FACTS §Topic: install.
