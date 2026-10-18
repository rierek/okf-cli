---
title: "Onboard an AI agent to a knowledge base with okf prime"
description: "Onboard an AI agent to your knowledge base: okf prime gives a fresh Claude Code or MCP session the catalogue map, okf ctx the pages that matter."
---

## Onboard an AI agent to a knowledge base

**An agent starts with the map of your catalogue and the pages that matter, in two calls.**

Search terms covered: onboard AI agent to knowledge base, `okf prime`, Claude Code context, MCP knowledge base. Output below comes from okf 0.2.5 against a copy of the golden test catalogue; `<catalogue>` replaces the real path.

## Set it up

Install okf, then connect your agents. See [Installation](/okf-cli/overview/installation/) for the install paths.

```bash title="Terminal"
okf install            # preview: prints a plan, changes nothing
okf install --apply    # installs skill, MCP server entry, completion
```

Restart the agent afterwards. The MCP server runs the `okf` binary; `OKF_BIN` overrides which one. See [Agent onboarding](/okf-cli/overview/agent-onboarding/).

## Work through it

**1. Give the agent the map.** `okf prime` prints the usage guide, the command directory and the catalogue state with the bundle TOC. An agent runs it once at session start.

```text title="okf --root <catalogue> prime (excerpt)"
## This catalogue

root: <catalogue>
bundles: 4 · concepts: 24
fts index: absent — `find` degrades to a substring scan; run `build-index`
semantic index: absent — `find` runs its lexical arm only
tag vocabulary: closed — 11 tags in TAGS.md; check a new one with `tags --validate`, adopt it with `tags --register`
ctx bundles: 3 — cooking · legacy · onboarding — `ctx show <slug>` lists one
root docs: SPEC.md · TYPES.md · PROPERTIES.md · TAGS.md

## Bundles
[exit 0]
```

**2. Hand over one topic.** `okf ctx` lists the context bundles. `okf ctx <slug>` prints that topic's pages in reading order, with a token estimate.

```text title="okf --root <catalogue> ctx onboarding"
ctx onboarding — Read this first on day one

required — read in this order:
  1. <catalogue>/handbook/getting-started.md  [Guide] Getting started  ~158 tok
     First steps: accounts, tools, and where to find things
  2. <catalogue>/handbook/glossary.md  [Concept] Glossary  ~62 tok
     Terms used here: "bundle" and "concept"
  3. <catalogue>/handbook/ops/deploy.md  [Runbook] Deploy  ~150 tok
     How to deploy: build, ship, verify
reference — query when needed:
  - <catalogue>/handbook/security.md  [Gadget] Security basics  ~55 tok
     why: Background on passwords

4 entries (3 required, 1 reference), ~370 tokens for the required set
[exit 0]
```

**3. Let the agent look things up.** Through MCP it calls the tools `okf_find` and `okf_read`. In a shell it runs `okf find` and `okf read`. A section read returns only that section:

```text title="okf --root <catalogue> read recipes/bread --section Steps"
## Steps

Mix, rise, bake. Related: [pasta](pasta.md).
```

## What you get

An agent that finds a concept with ranked search and reads one section of it, with no blind `grep` over files. Curate more topics with [Context bundles](/okf-cli/features/context-bundles/).

## Limits

- The `prime` state text, like `tags --register`, names `build_tagvec.py`, which a Go install lacks [erpf]. Ignore it, or run `okf build-tagvec --produce`. See [Known limitations](/okf-cli/known-limitations/).

## Reference

- [Agent onboarding](/okf-cli/overview/agent-onboarding/)
- [Context bundles](/okf-cli/features/context-bundles/)
- [`okf prime`](/okf-cli/reference/commands/okf-prime/)
- [`okf ctx`](/okf-cli/reference/commands/okf-ctx/)
- [`okf read`](/okf-cli/reference/commands/okf-read/)
