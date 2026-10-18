---
title: "Glossary: catalogue, bundle, concept and other okf terms"
description: "Definitions of the okf terms: catalogue, bundle, concept, type, frontmatter, ctx bundle, canon block, registry, envelope, root, FTS index, semantic arm, dry run and apply."
---

# OKF glossary: catalogue, bundle, concept

Every other page of this documentation uses these terms in exactly this meaning. For the file format itself see [Frontmatter and types](/reference/frontmatter-and-types/). For the settings that select a catalogue see [Configuration](/reference/configuration/).

## Terms

### Catalogue

A directory that holds knowledge as Markdown files. It is the *root* that okf works on. A directory counts as a catalogue when it contains `.okf.toml`, or `SPEC.md` together with `TYPES.md`. The catalogue-level files are `TYPES.md`, `PROPERTIES.md`, `TAGS.md`, `SPEC.md` and `.okf.toml`.

### Bundle

An immediate subdirectory of the catalogue whose name does not start with `.` or `_`. `_ctx/` is the one `_` directory that counts as a bundle (it holds the ctx bundles). `_archive/` holds archived concepts as `_archive/<bundle>/...`; search and list hide it unless you name `archived`. Not to be confused with a *ctx bundle*.

### Concept

A `.md` file in a bundle that has YAML frontmatter. Its *concept-id* is its path below the bundle without `.md`. The file `handbook/ops/deploy.md` is the concept `ops/deploy` in the bundle `handbook`. Output shows `path` as `<bundle>/<concept-id>`. The files `index.md`, `log.md`, `readme.md` and `index-map.md` are reserved: they are not concepts and never carry `type`.

### Type

The `type` frontmatter value of a concept, for example `Rule` or `Guide`. A type must be registered in `TYPES.md`. See [Types](/reference/frontmatter-and-types/#types).

### Frontmatter

The YAML block at the top of a concept, between two `---` lines. It carries `type`, `title`, `description`, `tags` and the provenance fields. See [Frontmatter fields](/reference/frontmatter-and-types/#frontmatter-fields).

ctx bundle
:   A curated reading list in `_ctx/<slug>.md`: a table of entries in reading order. Each entry has a position and a mode, `pflicht` (read first) or `nachschlag` (look up when needed). Titles and types of the entries are read live from the concept files. Commands: [`okf ctx`](/reference/commands/okf-ctx/). See [Context bundles](/features/context-bundles/).

### Canon block

Text with exactly one owner. The owner concept declares it between `<!-- okf:canon id=<block-id> -->` and `<!-- /okf:canon -->`. A consumer concept holds a *sync block*, a managed copy of the payload that carries `source=` and a hash. Do not edit a sync block by hand. Commands: `sync-export`, `sync-insert`, `sync-status`, `sync-update`. See [Canon blocks](/features/canon-blocks/).

### Registry

A closed vocabulary kept in a catalogue file. `TAGS.md` is the tag registry, `TYPES.md` is the type registry. Both are tables (`| Tag | Description |`, `| Type | Meaning |`), or block form. [`okf registry convert`](/reference/commands/okf-registry-convert/) switches between the two forms. See [Tags and the registry](/features/tags-and-registry/).

### Envelope

The JSON object that every command prints with `--json`: `{command, ok, data, warnings, error}`. See [JSON output and exit codes](/reference/json-output-and-exit-codes/).

### Root

The catalogue directory a command works on. okf resolves it from `--root`, from the nearest catalogue above the working directory, or from the user config. See [Root resolution order](/reference/configuration/#root-resolution-order).

### FTS index

The lexical search index `.fts/fts.sqlite` (SQLite FTS5, ranked with bm25: title weighs 3.0, tags 2.0, body 1.0). [`okf build-index`](/reference/commands/okf-build-index/) writes it.

### Semantic arm

The embedding-based half of search. It uses vectors in `.tagvec/tag_vectors.sqlite`, written by [`okf build-semantic-index`](/reference/commands/okf-build-semantic-index/). Models: `voyage-3-large` (Voyage API, needs `VOYAGE_API_KEY`) and `bge-m3` (local server at `http://localhost:11434`). See [Search](/features/search/).

### Dry run

The default of most commands that change files, for example `install`, `migrate`, `merge-tags` and `sync-update`. okf prints what it would change and writes nothing. Not every changing command has a dry run: `tags --register` writes at once.

### Apply

Running a command with `--apply` so that okf writes the change. The flag list on each command page states whether a command has it.
