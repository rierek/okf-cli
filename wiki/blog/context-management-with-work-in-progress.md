---
title: "Context management with work-in-progress"
description: "An agent needs a small, targeted context, not a full dump. Work in a topic folder, promote what lasts into the catalogue and hand it over with ctx."
date: 2026-10-18
tags: [context-management, okf, ai-agents]
---

**An agent needs a small, targeted context. Never a full dump.** Keep the work in a topic folder, keep the lasting knowledge in the catalogue, and hand the agent a `ctx` bundle.

## The problem

An agent session starts empty. Load everything and the useful lines drown in noise. Load nothing and the agent guesses. It gets worse when notes, plans and lasting knowledge sit in the same place: nobody can tell what is still true.

## One topic, one folder

Give each topic its own folder: `work-in-progress/<topic-slug>/`. It holds the thinking and planning chain, drafts and intermediate results. It is short-lived, but fully traceable.

Every file in it carries OKF frontmatter, and `type` is never empty. That keeps the folder readable for `okf` and for agents.

## Promote what lasts

Ask one question of each statement: is it lasting and reusable?

- **Yes:** it moves into the catalogue.
- **No:** it stays in the topic, or you discard it.

Each claim gets exactly one home. After the move, the topic points at the catalogue instead of copying it. Two copies drift apart.

## Agents read through `ctx`

A `ctx` bundle is a curated reading list in reading order. [`okf ctx show`](/reference/commands/okf-ctx-show/) prints it with the title and type of every entry, read live from the files, so the list does not go stale. Each entry has a mode:

| Mode | Meaning |
|---|---|
| `pflicht` | The agent must read it, in the given position. |
| `nachschlag` | Reference: look it up when needed. |

An example: load the Git canon before a hotfix, and nothing else. Put the bundle in the prompt instead of a list of paths.

```text
okf ctx show onboarding
```

## In practice

1. Create the topic folder.
2. Work in it.
3. Move what lasts into the catalogue.
4. Archive the topic.

Hand over context with `ctx`, not with path lists in the prompt.

## In short

- The topic folder is the workbench.
- The catalogue is the memory.
- `ctx` is the interface to the agent.

See also [Context bundles](/features/context-bundles/) and [Onboard agents](/use-cases/onboard-agents/).
