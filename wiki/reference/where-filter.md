---
title: "Where filter: the okf --where expression"
description: "Reference for the okf where filter: grammar, fields, operators, precedence, errors and examples for filtering Markdown frontmatter with okf find and okf list."
---

The `--where` option is the one filter language of okf. It selects concepts (Markdown files with frontmatter) by `type`, `tag`, `path`, status fields and any frontmatter key. This page is the reference for the okf where filter. Every `okf find` and `okf list` run on this page was measured with okf 0.2.4 on the golden test catalogue.

## Grammar

An expression is a boolean combination of comparisons.

```text
expr      := or-expr
or-expr   := and-expr ("or" and-expr)*
and-expr  := not-expr ("and" not-expr)*
not-expr  := "not" not-expr | atom
atom      := "(" expr ")" | field op value | field "in" "(" value ("," value)* ")"
```

| Operator | Meaning |
|---|---|
| `=` `!=` | equal, not equal |
| `<` `<=` `>` `>=` | ordered comparison (timestamps compare as instants) |
| `~` | contains |
| `in (a, b)` | equals one of the listed values |
| `and` `or` `not` | combine terms; `not` binds tighter than `and`, `and` tighter than `or` |

Precedence changes the result. Without parentheses `and` is applied first:

```text
$ okf list --where 'type = Guide or type = Runbook and tag = nosuch'
------
title: Getting started
type: Guide
path: handbook/getting-started
...
list: 1 concept(s)

$ okf list --where '(type = Guide or type = Runbook) and tag = nosuch'
(no matches)
```

Quoting rules:

- The characters `!<>=~` never belong to a bare word, so `path~a/b` and `x!=y` need no spaces.
- A bare word may hold letters, digits and `-_./:`.
- Quote every other value with `'...'` or `"..."`, for example `title = "Getting started"`.

:::note
Archived concepts are hidden unless the expression names `archived`.
:::

## Fields

| Field | Matches |
|---|---|
| `type` | the concept type |
| `tag` | one of the concept tags |
| `path` | `<bundle>/<concept-id>` |
| `archived` | `true` or `false` |
| `tier` | `unverified`, `machine-confirmed` or `human-reviewed` |
| `stale` | `true` or `false` |
| `status` | the status; an absent status counts as `stable` |
| any frontmatter key | a top-level key such as `title`; nested with `a.b`; through lists with `verified.by` or `sources.resource` |

An unknown frontmatter key matches nothing. It is not an error: `color = red` returns no concepts and exits 0.

Timestamp keys compare as instants: `generated.at`, `verified.at`, `stale_after`, `usage_window.from`, `usage_window.to`, `sources.last_modified`, `sources.usage_window.from`, `sources.usage_window.to`. The value must be ISO 8601 with an explicit offset, for example `stale_after < 2026-10-01T00:00:00Z`. Quote a value that holds `+`.

## Examples

Select by type, then by a list of tags (`--json` output is shortened to the paths):

```text
$ okf list --where 'type = Runbook' --json
{"command": "list", "ok": true, "data": [{"title": "Deploy", "type": "Runbook", "path": "handbook/ops/deploy", "description": "How to deploy: build, ship, verify", "tier": "human-reviewed", "stale": false}, {"title": "Setup", "type": "Runbook", "path": "handbook/ops/setup", "description": "Local setup", "tier": "unverified", "stale": false}], "warnings": [], "error": null}

$ okf list --where 'tag in (deploy, glossary)'
...
list: 3 concept(s)
```

More runs, result as paths:

| Expression | Result |
|---|---|
| `type = Guide or type = Runbook` | handbook/ops/deploy, handbook/getting-started, handbook/ops/setup |
| `path ~ ops/ and not tag = deploy` | handbook/ops/incident-2026, handbook/ops/retired-tool, handbook/ops/setup |
| `status = deprecated` | handbook/ops/retired-tool |
| `stale = true` | handbook/ops/incident-2026 |
| `archived = true` | _archive/handbook/old-process |
| `title = "Getting started"` | handbook/getting-started |
| `verified.by = human:golden` | handbook/ops/deploy |
| `generated.at < 2026-01-01T00:00:00Z` | no concepts |

## Errors

A malformed filter is exit 2, class `invalid_input` (see [JSON output and exit codes](/reference/json-output-and-exit-codes/)). The message names the problem and the position.

```text
$ okf list --where 'type ==' ; echo "[exit $?]"
--where: unknown operator '==' at position 6
[exit 2]

$ okf list --where 'type ='
--where: expected a value, found end of expression at position 7

$ okf list --where 'tag = a b'
--where: expected 'and', 'or' or end of expression, found 'b' at position 9

$ okf list --where 'stale_after < 2026-10-01'
--where: stale_after compares instants: = != < <= > >= or in, with an ISO 8601 datetime and an explicit offset, e.g. 2026-09-23T00:00:00Z (quote a value that holds +)
```

With `--json` the same failure is an error envelope:

```text
$ okf list --where 'type == Note' --json
{"command": "list", "ok": false, "data": null, "warnings": [], "error": {"kind": "invalid_input", "code": 2, "message": "--where: unknown operator '==' at position 6"}}
```

The parser accepts about 247 nested parentheses or 989 `not` in a row.

## Commands that take --where

The same expression language works on six commands:

- [`okf find`](/reference/commands/okf-find/): narrows the ranked hits.
- [`okf list`](/reference/commands/okf-list/): the complete set the expression selects.
- [`okf recent`](/reference/commands/okf-recent/)
- [`okf merge-tags`](/reference/commands/okf-merge-tags/)
- [`okf normalize-tags`](/reference/commands/okf-normalize-tags/)
- [`okf remove-tags`](/reference/commands/okf-remove-tags/)
