# Maintain a catalogue

Ongoing care of an existing catalogue. Every command takes `--root <catalogue>`. `<target>` means `<bundle>` or `<bundle>/<subdir>`; omitted, the command covers the whole catalogue.

## Contents

- 1. Orient
- 2. Retrieve
- 3. Conformance: check
- 4. Listings: reindex
- 5. Search indexes
- 6. Tags
- 7. Rename or move a concept
- 8. Move, rename or merge a directory or bundle
- 9. Archive and restore
- 10. Links
- 11. Placeholders
- 12. Stale content
- 13. Graph view
- 14. Health routine (checklist)
- Failure modes

## 1. Orient

```bash
okf-cli --root <catalogue> prime
okf-cli --root <catalogue> index --full
okf-cli --root <catalogue> info
okf-cli --root <catalogue> recent --limit 20
```

- `prime`: usage guide, command list, catalogue state and bundle list. `--compact` for a short form, `--full` adds types and tags per bundle, `--check-semantic` counts semantic index coverage exactly.
- `index`: one line per bundle. `index <bundle>` prints its `index.md`; `--full` prints description, concept count, directories, types and tags.
- `info`: `TYPES.md` and `PROPERTIES.md`.
- `recent`: newest concepts first, dated by the git commit that added them. Needs git (else exit 1); uncommitted concepts appear undated at the end.
- `--json` exists on `index`, `list`, `recent`, `refs`, `wikilinks`, `check` and `sync-status`.

## 2. Retrieve

```bash
okf-cli --root <catalogue> find "<query>" --scope <target> --type <Type> --tag <tag> --limit 10
okf-cli --root <catalogue> list --type <Type> --scope <target>
okf-cli --root <catalogue> toc <bundle>/<concept-id> --level 0
okf-cli --root <catalogue> read <bundle>/<concept-id>
okf-cli --root <catalogue> refs <bundle>/<concept-id>.md
okf-cli --root <catalogue> wikilinks <target> --unresolved
```

- `find`: ranked search over two arms, a lexical index (FTS5/BM25) and an optional semantic index. `rank: N` is the list position; `provenance:` names the arm. `--breakdown` adds raw `score:` and `contrib:` lines. `--include-archive` also searches `_archive/` (lexical arm only). Filters are exact matches. Quote multi-word queries. With a semantic index and `VOYAGE_API_KEY` set, the query goes to Voyage AI (section 5).
- `list`: complete, unranked set. Requires `--type` and/or `--tag`; `--scope` and `--include-archive` optional.
- `toc`: headings, default h2 only; `--level 0` prints the full tree. A bare `<bundle>` resolves to its `index.md`.
- `refs`: inbound and outbound markdown links of one file. Give the path with `.md`, relative to `--root`. `--in` or `--out` limits the direction.
- A result with a `superseded_by:` line is an outdated decision: read the target.
- Report "not in the catalogue" only with the query, the scope and the index state (`prime`).

## 3. Conformance: check

```bash
okf-cli --root <catalogue> check <target>
okf-cli --root <catalogue> check <target> --strict
okf-cli --root <catalogue> check <target> --json
okf-cli --root <catalogue> check <target> --types <path to TYPES.md>
```

Output: one `ERROR` or `WARNING` line per finding, then `OK — 0 violations` or `<n> VIOLATIONS` (errors only). Exit 1 on any error. `--strict` turns warnings into errors. `--types` overrides the type vocabulary source. A target that is not a directory fails with `not a directory`. Fix the findings, then rerun `check` until it is clean.

| Rule | Severity | Trigger | Fix |
|---|---|---|---|
| `frontmatter-parseable` | error | Non-reserved `.md` without a `---` block | Add frontmatter |
| `type-nonempty` | error | `type` missing or empty | Set a type |
| `reserved-no-type` | error | `index.md`, `INDEX-MAP.md`, `log.md` or `readme.md` (any letter case) carries `type` | Remove `type` |
| `filename-chars` | error | `# ^ [ ] \| \ : ? * " < > %` in a file name | `rename` |
| `asset-placement` | error | Non-markdown file outside `<bundle>/assets/` | Move it into `assets/` |
| `superseded-by-resolves` | error | `superseded_by` target missing | Fix the path |
| `sync-block` | error | Consumer copy edited, orphaned or malformed | `sync-status` names the state. Edited: move the change into the canon owner, then `sync-update --apply --force`. Owner gone or markers broken: delete the whole consumer copy, then `sync-insert` again |
| `canon-block` | error | Unclosed `okf:canon` block or duplicate block id | Fix the canon owner markers |
| `ctx` | error, warning | Problems in `_ctx/*.md` | `ctx check` |
| `type-registered` | warning | Type not in `TYPES.md` (only when `TYPES.md` exists) | Register it or change the type |
| `tag-registered` | warning | Tag not in `TAGS.md` (only when `TAGS.md` exists) | Section 6 |
| `english-keys` | warning | Non-English frontmatter key from a fixed list | Rename the key |
| `crosslink-format` | warning | Relative `.md` link, or `/`-link not resolving from the catalogue root | `fix-crosslinks`; fix the rest by hand |
| `superseded-by-scope` | warning | `superseded_by` on a non-Decision | Remove it or change the type |
| `tags-block-form` | warning | Inline `tags: [a, b]` | `normalize-tags --apply` |
| `xml-like-tags` | warning | Bare `<placeholder>` outside code | `fix-xml-tags` |
| `wikilink-resolvable` | warning | Unresolved or ambiguous `[[...]]`; only for bundles listed in `.okf.toml` `wikilink_checked_bundles = ["<bundle>"]` | Fix the link |
| `sync-stale` | warning | Canon owner changed | `sync-update --apply` |
| `entry-file-description` | warning | Bundle entry file (`INDEX-MAP.md`, else `index.md`) without H1 or intro paragraph | Add them |

Limits: `check` does not parse YAML (only the delimiters), does not see wikilinks unless opted in, does not report directories without `index.md`, and does not validate OKF v0.2 fields (`sources`, `generated`, `verified`, `status`, `stale_after`). `crosslink-format` skips bundles that are symlinks.

## 4. Listings: reindex

```bash
okf-cli --root <catalogue> reindex <target> --check
okf-cli --root <catalogue> reindex <target>
okf-cli --root <catalogue> reindex <target> --init --check
okf-cli --root <catalogue> reindex <target> --init
```

- `reindex` rewrites the block between `<!-- okf:index -->` and `<!-- /okf:index -->` in every `index.md` (one level) and `INDEX-MAP.md` (whole subtree) under the target, from each concept's `title` and `description`. Subdirectories are listed only when they carry an `index.md`.
- `--check` writes nothing, prints `STALE` and `UNCOVERED` paths, and exits 1 when any exist. `UNCOVERED` = an `index.md` without markers in a directory that holds concepts.
- `--init` creates a missing `index.md` for the named target and converts marker-less `index.md` files in the subtree that hold a single bullet-list section. It replaces that hand-written list with an empty marker block, then the normal run fills it. Multi-section indexes are skipped and flagged; `--force` also flattens pure heading-and-bullet multi-section lists. Preview with `--init --check`.
- A deliberately hand-curated `index.md` stays out of `UNCOVERED` when it contains `<!-- okf:index-exempt -->`.
- Run `reindex <bundle>` after adding, renaming or retitling a concept, and after creating a subdirectory.

## 5. Search indexes

```bash
okf-cli --root <catalogue> build-index --if-stale
okf-cli --root <catalogue> build-semantic-index --if-stale
okf-cli --root <catalogue> prime --check-semantic
```

- Lexical index: `<catalogue>/.fts/fts.sqlite`, local, no network. Without it `find` falls back to a substring scan. When stale, `find` prints `note: lexical index is stale` on stderr and misses recent changes. Rebuild after every batch of writes. `--if-stale` skips a rebuild when current.
- Semantic index (optional): `<catalogue>/.tagvec/tag_vectors.sqlite`. Building it sends the title and body of every concept to the Voyage AI API, and afterwards `find` sends each query there. Ask the user before the first build and before searching a catalogue that has one. Without consent, prefix commands with an empty key, for example `VOYAGE_API_KEY= okf-cli --root <catalogue> find "<query>"`.
- Without a key, `build-semantic-index` prints `note: semantic index build skipped (VOYAGE_API_KEY not set)` and builds nothing. It embeds only missing or changed concepts, so after an interruption run the same command again. `--if-stale` skips when every concept is embedded.
- `prime --check-semantic` prints `semantic index: complete`, `partial` or `absent`.
- A miss in `find` is a coverage question first: check both index states in `prime` before blaming the ranking.
- In git catalogues, list `.fts/` and `.tagvec/` in `.gitignore`.

## 6. Tags

```bash
okf-cli --root <catalogue> tags
okf-cli --root <catalogue> tags --singletons
okf-cli --root <catalogue> tags <candidate> <candidate>
okf-cli --root <catalogue> tags --validate <tag> <tag>
okf-cli --root <catalogue> tags --register <tag> "<description>"
okf-cli --root <catalogue> merge-tags <old> <old2> --into <new> --scope <target>
okf-cli --root <catalogue> remove-tags <tag> --scope <target>
okf-cli --root <catalogue> normalize-tags --scope <target>
```

- `tags`: every tag in use with its count. `--singletons`: tags used once, the merge candidates.
- `tags <candidate>`: fuzzy search against the tags in use, `--limit` per candidate (default 8).
- `TAGS.md` present = closed vocabulary. `--validate` exits 1 and prints `UNKNOWN <tag>` for unregistered tags; without `TAGS.md` it prints `(no TAGS.md — closed vocabulary not enabled)`.
- `--register <tag> "<description>"` writes to `TAGS.md` at once, no preview (description required, one line, at most 150 characters, no `|`); repeat the option for several tags. It also tries a local embedding service; a stderr `warning: auto-embed skipped` is harmless.
- `merge-tags`, `remove-tags` and `normalize-tags` preview; add `--apply` to write. `normalize-tags` converts inline `tags: [a, b]` to a block list.
- After merging or removing, delete the obsolete rows from `TAGS.md` by hand, then run `check`.

## 7. Rename or move a concept

```bash
okf-cli --root <catalogue> refs <bundle>/<old>.md
okf-cli --root <catalogue> wikilinks <bundle>
okf-cli --root <catalogue> rename <bundle>/<old>.md <bundle2>/<new>.md
okf-cli --root <catalogue> rename <bundle>/<old>.md <bundle2>/<new>.md --apply
okf-cli --root <catalogue> check
```

- Both paths must be `.md` concept files under the catalogue root. The destination may be in another bundle; missing directories are created, but their `index.md` is not (create it first).
- `rename` moves the file, rewrites every inbound markdown link, every unambiguous wikilink, ctx entries and canon `source=` attributes, rewrites the file's own outbound links on a bundle change, and reindexes the affected bundles.
- The preview counts inbound, outbound and wikilink rewrites and `skipped-ambiguous` wikilinks. Read it before `--apply`.
- It uses `git mv` and stages the move. Outside git it moves the file and prints `untracked — git declined`.
- `--force` overwrites an existing destination and proceeds when wikilinks would turn ambiguous.
- A source under `_archive/` is refused: use `archive --restore`.

## 8. Move, rename or merge a directory or bundle

`rename` moves single concept files only. Move a directory one concept at a time, so every link, ctx entry and consumer copy follows:

1. Create the destination directory with `mkdir -p <catalogue>/<new-bundle>/<new-dir>` and write its `index.md` (H1, intro sentence, `## Contents`, marker pair). A new bundle also needs `<catalogue>/<new-bundle>/index.md` in the same shape.
2. Record hand-written links to the old listing: `okf-cli --root <catalogue> refs <bundle>/<old-dir>/index.md --in`. Hits from generated listings disappear by themselves.
3. List the files with `ls <catalogue>/<bundle>/<old-dir>`. For each concept except `index.md`, preview, then apply:

   ```bash
   okf-cli --root <catalogue> rename <bundle>/<old-dir>/<concept>.md <new-bundle>/<new-dir>/<concept>.md
   okf-cli --root <catalogue> rename <bundle>/<old-dir>/<concept>.md <new-bundle>/<new-dir>/<concept>.md --apply
   ```

   A nested directory: run steps 1 to 4 for it first.
4. Only `index.md` is left: delete it and the directory. Git catalogue: `git -C <catalogue> rm -f <bundle>/<old-dir>/index.md` (`-f` because `rename` already rewrote its listing). Otherwise: `rm <catalogue>/<bundle>/<old-dir>/index.md`, then `rmdir <catalogue>/<bundle>/<old-dir>`. A listing file is not a concept, so hard rule 4 does not apply.
5. For each link from step 2: `okf-cli --root <catalogue> rewrite-path "/<bundle>/<old-dir>/index.md" "/<new-bundle>/<new-dir>/index.md" --check`, then the same without `--check`.
6. `okf-cli --root <catalogue> reindex <bundle>` and `okf-cli --root <catalogue> reindex <new-bundle>`.
7. Verify with `check`, `reindex <new-bundle> --check`, `fix-crosslinks --check`, `wikilinks --unresolved` and `ctx check`. Done when all are clean; otherwise fix and rerun step 7.

- Rename a bundle: move every directory and every root concept of `<bundle>` into `<new-bundle>` this way, then delete `<bundle>/index.md` (and `INDEX-MAP.md`) and the empty directory as in step 4.
- Merge bundle A into bundle B: the same with B as destination. First compare the file names of both: `rename` refuses an existing destination without `--force`.

## 9. Archive and restore

```bash
okf-cli --root <catalogue> archive <bundle>/<concept-id>.md
okf-cli --root <catalogue> archive <bundle>/<concept-id>.md --apply
okf-cli --root <catalogue> archive --restore _archive/<bundle>/<concept-id>.md --apply
```

- `archive` moves the concept to `_archive/<bundle>/<concept-id>.md`, rewrites inbound links to the new path and reindexes. The report starts with the number of active concepts that still link to it.
- Archived concepts are hidden from `find` and `list` unless `--include-archive`; the semantic arm never covers them. `check` and `index` skip `_archive/`.
- A ctx entry that now points into `_archive/` gives a `ctx` warning: drop or replace it.
- `--restore` reverses the move and the link rewrites. One concept per call.

## 10. Links

```bash
okf-cli --root <catalogue> fix-crosslinks <target> --check
okf-cli --root <catalogue> fix-crosslinks <target>
okf-cli --root <catalogue> fix-crosslinks <target> --include-reserved
okf-cli --root <catalogue> wikilinks <target> --unresolved
okf-cli --root <catalogue> rewrite-path "<old path>" "<new path>" --check
okf-cli --root <catalogue> rewrite-path "<old path>" "<new path>"
```

- `fix-crosslinks` rewrites links to the `/<bundle>/<subdir>/<concept>.md` form when the target exists, and reports the rest as `unresolved` without guessing. Repair those by hand. Reserved files are skipped unless `--include-reserved`, which rewrites their prose but never the generated block.
- `wikilinks` reports `[[...]]` links as `resolved`, `ambiguous` or `unresolved`. `refs` never sees wikilinks and `check` only for opted-in bundles; run `wikilinks` before renaming a concept that wikilinks may target.
- `rewrite-path` replaces a literal string in `.md`, code and config files under `--scan-root <dir>` (default `--root`). It matches only where the string is not glued to letters, digits, `_`, `.`, `/` or `-`, so `../<old>` does not match `<old>`, and a directory prefix such as `/<bundle>/` matches nothing. It skips `.git`, `node_modules` and dot-directories, resolves nothing and does not reindex. For catalogue links pass the `/`-prefixed form (`/<bundle>/<old>.md`); `<bundle>/<old>.md` does not match inside it. Use it for mentions that `rename` cannot reach.

## 11. Placeholders

```bash
okf-cli --root <catalogue> fix-xml-tags <target> --check
okf-cli --root <catalogue> fix-xml-tags <target>
```

Wraps bare `<tag>` and `<tag>.<tag2>` placeholders outside code in backticks (warning `xml-like-tags`).

## 12. Stale content

okf-cli has no staleness report: `check` ignores `stale_after` and `status`. List them with POSIX tools and compare each `stale_after` with the current UTC time; a concept is stale when now is at or past that instant:

```bash
grep -rn --include='*.md' '^stale_after:' <catalogue>/<bundle>
grep -rln --include='*.md' '^status: deprecated' <catalogue>/<bundle>
date -u +%Y-%m-%dT%H:%M:%SZ
```

Re-check a stale concept against its `sources` with the user, then update `generated`, `verified` (only for a real check) and `stale_after` per write-concepts.md, or set `status: deprecated`.

## 13. Graph view

```bash
okf-cli --root <catalogue> visualize <bundle> --out <path outside the catalogue>.html
```

Writes a concept graph that embeds the body of every concept, at once and without preview. The default path `<bundle>/assets/viz.html` puts that copy inside the bundle, where it gets committed or published: always pass `--out` with a path outside the catalogue. Opening the file loads scripts from public CDNs.

## 14. Health routine (checklist)

Run periodically and before a release of the catalogue. Copy into your task list (todo tool or scratch list), tick one by one:

- [ ] `okf-cli --root <catalogue> check --strict` -> done when `OK — 0 violations` -> on failure: fix per section 3, rerun
- [ ] `okf-cli --root <catalogue> reindex <bundle> --check`, per bundle -> done when it reports `0 stale, 0 uncovered` -> on failure: `reindex <bundle>` (stale) or add the marker pair (uncovered), rerun
- [ ] `okf-cli --root <catalogue> fix-crosslinks --check` -> done when `0 file(s) would rewrite, 0 unresolved link(s)` -> on failure: run it without `--check`, repair unresolved links by hand, rerun
- [ ] `okf-cli --root <catalogue> wikilinks --unresolved` -> done when `0 ambiguous, 0 unresolved` -> on failure: fix the links, rerun
- [ ] `okf-cli --root <catalogue> sync-status` -> done when exit 0 -> on failure: section 3, `sync-block` and `sync-stale` rows, rerun
- [ ] `okf-cli --root <catalogue> ctx check --stale` -> done when `OK — 0 violations` and every stale warning is reviewed -> on failure: context-bundles.md failure modes, rerun
- [ ] `okf-cli --root <catalogue> tags --singletons` -> done when each listed tag is merged or kept on purpose
- [ ] Stale content (section 12) -> done when every past `stale_after` is reported to the user
- [ ] `okf-cli --root <catalogue> build-index --if-stale` -> done when it prints `indexed` or `index is current`

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `find` returns nothing for an existing concept | Stale or missing lexical index, or concept archived | `build-index`; add `--include-archive` |
| `list` prints `(error: pass --type and/or --tag)` | `list` needs a filter | Add `--type` or `--tag`, or use `find` |
| `refs: target not found` | Path without `.md`, or not relative to `--root` | Pass `<bundle>/<concept-id>.md` |
| `refs --scan-root <dir>` marks existing targets `[missing]` | With `--scan-root`, `/`-links resolve against that directory | Read only inbound links from outside the catalogue; run `refs` without `--scan-root` for the rest |
| `recent: catalogue root is not a git repository` | `recent` dates concepts from git | Use `list` or `find` |
| `rename: both paths must live under the catalogue root` | Source or destination outside `--root` | Move outside files with `git mv`, then fix links with `rewrite-path` |
| `rename: source lies under _archive/` | Archived source | `archive --restore` |
| `rename: destination exists (use --force to overwrite)` | Target file exists | Choose another name, or `--force` once the user confirms the overwrite |
| Moved file not in the catalogue `git status` | Bundle is a symlink into another repository | Commit in `git -C <catalogue>/<bundle> rev-parse --show-toplevel` |
| `check` clean but links broken in Obsidian | Wikilinks are invisible to `check` | `wikilinks --unresolved`, or opt in via `wikilink_checked_bundles` |
| Unscoped `check` reports directories that are not knowledge | Every top-level directory not starting with `.` or `_` is a bundle | Scope `check <bundle>`, or prefix scratch directories with `_` |
