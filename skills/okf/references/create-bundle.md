# Create a bundle

Goal: a new bundle `<bundle>` in catalogue `<catalogue>` that passes `check`, shows its description in `index` and is found by `find`.

Inputs:

- `<catalogue>`: the catalogue root. It holds `.okf.toml`, or `SPEC.md` plus `TYPES.md`.
- `<bundle>`: directory name. Lowercase kebab-case, not starting with `.` or `_` (okf-cli ignores such directories).
- One sentence that states what the bundle holds.

okf-cli has no scaffold command. You create directories and `index.md` files by hand; okf-cli fills the listings and verifies the result. Concept rules live in write-concepts.md; load it together with this file.

## Contents

- Checklist
- 1. Orient
- 2. New catalogue only
- 3. Directories and index files
- 4. Vocabulary
- 5. First concept
- 6. Generate the listings
- 7. Verify
- 8. Commit, only when the user asked
- Failure modes

## Checklist

Copy into your task list (todo tool or scratch list), tick one by one:

- [ ] 1. Orient -> done when `prime`, `index` and `info` ran and no bundle covers the same scope -> if one does: stop and add concepts to it (write-concepts.md)
- [ ] 2. New catalogue only -> done when `prime --compact` prints no `carries no catalogue marker` note and `root docs:` lists `TYPES.md` -> on failure: fix the marker file or `--root`, rerun step 2
- [ ] 3. Directories and index files -> done when every new directory has an `index.md` with H1, intro sentence and the marker pair -> on failure: add what is missing, recheck step 3
- [ ] 4. Vocabulary -> done when every planned type is in `TYPES.md` and, with `TAGS.md`, `tags --validate` exits 0 -> on failure: reuse or register, rerun `tags --validate`
- [ ] 5. First concept -> done when the file has frontmatter with a registered `type`, a `description`, and only links whose targets exist -> on failure: fix the file, recheck step 5
- [ ] 6. Generate the listings -> done when `reindex` reports `0 skipped` -> on failure (`skipped (no markers)`): back to step 3
- [ ] 7. Verify -> done when every criterion in section 7 holds -> on failure: fix per "Failure modes", rerun steps 6 and 7 until clean
- [ ] 8. Commit, only when the user asked -> done when `git -C <catalogue> status --short` lists none of your paths -> on failure: stage the missing paths explicitly

## 1. Orient

```bash
okf-cli --root <catalogue> prime --compact
okf-cli --root <catalogue> index
okf-cli --root <catalogue> info
```

- A bundle with the same scope exists: add concepts there instead of creating a new bundle.
- `info` prints `TYPES.md` and `PROPERTIES.md`. `(missing: TYPES.md)` means the catalogue has no type vocabulary yet.
- `prime` prints `tag vocabulary: closed` when `TAGS.md` exists. Then every tag must be registered (step 4).

## 2. New catalogue only

Skip when `<catalogue>` exists. Otherwise create it:

1. `mkdir -p <catalogue>`
2. Write `<catalogue>/.okf.toml`. It is the catalogue marker; a comment line is enough. Do not add a `bundle` key to a shared catalogue: that key restricts search to one bundle.

   ```toml
   # okf-cli catalogue marker
   ```

3. Write `<catalogue>/TYPES.md`. `check` reads the first backticked cell of each table row as a registered type:

   ```markdown
   # Types

   | Type | Use for |
   |---|---|
   | `Concept` | An idea, definition or explanation |
   | `Decision` | A decision with its context and consequences |
   | `SOP` | A repeatable procedure |
   | `Reference` | Lookup material |
   | `Context` | A ctx reading list (written by the ctx commands) |
   ```

4. Optional: `<catalogue>/PROPERTIES.md` (frontmatter documentation, printed by `info`).
5. If the catalogue is a git repository: add `.fts/` and `.tagvec/` to `<catalogue>/.gitignore`. Both are local search indexes.

Verify: `okf-cli --root <catalogue> prime --compact` prints no `carries no catalogue marker` note on stderr, and its `root docs:` line lists `TYPES.md`.

## 3. Directories and index files

```bash
mkdir -p <catalogue>/<bundle>/<subdir>
```

Keep subdirectories few and one level deep, for example `architecture/`, `decisions/`, `operations/`, `reference/`. A small bundle needs none.

Write `<catalogue>/<bundle>/index.md`:

```markdown
# <Bundle title>

<One sentence: what this bundle holds.>

## Contents

<!-- okf:index -->
<!-- /okf:index -->
```

- The H1 and the first plain paragraph after it become the bundle description in `index` and `prime`.
- Write the same shape into every subdirectory, `<catalogue>/<bundle>/<subdir>/index.md`, before the first concept goes there. A directory without `index.md` never appears in any listing, and neither `check <bundle>` nor `reindex --check` reports the gap.
- Shortcut for a missing subdirectory index: `okf-cli --root <catalogue> reindex <bundle>/<subdir> --init`. It creates `index.md` with H1 = directory name, `## Contents` and the marker pair, but no intro line. Add the intro line by hand.
- Large bundle: also write `<catalogue>/<bundle>/INDEX-MAP.md` with an H1, an intro line and the marker pair. `reindex` fills it with the whole tree, and its H1 and intro then become the bundle description. Use this exact upper-case name: okf-cli looks up the description under it.
- Never put `type:` into an `index.md` or `INDEX-MAP.md`.

## 4. Vocabulary

Types: pick values from `info`. For a genuinely new type, add a row to `<catalogue>/TYPES.md`: ``| `NewType` | what it is for |``. An unregistered type is warning `kc/type/registered`.

Tags, when `TAGS.md` exists:

```bash
okf-cli --root <catalogue> tags <candidate> <candidate>
okf-cli --root <catalogue> tags --validate <tag> <tag>
okf-cli --root <catalogue> tags --register <tag> "<one-line description, max 150 characters>"
```

- `tags <candidate>` fuzzy-matches against the tags in use, with usage counts. Reuse a close hit.
- `tags --validate` exits 4 (non_conformant) and prints `UNKNOWN <tag>` for an unregistered tag.
- `tags --register` writes to `TAGS.md` at once, and creates the file when absent. Creating it closes the vocabulary for the whole catalogue, so do that only with the user's agreement. Repeat `--register <tag> "<description>"` for several tags. A stderr line `warning: auto-embed skipped` (no local embedding service) is harmless.

## 5. First concept

Write `<catalogue>/<bundle>/<subdir>/<slug>.md`. Full rules: write-concepts.md. Minimal valid concept:

```markdown
---
type: Concept
title: "<Title>"
description: "<One sentence.>"
tags:
  - <registered tag>
generated: { by: <actor>, at: <UTC now> }
---

# <Title>

<Body. Link the bundle index as [<Bundle title>](/<bundle>/index.md).>
```

- `<actor>`: your own `<agent>/<model>` identifier when you wrote the text; `human:<id>` only for a named person who wrote it.
- `<UTC now>`: the output of `date -u +%Y-%m-%dT%H:%M:%SZ`.
- Link only to files that exist; a link to a missing file is warning `kc/link/crosslink-format`.

## 6. Generate the listings

```bash
okf-cli --root <catalogue> reindex <bundle> --check
okf-cli --root <catalogue> reindex <bundle>
```

- `--check` prints `STALE <path>` for listings that would change, and exits 5 (drift) while any are stale.
- The write run prints `updated <path>` per changed `index.md` and ends `reindex: <n> updated, 0 skipped`.
- `skipped (no markers) <path>` names an `index.md` without the marker pair. Add the pair, or run `reindex <bundle> --init`.

## 7. Verify

```bash
okf-cli --root <catalogue> check <bundle>
okf-cli --root <catalogue> reindex <bundle> --check
okf-cli --root <catalogue> index
okf-cli --root <catalogue> build-index
okf-cli --root <catalogue> find "<words from the concept title>"
```

Done when all hold:

- `check` ends `OK — 0 violations` and shows no `kc/asset/entry-file-description` warning.
- `reindex --check` reports `0 stale, 0 uncovered`.
- `index` lists `<bundle>: <your description sentence>`.
- `find` returns the concept as `rank: 1` or close to it.

Any criterion fails: fix it (see "Failure modes"), then rerun steps 6 and 7 until all hold.

## 8. Commit, only when the user asked

Needs git (`git --version`). Stage explicit paths only:

```bash
git -C <catalogue> add <bundle>/index.md <bundle>/<subdir>/index.md <bundle>/<subdir>/<slug>.md
git -C <catalogue> commit -m "Add bundle <bundle>"
```

Add `TYPES.md`, `TAGS.md`, `.okf.toml` and `.gitignore` when you created or changed them. Never push.

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| stderr `note: --root ... carries no catalogue marker` | `--root` is not the catalogue root, often the bundle directory itself; `check` then misses files | Point `--root` at the directory that contains the bundle. New catalogue: add `.okf.toml` |
| `WARNING kc/asset/entry-file-description <bundle>` | Bundle `index.md` lacks the H1 or the intro paragraph | Add `# Title` and one plain sentence under it |
| Concept missing from every listing, `check` clean | Its directory has no `index.md` with markers | Create it (step 3), then `reindex <bundle>` |
| New subdirectory missing from the bundle listing | Only the subdirectory was reindexed | `reindex <bundle>` (the parent lists subdirectories that carry an `index.md`) |
| `skipped (no markers)` | `index.md` without the marker pair | Add the pair, or `reindex <bundle> --init` |
| `ERROR kc/asset/placement` | Non-markdown file outside `assets/` | Move it to `<bundle>/assets/` and link it there |
| `ERROR okf/type/reserved-no-type` | An `index.md` carries `type:` | Remove the `type` key |
| `WARNING kc/link/crosslink-format ... not resolving from root` | Link target does not exist | Point the link at an existing file |
| `find` misses the new concept; stderr `lexical index is stale` | Search index built before the write | `build-index`, then `find` again |
| `find` covers only one bundle | `.okf.toml` holds a `bundle = "..."` key | Remove the key from a shared catalogue |
