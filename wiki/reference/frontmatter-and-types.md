---
title: "Frontmatter and types: OKF fields and provenance"
description: "Frontmatter fields, the TYPES.md type vocabulary and the OKF v0.2 provenance fields generated, sources, verified and stale_after."
---

# OKF frontmatter and Open Knowledge Format types

A concept is a Markdown file that starts with a YAML block. This page lists the keys okf reads and writes, the type vocabulary, and the provenance fields (`generated`, `sources`, `verified`, `stale_after`). Terms are defined in the [Glossary](/okf-cli/reference/glossary/). The format itself is specified by the [Open Knowledge Format](https://github.com/GoogleCloudPlatform/open-knowledge-format).

A concept as okf reads it (output of [`okf read`](/okf-cli/reference/commands/okf-read/) on the test catalogue):

```yaml title="handbook/ops/deploy.md"
---
type: Runbook
title: Deploy
description: "How to deploy: build, ship, verify"
tags:
  - ops
  - deploy
generated:
  by: human:golden
  at: 2026-01-02T10:00:00Z
verified:
  - by: human:golden
    at: 2026-01-03T10:00:00Z
sources:
  - resource: https://example.org/deploy-docs
stale_after: 2099-01-01T00:00:00Z
---
```

## Frontmatter fields

[`okf info`](/okf-cli/reference/commands/okf-info/) prints the `PROPERTIES.md` of your catalogue. The fields below are the ones `okf check` knows.

| Field | Required | Content | Check rule |
|---|---|---|---|
| `type` | yes | A type registered in `TYPES.md`. Must not be empty. | `okf/frontmatter/type-nonempty`, `kc/type/registered` |
| `title` | no | Display title. | |
| `description` | no | One-line summary. | |
| `tags` | no | Tags registered in `TAGS.md`, written as a block list. | `kc/tag/registered`, `kc/frontmatter/tags-block-form` |
| `status` | no | `draft`, `stable` or `deprecated`. Absent means `stable`. | `okf/lifecycle/status` |
| `generated` | no | `by` and `at`: who or what produced the text. | `okf/trust/generated` |
| `sources` | no | List of `{resource, ...}`. | `okf/provenance/*` |
| `verified` | no | List of `{by, at}`. | `okf/trust/verified` |
| `stale_after` | no | Instant after which the concept is stale. | `okf/lifecycle/stale-after` |
| `superseded_by` | no | Concept that replaces this one. Used on Decision concepts. | `kc/supersede/resolves`, `kc/supersede/scope` |

Reserved files (`index.md`, `log.md`, `readme.md`, `index-map.md`) are not concepts and carry no `type` (rule `okf/type/reserved-no-type`).

An actor (`by`) is `human:<id>`, `process:<id>` or `<producer>/<version>`. An instant is ISO 8601 with an explicit offset (rule `okf/format/timestamp`).

## Types

`TYPES.md` in the catalogue root is the type vocabulary: a table `| Type | Meaning |`. The test catalogue registers:

| Type | Meaning |
|---|---|
| `Concept` | An explained idea |
| `Context` | A curated reading list |
| `Guide` | Step-by-step instructions |
| `Runbook` | Operational procedure |
| `Rule` | A binding statement |
| `Recipe` | Food preparation |
| `Note` | Loose observation |

[`okf check`](/okf-cli/reference/commands/okf-check/) reports a concept whose `type` is missing from this table (`kc/type/registered`). Set `types_source` in [`.okf.toml`](/okf-cli/reference/configuration/#okftoml), or pass `okf check --types`, to read the table from another file. `okf registry convert TYPES.md --to block` switches the file between table and block form.

## Provenance

OKF v0.2 adds fields that say where a concept came from and how far to trust it.

- `generated`: `by` (required, non-empty) and `at`. Rule `okf/trust/generated` demands a `by`.
- `sources`: a list of entries, each with a `resource`. `sources.last_modified` and `sources.usage_window.from` / `.to` are timestamp keys you can filter on with [`--where`](/okf-cli/reference/where-filter/).
- `verified`: a list of `{by, at}`. [`okf verify`](/okf-cli/reference/commands/okf-verify/) writes an entry.
- `stale_after`: an instant. A concept is **stale** once that instant has passed.

okf derives a **trust tier** from `verified` only:

| Tier | Meaning |
|---|---|
| `unverified` | No entry names a `by`. |
| `human-reviewed` | At least one entry has a `human:<id>` actor. |
| `machine-confirmed` | Any other verified entry. |

`--json` output of `list`, `find`, `read` and `recent` shows the tier as `tier` and the stale state as `stale`.

The v0.2 rules of `check` run in bundles whose root `index.md` declares `okf_version: "0.2"`. [`okf migrate`](/okf-cli/reference/commands/okf-migrate/) moves a catalogue to 0.2. See [Migrate to OKF 0.2](/okf-cli/use-cases/migrate-to-okf-0-2/).

## Editing rules

Commands that change frontmatter (`merge-tags`, `normalize-tags`, `remove-tags`) patch it line by line, so the existing formatting is kept.

It refuses shapes it cannot edit safely:

- a lone CR line ending;
- a flow-mapping root;
- anchors or aliases on the edited value;
- a comment inside a multi-line flow list;
- some list layouts.

A refused file ends the whole run with exit 2 and the message `<path>: <reason>`. okf writes nothing, also in a dry run. Fix the file by hand, then run again.

:::note
`okf check` reports invalid frontmatter as `okf/frontmatter/parseable`.
:::

Read next: [Conformance checks](/okf-cli/features/conformance-checks/), [Safe edits](/okf-cli/features/safe-edits/).
