---
title: "Agent onboarding"
description: "Teach a coding agent to use okf: MCP server, skill, okf install, okf prime, llms.txt."
---

## Purpose

Show the shortest path from a fresh agent session to an agent that finds and edits catalogue content through okf.

## Audience

A user who runs Claude Code, Codex, opencode, omp, Kimi Code, OpenClaw or Hermes and wants okf available to it.

## Required sections

### Result sentence

- Bold sentence: after this page your agent calls okf through MCP or the shell. Source: FACTS §Topic: install; FACTS §Topic: MCP server and `OKF_BIN`.

### One command: okf install

- `okf install` shows a plan; `--apply` registers the skill, the MCP server and shell completion with each agent found; a second apply changes nothing. Source: FACTS §Topic: install.
- A lone release binary installs completion only: skill and MCP need a Homebrew keg or a clone ("source not found") [fs8c]. Source: FACTS §Topic: install; FACTS §Defect list j.
- Targets for opencode, kimi and hermes are not verified. TODO: verify go/internal/install/configs.go

### MCP server

- 21 tools, each with `root` and `use_global`; every call runs the `okf` binary with `--json`. Source: FACTS §Topic: MCP server and `OKF_BIN`.
- Binary lookup order: `$OKF_BIN`, then `bin/okf` or `go/bin/okf` next to `mcp/`, then `okf` on PATH. Source: FACTS §Topic: MCP server and `OKF_BIN`.
- `okf_reindex` has no `check` argument and writes. TODO: verify by a run over MCP

### Skill

- The `okf` skill from `skills/okf`: what it teaches and where it is installed. Source: FACTS §Topic: agent skill.

### okf prime

- `okf prime` prints the usage guide, the command directory and the catalogue state in one call. Source: FACTS §okf prime.
- The state text names `build_tagvec.py`, which a Go install does not ship [erpf]. Source: FACTS §Defect list h.

### llms.txt and llms-full.txt

- The site publishes both files at build time; link them here. Source: site/scripts/llms.mjs (CONCEPT D02, DESIGN Q5).

### Reference

- Links to `okf install`, `okf prime` and the MCP tool list. Source: FACTS §okf install; FACTS §okf prime; FACTS §Topic: MCP server and `OKF_BIN`.
