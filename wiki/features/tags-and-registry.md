---
title: "Tag management and the TAGS.md registry"
description: "Tag management for Markdown frontmatter: usage counts, fuzzy search, the TAGS.md registry, merge tags, and tag hygiene checks from the CLI."
---

## Tag management and the `TAGS.md` registry

**List, check, merge and register the tags of a catalogue from the shell, against one closed vocabulary in `TAGS.md`.**

Output below comes from okf 0.2.4 (`git describe`: `0.2.4-115-g91f54bf`), run against a throwaway copy of the test catalogue.

## How it looks

```text title="okf tags"
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
[exit 0]
```

```text title="okf tags sup --limit 3"
== searched: sup ==
  - soup  (2)

[exit 0]
```

```text title="okf tags --validate soup nonsense"
UNKNOWN  nonsense
1 UNKNOWN — register with: okf tags --register <tag> "<description, max 150 chars>"
[exit 4]
```

## Why it matters

**One tag vocabulary, checked and repairable from the shell.**

## What you get

- `okf tags` lists usage counts, most used first. `--singletons` shows tags used once. With a query it fuzzy-searches the tag universe.
- `okf tags --validate TAG...` checks tags against `TAGS.md`.
- `okf tags --register TAG DESCRIPTION` adds a tag. The description is required, 150 characters at most. Repeat the option for several tags.
- `okf merge-tags`, `okf remove-tags` and `okf normalize-tags` edit tags across concepts. Each one takes `--where` to limit the concepts.
- `okf registry convert` rewrites the entries of `TAGS.md` or `TYPES.md` between table and block form.

The registry is `TAGS.md` in the catalogue root: a table `| Tag | Description |`, or block form. The `check` rule `kc/tag/registered` warns for a tag that is not in it:

```text title="okf check (tag lines)"
WARNING  kc/tag/registered    handbook/security.md  (tag `x-experimental` not registered in TAGS.md)
WARNING  kc/tag/registered    recipes/stew.md  (tag `misc` not registered in TAGS.md)
```

### Merge preview

```text title="okf merge-tags misc --into food"
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
[exit 0]
```

Nothing is written until you add `--apply`. The merge skips a file whose frontmatter does not parse and reports it.

### Registry conversion preview

```text title="okf registry convert TAGS.md --to block (diff head)"
--- a/TAGS.md
+++ b/TAGS.md
@@ -2,16 +2,35 @@
 
 Closed vocabulary for concept `tags:`.
 
-| Tag | Description |
-|-----|-------------|
-| `bread` | Bread and baking |
+### `bread`
+Bread and baking
+
+### `deploy`
+Deployment procedures
```

The last line of the real run is `registry convert: 11 entries in TAGS.md would rewrite as block`. Text outside the entries stays byte for byte. The `.okf.toml` key `registry_format` sets the form that `--register` writes.

## Details

- `merge-tags`, `remove-tags`, `normalize-tags` and `registry convert` preview a diff and need `--apply` to write.
- `tags --register` writes `TAGS.md` immediately. It has no preview.
- `--validate` and `--json` follow the [envelope and exit-code rules](/okf-cli/reference/json-output-and-exit-codes/). `--json` data is `{tags: [{tag, count}]}` for the list and `{closed_vocabulary, unknown}` for `--validate`.

:::tip[Tag hygiene]
Register every tag in `TAGS.md`. Run `okf tags --validate` in CI: an unregistered tag exits 4 and fails the job. Run `okf tags --singletons` to find near-duplicates, then `okf merge-tags` them into one tag.
:::

## Limits

- `tags --validate` exits 4. The `--help` text says 1 [irxe].
- `tags --register` then tries to embed the new tag with a local Ollama `bge-m3` at `http://localhost:11434/api/embed`. Without that server it warns `auto-embed skipped for new tag(s) (connection refused)` and names `cli/embeddings/build_tagvec.py`, a script a Go install does not contain [erpf]. The tag is registered anyway. The endpoint is fixed today; a configurable endpoint is planned [76eb].

## Reference

- [`okf tags`](/okf-cli/reference/commands/okf-tags/)
- [`okf merge-tags`](/okf-cli/reference/commands/okf-merge-tags/)
- [`okf remove-tags`](/okf-cli/reference/commands/okf-remove-tags/)
- [`okf normalize-tags`](/okf-cli/reference/commands/okf-normalize-tags/)
- [`okf registry convert`](/okf-cli/reference/commands/okf-registry-convert/)
