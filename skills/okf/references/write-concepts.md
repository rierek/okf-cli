# Write or update a concept

Goal: one concept that states one idea, carries valid frontmatter, links in catalogue-root-absolute form, appears in its directory listing and passes `check`. This file is also the reference for every frontmatter field, including the OKF v0.2 provenance fields.

## Contents

- Checklist
- 1. Look before writing
- 2. One idea per concept
- 3. Path and file name
- 4. Frontmatter
- 5. Body
- 6. Update an existing concept
- 7. Share canonical text: canon blocks
- 8. Finish and verify
- Failure modes

## Checklist

Copy into your task list (todo tool or scratch list), tick one by one. Step 6 applies only to updates, step 7 only to canon blocks:

- [ ] 1. Look before writing -> done when `find` on a current index shows no concept with the same idea, or you chose the one to update -> on failure (stderr `lexical index is stale`): `build-index`, rerun step 1
- [ ] 2. One idea -> done when title and description state exactly one idea -> otherwise split it and run steps 3 to 5 per concept
- [ ] 3. Path -> done when the slug is kebab-case, not reserved, and the directory has an `index.md` with markers -> on failure: fix the name or create the index, recheck step 3
- [ ] 4. Frontmatter -> done when `type` is registered, `description` is one sentence, `generated` names the real author and quoted values parse -> on failure: fix, recheck step 4
- [ ] 5. Body -> done when every concept link uses the `/<bundle>/...` form and its target exists -> on failure: fix the links, recheck step 5
- [ ] 6. Update only -> done when new facts are merged into the existing structure and `generated` is current -> on failure: back to step 4
- [ ] 7. Canon blocks only -> done when `sync-status` reports every block `synced` -> on failure: act per the state table in section 7, rerun `sync-status`
- [ ] 8. Finish and verify -> done when every criterion in section 8 holds -> on failure: back to step 4 (frontmatter) or 5 (links), rerun step 8 until clean

## 1. Look before writing

```bash
okf-cli --root <catalogue> find "<topic words>"
okf-cli --root <catalogue> toc <bundle>/<concept-id>
okf-cli --root <catalogue> info
```

- An on-topic concept exists: update it (section 6). Never create a near-duplicate.
- A neighbouring concept covers a second idea: link to it instead of restating it.
- `info` prints the valid `type` values (`TYPES.md`) and the documented frontmatter properties (`PROPERTIES.md`).
- `find` searches the last built index. stderr `lexical index is stale`: run `build-index` first, else recent concepts are missing.

## 2. One idea per concept

- The title names the idea. The description states it in one sentence.
- Split a source that covers several independent ideas into several concepts that link each other.
- Text that another concept owns: link to it, or insert a consumer copy (section 7). Never copy-paste it.

## 3. Path and file name

- Path: `<catalogue>/<bundle>/<subdir>/<slug>.md`. Concept-id: `<subdir>/<slug>`. Commands address it as `<bundle>/<subdir>/<slug>`.
- Slug: English, lowercase kebab-case, named after the meaning, no numeric prefixes.
- Forbidden characters in file names: `# ^ [ ] | \ : ? * " < > %` (error `filename-chars`).
- Never use a reserved name, in any letter case: `index.md`, `INDEX-MAP.md`, `log.md`, `readme.md`.
- The directory needs an `index.md` with the `<!-- okf:index -->` marker pair, otherwise the concept appears in no listing. Missing: `okf-cli --root <catalogue> reindex <bundle>/<subdir> --init`, then add an intro line under its H1.

## 4. Frontmatter

```yaml
---
type: Decision
title: "<Title>"
description: "<One sentence.>"
tags:
  - <registered tag>
generated: { by: <actor>, at: <UTC now> }
sources:
  - id: <source-id>
    resource: <URL or path of the material>
    title: <Source title>
---
```

| Key | Rule |
|---|---|
| `type` | Required and non-empty (error `type-nonempty`). A value from `TYPES.md`, else warning `type-registered`. |
| `title` | Display name. Feeds listings and search. |
| `description` | One sentence. Becomes the listing line and the search snippet. Never leave it empty. |
| `tags` | YAML block list; inline `[a, b]` is warning `tags-block-form`. When `TAGS.md` exists: `tags <candidate>` to find an existing tag, `tags --validate <tag>`, and `tags --register <tag> "<description>"` only for a new tag that will be reused. |
| `generated` | `{ by: <actor>, at: <time> }`, `by` required. Set on creation and on every meaningful content change. `<UTC now>`: output of `date -u +%Y-%m-%dT%H:%M:%SZ`. |
| `sources` | One entry per material the content derives from. `resource` is required (URL, path, or a scope description such as "all queries in project X"); `id` when the body cites the source; optional `title`, `author`, `usage_count`, `last_modified`; a sibling key `usage_window: { from, to }` frames `usage_count`. Cite a claim with a footnote whose label is the id: `[^<source-id>]`. |
| `status` | `draft`, `stable` (the default when absent) or `deprecated`. |
| `verified` | Only for a real confirmation against the sources: `{ by: <actor>, at: <time> }`, or a list of such entries. Writing a concept is not verifying it. Trust tier: none = unverified, only non-human actors = machine-confirmed, any `human:` actor = human-reviewed. |
| `stale_after` | Absolute time from which the content counts as stale, for example `2027-01-31T00:00:00Z`. Only for content that expires. |
| `superseded_by` | Only on `type: Decision`: catalogue-root-absolute path of the replacing decision, for example `/<bundle>/decisions/<new>.md`. Must resolve (error `superseded-by-resolves`); on another type it is warning `superseded-by-scope`. |

- Actors: your own `<agent>/<model>` identifier for text you wrote; `human:<id>` only for a named person who wrote or confirmed it; `process:<id>` for an automated job. Never fill in a person you have not been told about.
- Times: ISO 8601 with an explicit offset, `Z` or `+02:00`.
- Keys are English. Warning `english-keys` flags a fixed list of non-English key names.
- Extra keys are allowed and kept.
- YAML: quote values that contain `: ` or ` #`, or that start with `[`, `{`, `*`, `&`, `!`, `|`, `>`, `'`, `"`, `%`, `@` or a backtick. `check` verifies only the `---` delimiters, not YAML syntax: a broken value passes `check` and breaks other OKF readers.

## 5. Body

- Start with `# <Title>`. Prefer headings, lists, tables and code fences over long prose.
- Link concepts as `[Text](/<bundle>/<subdir>/<concept>.md)`. The leading `/` is the catalogue root, so the same form works across bundles. Relative links are warning `crosslink-format`; `okf-cli --root <catalogue> fix-crosslinks <bundle>` converts every relative link whose target exists.
- External links stay full URLs.
- Wrap placeholders such as `<name>` in backticks. Bare ones are warning `xml-like-tags`; `okf-cli --root <catalogue> fix-xml-tags <bundle>` wraps them.
- Non-markdown files go to `<bundle>/assets/`; anywhere else they are error `asset-placement`.
- Follow the body language of the bundle. Frontmatter keys stay English.

## 6. Update an existing concept

1. `okf-cli --root <catalogue> read <bundle>/<concept-id>`
2. Edit the file in place. Merge new facts into the existing structure; do not append a second copy of a section.
3. Content changed meaningfully: set `generated` to your actor and the current time. Keep existing `verified` entries; add one only after a real re-check.
4. New file name or bundle: never `mv`. Preview with `okf-cli --root <catalogue> rename <bundle>/<old>.md <bundle>/<new>.md`, then repeat with `--apply`; it rewrites every inbound link and reindexes.
5. Content no longer current: `status: deprecated` keeps it in place for inbound links; `okf-cli --root <catalogue> archive <bundle>/<concept-id>.md --apply` (after the preview without `--apply`) removes it from default search.

## 7. Share canonical text: canon blocks

Use a canon block when several concepts need the same normative text and exactly one concept, the canon owner, holds it.

Canon owner, inside its body:

```markdown
<!-- okf:canon id=<block-id> -->
The canonical text.
<!-- /okf:canon -->
```

`<block-id>`: letters, digits, `.`, `_`, `-`. Unique within the canon owner; an unclosed or duplicated block is error `canon-block`.

Consumer copy:

```bash
okf-cli --root <catalogue> sync-export <owner-bundle>/<owner-id> <block-id>
okf-cli --root <catalogue> sync-insert <consumer-bundle>/<consumer-id> <owner-bundle>/<owner-id> <block-id>
okf-cli --root <catalogue> sync-insert <consumer-bundle>/<consumer-id> <owner-bundle>/<owner-id> <block-id> --apply
```

- `sync-export` prints the payload and writes nothing.
- `sync-insert` previews by default. Run it without `--apply` first and read the preview (hard rule 5); only then repeat it with `--apply`, which appends the consumer copy to the end of the consumer body: an `<!-- okf:sync id=... source=... hash=... -->` line, a generated attribution callout (the CLI writes it in German; leave it unchanged), `<!-- okf:sync-body -->`, the payload, `<!-- /okf:sync -->`. You may move the whole copy within the body. Never edit its content.
- `sync-insert` refuses an unknown block id and a block the consumer already holds.

Keep consumer copies current:

```bash
okf-cli --root <catalogue> sync-status
okf-cli --root <catalogue> sync-status --source /<owner-bundle>/<owner-id>.md
okf-cli --root <catalogue> sync-update
okf-cli --root <catalogue> sync-update --apply
```

`sync-status` exits 1 unless every block is `synced`; `--source` lists the consumers of one canon owner. `sync-update` previews; `--apply` rewrites outdated consumer copies.

| State | Meaning | `check` | Action |
|---|---|---|---|
| `synced` | Consumer copy equals the canon block | none | None |
| `source-changed` | Canon owner changed, consumer copy untouched | warning `sync-stale` | `sync-update --apply` |
| `consumer-modified` | Consumer copy edited by hand | error `sync-block` | Move the wanted change into the canon owner, then `sync-update --apply --force` (discards the local edit) |
| `both-changed` | Canon block and consumer copy both changed | error `sync-block` | Same as `consumer-modified` |
| `source-missing` | Canon owner or block id gone | error `sync-block` | Restore the canon block, or delete the whole consumer copy by hand |
| `malformed` | Marker set unreadable, or `source` not catalogue-root-absolute | error `sync-block` | Delete the whole consumer copy by hand, then `sync-insert` again |

`sync-update` refuses `consumer-modified` and `both-changed` without `--force`, and never writes `source-missing` or `malformed`. `rename` and `archive` of a canon owner rewrite the `source=` of every consumer copy.

## 8. Finish and verify

```bash
okf-cli --root <catalogue> reindex <bundle>
okf-cli --root <catalogue> check <bundle>
okf-cli --root <catalogue> build-index --if-stale
okf-cli --root <catalogue> find "<words from the title>"
okf-cli --root <catalogue> read <bundle>/<concept-id>
```

Done when `reindex` lists the concept's `index.md` as `updated` (or reports no change for an edit that kept title and description), `check` ends `OK — 0 violations`, `find` returns the concept and `read` shows the frontmatter. A criterion fails: fix it, then rerun this step until clean.

Commit only when the user asked: the concept, the regenerated `index.md` files and any changed `TYPES.md` or `TAGS.md`, with explicit paths.

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `ERROR type-nonempty` | `type` missing or empty | Set a registered type |
| `ERROR frontmatter-parseable` | File does not start with a `---` block closed by `---` | Add the frontmatter block |
| `ERROR filename-chars` | Forbidden character in the file name | `rename` to a kebab-case slug |
| `WARNING crosslink-format ... non catalogue-absolute link(s)` | Relative link | `fix-crosslinks <bundle>` |
| `WARNING crosslink-format ... not resolving from root` | `/`-link to a missing file, or bundle-relative form without the bundle name | Correct the path to `/<bundle>/...` by hand |
| `WARNING tag-registered` | Tag not in `TAGS.md` | Reuse an existing tag, or `tags --register` |
| Listing shows the old title or description | `reindex` not run after the edit | `reindex <bundle>` |
| Another OKF reader rejects the file while `check` passes | Invalid YAML, for example an unquoted `: ` inside a value | Quote the value |
| `find` does not return the new concept | Stale search index | `build-index`, then `find` |
| `sync-update` prints `refused` | Consumer copy was edited by hand | Section 7, `consumer-modified` row |
