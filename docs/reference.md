# okf command reference

One entry per command of the `okf` binary: 33 commands, the 14 verbs of `ctx`, and the hidden `build-tagvec`. The blocks headed `text` that start with `usage:` are the verbatim output of `okf <command> --help`; the second block of an entry is a real run against a copy of the fixture catalogue `tests/golden/catalogue/` (a git repository). In the examples `<catalogue>` stands for the path of that copy, `… (N more lines)` marks output cut for this page, and a line that starts with `stderr:` was written to stderr. Output that contains a time (`recent`) differs from run to run.

Install: [install.md](install.md). Concepts, filters and rule IDs: [README](../README.md).

## Global usage

```text
okf [--root ROOT | --global] <command> [options]
```

`--root` and `--global` belong **before** the command: `okf --root /path/to/catalogue find git`. After the command they are a usage error (exit 2).

The catalogue root is, in this order:

1. `--root ROOT` (a `~` is expanded),
2. the nearest catalogue above the current directory (a directory holding `.okf.toml`, or `SPEC.md` plus `TYPES.md`, also in a `docs/` child),
3. `root` in `$XDG_CONFIG_HOME/okf/config.toml` (default `~/.config/okf/config.toml`).

`--global` skips step 2 and takes step 3; it excludes `--root`. If no root is found, the command fails with exit 3 and `root not found`. `okf install` needs no catalogue.

Every command takes `--json`. With it, a command that runs prints exactly one envelope on stdout:

```json
{"command": "read", "ok": false, "data": null, "warnings": [], "error": {"kind": "not_found", "code": 3, "message": "not found: notes/nope"}}
```

The exit code equals `error.code`:

| code | `error.kind` | meaning |
|---|---|---|
| 0 | | success |
| 1 | `internal` | the command itself failed (for example `git` is missing for `recent`, or an `install` step is blocked) |
| 2 | `invalid_input` | usage error, invalid `--where` expression, unusable option combination, ambiguous section heading, or refused input |
| 3 | `not_found` | a named concept, section, file, slug or root does not exist |
| 4 | `non_conformant` | `check` or `ctx check` found a violation |
| 5 | `drift` | `sync-status`, `sync-update` or `reindex --check` found something out of date |

A usage error caught by the argument parser exits 2 with `usage: okf …` on stderr and no envelope.

Notes go to stderr (or into `warnings` with `--json`). Only these commands use the network: `build-semantic-index`, the semantic arm of `find`, `build-tagvec --produce`, and the page `visualize` writes (it loads two scripts when you open it). `--json` is an option of the command, not a global option: it goes after the command name.

Two environment variables matter to commands: `VOYAGE_API_KEY` (semantic arm of `find`, `build-semantic-index`, `build-tagvec`) and `VISUAL`/`EDITOR` (`ctx edit`).

Which commands write: the table at [README, Preview, then apply](../README.md#preview-then-apply). Each entry below repeats it.

## Commands at a glance

| command | what it does |
|---|---|
| [`prime`](#okf-prime) | one-shot agent onboarding: usage guide, command directory, catalogue state and bundle TOC |
| [`index`](#okf-index) | catalogue TOC (bundle names + one-line descriptions), or one bundle's index.md |
| [`info`](#okf-info) | print catalogue schema docs (TYPES.md + PROPERTIES.md) |
| [`list`](#okf-list) | list the complete, unranked set of concepts a required --where expression selects |
| [`recent`](#okf-recent) | list the most recently created concepts, newest first |
| [`toc`](#okf-toc) | print a concept's headings (default: h2 only) |
| [`read`](#okf-read) | print one concept page |
| [`ctx`](#okf-ctx) | context bundles: curated, ordered reading lists per topic (`ctx` lists them, `ctx `<slug>`` shows one) |
| [`visualize`](#okf-visualize) | write a viz.html concept graph for a bundle (embeds every concept body; needs network for cytoscape/marked) |
| [`sync-export`](#okf-sync-export) | print a canonical block's payload for materialisation elsewhere |
| [`find`](#okf-find) | hybrid ranked search: lexical FTS5/BM25 arm plus semantic arm |
| [`refs`](#okf-refs) | list inbound and outbound markdown links of a file |
| [`build-index`](#okf-build-index) | (re)build the FTS5 lexical search index at `<root>/.fts/fts.sqlite` (local only, no network) |
| [`build-semantic-index`](#okf-build-semantic-index) | fill `<root>/.tagvec/tag_vectors.sqlite's` concept_emb table for every concept still missing a voyage-3-large embedding (NETWORK, requires VOYAGE_API_KEY) |
| [`build-tagvec`](#okf-build-tagvec) | hidden: offline producer for the tag vectors (dry run unless --produce) |
| [`tags`](#okf-tags) | list all tags with usage counts, or fuzzy-search candidate tags |
| [`merge-tags`](#okf-merge-tags) | merge/rename one or more tags into a target tag across concept frontmatter |
| [`remove-tags`](#okf-remove-tags) | remove one or more tags from concept frontmatter (no merge target) |
| [`normalize-tags`](#okf-normalize-tags) | convert inline `tags: [...]` fields to YAML block-list form (local convention) |
| [`check`](#okf-check) | conformance scan: §9 hard rules + local invariants |
| [`verify`](#okf-verify) | record that a concept was checked against its sources |
| [`migrate`](#okf-migrate) | migrate frontmatter to OKF 0.2: `timestamp` to `generated` (git), `status` per D37 (dry-run default) |
| [`rename`](#okf-rename) | move a concept + rewrite every inbound/outbound link + reindex (dry-run default) |
| [`archive`](#okf-archive) | move a concept into `_archive/<bundle>/`, or back with --restore (dry-run default) |
| [`reindex`](#okf-reindex) | (re)generate marker-bounded index listings: index.md one level, index-map.md the whole subtree |
| [`fix-crosslinks`](#okf-fix-crosslinks) | rewrite links to catalogue-root-absolute form (/bundle/subdir/concept.md) |
| [`fix-xml-tags`](#okf-fix-xml-tags) | wrap `<tag>`/`<tag>.<tag2>` placeholders in inline code |
| [`rewrite-path`](#okf-rewrite-path) | literal path-string rewrite across text files |
| [`wikilinks`](#okf-wikilinks) | report Obsidian wikilinks ([[…]]) and whether each resolves to a concept |
| [`sync-status`](#okf-sync-status) | drift report for every materialised canon block |
| [`sync-insert`](#okf-sync-insert) | materialise a canonical block inside a consumer concept (dry-run default) |
| [`sync-update`](#okf-sync-update) | re-materialise outdated consumer blocks from their canon owner (dry-run default) |
| [`registry`](#okf-registry) | reformat registry entries of TAGS.md or TYPES.md (table or block form); prose stays |
| [`install`](#okf-install) | register okf, its agent skill, MCP server and shell completion with this machine's agents and shells (dry-run default; needs no catalogue) |


## Navigation

### `okf prime`

Onboarding in one call for a fresh agent session: the usage guide, the command list and the state of this catalogue (indexes, tag vocabulary, bundles). `--compact` lists bundles as one-liners, `--full` adds types and tags per bundle, `--check-semantic` runs the exact content-hash check of the semantic index.

Read-only. Exit codes: 0 success; 2 usage error.

```text
usage: okf prime [-h] [--full] [--compact] [--check-semantic] [--json]

one-shot agent onboarding: usage guide, command directory, catalogue state and
bundle TOC

options:
  -h, --help        show this help message and exit
  --full            add types+tags to each bundle block
  --compact         list bundles as name+count one-liners instead of the
                    `index` blocks (description+directories)
  --check-semantic  run the exact content-hash semantic coverage check (~2s on
                    a large catalogue) instead of reporting only whether the
                    semantic index is present
  --json            print one JSON envelope {command, ok, data, warnings,
                    error}
```

```text
$ okf prime --compact | tail -n 12
root docs: SPEC.md · TYPES.md · PROPERTIES.md · TAGS.md

## Bundles

The catalogue TOC, as `index` renders it. Each name is a path: `toc <bundle>`,
`index <bundle>`, `--where "path ~ <bundle>/"` on find and list.

- _ctx (3 concepts)
- handbook (10 concepts)
- kc-gov (2 concepts)
- recipes (9 concepts)
(`prime` without --compact inlines each bundle's description and directories)
```

### `okf index`

Without an argument: one line per bundle with its description. With a bundle: that bundle's `index.md`.

Read-only. Exit codes: 0 success; 2 usage error; 3 unknown bundle.

```text
usage: okf index [-h] [--full] [--json] [bundle]

catalogue TOC (bundle names + one-line descriptions), or one bundle's index.md

positional arguments:
  bundle      bundle to print (default: the whole catalogue TOC)

options:
  -h, --help  show this help message and exit
  --full      catalogue TOC: print the structured per-bundle block
              (description, concept count, directories, types, tags) instead
              of the default one-line name+description listing; with a bundle
              arg: print the structured bundle summary instead of the raw
              index.md
  --json      print one JSON envelope {command, ok, data, warnings, error}
```

```text
$ okf index
_ctx: Curated, ordered reading lists per topic — one file per ctx slug, managed by `okf ctx`.
handbook: Welcome to the handbook.
kc-gov: 
recipes: 
$ okf index handbook | head -n 8
---
okf_version: "0.2"
description: "Team handbook: onboarding, operations, security"
---

# Handbook

Welcome to the handbook.
```

### `okf info`

Prints the catalogue's schema documents `TYPES.md` and `PROPERTIES.md`.

Read-only. Exit codes: 0 success; 2 usage error.

```text
usage: okf info [-h] [--json]

print catalogue schema docs (TYPES.md + PROPERTIES.md)

options:
  -h, --help  show this help message and exit
  --json      print one JSON envelope {command, ok, data, warnings, error}
```

```text
$ okf info
------
# TYPES.md

Registered concept types.

| Type | Meaning |
|---|---|
| `Concept` | An explained idea |
| `Context` | A curated reading list |
| `Guide` | Step-by-step instructions |
| `Runbook` | Operational procedure |
| `Rule` | A binding statement |
… (20 more lines)
```

### `okf list`

The complete, unranked set of concepts a `--where` expression selects; `--where` is required. Grammar: [README, `--where`](../README.md#filter-concepts-with---where).

Read-only. Exit codes: 0 success; 2 usage error; 2 `--where` missing or malformed.

```text
usage: okf list [-h] [--where EXPR] [--json]

list the complete, unranked set of concepts a required --where expression
selects

options:
  -h, --help    show this help message and exit
  --where EXPR  select concepts by an expression: `field op value` with op one
                of = != < <= > >= ~ (contains), or `field in (a, b)`; combine
                with and, or, not and parentheses. Fields: type, tag, path
                (<bundle>/<concept-id>), archived (true or false), tier
                (unverified, machine-confirmed or human-reviewed), stale (true
                or false), status (an absent status is stable) and any
                frontmatter key (nested: a.b; through lists: verified.by,
                sources.resource). Timestamp keys (generated.at, verified.at,
                stale_after, usage_window.from/to, sources.last_modified,
                sources.usage_window.from/to) compare as instants and take an
                ISO 8601 value with an explicit offset: stale_after <
                2026-10-01T00:00:00Z. Archived concepts are hidden unless the
                expression names `archived`. Quote a value holding spaces, +
                or other characters: 'a b'. Example: (type = Runbook and tag
                != draft) and path ~ home-lab/
  --json        print one JSON envelope {command, ok, data, warnings, error}
```

```text
$ okf list --where 'tier = unverified and type = Runbook'
------
title: Setup
type: Runbook
path: handbook/ops/setup
description: Local setup
------
list: 1 concept(s)
```

### `okf recent`

Newest concepts first, from git history. `--where` narrows the set.

Read-only. Exit codes: 0 success; 2 usage error; 1 `git` missing.

```text
usage: okf recent [-h] [--limit LIMIT] [--where EXPR] [--json]

list the most recently created concepts, newest first

options:
  -h, --help     show this help message and exit
  --limit LIMIT  max results to print (default 10)
  --where EXPR   select concepts by an expression: `field op value` with op
                 one of = != < <= > >= ~ (contains), or `field in (a, b)`;
                 combine with and, or, not and parentheses. Fields: type, tag,
                 path (<bundle>/<concept-id>), archived (true or false), tier
                 (unverified, machine-confirmed or human-reviewed), stale
                 (true or false), status (an absent status is stable) and any
                 frontmatter key (nested: a.b; through lists: verified.by,
                 sources.resource). Timestamp keys (generated.at, verified.at,
                 stale_after, usage_window.from/to, sources.last_modified,
                 sources.usage_window.from/to) compare as instants and take an
                 ISO 8601 value with an explicit offset: stale_after <
                 2026-10-01T00:00:00Z. Archived concepts are hidden unless the
                 expression names `archived`. Quote a value holding spaces, +
                 or other characters: 'a b'. Example: (type = Runbook and tag
                 != draft) and path ~ home-lab/
  --json         print one JSON envelope {command, ok, data, warnings, error}
```

```text
$ okf recent --limit 3
2026-10-17 14:32  Context  _ctx/cooking
2026-10-17 14:32  Context  _ctx/legacy
2026-10-17 14:32  Context  _ctx/onboarding
recent: 3 of 24 concept(s)
```

### `okf toc`

Headings of one concept: the cheapest way to decide whether a page is worth reading. Default is h2 only; `--level 0` prints the full indented tree.

Read-only. Exit codes: 0 success; 2 usage error; 3 concept not found.

```text
usage: okf toc [-h] [--level LEVEL] [--json] path

print a concept's headings (default: h2 only)

positional arguments:
  path           <bundle>/<concept-id> to list headings for

options:
  -h, --help     show this help message and exit
  --level LEVEL  heading level to list (default 2 = h2); 0 = full indented
                 tree
  --json         print one JSON envelope {command, ok, data, warnings, error}
```

```text
$ okf toc handbook/getting-started
# Getting started  [Guide]
- Accounts
- Tools
- Next
```

### `okf read`

Prints one concept. Choose what comes back with `--section HEADING`, `--frontmatter-only` or `--body-only` (mutually exclusive); widen it with `--follow N` (and `--inbound`, `--max-tokens`, which take effect only together with `--follow`). More: [README, Read a concept](../README.md#read-a-concept).

Read-only. Exit codes: 0 success; 2 usage error; 2 an ambiguous `--section` heading; 3 concept or section not found.

```text
usage: okf read [-h] [--section HEADING | --frontmatter-only | --body-only]
                [--follow N] [--inbound] [--max-tokens K] [--json]
                path

print one concept page

positional arguments:
  path                <bundle>/<concept-id> of the page to print

options:
  -h, --help          show this help message and exit
  --section HEADING   print only this section: heading text (case-insensitive,
                      exact) up to the next heading of equal or higher level,
                      sub-sections included; 'A > B' resolves B inside A
  --frontmatter-only  print only the frontmatter block, delimiters included
  --body-only         print everything after the frontmatter block
  --follow N          also print the concepts the page links to, up to N hops
                      deep, as one block (BFS, each page once); combines with
                      --section (narrows the root), not with --frontmatter-
                      only or --body-only
  --inbound           with --follow: the pages linking to a page count as its
                      neighbours too
  --max-tokens K      with --follow: keep the block within K tokens (chars/4);
                      the root always prints in full, from the first page that
                      does not fit on, pages show title and description only
  --json              print one JSON envelope {command, ok, data, warnings,
                      error}
```

```text
$ okf read handbook/getting-started --section Tools
## Tools

Read the [deploy runbook](ops/deploy.md) and the [security page](security.md).
The old tool is described in [retired tool](ops/retired-tool.md).
Download the [diagram](assets/diagram.svg). A [missing page](/handbook/ops/missing.md) is dead.

### Wikilinks

Also see [[glossary]], [[deploy|the deploy page]] and [[does-not-exist]].

```

### `okf ctx`

Context bundles: curated, ordered reading lists, one file per slug in `<root>/_ctx/<slug>.md`. `okf ctx` lists them; `okf ctx <slug>` is short for `okf ctx show <slug>`. The verbs `add`, `create`, `drop`, `edit`, `move`, `remove` and `rename` change files and write immediately; the other verbs only read. All 14 verbs are listed below.

Read-only. Exit codes: 0 success; 2 usage error; 3 unknown slug; 4 `ctx check` found a violation.

```text
usage: okf ctx [-h] VERB ...

context bundles: curated, ordered reading lists per topic (`ctx` lists them,
`ctx <slug>` shows one)

positional arguments:
  VERB        ctx verb; `ctx <slug>` is short for `ctx show <slug>`
    add       add one entry to a ctx bundle
    check     validate ctx bundles
    create    create a ctx bundle from paths and/or an import file
    drop      remove one entry from a ctx bundle
    edit      open a ctx bundle in $VISUAL/$EDITOR/vi and validate it
    list      list ctx bundles with entry and required counts
    move      reorder an entry or change its mode
    outbound  list the links each entry points to
    inbound   list the files that link to each entry
    read      print the full content of every required entry
    remove    delete a ctx bundle and list files that still link to it
    rename    rename a ctx bundle and rewrite inbound links
    show      list a ctx in reading order with live metadata and token
              estimates
    toc       print the headings of every entry

options:
  -h, --help  show this help message and exit
```

```text
$ okf ctx
  cooking     Cooking basics  (3 entries, 3 required)
  legacy        (5 entries, 3 required)
  onboarding  Read this first on day one  (4 entries, 3 required)
$ okf ctx show onboarding
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
… (2 more lines)
```

The 14 `ctx` verbs:

#### `okf ctx list`

Lists the ctx bundles with entry and required counts.

Read-only. Exit codes: 0 success; 2 usage error.

```text
usage: okf ctx list [-h] [--for PATH] [--json]

list ctx bundles: slug, description, entry and required counts

options:
  -h, --help  show this help message and exit
  --for PATH  only bundles whose entries contain PATH (also when the file is
              gone)
  --json      print one JSON envelope {command, ok, data, warnings, error}
```

```text
$ okf ctx list
  cooking     Cooking basics  (3 entries, 3 required)
  legacy        (5 entries, 3 required)
  onboarding  Read this first on day one  (4 entries, 3 required)
```

#### `okf ctx show`

Lists a bundle in reading order with live title, type, description and a token estimate per entry.

Read-only. Exit codes: 0 success; 2 usage error; 3 unknown slug.

```text
usage: okf ctx show [-h] [--json] slug

list the required entries in reading order, then the reference entries; `ctx
<slug>` is short for `ctx show <slug>`; exit 1 when an entry is dead

positional arguments:
  slug        ctx slug

options:
  -h, --help  show this help message and exit
  --json      print one JSON envelope {command, ok, data, warnings, error}
```

```text
$ okf ctx show onboarding
ctx onboarding — Read this first on day one

required — read in this order:
  1. <catalogue>/handbook/getting-started.md  [Guide] Getting started  ~158 tok
     First steps: accounts, tools, and where to find things
  2. <catalogue>/handbook/glossary.md  [Concept] Glossary  ~62 tok
     Terms used here: "bundle" and "concept"
  3. <catalogue>/handbook/ops/deploy.md  [Runbook] Deploy  ~150 tok
… (6 more lines)
```

#### `okf ctx read`

Prints the full content of every required entry.

Read-only. Exit codes: 0 success; 2 usage error; 3 unknown slug.

```text
usage: okf ctx read [-h] [--json] slug

print every required entry of a ctx in position order, each after a `===== i/p
<abspath> =====` separator; reference entries are not printed; exit 1 when a
required entry is dead

positional arguments:
  slug        ctx slug

options:
  -h, --help  show this help message and exit
  --json      print one JSON envelope {command, ok, data, warnings, error}
```

```text
$ okf ctx read cooking
===== 1/3 <catalogue>/recipes/bread.md =====
---
type: Recipe
title: Bread
description: Bread with a long rise
tags:
  - food
  - bread
… (48 more lines)
```

#### `okf ctx toc`

Prints the headings of every entry.

Read-only. Exit codes: 0 success; 2 usage error; 3 unknown slug.

```text
usage: okf ctx toc [-h] [--depth N] [--json] slug

print per entry an H1 with the entry path, then the member's headings demoted
by one level; dead entries are marked [DEAD]

positional arguments:
  slug        ctx slug

options:
  -h, --help  show this help message and exit
  --depth N   only headings of original level <= N (default 0 = all)
  --json      print one JSON envelope {command, ok, data, warnings, error}
```

```text
$ okf ctx toc cooking
# recipes/bread.md
## Bread
### Steps

# recipes/pasta.md
## Pasta
### Zutaten
### Quellen
… (5 more lines)
```

#### `okf ctx inbound`

Lists the files outside the bundle that link to each entry.

Read-only. Exit codes: 0 success; 2 usage error; 3 unknown slug.

```text
usage: okf ctx inbound [-h] [--file X] [--include-internal] [--json] slug

per entry, the files linking to it; other members are excluded unless
--include-internal; files under _ctx/ are always excluded

positional arguments:
  slug                ctx slug

options:
  -h, --help          show this help message and exit
  --file X            only the entry whose title, path or stem equals X (case-
                      insensitive)
  --include-internal  also list links between members of the ctx
  --json              print one JSON envelope {command, ok, data, warnings,
                      error}
```

```text
$ okf ctx inbound onboarding
inbound — ctx onboarding, 4 member(s), external sources only:
handbook/getting-started.md
  <- handbook/index.md  (/handbook/getting-started.md)
  <- handbook/overview.md  (getting-started.md)
handbook/glossary.md
  <- handbook/index.md  (/handbook/glossary.md)
handbook/ops/deploy.md
  <- handbook/ops/index.md  (/handbook/ops/deploy.md)
… (3 more lines)
```

#### `okf ctx outbound`

Lists the links each entry points to.

Read-only. Exit codes: 0 success; 2 usage error; 3 unknown slug.

```text
usage: okf ctx outbound [-h] [--file X] [--include-internal] [--json] slug

per entry, markdown link targets; missing targets are marked [missing], dead
entries [DEAD]; other members are excluded unless --include-internal

positional arguments:
  slug                ctx slug

options:
  -h, --help          show this help message and exit
  --file X            only the entry whose title, path or stem equals X (case-
                      insensitive)
  --include-internal  also list links between members of the ctx
  --json              print one JSON envelope {command, ok, data, warnings,
                      error}
```

```text
$ okf ctx outbound onboarding
outbound — ctx onboarding, 4 member(s), external targets only:
handbook/getting-started.md
  -> handbook/ops/retired-tool.md  (ops/retired-tool.md)
  -> handbook/assets/diagram.svg  (assets/diagram.svg)
  -> handbook/ops/missing.md  (/handbook/ops/missing.md)  [missing]
handbook/glossary.md
  (none)
handbook/ops/deploy.md
… (4 more lines)
```

#### `okf ctx check`

Validates ctx bundles: dead entries, empty descriptions, entries under `_archive/`.

Read-only. Exit codes: 0 success; 2 usage error; 4 a violation was found.

```text
usage: okf ctx check [-h] [--stale] [--json] [slug]

report ctx errors and warnings in the `check` line format; exit 1 on any error

positional arguments:
  slug        ctx slug (default: all)

options:
  -h, --help  show this help message and exit
  --stale     warn for every member modified after the ctx file
  --json      print one JSON envelope {command, ok, data, warnings, error}
```

```text
$ okf ctx check; echo "exit code: $?"
ERROR    kc/ctx/dead-entry    _ctx/legacy.md  (dead entry: handbook/ops/gone.md)
WARNING  kc/ctx/empty-description _ctx/legacy.md  (empty description)
WARNING  kc/ctx/archived-entry _ctx/legacy.md  (entry under _archive/: _archive/handbook/old-process.md)
1 VIOLATIONS
exit code: 4
```

#### `okf ctx create`

Creates a bundle from paths and/or an import file.

Writes immediately. Exit codes: 0 success; 2 usage error.

```text
usage: okf ctx create [-h] [--import FILE] [--description DESCRIPTION]
                      [--json]
                      slug [PATH ...]

create _ctx/<slug>.md; every path becomes a required entry, ordered
alphabetically by normalised path

positional arguments:
  slug                  new ctx slug: lowercase letters, digits, hyphens
  PATH                  concept or file path to add as required entry

options:
  -h, --help            show this help message and exit
  --import FILE         read one path per line (blank and # lines skipped,
                        text after a TAB is the entry comment)
  --description DESCRIPTION
                        one-line description of the bundle
  --json                print one JSON envelope {command, ok, data, warnings,
                        error}
```

#### `okf ctx add`

Adds one entry to a bundle.

Writes immediately. Exit codes: 0 success; 2 usage error.

```text
usage: okf ctx add [-h] [--pos POS] [--mode {pflicht,nachschlag}]
                   [--comment COMMENT] [--json]
                   slug PATH

add PATH as required entry (default: last position) or as reference entry

positional arguments:
  slug                  ctx slug
  PATH                  concept or file path

options:
  -h, --help            show this help message and exit
  --pos POS             required position (clamped to 1..n+1)
  --mode {pflicht,nachschlag}
                        entry mode
  --comment COMMENT     entry comment
  --json                print one JSON envelope {command, ok, data, warnings,
                        error}
```

#### `okf ctx drop`

Removes one entry from a bundle.

Writes immediately. Exit codes: 0 success; 2 usage error.

```text
usage: okf ctx drop [-h] [--json] slug PATH

remove an entry (also when its file is gone); required positions are
renumbered 1..n

positional arguments:
  slug        ctx slug
  PATH        entry path

options:
  -h, --help  show this help message and exit
  --json      print one JSON envelope {command, ok, data, warnings, error}
```

#### `okf ctx move`

Reorders an entry or changes its mode.

Writes immediately. Exit codes: 0 success; 2 usage error.

```text
usage: okf ctx move [-h] [--pos POS] [--mode {pflicht,nachschlag}] [--json]
                    slug PATH

move an entry to required position N (--pos) and/or change its mode; required
positions are renumbered 1..n

positional arguments:
  slug                  ctx slug
  PATH                  entry path

options:
  -h, --help            show this help message and exit
  --pos POS             required position (clamped to 1..n)
  --mode {pflicht,nachschlag}
                        new mode
  --json                print one JSON envelope {command, ok, data, warnings,
                        error}
```

#### `okf ctx edit`

Opens the bundle in `$VISUAL`, `$EDITOR` or `vi` and validates it afterwards.

Writes immediately. Exit codes: 0 success; 2 usage error.

```text
usage: okf ctx edit [-h] [--json] slug

open _ctx/<slug>.md in $VISUAL, else $EDITOR, else vi; afterwards refresh the
_ctx index and run `ctx check` on the file; exit 1 on errors

positional arguments:
  slug        ctx slug

options:
  -h, --help  show this help message and exit
  --json      print one JSON envelope {command, ok, data, warnings, error}
```

#### `okf ctx rename`

Renames a bundle and rewrites inbound links.

Writes immediately. Exit codes: 0 success; 2 usage error.

```text
usage: okf ctx rename [-h] [--json] old new

move _ctx/<old>.md to _ctx/<new>.md; inbound links and the _ctx index follow

positional arguments:
  old         current ctx slug
  new         new ctx slug: lowercase letters, digits, hyphens

options:
  -h, --help  show this help message and exit
  --json      print one JSON envelope {command, ok, data, warnings, error}
```

#### `okf ctx remove`

Deletes a bundle and lists the files that still link to it.

Writes immediately. Exit codes: 0 success; 2 usage error.

```text
usage: okf ctx remove [-h] [--json] slug

delete _ctx/<slug>.md, refresh the _ctx index and list every file that still
links to the removed ctx

positional arguments:
  slug        ctx slug

options:
  -h, --help  show this help message and exit
  --json      print one JSON envelope {command, ok, data, warnings, error}
```

### `okf visualize`

Writes `<bundle>/assets/viz.html`, a concept graph of the bundle. The page embeds every concept body and loads cytoscape and marked from the network when you open it.

Writes immediately. Exit codes: 0 success; 2 usage error.

```text
usage: okf visualize [-h] [--out OUT] [--json] bundle

write a viz.html concept graph for a bundle (embeds every concept body; needs
network for cytoscape/marked)

positional arguments:
  bundle      bundle to render the graph for

options:
  -h, --help  show this help message and exit
  --out OUT   output path (default: <bundle>/assets/viz.html)
  --json      print one JSON envelope {command, ok, data, warnings, error}
```

```text
$ okf visualize handbook
wrote <catalogue>/handbook/assets/viz.html (10 nodes, 7 edges)
```

### `okf sync-export`

Prints the payload of one canonical block, as declared in its owner concept. See [README, Canon blocks](../README.md#canon-blocks).

Read-only. Exit codes: 0 success; 2 usage error; 3 concept or block not found.

```text
usage: okf sync-export [-h] [--json] concept block-id

print a canonical block's payload for materialisation elsewhere

positional arguments:
  concept     canonical concept (<bundle>/<concept-id>)
  block-id    canon block id declared in that concept

options:
  -h, --help  show this help message and exit
  --json      print one JSON envelope {command, ok, data, warnings, error}
```

```text
$ okf sync-export kc-gov/ownership ownership-rule
Every normative statement has exactly one owner.
```

## Search

### `okf find`

Hybrid ranked search: a lexical FTS5/BM25 arm over `<root>/.fts/fts.sqlite` (built by `build-index`) and a semantic arm (needs `VOYAGE_API_KEY` and `build-semantic-index`). Each arm that is unavailable is announced on stderr and the other arm answers alone; without the lexical index `find` falls back to a substring scan. A search without hits prints `(no matches for: …)` and exits 0. The options below explain `rank`, `--breakdown` and `provenance`.

Read-only. Exit codes: 0 success; 2 usage error.

```text
usage: okf find [-h] [--include-topics] [--limit LIMIT] [--where EXPR]
                [--breakdown] [--expand-tags] [--json]
                query

hybrid ranked search: lexical FTS5/BM25 arm plus semantic arm

positional arguments:
  query             search terms; quote multi-word queries

options:
  -h, --help        show this help message and exit
  --include-topics  widen beyond .okf.toml declared bundle to topic folders
  --limit LIMIT     max results to print (default 10)
  --where EXPR      select concepts by an expression: `field op value` with op
                    one of = != < <= > >= ~ (contains), or `field in (a, b)`;
                    combine with and, or, not and parentheses. Fields: type,
                    tag, path (<bundle>/<concept-id>), archived (true or
                    false), tier (unverified, machine-confirmed or human-
                    reviewed), stale (true or false), status (an absent status
                    is stable) and any frontmatter key (nested: a.b; through
                    lists: verified.by, sources.resource). Timestamp keys
                    (generated.at, verified.at, stale_after,
                    usage_window.from/to, sources.last_modified,
                    sources.usage_window.from/to) compare as instants and take
                    an ISO 8601 value with an explicit offset: stale_after <
                    2026-10-01T00:00:00Z. Archived concepts are hidden unless
                    the expression names `archived`. Quote a value holding
                    spaces, + or other characters: 'a b'. Example: (type =
                    Runbook and tag != draft) and path ~ home-lab/
  --breakdown       print per-hit contributing field(s)/term(s); output is
                    byte-identical to today without this flag
  --expand-tags     expand the query with semantically near registered tags
                    before lexical scoring; measured against the full
                    catalogue and found ineffective for the vocabulary-
                    mismatch class it was built for, so it stays off by
                    default (Q05/D17)
  --json            print one JSON envelope {command, ok, data, warnings,
                    error}

rank / score lines:
  Every hit's headline number is `rank: N` — its 1-based position in the
  delivered list. It is the one scale comparable across a mixed-arm result,
  because it IS the list order, and it claims nothing about the two arms'
  raw scores being on one scale (D12: fuse_conditional hands the ranking to
  whichever arm owns it, it never blends the two by score). Those raw,
  non-comparable values stay out of the default output and show only with
  --breakdown, one `score:` line per hit naming which arm produced it:
    a/100        the FTS5/BM25 lexical arm, relative to this run's own top
                 hit.
    a/(6 * n)    the substring fallback used when no FTS index is available:
                 per query term 3 for a title hit, 2 for a tag hit, 1 for a
                 body hit, capped at one per field per term — so the maximum
                 is 6 * number of terms.
    cosine X.XX  the semantic arm's raw cosine similarity — printed on its
                 own line, not folded into an a/100 fraction, because that
                 shape would invite comparing it against a lexical score
                 (D12, same rule as above).
  `provenance:` names the arm that produced the line. Degradations (index
  absent or stale, embedding backend unavailable) are announced on stderr,
  one note per degraded arm.

filters:
  --where EXPR selects the concepts the answer may hold, whichever arm owns
  the ranking: the lexical, substring and semantic arms all apply it before
  the result is cut to --limit. Without `archived` in the expression,
  archived concepts are hidden; the semantic arm never covers them.
```

```text
$ okf build-index
indexed 25 concept(s) -> <catalogue>/.fts/fts.sqlite
$ okf find pasta --limit 2
------
rank: 1
title: Pasta
type: Recipe
path: recipes/pasta
description: Spaghetti, simple
body-snippet: # Pasta ## Zutaten Nudeln, Salz, Wasser. ## Quellen - [Pasta basics](https://example.org/pasta)…
provenance: lexical
------
rank: 2
title: Bread
type: Recipe
path: recipes/bread
description: Bread with a long rise
… (3 more lines)
stderr: note: semantic arm skipped (.tagvec cache/concept embeddings absent) — lexical results only
```

### `okf refs`

Inbound and outbound markdown links of one file; a link that points nowhere is marked `[missing]`.

Read-only. Exit codes: 0 success; 2 usage error; 3 target not found.

```text
usage: okf refs [-h] [--scan-root SCAN_ROOT] [--in | --out] [--json] path

list inbound and outbound markdown links of a file

positional arguments:
  path                  target file (abs, or relative to --root)

options:
  -h, --help            show this help message and exit
  --scan-root SCAN_ROOT
                        dir to scan (default: --root); pass repo root for
                        repo-wide
  --in                  only inbound links
  --out                 only outbound links
  --json                print one JSON envelope {command, ok, data, warnings,
                        error}
```

```text
$ okf refs handbook/getting-started.md
inbound (4):
  _ctx/onboarding.md  ->  /handbook/getting-started.md
  handbook/index.md  ->  /handbook/getting-started.md
  handbook/overview.md  ->  getting-started.md
  handbook/ops/deploy.md  ->  ../getting-started.md
outbound (6):
  /handbook/glossary.md  ->  handbook/glossary.md
  ops/deploy.md  ->  handbook/ops/deploy.md
  security.md  ->  handbook/security.md
  ops/retired-tool.md  ->  handbook/ops/retired-tool.md
  assets/diagram.svg  ->  handbook/assets/diagram.svg
  /handbook/ops/missing.md  ->  handbook/ops/missing.md  [missing]
```

### `okf build-index`

Builds the lexical index `<root>/.fts/fts.sqlite`. Local, no network. `--if-stale` skips the work when the index is current. `find` prints a staleness note when the catalogue changed after the build.

Writes immediately. Exit codes: 0 success; 2 usage error.

```text
usage: okf build-index [-h] [--include-topics] [--if-stale] [--json]

(re)build the FTS5 lexical search index at <root>/.fts/fts.sqlite (local only,
no network)

options:
  -h, --help        show this help message and exit
  --include-topics  widen beyond .okf.toml declared bundle to topic folders
  --if-stale        skip the rebuild when the existing index is already
                    current (default: always rebuild)
  --json            print one JSON envelope {command, ok, data, warnings,
                    error}
```

```text
$ okf build-index
indexed 25 concept(s) -> <catalogue>/.fts/fts.sqlite
```

### `okf build-semantic-index`

Embeds every concept that still lacks a `voyage-3-large` embedding into `<root>/.tagvec/tag_vectors.sqlite`. Uses the network and needs `VOYAGE_API_KEY`; without the key it prints a note on stderr and exits 0. `--if-stale` skips the work when the index is current.

Writes immediately. Exit codes: 0 success; 2 usage error.

```text
usage: okf build-semantic-index [-h] [--if-stale] [--json]

fill <root>/.tagvec/tag_vectors.sqlite's concept_emb table for every concept
still missing a voyage-3-large embedding (NETWORK, requires VOYAGE_API_KEY)

options:
  -h, --help  show this help message and exit
  --if-stale  skip the run when semantic_coverage() already reports every on-
              disk concept embedded (default: always fill the delta)
  --json      print one JSON envelope {command, ok, data, warnings, error}
```

```text
$ env -u VOYAGE_API_KEY okf build-semantic-index
stderr: note: semantic index build skipped (VOYAGE_API_KEY not set) -- run again once it is set, or set it before the next SessionStart hook run
```

### `okf build-tagvec`

Hidden command: it does not appear in `okf --help`. Offline producer for `<root>/.tagvec/tag_vectors.sqlite`. Without `--produce` it is a dry run: it prints the plan, makes no network call and writes nothing. With `--produce` it embeds the tags (and, with `--target`, concepts) through Ollama (`bge-m3`, `http://localhost:11434/api/embed`) and through Voyage (`voyage-3-large`, needs `VOYAGE_API_KEY`).

Previews by default and writes nothing; `--apply` performs exactly the previewed plan. Exit codes: 0 success; 2 usage error.

```text
usage: okf build-tagvec [-h] [--output OUTPUT]
                        [--model {bge-m3,voyage-3-large}]
                        [--target {tags,concepts,both}]
                        [--concept-path-prefix CONCEPT_PATH_PREFIX]
                        [--concept-limit CONCEPT_LIMIT] [--produce]

offline producer for <root>/.tagvec/tag_vectors.sqlite (dry-run unless
--produce)

options:
  -h, --help            show this help message and exit
  --output OUTPUT       output sqlite path (default:
                        <root>/.tagvec/tag_vectors.sqlite)
  --model {bge-m3,voyage-3-large}
                        model to (re)embed with; repeatable. Default: both
                        models.
  --target {tags,concepts,both}
                        what to embed: tags only (default, unchanged
                        behavior), concept titles+bodies only (P8/8c), or
                        both.
  --concept-path-prefix CONCEPT_PATH_PREFIX
                        only plan/produce concept embeddings for paths
                        starting with this prefix (e.g. 'bundle/' or
                        'bundle/_okfeval-') — scoping for small, deterministic
                        manual --produce runs.
  --concept-limit CONCEPT_LIMIT
                        cap the number of concepts (re-)embedded per model,
                        after --concept-path-prefix filtering.
  --produce             perform network embedding calls and write rows.
                        Without this flag: dry-run only (plan + print, no
                        network, no writes).
```

```text
$ okf build-tagvec
bge-m3: 13 tag(s) need embedding, 0 already cached
voyage-3-large: 13 tag(s) need embedding, 0 already cached
(dry-run — no network calls, no writes. Re-run with --produce to embed.)
```

## Tags

### `okf tags`

Without arguments: every tag with its usage count; `--singletons` shows tags used once. With one or more `query` arguments: fuzzy search of candidate tags. `--register TAG DESCRIPTION` is the one writing form: it inserts an entry into `TAGS.md` at once and every other byte of the file stays. `--validate TAG…` checks tags against the registry. Registry forms: [README, Tags](../README.md#tags).

Read-only. Exit codes: 0 success; 2 usage error; 4 with `--validate`: a tag is not registered (the `--help` text says exit 1; the binary exits 4).

```text
usage: okf tags [-h] [--limit LIMIT] [--singletons]
                [--register TAG DESCRIPTION] [--validate TAG [TAG ...]]
                [--json]
                [query ...]

list all tags with usage counts, or fuzzy-search candidate tags

positional arguments:
  query                 candidate tag(s) to fuzzy-search against the tag
                        universe; omit for full audit dump

options:
  -h, --help            show this help message and exit
  --limit LIMIT         max matches per candidate (default 8)
  --singletons          full-dump mode only: show tags used exactly once
  --register TAG DESCRIPTION
                        add a tag to the TAGS.md registry (closed-vocabulary
                        allow-list); DESCRIPTION is required, max 150 chars;
                        repeat the option for several tags
  --validate TAG [TAG ...]
                        check tag(s) against TAGS.md; exit 1 if any are
                        unregistered
  --json                print one JSON envelope {command, ok, data, warnings,
                        error}
```

```text
$ okf tags
  food            9
  ops             5
  glossary        2
  governance      2
  onboarding      2
  soup            2
  bread           1
  deploy          1
  incident        1
  misc            1
  pasta           1
  security        1
  x-experimental  1
$ okf tags --validate food nosuchtag; echo "exit code: $?"
UNKNOWN  nosuchtag
1 UNKNOWN — register with: okf tags --register <tag> "<description, max 150 chars>"
exit code: 4
```

### `okf merge-tags`

Merges or renames one or more tags into a target tag across concept frontmatter. `--where` narrows the concepts. A frontmatter the line patcher cannot patch ends the whole run (see [Differences](../README.md#differences-from-the-python-cli)).

Previews by default and writes nothing; `--apply` performs exactly the previewed plan. Exit codes: 0 success; 2 usage error.

```text
usage: okf merge-tags [-h] --into TAG [--where EXPR] [--apply] [--json]
                      tags [tags ...]

merge/rename one or more tags into a target tag across concept frontmatter

positional arguments:
  tags          source tag(s) to merge, e.g. workflow workflows

options:
  -h, --help    show this help message and exit
  --into TAG    destination tag name
  --where EXPR  select concepts by an expression: `field op value` with op one
                of = != < <= > >= ~ (contains), or `field in (a, b)`; combine
                with and, or, not and parentheses. Fields: type, tag, path
                (<bundle>/<concept-id>), archived (true or false), tier
                (unverified, machine-confirmed or human-reviewed), stale (true
                or false), status (an absent status is stable) and any
                frontmatter key (nested: a.b; through lists: verified.by,
                sources.resource). Timestamp keys (generated.at, verified.at,
                stale_after, usage_window.from/to, sources.last_modified,
                sources.usage_window.from/to) compare as instants and take an
                ISO 8601 value with an explicit offset: stale_after <
                2026-10-01T00:00:00Z. Archived concepts are hidden unless the
                expression names `archived`. Quote a value holding spaces, +
                or other characters: 'a b'. Example: (type = Runbook and tag
                != draft) and path ~ home-lab/
  --apply       write changes (default: dry-run preview only)
  --json        print one JSON envelope {command, ok, data, warnings, error}
```

```text
$ okf merge-tags misc --into food
--- a/recipes/stew.md
+++ b/recipes/stew.md
@@ -4,7 +4,6 @@
 beschreibung: Deutscher Eintopf
 tags:
   - food
-  - misc
 superseded_by: handbook/ops/deploy
 ---
 
unparseable    handbook/broken-yaml.md  (frontmatter does not parse: did not find expected ',' or ']' (line 3, column 9) — skipped)
merge-tags: 1 file(s) would rewrite, 1 unparseable — misc -> food
```

### `okf remove-tags`

Removes one or more tags from concept frontmatter. `--where` narrows the concepts.

Previews by default and writes nothing; `--apply` performs exactly the previewed plan. Exit codes: 0 success; 2 usage error.

```text
usage: okf remove-tags [-h] [--where EXPR] [--apply] [--json] tags [tags ...]

remove one or more tags from concept frontmatter (no merge target)

positional arguments:
  tags          tag(s) to remove, e.g. stale draft

options:
  -h, --help    show this help message and exit
  --where EXPR  select concepts by an expression: `field op value` with op one
                of = != < <= > >= ~ (contains), or `field in (a, b)`; combine
                with and, or, not and parentheses. Fields: type, tag, path
                (<bundle>/<concept-id>), archived (true or false), tier
                (unverified, machine-confirmed or human-reviewed), stale (true
                or false), status (an absent status is stable) and any
                frontmatter key (nested: a.b; through lists: verified.by,
                sources.resource). Timestamp keys (generated.at, verified.at,
                stale_after, usage_window.from/to, sources.last_modified,
                sources.usage_window.from/to) compare as instants and take an
                ISO 8601 value with an explicit offset: stale_after <
                2026-10-01T00:00:00Z. Archived concepts are hidden unless the
                expression names `archived`. Quote a value holding spaces, +
                or other characters: 'a b'. Example: (type = Runbook and tag
                != draft) and path ~ home-lab/
  --apply       write changes (default: dry-run preview only)
  --json        print one JSON envelope {command, ok, data, warnings, error}
```

```text
$ okf remove-tags misc
--- a/recipes/stew.md
+++ b/recipes/stew.md
@@ -4,7 +4,6 @@
 beschreibung: Deutscher Eintopf
 tags:
   - food
-  - misc
 superseded_by: handbook/ops/deploy
 ---
 
unparseable    handbook/broken-yaml.md  (frontmatter does not parse: did not find expected ',' or ']' (line 3, column 9) — skipped)
remove-tags: 1 file(s) would rewrite, 0 emptied, 1 unparseable — removed misc
```

### `okf normalize-tags`

Rewrites inline `tags: [a, b]` to the YAML block-list form. `--where` narrows the concepts.

Previews by default and writes nothing; `--apply` performs exactly the previewed plan. Exit codes: 0 success; 2 usage error.

```text
usage: okf normalize-tags [-h] [--where EXPR] [--apply] [--json]

convert inline `tags: [...]` fields to YAML block-list form (local convention)

options:
  -h, --help    show this help message and exit
  --where EXPR  select concepts by an expression: `field op value` with op one
                of = != < <= > >= ~ (contains), or `field in (a, b)`; combine
                with and, or, not and parentheses. Fields: type, tag, path
                (<bundle>/<concept-id>), archived (true or false), tier
                (unverified, machine-confirmed or human-reviewed), stale (true
                or false), status (an absent status is stable) and any
                frontmatter key (nested: a.b; through lists: verified.by,
                sources.resource). Timestamp keys (generated.at, verified.at,
                stale_after, usage_window.from/to, sources.last_modified,
                sources.usage_window.from/to) compare as instants and take an
                ISO 8601 value with an explicit offset: stale_after <
                2026-10-01T00:00:00Z. Archived concepts are hidden unless the
                expression names `archived`. Quote a value holding spaces, +
                or other characters: 'a b'. Example: (type = Runbook and tag
                != draft) and path ~ home-lab/
  --apply       write changes (default: dry-run preview only)
  --json        print one JSON envelope {command, ok, data, warnings, error}
```

```text
$ okf normalize-tags
--- a/handbook/glossary.md
+++ b/handbook/glossary.md
@@ -2,7 +2,9 @@
 type: Concept
 title: Glossary
 description: 'Terms used here: "bundle" and "concept"'
-tags: [glossary, ops]   # flow form on purpose
+tags:                   # flow form on purpose
+  - glossary
+  - ops
 ---
 
 # Glossary
--- a/recipes/overview.md
… (26 more lines)
```

## Maintenance

### `okf check`

Conformance scan: the format rules (`okf/…`) and the catalogue rules (`kc/…`). `--ignore RULE` takes an exact rule ID or a prefix ending in `*`; it adds to `ignore_rules` in `.okf.toml`. Rules: [README, Check conformance](../README.md#check-conformance).

Read-only. Exit codes: 0 success; 2 usage error; 4 a rule of severity ERROR fired (with `--strict`: or a WARNING).

```text
usage: okf check [-h] [--strict] [--ignore PATTERN] [--json] [--types TYPES]
                 [target]

conformance scan: §9 hard rules + local invariants

positional arguments:
  target            <bundle> or <bundle>/<subdir> (default: whole catalogue)

options:
  -h, --help        show this help message and exit
  --strict          count warnings toward the exit code; each finding keeps
                    its severity
  --ignore PATTERN  suppress rules: an exact rule ID, or a prefix ending in
                    `*` (kc/*, okf/link/*); repeatable, added to .okf.toml
                    ignore_rules; suppressed findings neither print nor count
  --json            print one JSON envelope {command, ok, data, warnings,
                    error}
  --types TYPES     explicit TYPES.md path (overrides .okf.toml types_source)
```

```text
$ okf check kc-gov; echo "exit code: $?"
WARNING  kc/sync/stale        kc-gov/naming.md  (sync block `naming-rule` from /kc-gov/ownership.md is outdated — run sync-update)
OK — 0 violations
exit code: 0
$ okf check --strict kc-gov; echo "exit code: $?"
WARNING  kc/sync/stale        kc-gov/naming.md  (sync block `naming-rule` from /kc-gov/ownership.md is outdated — run sync-update)
1 VIOLATIONS
exit code: 4
```

### `okf verify`

Appends `{by, at}` with the current UTC time to the concept's `verified` list. `--by` is `human:<id>`, `process:<id>` or `<producer>/<version>`. Only the frontmatter block is rewritten.

Writes immediately. Exit codes: 0 success; 2 usage error; 2 `--by` missing or malformed.

```text
usage: okf verify [-h] --by ACTOR [--json] concept

record that a concept was checked against its sources

positional arguments:
  concept     <bundle>/<concept-id> of the concept

options:
  -h, --help  show this help message and exit
  --by ACTOR  who verified it: `human:<id>`, `process:<id>` or
              `<producer>/<version>`
  --json      print one JSON envelope {command, ok, data, warnings, error}
```

```text
$ okf verify handbook/ops/setup --by human:erik
verified handbook/ops/setup by human:erik at 2026-10-17T12:40:49Z
$ git diff
diff --git a/handbook/ops/setup.md b/handbook/ops/setup.md
index 044c736..53b6a58 100644
--- a/handbook/ops/setup.md
+++ b/handbook/ops/setup.md
@@ -5,6 +5,9 @@ description: Local setup
 tags:
   - ops
 status: stable
+verified:
+  - by: human:erik
+    at: 2026-10-17T12:40:49Z
 ---
 
 # Setup
```

### `okf migrate`

Brings frontmatter to OKF v0.2: the old date field becomes `generated`, `status` maps to the three v0.2 values, a citations list moves to `sources`. Concepts without a usable git history are reported as `unresolved`. Details: [README, Migrate](../README.md#migrate-a-catalogue-to-v02).

Previews by default and writes nothing; `--apply` performs exactly the previewed plan. Exit codes: 0 success; 2 usage error.

```text
usage: okf migrate [-h] [--apply] [--json] [target]

migrate frontmatter to OKF 0.2: `timestamp` to `generated` (git), `status` per
D37 (dry-run default)

positional arguments:
  target      <bundle> or <bundle>/<subdir> (default: whole catalogue)

options:
  -h, --help  show this help message and exit
  --apply     write the previewed changes (default: dry-run preview only)
  --json      print one JSON envelope {command, ok, data, warnings, error}
```

```text
$ okf migrate
status mapping:
  active -> stable (1 concept(s))
  deprecated -> deprecated (1 concept(s))
  maybe-later -> (no decision) (1 concept(s))
  obsolete -> deprecated (1 concept(s))
  stable -> stable (1 concept(s))
  todo -> draft (1 concept(s))
--- a/recipes/bread.md
+++ b/recipes/bread.md
@@ -5,8 +5,10 @@
 tags:
   - food
   - bread
-timestamp: 2025-12-02T08:00:00Z
-status: todo
+generated:
… (44 more lines)
```

### `okf rename`

Moves a concept and rewrites every inbound and outbound link, unambiguous wikilinks and context-bundle entries, then reindexes. `--force` overwrites an existing destination and proceeds when inbound wikilinks would turn ambiguous. Use it instead of `mv`.

Previews by default and writes nothing; `--apply` performs exactly the previewed plan. Exit codes: 0 success; 2 usage error; 3 source not found.

```text
usage: okf rename [-h] [--apply] [--force] [--json] old new

move a concept + rewrite every inbound/outbound link + reindex (dry-run
default)

positional arguments:
  old         source concept path (<bundle>/<concept>.md, abs or --root-
              relative)
  new         destination path (same or different bundle)

options:
  -h, --help  show this help message and exit
  --apply     perform the move (default: dry-run preview only)
  --force     overwrite an existing destination, and proceed when the new
              basename is already taken and inbound wikilinks would turn
              ambiguous
  --json      print one JSON envelope {command, ok, data, warnings, error}
```

```text
$ okf rename handbook/ops/retired-tool.md handbook/ops/legacy-tool.md
--- a/_ctx/legacy.md
+++ b/_ctx/legacy.md
@@ -7,7 +7,7 @@
 
 | pos | mode | path | comment |
 |---|---|---|---|
-| 1 | pflicht | [retired-tool](/handbook/ops/retired-tool.md) |  |
+| 1 | pflicht | [legacy-tool](/handbook/ops/legacy-tool.md) |  |
 | 2 | pflicht | [setup](/handbook/ops/setup.md) |  |
 | 3 | pflicht | [gone](/handbook/ops/gone.md) | removed long ago |
 | - | nachschlag | [old-process](/_archive/handbook/old-process.md) |  |
--- a/handbook/getting-started.md
+++ b/handbook/getting-started.md
@@ -16,7 +16,7 @@
… (39 more lines)
```

### `okf archive`

Moves a concept to `_archive/<bundle>/`. `--restore _archive/<bundle>/<concept>` moves it back. Links are rewritten as in `rename`.

Previews by default and writes nothing; `--apply` performs exactly the previewed plan. Exit codes: 0 success; 2 usage error; 3 concept not found.

```text
usage: okf archive [-h] [--restore] [--apply] [--force] [--json] path

move a concept into _archive/<bundle>/, or back with --restore (dry-run
default)

positional arguments:
  path        <bundle>/<concept>[.md]; with --restore:
              _archive/<bundle>/<concept>[.md]. The other end is derived,
              never typed

options:
  -h, --help  show this help message and exit
  --restore   move the path back out of _archive/ instead of into it
  --apply     perform the move (default: dry-run preview only)
  --force     overwrite an existing destination, and proceed when the new
              basename is already taken and inbound wikilinks would turn
              ambiguous
  --json      print one JSON envelope {command, ok, data, warnings, error}
```

```text
$ okf archive handbook/ops/retired-tool
3 active concept(s) still link to this concept
rename from handbook/ops/retired-tool.md
rename to _archive/handbook/ops/retired-tool.md
--- a/handbook/ops/retired-tool.md
+++ b/_archive/handbook/ops/retired-tool.md
@@ -9,4 +9,4 @@
 
 # Retired tool
 
-Replaced by [deploy](deploy.md). See [[deploy]].
+Replaced by [deploy](/handbook/ops/deploy.md). See [[deploy]].
--- a/_ctx/legacy.md
+++ b/_ctx/legacy.md
@@ -7,7 +7,7 @@
… (36 more lines)
```

### `okf reindex`

Regenerates the marker-bounded listings in `index.md` (one level) and `index-map.md` (the whole subtree). `--init` converts marker-less flat `index.md` files to managed ones.

Writes immediately; `--check` previews without writing. Exit codes: 0 success; 2 usage error; 5 with `--check`: a listing is stale or uncovered.

```text
usage: okf reindex [-h] [--init] [--check] [--force] [--json] target

(re)generate marker-bounded index listings: index.md one level, index-map.md
the whole subtree

positional arguments:
  target      <bundle> or <bundle>/<subdir>

options:
  -h, --help  show this help message and exit
  --init      recursively migrate marker-less flat index.md in the subtree to
              managed marker blocks (bespoke multi-section indexes are skipped
              + flagged)
  --check     dry-run: with --init preview conversions; else report stale +
              uncovered. No writes
  --force     with --init, also flatten a pure multi-section listing
              (prose/tables still refuse)
  --json      print one JSON envelope {command, ok, data, warnings, error}
```

```text
$ okf reindex recipes --check | head -n 8
--- a/recipes/index.md
+++ b/recipes/index.md
@@ -7,10 +7,12 @@
 ## Contents
 
 <!-- okf:index -->
-* [Drafts](/recipes/drafts/index.md)
+* [Drafts](/recipes/drafts/index.md) - Unfinished ideas.
$ okf reindex recipes --check >/dev/null; echo "exit code: $?"
exit code: 5
```

### `okf fix-crosslinks`

Rewrites links to the catalogue-root-absolute form `/bundle/subdir/concept.md`. `--include-reserved` also covers `index.md`, `log.md`, `readme.md` and `index-map.md` outside their managed block.

Writes immediately; `--check` previews without writing. Exit codes: 0 success; 2 usage error.

```text
usage: okf fix-crosslinks [-h] [--check] [--include-reserved] [--json]
                          [target]

rewrite links to catalogue-root-absolute form (/bundle/subdir/concept.md)

positional arguments:
  target              <bundle> or <bundle>/<subdir> (default: whole catalogue)

options:
  -h, --help          show this help message and exit
  --check             dry-run: report without writing
  --include-reserved  also rewrite RESERVED files (index.md, log.md,
                      readme.md, index-map.md), narrowed to the text outside
                      the managed <!-- okf:index --> block, which stays byte-
                      identical (D-fxcr-01, off by default)
  --json              print one JSON envelope {command, ok, data, warnings,
                      error}
```

```text
$ okf fix-crosslinks --check
--- a/handbook/getting-started.md
+++ b/handbook/getting-started.md
@@ -15,8 +15,8 @@
 
 ## Tools
 
-Read the [deploy runbook](ops/deploy.md) and the [security page](security.md).
-The old tool is described in [retired tool](ops/retired-tool.md).
+Read the [deploy runbook](/handbook/ops/deploy.md) and the [security page](/handbook/security.md).
+The old tool is described in [retired tool](/handbook/ops/retired-tool.md).
 Download the [diagram](assets/diagram.svg). A [missing page](/handbook/ops/missing.md) is dead.
 
 ### Wikilinks
--- a/handbook/ops/deploy.md
… (53 more lines)
```

### `okf fix-xml-tags`

Wraps `<tag>` and `<tag>.<tag2>` placeholders in inline code.

Writes immediately; `--check` previews without writing. Exit codes: 0 success; 2 usage error.

```text
usage: okf fix-xml-tags [-h] [--check] [--json] [target]

wrap `<tag>`/`<tag>.<tag2>` placeholders in inline code

positional arguments:
  target      <bundle> or <bundle>/<subdir> (default: whole catalogue)

options:
  -h, --help  show this help message and exit
  --check     dry-run: report without writing
  --json      print one JSON envelope {command, ok, data, warnings, error}
```

```text
$ okf fix-xml-tags --check
--- a/recipes/soup.md
+++ b/recipes/soup.md
@@ -14,4 +14,4 @@
 
 ## Hinweis
 
-Use a pot <size>. Compare with [bread](/recipes/bread.md).
+Use a pot `<size>`. Compare with [bread](/recipes/bread.md).
fix-xml-tags: 1 file(s) would wrap, 1 chain(s) total
```

### `okf rewrite-path`

Replaces a literal path string across text files. `--scan-root` sets the directory.

Writes immediately; `--check` previews without writing. Exit codes: 0 success; 2 usage error.

```text
usage: okf rewrite-path [-h] [--scan-root SCAN_ROOT] [--check] [--json]
                        old new

literal path-string rewrite across text files

positional arguments:
  old                   literal path string to replace
  new                   replacement path string

options:
  -h, --help            show this help message and exit
  --scan-root SCAN_ROOT
                        dir to scan (default: --root)
  --check               dry-run: report, write nothing
  --json                print one JSON envelope {command, ok, data, warnings,
                        error}
```

```text
$ okf rewrite-path old-host.example.org new-host.example.org --check
--- a/handbook/ops/setup.md
+++ b/handbook/ops/setup.md
@@ -9,7 +9,7 @@
 
 # Setup
 
-Install the tools. Plain `old-host.example.org` is the old status host.
+Install the tools. Plain `new-host.example.org` is the old status host.
 
 <!-- okf:sync id=ownership-rule source=/kc-gov/ownership.md hash=594970cbf139 -->
 > [!quote] Synchronisiert aus `/kc-gov/ownership.md` — Canon-Owner, hier nicht bearbeiten.
1 file(s) affected (dry-run)
```

### `okf wikilinks`

Reports Obsidian `[[wikilinks]]` and whether each resolves to a concept.

Read-only. Exit codes: 0 success; 2 usage error.

```text
usage: okf wikilinks [-h] [--unresolved] [--json] [target]

report Obsidian wikilinks ([[…]]) and whether each resolves to a concept

positional arguments:
  target        <bundle> or <bundle>/<subdir> (default: whole catalogue)

options:
  -h, --help    show this help message and exit
  --unresolved  list only unresolved and ambiguous occurrences (summary stays
                complete)
  --json        print one JSON envelope {command, ok, data, warnings, error}
```

```text
$ okf wikilinks
resolved   body        handbook/getting-started.md  [[glossary]]
resolved   body        handbook/getting-started.md  [[deploy|the deploy page]]
unresolved body        handbook/getting-started.md  [[does-not-exist]]
resolved   body        handbook/getting-started.md  [[overview]]
resolved   body        handbook/security.md  [[wiki-notes]]
resolved   body        handbook/wiki-notes.md  [[glossary]]
resolved   body        handbook/wiki-notes.md  [[handbook/ops/deploy]]
resolved   body        handbook/wiki-notes.md  [[retired-tool|old tool]]
… (6 more lines)
```

### `okf sync-status`

Reports each materialised canon block as `synced`, `source-changed`, `consumer-modified`, `both-changed`, `source-missing` or `malformed`.

Read-only. Exit codes: 0 success; 2 usage error; 5 any block is not `synced`.

```text
usage: okf sync-status [-h] [--source SOURCE] [--block BLOCK_ID] [--json]
                       [target]

drift report for every materialised canon block

positional arguments:
  target            <bundle> or <bundle>/<subdir> (default: whole catalogue)

options:
  -h, --help        show this help message and exit
  --source SOURCE   only blocks whose canonical source is this path
                    (/bundle/concept.md)
  --block BLOCK_ID  only blocks with this id
  --json            print one JSON envelope {command, ok, data, warnings,
                    error}
```

```text
$ okf sync-status; echo "exit code: $?"
synced             handbook/ops/setup.md            /kc-gov/ownership.md#ownership-rule
source-changed     kc-gov/naming.md                 /kc-gov/ownership.md#naming-rule
sync-status: 1 synced, 1 source-changed, 0 consumer-modified, 0 both-changed, 0 source-missing, 0 malformed
exit code: 5
```

### `okf sync-insert`

Materialises a canonical block in a consumer concept: `sync-insert <consumer> <concept> <block-id>`.

Previews by default and writes nothing; `--apply` performs exactly the previewed plan. Exit codes: 0 success; 2 usage error.

```text
usage: okf sync-insert [-h] [--apply] [--json] consumer concept block-id

materialise a canonical block inside a consumer concept (dry-run default)

positional arguments:
  consumer    consumer concept to insert into (<bundle>/<concept-id>)
  concept     canonical owner concept (<bundle>/<concept-id>)
  block-id    canon block id to materialise

options:
  -h, --help  show this help message and exit
  --apply     write the block (default: dry-run preview only)
  --json      print one JSON envelope {command, ok, data, warnings, error}
```

```text
$ okf sync-insert recipes/soup kc-gov/ownership ownership-rule
--- a/recipes/soup.md
+++ b/recipes/soup.md
@@ -15,3 +15,9 @@
 ## Hinweis
 
 Use a pot <size>. Compare with [bread](/recipes/bread.md).
+
+<!-- okf:sync id=ownership-rule source=/kc-gov/ownership.md hash=594970cbf139 -->
+> [!quote] Synchronisiert aus `/kc-gov/ownership.md` — Canon-Owner, hier nicht bearbeiten.
+<!-- okf:sync-body -->
+Every normative statement has exactly one owner.
+<!-- /okf:sync -->
would insert    recipes/soup.md   /kc-gov/ownership.md#ownership-rule
sync-insert (dry-run): re-run with --apply.
```

### `okf sync-update`

Re-materialises outdated consumer blocks from their canon owner. `--force` also overwrites a locally modified copy.

Previews by default and writes nothing; `--apply` performs exactly the previewed plan. Exit codes: 0 success; 2 usage error; 5 a copy was refused (consumer modified, no `--force`) or cannot be resolved.

```text
usage: okf sync-update [-h] [--source SOURCE] [--block BLOCK_ID] [--apply]
                       [--force] [--json]
                       [target]

re-materialise outdated consumer blocks from their canon owner (dry-run
default)

positional arguments:
  target            <bundle> or <bundle>/<subdir> (default: whole catalogue)

options:
  -h, --help        show this help message and exit
  --source SOURCE   only blocks whose canonical source is this path
                    (/bundle/concept.md)
  --block BLOCK_ID  only blocks with this id
  --apply           write changes (default: dry-run preview only)
  --force           also overwrite a consumer copy that was modified locally
                    (discards it)
  --json            print one JSON envelope {command, ok, data, warnings,
                    error}
```

```text
$ okf sync-update
--- a/kc-gov/naming.md
+++ b/kc-gov/naming.md
@@ -9,8 +9,8 @@
 
 Refer to [ownership](/kc-gov/ownership.md).
 
-<!-- okf:sync id=naming-rule source=/kc-gov/ownership.md hash=68dca574d22c -->
+<!-- okf:sync id=naming-rule source=/kc-gov/ownership.md hash=5f1068e89974 -->
 > [!quote] Synchronisiert aus `/kc-gov/ownership.md` — Canon-Owner, hier nicht bearbeiten.
 <!-- okf:sync-body -->
-Names are lowercase, hyphenated and stable.
+Names are lowercase, hyphenated, stable and unique.
 <!-- /okf:sync -->
would update   kc-gov/naming.md   /kc-gov/ownership.md#naming-rule
… (1 more lines)
```

### `okf registry`

`registry convert TAGS.md|TYPES.md --to block|table` rewrites every registry entry in the target form; the text between entries stays. It refuses, with exit 2, a conversion that would lose text (see [README, Tags](../README.md#tags)).

Previews by default and writes nothing; `--apply` performs exactly the previewed plan. Exit codes: 0 success; 2 usage error; 2 the conversion would lose text (file untouched).

```text
usage: okf registry [-h] VERB ...

reformat registry entries of TAGS.md or TYPES.md (table or block form); prose
stays

positional arguments:
  VERB        registry verb
    convert   rewrite every entry of one registry file in the target form

options:
  -h, --help  show this help message and exit
```

```text
$ okf registry convert TAGS.md --to block
--- a/TAGS.md
+++ b/TAGS.md
@@ -2,16 +2,35 @@
 
 Closed vocabulary for concept `tags:`.
 
-| Tag | Description |
-|-----|-------------|
-| `bread` | Bread and baking |
-| `deploy` | Deployment procedures |
-| `food` | Anything edible |
-| `glossary` | Term definitions |
-| `governance` | Rules and ownership |
-| `incident` | Incident reports |
-| `ops` | Operations |
-| `onboarding` | First-day material |
… (36 more lines)
```

### `okf install`

Registers okf with this machine's coding agents and shells: agent skill, MCP server and shell completion. Needs no catalogue. Without `--only` it handles every agent and shell it detects. Details and per-platform steps: [docs/install.md](install.md).

Previews by default and writes nothing; `--apply` performs exactly the previewed plan. Exit codes: 0 success; 2 usage error; 1 a step is blocked or failed.

```text
usage: okf install [-h] [--apply] [--uninstall] [--only NAMES] [--json]

register okf, its agent skill, MCP server and shell completion with this
machine's agents and shells (dry-run default; needs no catalogue)

options:
  -h, --help    show this help message and exit
  --apply       perform the plan (default: print the plan, change nothing)
  --uninstall   plan, or with --apply perform, the removal of everything
                install created
  --only NAMES  comma-separated subset: claude, omp, codex, opencode, kimi,
                openclaw, hermes (agents), zsh, bash, fish (shells). Default:
                install for every agent and shell found on this machine;
                uninstall covers all of them
  --json        print one JSON envelope {command, ok, data, warnings, error}
```

```text
$ okf install --only zsh
okf install - PLAN only, nothing is changed (add --apply to perform it)
source: /usr/local/bin (installed package, skills are copied)

shell
  skip      PATH            okf is already on PATH: /usr/local/bin/okf
  create    zsh completion  ~/.zsh/completions/_okf
  create    zsh rc          ~/.zshrc (managed block)

2 step(s) planned. Run again with --apply to perform them.
```
