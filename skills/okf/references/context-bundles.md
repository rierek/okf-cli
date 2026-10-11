# Context bundles: ctx

A ctx (context bundle) is a curated, ordered reading list for one topic, stored as `<catalogue>/_ctx/<slug>.md`. Use it to hand an agent or a person the minimal set of pages for a task, in reading order. The ctx commands write and validate these files; `_ctx/index.md` lists them and is kept current automatically.

The ctx verbs `create`, `add`, `move`, `drop`, `rename` and `remove` write at once, without a preview. `remove` deletes the file: confirm with the user first.

## Contents

- Checklist: create a ctx
- File format
- Read a ctx
- Create a ctx
- Edit a ctx
- Verify
- Maintenance
- Failure modes

## Checklist: create a ctx

Copy into your task list (todo tool or scratch list), tick one by one:

- [ ] 1. Pick the pages -> done when every entry is a page you read with `toc` or `read`, and the user agreed to the list
- [ ] 2. Create -> done when `ctx create` printed `created _ctx/<slug>.md` -> on failure (slug rejected): choose a valid slug, rerun step 2
- [ ] 3. Order and modes -> done when `ctx <slug>` lists the required entries in reading order and look-up pages as reference entries -> on failure: `ctx move`, rerun step 3
- [ ] 4. Verify -> done when `ctx check <slug>` and `check _ctx` end `OK — 0 violations` -> on failure: fix per "Failure modes", rerun step 4

## File format

```markdown
---
type: Context
description: "Read these first when joining the widget project"
---

# <slug>

| pos | mode | path | comment |
|---|---|---|---|
| 1 | pflicht | [overview](/<bundle>/architecture/overview.md) |  |
| 2 | pflicht | [use-postgres](/<bundle>/decisions/use-postgres.md) | why the storage looks like this |
| - | nachschlag | [glossary](/<bundle>/reference/glossary.md) | look up terms as needed |
```

- Modes are literal CLI values: `pflicht` = required entry, read in order, positions `1..n`. `nachschlag` = reference entry, consulted when needed, position `-`.
- A path is a catalogue concept, written as a `/`-link, or any other file, written as a code span.
- `type: Context` must be registered in `TYPES.md` when that file exists, else `check` warns `kc/type/registered`. Add the row ``| `Context` | Curated reading list (ctx) |``.
- Slug: lowercase letters, digits and hyphens. Reserved: the ctx verb names and `index`, `log`, `readme`, `index-map`.

## Read a ctx

```bash
okf-cli --root <catalogue> ctx list
okf-cli --root <catalogue> ctx list --for <bundle>/<concept-id>.md
okf-cli --root <catalogue> ctx <slug>
okf-cli --root <catalogue> ctx read <slug>
okf-cli --root <catalogue> ctx toc <slug> --depth 2
okf-cli --root <catalogue> ctx outbound <slug>
okf-cli --root <catalogue> ctx inbound <slug>
```

- `ctx list`: slug, description, entry and required counts. `--for <path>`: only the ctx files that contain that path.
- `ctx <slug>` (short for `ctx show <slug>`): required entries in reading order, then reference entries, with type, title, description and a token estimate. Exit 1 when an entry is dead.
- `ctx read <slug>`: prints the full text of every required entry in position order, each after a `===== i/n <path> =====` separator. Reference entries are not printed. This is the one call that loads a whole ctx into context.
- `ctx toc <slug>`: headings of every entry; `--depth N` limits the heading level.
- `ctx outbound` and `ctx inbound`: links leaving or reaching each entry; `--file <title, path or stem>` limits to one entry, `--include-internal` adds links between members.
- `--json` exists on `ctx list`, `ctx show`, `ctx check`, `ctx inbound` and `ctx outbound`.

## Create a ctx

```bash
okf-cli --root <catalogue> find "<topic>"
okf-cli --root <catalogue> ctx create <slug> <bundle>/<concept-id> <bundle>/<concept-id> --description "<one line>"
okf-cli --root <catalogue> ctx create <slug> --import <file> --description "<one line>"
```

1. Pick the pages with `find`, `toc` and `read`. Fewer is better: every required entry costs reading time.
2. Create the ctx. Paths are `<bundle>/<concept-id>` (with or without `.md`) or file paths. `--import <file>` reads a local text file with one path per line; blank lines and lines starting with `#` are skipped; text after a TAB becomes the entry comment.
3. `ctx create` makes every path a required entry, ordered alphabetically by path, not in the order given. Fix the order with `ctx move` (next section).
4. Always pass `--description`; an empty description is a `kc/ctx/empty-description` warning.

## Edit a ctx

```bash
okf-cli --root <catalogue> ctx add <slug> <path> --pos 2 --comment "<why>"
okf-cli --root <catalogue> ctx add <slug> <path> --mode nachschlag --comment "<why>"
okf-cli --root <catalogue> ctx move <slug> <path> --pos 1
okf-cli --root <catalogue> ctx move <slug> <path> --mode nachschlag
okf-cli --root <catalogue> ctx drop <slug> <path>
okf-cli --root <catalogue> ctx rename <old-slug> <new-slug>
okf-cli --root <catalogue> ctx remove <slug>
```

- `ctx add`: new required entry at the end, or at `--pos N`; `--mode nachschlag` adds a reference entry.
- `ctx move`: new position and/or mode. Required positions are renumbered `1..n` after every change.
- `ctx drop`: removes an entry, also when its file is gone.
- `ctx rename`: renames the file and rewrites inbound links.
- `ctx remove`: deletes the ctx and lists the files that still link to it; fix those links.
- Do not use `ctx edit`: it opens an interactive editor. Hand edits of the table are possible, but run `ctx check <slug>` afterwards.

## Verify

```bash
okf-cli --root <catalogue> ctx check <slug>
okf-cli --root <catalogue> ctx check --stale
okf-cli --root <catalogue> check _ctx
okf-cli --root <catalogue> ctx <slug>
```

Done when `ctx check` and `check _ctx` end `OK — 0 violations` and `ctx <slug>` lists the entries in the intended order. `--stale` reports `kc/ctx/stale-entry` as a warning for every entry modified after the ctx file: review whether the ctx still fits. A check fails: fix the entry, then rerun the checks until clean.

## Maintenance

- `rename` and `archive` of a concept rewrite ctx entries automatically. An entry that now points into `_archive/` is a `kc/ctx/archived-entry` warning: drop it or replace it.
- `ctx list --for <path>` before deleting or archiving a concept shows which ctx files depend on it.
- MCP offers only `okf_ctx_list` and `okf_ctx_show`; every other ctx verb is CLI-only.

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `ctx: unknown slug: <slug>` | Typo, or the ctx was renamed | `ctx list` |
| `ctx create` rejects the slug | Uppercase, underscore, or a reserved name | Use lowercase letters, digits, hyphens |
| `ctx <slug>` exits 1, entry shown `[DEAD]` | Entry file deleted or moved outside `rename` | `ctx drop <slug> <path>`, then `ctx add` the new path |
| `WARNING kc/type/registered _ctx/<slug>.md` | `Context` missing from `TYPES.md` | Add the `Context` row |
| `WARNING kc/ctx/archived-entry ... entry under _archive/` | Member was archived | Drop or replace the entry |
| Reading order wrong after `create` | `create` sorts alphabetically | `ctx move <slug> <path> --pos <n>` |
| `ERROR kc/ctx/required-positions ... required positions are not 1..n` | Table edited by hand | Fix the `pos` column, or rebuild with `ctx move` |
