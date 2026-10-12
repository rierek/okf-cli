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
okf --root <catalogue> prime
okf --root <catalogue> index --full
okf --root <catalogue> info
okf --root <catalogue> recent --limit 20
```

- `prime`: usage guide, command list, catalogue state and bundle list. `--compact` for a short form, `--full` adds types and tags per bundle, `--check-semantic` counts semantic index coverage exactly.
- `index`: one line per bundle. `index <bundle>` prints its `index.md`; `--full` prints description, concept count, directories, types and tags.
- `info`: `TYPES.md` and `PROPERTIES.md`.
- `recent`: newest concepts first, dated by the git commit that added them. Needs git (exit 1 when the git binary is missing, exit 2 when the catalogue root is no git repository); uncommitted concepts appear undated at the end.
- `--json` exists on every command and prints one line, the envelope `{command, ok, data, warnings, error}`, and nothing else on stdout. `data` is the result, `warnings` the notes that text mode prints as `note:` lines on stderr, `error` is `null` or `{kind, code, message}` with `code` equal to the exit code. A failure that has a result keeps it in `data` (`check` findings, `sync-status` rows, the candidates of an ambiguous `read --section`). Read success from `ok`.

## 2. Retrieve

```bash
okf --root <catalogue> find "<query>" --where "path ~ <target>/ and type = <Type> and tag = <tag>" --limit 10
okf --root <catalogue> list --where "type = <Type> and path ~ <target>/"
okf --root <catalogue> toc <bundle>/<concept-id> --level 0
okf --root <catalogue> read <bundle>/<concept-id>
okf --root <catalogue> refs <bundle>/<concept-id>.md
okf --root <catalogue> wikilinks <target> --unresolved
```

- `find`: ranked search over two arms, a lexical index (FTS5/BM25) and an optional semantic index. `rank: N` is the list position; `provenance:` names the arm. `--breakdown` adds raw `score:` and `contrib:` lines. `--where` filters; `archived in (true, false)` in it also searches `_archive/` (lexical arm only). Quote multi-word queries. With a semantic index and `VOYAGE_API_KEY` set, the query goes to Voyage AI (section 5).
- `list`: complete, unranked set. Requires `--where`.
- `--where "<expr>"` is the one filter on `find`, `list`, `recent`, `merge-tags`, `remove-tags` and `normalize-tags`: `field op value` with op one of `=` `!=` `<` `<=` `>` `>=` `~` (contains), or `field in (a, b)`, joined by `and`, `or`, `not` and parentheses. Fields: `type`, `tag`, `path` (`<bundle>/<concept-id>`), `archived` (`true` or `false`), `tier` (`unverified`, `machine-confirmed` or `human-reviewed`), `stale` (`true` or `false`), `status` (an absent status is `stable`) and any frontmatter key (nested: `a.b`; through lists: `verified.by`, `sources.resource`). The timestamp keys `generated.at`, `verified.at`, `stale_after`, `usage_window.from`/`to` and `sources.last_modified` compare as instants and take an ISO 8601 value with an explicit offset, for example `stale_after < 2026-10-01T00:00:00Z`; any other value is exit 2. Quote a value holding spaces or `+`: `'a b'`. A malformed expression exits with code 2.
- `toc`: headings, default h2 only; `--level 0` prints the full tree. A bare `<bundle>` resolves to its `index.md`.
- `refs`: inbound and outbound markdown links of one file. Give the path with `.md`, relative to `--root`. `--in` or `--out` limits the direction.
- A result with a `superseded_by:` line is an outdated decision: read the target.
- Report "not in the catalogue" only with the query, the scope and the index state (`prime`).

## 3. Conformance: check

```bash
okf --root <catalogue> check <target>
okf --root <catalogue> check <target> --strict
okf --root <catalogue> check <target> --json
okf --root <catalogue> check <target> --ignore 'kc/*' --ignore okf/frontmatter/parseable
okf --root <catalogue> check <target> --types <path to TYPES.md>
```

Output: one `ERROR` or `WARNING` line per finding, then `OK — 0 violations` or `<n> VIOLATIONS`; every line carries the rule ID of the table below. Only findings that count are numbered: an error always, a warning only under `--strict`. Exit 4 (non_conformant) when any finding counts. `--strict` counts warnings toward the exit code; every finding keeps its severity. `--json` prints the envelope, with the findings as `data.findings`, a list of `{rule, severity, path, message}`; a run with counting findings has `ok` false and `error.kind` `non_conformant`, and `data.findings` still lists them. `--ignore <pattern>` (repeatable) and the `.okf.toml` key `ignore_rules` (array of patterns) suppress rules: a pattern ending in `*` matches every rule ID with that prefix (`kc/*`, `okf/link/*`), any other pattern only the identical ID; a suppressed finding neither prints nor counts, with or without `--strict`. An `ignore_rules` that is not an array of strings suppresses nothing and prints a `note:` line on stderr (with `--json`: an entry of `warnings`). `--types` overrides the type vocabulary source. A target that is not a directory fails with `not a directory`. Fix the findings, then rerun `check` until it is clean.

| Rule | Severity | Trigger | Fix |
|---|---|---|---|
| `okf/frontmatter/parseable` | error | Non-reserved `.md` without a `---` block | Add frontmatter |
| `okf/frontmatter/type-nonempty` | error | `type` missing or empty | Set a type |
| `okf/type/reserved-no-type` | error | `index.md`, `INDEX-MAP.md`, `log.md` or `readme.md` (any letter case) carries `type` | Remove `type` |
| `kc/name/filename-chars` | error | `# ^ [ ] \| \ : ? * " < > %` in a file name | `rename` |
| `kc/asset/placement` | error | Non-markdown file outside `<bundle>/assets/` | Move it into `assets/` |
| `okf/provenance/sources-shape`, `okf/provenance/source-resource`, `okf/provenance/usage-window` | error | `sources` is not a list of mappings, an entry lacks a non-empty `resource`, or a `usage_window` is not a mapping with `from` and `to`; declaring bundles only | Fix the field |
| `okf/trust/generated`, `okf/trust/verified` | error | `generated` is not a mapping with a non-empty `by`; `verified` is not a mapping or list of mappings each with non-empty `by` and `at`; declaring bundles only | Fix the field |
| `okf/lifecycle/status` | error | `status` is not `draft`, `stable` or `deprecated`; declaring bundles only | Use one of the three |
| `okf/format/actor`, `okf/format/timestamp` | error | `generated.by` or `verified[].by` is not `<producer>/<version>`, `human:<id>` or `process:<id>`; a timestamp key is not an ISO 8601 datetime with an explicit UTC offset; declaring bundles only | Fix the value |
| `okf/computation/runtime` | error | Type `Attested Computation` without a non-empty `runtime`; declaring bundles only | Add `runtime` |
| `kc/supersede/resolves` | error | `superseded_by` target missing | Fix the path |
| `kc/sync/block` | error | Consumer copy edited, orphaned or malformed | `sync-status` names the state. Edited: move the change into the canon owner, then `sync-update --apply --force`. Owner gone or markers broken: delete the whole consumer copy, then `sync-insert` again |
| `kc/sync/canon-block` | error | Unclosed `okf:canon` block or duplicate block id | Fix the canon owner markers |
| `kc/ctx/type`, `kc/ctx/slug`, `kc/ctx/row-format`, `kc/ctx/mode`, `kc/ctx/required-positions`, `kc/ctx/reference-position`, `kc/ctx/duplicate-entry`, `kc/ctx/dead-entry` | error | One problem kind of a `_ctx/<slug>.md` file each | `ctx check` |
| `kc/ctx/empty-description`, `kc/ctx/archived-entry`, `kc/ctx/stale-entry` | warning | Empty description; entry under `_archive/`; member newer than the ctx file (only `ctx check --stale`) | `ctx check` |
| `kc/type/registered` | warning | Type not in `TYPES.md` (only when `TYPES.md` exists) | Register it or change the type |
| `kc/tag/registered` | warning | Tag not in `TAGS.md` (only when `TAGS.md` exists) | Section 6 |
| `kc/frontmatter/english-keys` | warning | Non-English frontmatter key from a fixed list | Rename the key |
| `kc/link/crosslink-format` | warning | Relative `.md` link, or `/`-link not resolving from the catalogue root | `fix-crosslinks`; fix the rest by hand |
| `kc/supersede/scope` | warning | `superseded_by` on a non-Decision | Remove it or change the type |
| `kc/frontmatter/tags-block-form` | warning | Inline `tags: [a, b]` | `normalize-tags --apply` |
| `kc/markup/xml-like-tags` | warning | Bare `<placeholder>` outside code | `fix-xml-tags` |
| `kc/link/wikilink-resolvable` | warning | Unresolved or ambiguous `[[...]]`; only for bundles listed in `.okf.toml` `wikilink_checked_bundles = ["<bundle>"]` | Fix the link |
| `kc/sync/stale` | warning | Canon owner changed | `sync-update --apply` |
| `kc/asset/entry-file-description` | warning | Bundle entry file (`INDEX-MAP.md`, else `index.md`) without H1 or intro paragraph | Add them |
| `okf/lifecycle/stale-after` | warning | `stale_after` has passed (compared as an instant against one UTC `now` per run); declaring bundles only | Re-check the concept, then set a new `stale_after` or `status: deprecated` |
| `okf/trust/drift` | warning | The body changed in a commit after `generated.at` that did not change `generated.at`; frontmatter-only commits and renames do not count; declaring bundles only; needs git, else one note | Regenerate or review the concept, then set a new `generated.at` |

Limits: `check` does not parse YAML (only the delimiters), does not see wikilinks unless opted in, does not report directories without `index.md`, and reports the OKF v0.2 rules (`okf/provenance/*`, `okf/trust/*`, `okf/lifecycle/*`, `okf/format/*`, `okf/computation/*`) only in a bundle whose root `index.md` declares `okf_version: "0.2"`, quoted: an unquoted `0.2` is a number and declares nothing. `check` never writes; record a confirmation with `verify`, never by editing `verified` for the sake of a clean `check`. `kc/link/crosslink-format` skips bundles that are symlinks.

## 4. Listings: reindex

```bash
okf --root <catalogue> reindex <target> --check
okf --root <catalogue> reindex <target>
okf --root <catalogue> reindex <target> --init --check
okf --root <catalogue> reindex <target> --init
```

- `reindex` rewrites the block between `<!-- okf:index -->` and `<!-- /okf:index -->` in every `index.md` (one level) and `INDEX-MAP.md` (whole subtree) under the target, from each concept's `title` and `description`. Subdirectories are listed only when they carry an `index.md`.
- `--check` writes nothing, prints `STALE` and `UNCOVERED` paths, and exits 5 (drift) when any exist. `UNCOVERED` = an `index.md` without markers in a directory that holds concepts.
- `--init` creates a missing `index.md` for the named target and converts marker-less `index.md` files in the subtree that hold a single bullet-list section. It replaces that hand-written list with an empty marker block, then the normal run fills it. Multi-section indexes are skipped and flagged; `--force` also flattens pure heading-and-bullet multi-section lists. Preview with `--init --check`.
- A deliberately hand-curated `index.md` stays out of `UNCOVERED` when it contains `<!-- okf:index-exempt -->`.
- Run `reindex <bundle>` after adding, renaming or retitling a concept, and after creating a subdirectory.

## 5. Search indexes

```bash
okf --root <catalogue> build-index --if-stale
okf --root <catalogue> build-semantic-index --if-stale
okf --root <catalogue> prime --check-semantic
```

- Lexical index: `<catalogue>/.fts/fts.sqlite`, local, no network. Without it `find` falls back to a substring scan. When stale, `find` prints `note: lexical index is stale` on stderr and misses recent changes. Rebuild after every batch of writes. `--if-stale` skips a rebuild when current.
- Semantic index (optional): `<catalogue>/.tagvec/tag_vectors.sqlite`. Building it sends the title and body of every concept to the Voyage AI API, and afterwards `find` sends each query there. Ask the user before the first build and before searching a catalogue that has one. Without consent, prefix commands with an empty key, for example `VOYAGE_API_KEY= okf --root <catalogue> find "<query>"`.
- Without a key, `build-semantic-index` prints `note: semantic index build skipped (VOYAGE_API_KEY not set)` and builds nothing. It embeds only missing or changed concepts, so after an interruption run the same command again. `--if-stale` skips when every concept is embedded.
- `prime --check-semantic` prints `semantic index: complete`, `partial` or `absent`.
- A miss in `find` is a coverage question first: check both index states in `prime` before blaming the ranking.
- In git catalogues, list `.fts/` and `.tagvec/` in `.gitignore`.

## 6. Tags

```bash
okf --root <catalogue> tags
okf --root <catalogue> tags --singletons
okf --root <catalogue> tags <candidate> <candidate>
okf --root <catalogue> tags --validate <tag> <tag>
okf --root <catalogue> tags --register <tag> "<description>"
okf --root <catalogue> merge-tags <old> <old2> --into <new> --where "path ~ <target>/"
okf --root <catalogue> remove-tags <tag> --where "path ~ <target>/"
okf --root <catalogue> normalize-tags --where "path ~ <target>/"
```

- `tags`: every tag in use with its count. `--singletons`: tags used once, the merge candidates.
- `tags <candidate>`: fuzzy search against the tags in use, `--limit` per candidate (default 8).
- `TAGS.md` present = closed vocabulary. `--validate` exits 4 (non_conformant) and prints `UNKNOWN <tag>` for unregistered tags; without `TAGS.md` it prints `(no TAGS.md — closed vocabulary not enabled)`.
- `--register <tag> "<description>"` writes to `TAGS.md` at once, no preview (description required, one line, at most 150 characters, no `|`); repeat the option for several tags. It also tries a local embedding service; a stderr `warning: auto-embed skipped` is harmless.
- `merge-tags`, `remove-tags` and `normalize-tags` preview; add `--apply` to write. `normalize-tags` converts inline `tags: [a, b]` to a block list.
- After merging or removing, delete the obsolete entries (rows or blocks) from `TAGS.md` by hand, then run `check`.

## 7. Rename or move a concept

```bash
okf --root <catalogue> refs <bundle>/<old>.md
okf --root <catalogue> wikilinks <bundle>
okf --root <catalogue> rename <bundle>/<old>.md <bundle2>/<new>.md
okf --root <catalogue> rename <bundle>/<old>.md <bundle2>/<new>.md --apply
okf --root <catalogue> check
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
2. Record hand-written links to the old listing: `okf --root <catalogue> refs <bundle>/<old-dir>/index.md --in`. Hits from generated listings disappear by themselves.
3. List the files with `ls <catalogue>/<bundle>/<old-dir>`. For each concept except `index.md`, preview, then apply:

   ```bash
   okf --root <catalogue> rename <bundle>/<old-dir>/<concept>.md <new-bundle>/<new-dir>/<concept>.md
   okf --root <catalogue> rename <bundle>/<old-dir>/<concept>.md <new-bundle>/<new-dir>/<concept>.md --apply
   ```

   A nested directory: run steps 1 to 4 for it first.
4. Only `index.md` is left: delete it and the directory. Git catalogue: `git -C <catalogue> rm -f <bundle>/<old-dir>/index.md` (`-f` because `rename` already rewrote its listing). Otherwise: `rm <catalogue>/<bundle>/<old-dir>/index.md`, then `rmdir <catalogue>/<bundle>/<old-dir>`. A listing file is not a concept, so hard rule 4 does not apply.
5. For each link from step 2: `okf --root <catalogue> rewrite-path "/<bundle>/<old-dir>/index.md" "/<new-bundle>/<new-dir>/index.md" --check`, then the same without `--check`.
6. `okf --root <catalogue> reindex <bundle>` and `okf --root <catalogue> reindex <new-bundle>`.
7. Verify with `check`, `reindex <new-bundle> --check`, `fix-crosslinks --check`, `wikilinks --unresolved` and `ctx check`. Done when all are clean; otherwise fix and rerun step 7.

- Rename a bundle: move every directory and every root concept of `<bundle>` into `<new-bundle>` this way, then delete `<bundle>/index.md` (and `INDEX-MAP.md`) and the empty directory as in step 4.
- Merge bundle A into bundle B: the same with B as destination. First compare the file names of both: `rename` refuses an existing destination without `--force`.

## 9. Archive and restore

```bash
okf --root <catalogue> archive <bundle>/<concept-id>.md
okf --root <catalogue> archive <bundle>/<concept-id>.md --apply
okf --root <catalogue> archive --restore _archive/<bundle>/<concept-id>.md --apply
```

- `archive` moves the concept to `_archive/<bundle>/<concept-id>.md`, rewrites inbound links to the new path and reindexes. The report starts with the number of active concepts that still link to it.
- Archived concepts are hidden from `find` and `list` unless the `--where` expression names `archived`, for example `archived in (true, false)`; the semantic arm never covers them. `check` and `index` skip `_archive/`.
- A ctx entry that now points into `_archive/` gives a `kc/ctx/archived-entry` warning: drop or replace it.
- `--restore` reverses the move and the link rewrites. One concept per call.

## 10. Links

```bash
okf --root <catalogue> fix-crosslinks <target> --check
okf --root <catalogue> fix-crosslinks <target>
okf --root <catalogue> fix-crosslinks <target> --include-reserved
okf --root <catalogue> wikilinks <target> --unresolved
okf --root <catalogue> rewrite-path "<old path>" "<new path>" --check
okf --root <catalogue> rewrite-path "<old path>" "<new path>"
```

- `fix-crosslinks` rewrites links to the `/<bundle>/<subdir>/<concept>.md` form when the target exists, and reports the rest as `unresolved` without guessing. Repair those by hand. Reserved files are skipped unless `--include-reserved`, which rewrites their prose but never the generated block.
- `wikilinks` reports `[[...]]` links as `resolved`, `ambiguous` or `unresolved`. `refs` never sees wikilinks and `check` only for opted-in bundles; run `wikilinks` before renaming a concept that wikilinks may target.
- `rewrite-path` replaces a literal string in `.md`, code and config files under `--scan-root <dir>` (default `--root`). It matches only where the string is not glued to letters, digits, `_`, `.`, `/` or `-`, so `../<old>` does not match `<old>`, and a directory prefix such as `/<bundle>/` matches nothing. It skips `.git`, `node_modules` and dot-directories, resolves nothing and does not reindex. For catalogue links pass the `/`-prefixed form (`/<bundle>/<old>.md`); `<bundle>/<old>.md` does not match inside it. Use it for mentions that `rename` cannot reach.

## 11. Placeholders

```bash
okf --root <catalogue> fix-xml-tags <target> --check
okf --root <catalogue> fix-xml-tags <target>
```

Wraps bare `<tag>` and `<tag>.<tag2>` placeholders outside code in backticks (warning `kc/markup/xml-like-tags`).

## 12. Stale content

In a bundle declaring `okf_version: "0.2"`, `check` warns `okf/lifecycle/stale-after` for every concept whose `stale_after` has passed, and `list --where "stale = true"` (or `find`, `recent`) selects them in any bundle; `tier` and `stale` are also keys of every concept record in `--json` output. For a bundle without the declaration, list the values with POSIX tools and compare each `stale_after` with the current UTC time; a concept is stale when now is at or past that instant:

```bash
okf --root <catalogue> list --where "stale = true"
grep -rn --include='*.md' '^stale_after:' <catalogue>/<bundle>
grep -rln --include='*.md' '^status: deprecated' <catalogue>/<bundle>
date -u +%Y-%m-%dT%H:%M:%SZ
```

Re-check a stale concept against its `sources` with the user, then update `generated` and `stale_after` per write-concepts.md and record the check with `okf --root <catalogue> verify <bundle>/<concept> --by human:<id>` (only for a real check; `--by` is `human:<id>`, `process:<id>` or `<producer>/<version>`; it appends one `{by, at}` entry and changes nothing else), or set `status: deprecated`.

## 13. Graph view

```bash
okf --root <catalogue> visualize <bundle> --out <path outside the catalogue>.html
```

Writes a concept graph that embeds the body of every concept, at once and without preview. The default path `<bundle>/assets/viz.html` puts that copy inside the bundle, where it gets committed or published: always pass `--out` with a path outside the catalogue. Opening the file loads scripts from public CDNs.

## 14. Health routine (checklist)

Run periodically and before a release of the catalogue. Copy into your task list (todo tool or scratch list), tick one by one:

- [ ] `okf --root <catalogue> check --strict` -> done when `OK — 0 violations` -> on failure: fix per section 3, rerun
- [ ] `okf --root <catalogue> reindex <bundle> --check`, per bundle -> done when it reports `0 stale, 0 uncovered` -> on failure: `reindex <bundle>` (stale) or add the marker pair (uncovered), rerun
- [ ] `okf --root <catalogue> fix-crosslinks --check` -> done when `0 file(s) would rewrite, 0 unresolved link(s)` -> on failure: run it without `--check`, repair unresolved links by hand, rerun
- [ ] `okf --root <catalogue> wikilinks --unresolved` -> done when `0 ambiguous, 0 unresolved` -> on failure: fix the links, rerun
- [ ] `okf --root <catalogue> sync-status` -> done when exit 0 -> on failure: section 3, `kc/sync/block` and `kc/sync/stale` rows, rerun
- [ ] `okf --root <catalogue> ctx check --stale` -> done when `OK — 0 violations` and every stale warning is reviewed -> on failure: context-bundles.md failure modes, rerun
- [ ] `okf --root <catalogue> tags --singletons` -> done when each listed tag is merged or kept on purpose
- [ ] Stale content (section 12) -> done when every past `stale_after` is reported to the user
- [ ] `okf --root <catalogue> build-index --if-stale` -> done when it prints `indexed` or `index is current`

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `find` returns nothing for an existing concept | Stale or missing lexical index, or concept archived | `build-index`; add `--where "archived in (true, false)"` |
| `list` prints `(error: pass --where, e.g. --where 'type = Runbook')` | `list` needs a filter | Add `--where`, or use `find` |
| `refs: target not found` | Path without `.md`, or not relative to `--root` | Pass `<bundle>/<concept-id>.md` |
| `refs --scan-root <dir>` marks existing targets `[missing]` | With `--scan-root`, `/`-links resolve against that directory | Read only inbound links from outside the catalogue; run `refs` without `--scan-root` for the rest |
| `recent: catalogue root is not a git repository` | `recent` dates concepts from git | Use `list` or `find` |
| `rename: both paths must live under the catalogue root` | Source or destination outside `--root` | Move outside files with `git mv`, then fix links with `rewrite-path` |
| `rename: source lies under _archive/` | Archived source | `archive --restore` |
| `rename: destination exists (use --force to overwrite)` | Target file exists | Choose another name, or `--force` once the user confirms the overwrite |
| Moved file not in the catalogue `git status` | Bundle is a symlink into another repository | Commit in `git -C <catalogue>/<bundle> rev-parse --show-toplevel` |
| `check` clean but links broken in Obsidian | Wikilinks are invisible to `check` | `wikilinks --unresolved`, or opt in via `wikilink_checked_bundles` |
| Unscoped `check` reports directories that are not knowledge | Every top-level directory not starting with `.` or `_` is a bundle | Scope `check <bundle>`, or prefix scratch directories with `_` |
