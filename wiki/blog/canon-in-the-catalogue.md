---
title: "Canon in the catalogue"
description: "One truth in one place. A shared canon in the catalogue gives every project the same rules, and okf keeps the copies in step."
date: 2026-10-18
tags: [canon, architecture, okf]
---

**One truth, in one place. Everything else points at it.** A shared canon in the catalogue makes knowledge shareable, checkable and current.

## The problem

The same rule lives in many projects. The copies drift apart, and nobody knows which one holds.

## The idea

Keep one shared bundle in the catalogue, for example an architecture canon: layers, naming, the ADR pattern. Projects refer to it. They do not copy it.

## What it gives you

- One source of truth.
- New projects start with a frame of reference.
- Agents load the canon through `ctx` and get the same rules every time.
- Reviews measure against a fixed yardstick.

## How okf does it

A canon block has an owner. [`okf sync-insert`](/okf-cli/reference/commands/okf-sync-insert/) materialises it in the consumer, so the consumer stays readable even without the catalogue. [`okf sync-status`](/okf-cli/reference/commands/okf-sync-status/) shows drift. [`okf sync-update`](/okf-cli/reference/commands/okf-sync-update/) pulls outdated blocks up to date. [`okf sync-export`](/okf-cli/reference/commands/okf-sync-export/) prints a block's payload.

Both writing commands print a diff first and write only with `--apply`.

```text
okf sync-status
okf sync-update --apply
```

## Limits

- A canon needs a keeper.
- Too much canon sets hard. Only what is stable belongs in it.
- Project-specific rules stay local.

## In short

The canon makes knowledge shareable, checkable and current. It is the base for [context management](/okf-cli/blog/context-management-with-work-in-progress/) and for a [controlled tag vocabulary](/okf-cli/blog/tag-hygiene/).

See also [Canon blocks](/okf-cli/features/canon-blocks/) and [Define canon knowledge](/okf-cli/use-cases/define-canon-knowledge/).
