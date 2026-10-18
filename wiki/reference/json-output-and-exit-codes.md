---
title: "JSON output and exit codes (machine-readable okf)"
description: "Reference for okf JSON output: the --json envelope, exit-code classes 0 to 5 and failure shapes for scripts, CI and agents that need a machine-readable CLI."
---

Scripts, CI jobs and agents consume okf through the `--json` envelope and the exit code. Both are the same on every command. Runs on this page were measured with okf 0.2.4 on the golden test catalogue.

## Envelope

Every command that takes `--json` prints exactly one line of JSON on stdout. The key order is fixed.

```json
{"command": "find", "ok": true, "data": {"hits": ["..."], "nearest_tags": []}, "warnings": ["lexical index absent — falling back to substring scan; run `okf build-index` for BM25 ranking"], "error": null}
```

| Key | Content |
|---|---|
| `command` | the command as typed, verb included (`find`, `ctx show`) |
| `ok` | `true` on success |
| `data` | the result, or `null` |
| `warnings` | the notes that text mode prints on stderr as `note: ...` |
| `error` | `null`, or `{"kind", "code", "message"}` |

What `data` holds:

| Command family | `data` |
|---|---|
| `find` | `{"hits": [...], "nearest_tags": [...]}`; a hit has `rank`, `title`, `type`, `path`, `description`, `snippet`, `provenance`, `tier`, `stale` |
| `list` | array of `{title, type, path, description, tier, stale}` |
| `read` | `{"path", "text"}` |
| `toc` | `{"path", "title", "type", "headings": [{"level", "text"}]}` |
| `tags` | `{"tags": [{"tag", "count"}]}` |
| `check` | `{"findings": [{"rule", "severity", "path", "message"}]}` |
| `sync-status` | `{"blocks": [...], "totals": {...}}` |

Other commands use their own shape; see the page of each command. Usage errors from the argument parser are not wrapped: they print usage on stderr and exit 2 without an envelope.

## Exit-code classes

Every command ends with exactly one class. An error without a class exits 1.

| Code | `error.kind` | Meaning | Returned by |
|---|---|---|---|
| 0 | none | success | every command; also `find` with a degraded arm and `wikilinks` with unresolved links |
| 1 | `internal` | unexpected error, command not ported, blocked install step | `install` (blocked step); panics |
| 2 | `invalid_input` | usage error, malformed `--where`, refused frontmatter write, `rename` without `.md` paths, `recent` outside a git repository, `--global` together with `--root` | all commands |
| 3 | `not_found` | catalogue root, bundle, concept, file, ctx slug or block not found | navigation, search, ctx, tags, sync-*, move, check target |
| 4 | `non_conformant` | data does not conform | `check` (errors; with `--strict` also warnings); `tags --validate` with an unregistered tag; `ctx show`, `ctx read`, `ctx check`, `ctx edit` with a dead entry; `sync-insert` consumer not valid UTF-8 |
| 5 | `drift` | something is out of date | `sync-status` (any block not `synced`); `sync-update` (refused or unresolvable blocks); `reindex --check` (stale or uncovered index) |
| 120 | none | stdout could not be written (a broken pipe is no failure) | any command |

Observed runs of the error classes on commands that mutate or check a catalogue (run without `--apply`):

| Command | Input | Exit |
|---|---|---|
| `archive` | missing concept | 3 |
| `ctx add`, `ctx drop`, `ctx move`, `ctx remove`, `ctx rename` | unknown slug | 3 |
| `ctx create` | slug already exists | 2 |
| `fix-crosslinks`, `migrate`, `sync-update` | target is not a directory | 3 |
| `merge-tags`, `normalize-tags`, `remove-tags` | malformed `--where` | 2 |
| `registry convert` | file other than `TAGS.md` or `TYPES.md` | 2 (usage error) |
| `rename` | paths without `.md` | 2 |
| `sync-insert` | block not found | 3 |
| `rewrite-path` | `old` matches nothing | 0, empty `files` |

Known deviations from the help text:

- `tags --validate` and the ctx verbs `show`, `read`, `check`, `edit` exit 4 where the help says 1 [irxe] [vf2r].
- A blocked `install` plan exits 1 with a generic message [fs8c].

## Failures

A failure prints the same envelope with `ok: false`. When the failure carries a result, it stays in `data`; otherwise `data` is `null`. The exit code equals `error.code`.

Failure without data:

```text
$ okf read handbook/nope --json
{"command": "read", "ok": false, "data": null, "warnings": [], "error": {"kind": "not_found", "code": 3, "message": "not found: handbook/nope"}}
[exit 3]
```

Failure with data (`check`, shortened):

```text
$ okf check recipes --json
{"command": "check", "ok": false, "data": {"findings": [{"rule": "okf/type/reserved-no-type", "severity": "error", "path": "recipes/readme.md", "message": "reserved file must not carry `type`"}, ...]}, ...}
[exit 4]
```

```text
$ okf tags --validate nosuchtag --json
{"command": "tags", "ok": false, "data": {"closed_vocabulary": true, "unknown": ["nosuchtag"]}, "warnings": [], "error": {"kind": "non_conformant", "code": 4, "message": "non_conformant"}}
[exit 4]

$ okf sync-status --json
{"command": "sync-status", "ok": false, "data": {"blocks": [...], "totals": {"synced": 1, "source-changed": 1, ...}}, ...}
[exit 5]
```

In text mode the error message goes to stderr, for example `--where: unknown operator '==' at position 6`. An unclassified error or a panic becomes `kind: internal`, exit 1; its text also goes to stderr.
