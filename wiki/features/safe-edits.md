---
title: "Safe edits: rename markdown files and keep every link"
description: "Rename or archive a concept, preview the diff first, and let okf update links in one step. Safe edits for a markdown knowledge base: okf rename, archive, dry run."
---

# Safe edits: rename markdown files and update links

**Preview a rename or archive as a diff, then apply it. okf moves the concept and rewrites every link that pointed to it.**

Reorganising a knowledge base by hand breaks links. With `okf rename` and `okf archive` the move, the link fixes and the index refresh happen in one command. Without `--apply` nothing is written.

## How it looks

The measured version is okf 0.2.5. The runs below use a throwaway copy of the test catalogue that is also a git repository.

Step 1: a dry run. okf prints a diff for each file it would change, then a summary.

```text title="okf rename: dry run (output shortened)"
$ okf --root <catalogue> rename handbook/overview.md handbook/intro.md
--- a/handbook/getting-started.md
+++ b/handbook/getting-started.md
@@ -25,4 +25,4 @@
 
 ## Next
 
-Continue with [[overview]].
+Continue with [[intro]].
--- a/handbook/index.md
+++ b/handbook/index.md
@@ -14,7 +14,7 @@
-* [Handbook overview](/okf-cli/handbook/overview.md) - Overview of the handbook
+* [Handbook overview](/okf-cli/handbook/intro.md) - Overview of the handbook
…
rename (dry-run): 1 inbound, 0 outbound link(s), 2 wikilink(s) (0 skipped-ambiguous), 1 bundle(s), 0 sync source(s). Re-run with --apply.
```

After the dry run `git status --short` prints nothing: no file changed.

Step 2: apply.

```text title="okf rename --apply"
$ okf --root <catalogue> rename handbook/overview.md handbook/intro.md --apply
moved (git mv)  handbook/overview.md  ->  handbook/intro.md
rewrote 1 inbound link(s) in 1 file(s), 0 outbound link(s)
rewrote 2 wikilink(s) in 2 file(s)
rewrote 0 sync source(s) in 0 file(s)
reindexed 0 index file(s) across: handbook
staged for commit — run `okf check` before committing.
```

```text title="git status --short"
 M handbook/getting-started.md
 M handbook/index.md
R  handbook/overview.md -> handbook/intro.md
 M handbook/wiki-notes.md
```

Run [`okf check`](/okf-cli/features/conformance-checks/) before you commit.

## Why it matters

**One command moves a concept and rewrites every inbound and outbound link, so a reorganisation does not leave dead links behind.**

## What you get

- **Move.** [`okf rename`](/okf-cli/reference/commands/okf-rename/) moves a concept to a new path. Inbound links, outbound links, wikilinks, `source=` of [canon blocks](/okf-cli/features/canon-blocks/) and ctx bundle entries follow.
- **Archive.** [`okf archive`](/okf-cli/reference/commands/okf-archive/) moves a concept to `_archive/<bundle>/`. `okf archive --restore` moves it back. Links are rewritten both ways.
- **Bulk edits.**
  - [`okf rewrite-path`](/okf-cli/reference/commands/okf-rewrite-path/) replaces a literal path string in text files.
  - [`okf fix-crosslinks`](/okf-cli/reference/commands/okf-fix-crosslinks/) rewrites links to the catalogue-root-absolute form `/bundle/subdir/concept.md`.
  - [`okf fix-xml-tags`](/okf-cli/reference/commands/okf-fix-xml-tags/) wraps `<tag>` placeholders in inline code.
  - [`okf reindex`](/okf-cli/reference/commands/okf-reindex/) regenerates the marker-bounded index listings.
  - [`okf migrate`](/okf-cli/reference/commands/okf-migrate/) migrates frontmatter to OKF 0.2.

## Details

An archive dry run lists every change it plans:

```text title="okf archive: dry run"
$ okf --root <catalogue> archive handbook/ops/retired-tool
would move   handbook/ops/retired-tool.md  ->  _archive/handbook/ops/retired-tool.md
  inbound    _ctx/legacy.md   /handbook/ops/retired-tool.md  ->  /_archive/handbook/ops/retired-tool.md
  inbound    handbook/getting-started.md   ops/retired-tool.md  ->  /_archive/handbook/ops/retired-tool.md
  inbound    handbook/ops/index.md   /handbook/ops/retired-tool.md  ->  /_archive/handbook/ops/retired-tool.md
  outbound   deploy.md  ->  /handbook/ops/deploy.md
  ctx        legacy (pos 1)
  reindex    _archive, handbook
rename (dry-run): 3 inbound, 1 outbound link(s), 0 wikilink(s) (0 skipped-ambiguous), 2 bundle(s), 0 sync source(s). Re-run with --apply.
```

The dry run is not the same for every command:

| Behaviour | Commands |
|---|---|
| Preview first, `--apply` writes | `archive`, `rename`, `migrate`, `merge-tags`, `normalize-tags`, `remove-tags`, `registry convert`, `sync-insert`, `sync-update`, `install` |
| Write by default, `--check` is the dry run | `fix-crosslinks`, `fix-xml-tags`, `rewrite-path`, `reindex` |
| Write at once, no preview | `verify`, `tags --register`, `build-index`, `visualize`, and the ctx verbs `create`, `add`, `drop`, `move`, `rename`, `remove` |

:::caution
Do not assume that a changing command previews first. `okf rewrite-path old new` writes at once. Add `--check` to see the effect first.
:::

Frontmatter edits (`migrate` and the tag commands) patch single lines and keep your formatting. If a frontmatter has a shape okf cannot patch safely, okf refuses. The run ends with exit 2 and the message `<path>: <reason>`, and nothing is written, also in a dry run.

`--force` on `okf archive` overwrites an existing destination and also proceeds when a new basename is already taken and wikilinks would turn ambiguous.

## Limits

- Only `rename` and `archive` are shown with real output on this page. Run the other commands with `--check` or without `--apply` first.
- A refused frontmatter ends the whole run of the tag commands and `migrate`. It does not skip the one file.
- Over MCP, the tool `okf_reindex` has no `check` argument, so it writes. This comes from the tool signature in `mcp/okf_mcp.py`; no MCP call was run.
- `rename` and `archive` exit 3 when the source is not found, and 2 for a path that is not a `.md` concept file or a reserved file such as `index.md`. `rename --apply` exits 2 when the destination exists, unless `--force` is given. A dry run of `rename` onto an existing destination exits 0.

## Reference

- [`okf rename`](/okf-cli/reference/commands/okf-rename/), [`okf archive`](/okf-cli/reference/commands/okf-archive/), [`okf rewrite-path`](/okf-cli/reference/commands/okf-rewrite-path/)
- [`okf fix-crosslinks`](/okf-cli/reference/commands/okf-fix-crosslinks/), [`okf fix-xml-tags`](/okf-cli/reference/commands/okf-fix-xml-tags/)
- [`okf reindex`](/okf-cli/reference/commands/okf-reindex/), [`okf migrate`](/okf-cli/reference/commands/okf-migrate/)
- [Dry run](/okf-cli/reference/glossary/#dry-run) and [Apply](/okf-cli/reference/glossary/#apply) in the glossary
