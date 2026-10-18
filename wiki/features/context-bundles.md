---
title: "Context bundles"
description: "Context management for AI agents: a ctx bundle is a curated reading list in reading order, with live titles and token estimates."
---

## Context bundles: curated context for AI agents

**Print the pages a topic needs, in reading order, with their real titles and a token estimate, and give them to a session or an agent.**

All outputs on this page come from okf 0.2.4 (`rel-0-2-4-115-g91f54bf`), run against a copy of the test catalogue.

## How it looks

```text title="okf --root <catalogue> ctx show onboarding"
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
```

```mermaid
flowchart LR
  A[Session starts] --> B["okf ctx show onboarding"]
  B --> C[Read required entries in order]
  C --> D[Query reference entries when needed]
```

## Why it matters

**A session starts with the right pages, in the right order, and you know the token cost of the required set before you read it.**

## What you get

- **A bundle is one file.** It lives at `_ctx/<slug>.md` in the catalogue. The file holds a table of entries: position, mode, path and comment. The mode is `pflicht` (shown as *required*) or `nachschlag` (shown as *reference*).

  ```markdown title="_ctx/onboarding.md (excerpt)"
  | pos | mode | path | comment |
  |---|---|---|---|
  | 1 | pflicht | [getting-started](/handbook/getting-started.md) |  |
  | - | nachschlag | [security](/handbook/security.md) | Background on passwords |
  ```

- **A short form.** `okf ctx <slug>` means `okf ctx show <slug>`. `okf ctx list` lists all bundles with their entry counts.
- **Live metadata.** `show` reads title, type and description from each entry file when you run it. The bundle file holds only paths, so it does not go stale.
- **Bulk verbs.** `read`, `toc`, `inbound` and `outbound` run over all entries of a bundle: print the full required entries, print all headings, list who links to each entry, list the links each entry points to.
- **Curation verbs.** `create`, `add`, `drop`, `move` and `rename` change one bundle. `edit` opens it in `$VISUAL`, `$EDITOR` or `vi` and validates it. `remove` deletes a bundle and lists the files that still link to it.

## Details

- The write verbs `create`, `add`, `drop`, `move`, `rename` and `remove` write at once. They have no preview. Use git to review or undo a change.
- `okf ctx check` validates all bundles. Findings use the same format as `okf check`:

```text title="okf --root <catalogue> ctx check"
ERROR    kc/ctx/dead-entry    _ctx/legacy.md  (dead entry: handbook/ops/gone.md)
WARNING  kc/ctx/empty-description _ctx/legacy.md  (empty description)
WARNING  kc/ctx/archived-entry _ctx/legacy.md  (entry under _archive/: _archive/handbook/old-process.md)
1 VIOLATIONS
[exit 4]
```

- `okf check` runs the same ctx rules, for example `kc/ctx/dead-entry`. See [Conformance checks](/features/conformance-checks/).

## Limits

- A dead entry, a path that no longer exists, makes `ctx show` print `[DEAD]` and the warning `this list is incomplete`, and the exit code is 4. The `--help` text of `ctx show`, `ctx read`, `ctx check` and `ctx edit` says exit 1 [vf2r]. `TODO: finding`. Script against 4.

  ```text title="okf --root <catalogue> ctx show legacy (excerpt)"
    3. [DEAD] <catalogue>/handbook/ops/gone.md
       why: removed long ago
  WARNING: 1 dead entry — this list is incomplete; fix with `ctx edit legacy`
  [exit 4]
  ```

## Reference

- [`okf ctx`](/reference/commands/okf-ctx/)
- Verbs: [`show`](/reference/commands/okf-ctx-show/), [`list`](/reference/commands/okf-ctx-list/), [`read`](/reference/commands/okf-ctx-read/), [`toc`](/reference/commands/okf-ctx-toc/), [`inbound`](/reference/commands/okf-ctx-inbound/), [`outbound`](/reference/commands/okf-ctx-outbound/), [`check`](/reference/commands/okf-ctx-check/), [`create`](/reference/commands/okf-ctx-create/), [`add`](/reference/commands/okf-ctx-add/), [`drop`](/reference/commands/okf-ctx-drop/), [`move`](/reference/commands/okf-ctx-move/), [`rename`](/reference/commands/okf-ctx-rename/), [`edit`](/reference/commands/okf-ctx-edit/), [`remove`](/reference/commands/okf-ctx-remove/)
