---
# okf-cli-8rwy
title: T04 Alphabetical listing, pointer, generated grouped overview
status: completed
type: task
priority: normal
created_at: 2026-07-26T13:03:25Z
updated_at: 2026-07-26T13:53:37Z
parent: okf-cli-5uog
blocked_by:
    - okf-cli-2ljd
---

Plan: `docs/okf-cli-capability-surface/PLAN.md` → **Task 4**.

Both help layouts come from the same registrations, so neither can go stale. The hand-written block that already drifted is deleted.

### Requirement 1: The command directory is predictable and self-pointing

**Objective:** As someone looking up a known command, I want the listing alphabetical and a pointer to per-command detail, so that I neither scan registration order nor guess that `<command> --help` exists.

#### Acceptance Criteria

1. THE subcommands SHALL be registered in alphabetical order, since registration order is what argparse prints.
2. THE top-level help SHALL contain the literal string `<command> --help`.

### Requirement 2: The purpose-grouped overview is rendered, not maintained

**Objective:** As a newcomer to a 21-command CLI, I want the commands grouped by purpose, without that view being a second thing to keep in sync.

#### Acceptance Criteria

1. THE CLI SHALL render the epilog from the registered parsers via `render_command_overview(sub)`, grouping by `COMMAND_GROUPS` in `_GROUP_ORDER` sequence and wrapping its own lines (the top-level parser uses `RawDescriptionHelpFormatter`, `cli/okf-cli.py:2579-2580`).
2. THE module docstring SHALL no longer list commands by hand; the `Commands:` block at `cli/okf-cli.py:8-45` is replaced by a three-line pointer.
3. THE docstring's blank line `:46`, the `Run from the catalogue root, or pass --root <path>.` line `:47` and the terminator `"""` `:48` SHALL survive unchanged — the replacement range ends at `:45`.

#### Success Criteria

- SC-01: `list(subcommand_parsers(build_parser())) == sorted(...)`.
- SC-02: top-level help contains `<command> --help` and `commands by purpose:` and one heading per group in `_GROUP_ORDER`.
- SC-03: every name in `COMMAND_GROUPS` appears in the overview section of the help text.
- SC-04: `okf.__doc__` contains neither `okf-cli.py find` nor `okf-cli.py merge-tags`.
- SC-05: full suite at `Ran 272 tests`, exactly 19 failures / 2 errors.
- SC-06: `python3 cli/okf-cli.py --help` is run by hand and its full output pasted into `## Smoke`.

**Files:** `cli/okf-cli.py:8-45` (docstring), `:49-62` (add `import textwrap`), `build_parser()` (order + `ap.epilog`), new `render_command_overview()` · `cli/test_okf_cli.py` (append classes `CommandDirectoryOrder`, `GroupedOverview`)

## Steps

- [x] Write the failing `CommandDirectoryOrder` + `GroupedOverview` tests
- [x] Run them, confirm the order mismatch and the missing pointer/overview
- [x] Add `import textwrap`; add `render_command_overview()`
- [x] Sort the 21 registrations alphabetically, moving each command's own `add_argument` calls with it; set `ap.epilog`
- [x] Replace the docstring block `:8-45` only — check `:46-48` survived
- [x] Full suite; read the help as a user; commit `feat(cli): generated command directory in help` (`ecd2058`)

## Recommended Skills

- superpowers:test-driven-development



## Prelude from the T01-T03 reviews (2026-07-26, non-blocking)

1. **The plan can contradict itself. When it does, adapt the text to the test, never the test to the text.** T03 hit this: PLAN.md Task 3's literal replacement string starts a sentence with capital `Measured`, while the plan's own test asserts the case-sensitive substring `"measured"`. The implementer joined the clauses with a semicolon, kept every other word, and left the test untouched — the reviewer diffed the shipped test against the plan and found zero differences. That is the correct resolution. Weakening a plan-authored test to accept plan-authored text is a blocking defect. Your Task 4 has the same shape: `test_module_docstring_no_longer_lists_commands_by_hand` asserts on the docstring you rewrite.
2. The 50-character subject cap applies to EVERY commit, the bean-close meta commit included. There is no `commit-msg` hook in `.git/hooks/`, so nothing catches an overrun. Count before committing.
3. For any before/after proof, snapshot with `git show <rev>:<path> > /tmp/<x>.py` and diff. Do not use `git stash` — shared-tree operation, this repo sees concurrent activity.


## Summary

Implemented PLAN.md Task 4 exactly. `render_command_overview(sub)` was added below `_sub()` (`cli/okf-cli.py:2617-2637`); `import textwrap` was inserted in alphabetical position after `import sys` (`cli/okf-cli.py`, import block). All 21 `_sub()` registrations in `build_parser()` were reordered alphabetically (`build-index, check, find, fix-crosslinks, fix-xml-tags, index, info, list, log, merge-tags, normalize-tags, prime, read, refs, reindex, remove-tags, rename, rewrite-path, tags, toc, visualize`), each command's own `add_argument()` calls moved with it, and `ap.epilog = render_command_overview(sub)` was set immediately before `return ap`. The module docstring's hand-written `Commands:` block (`:8-45`) was replaced by the three-line pointer the plan specifies; the first paragraph (`:2-6`), the blank line, the closing `Run from the catalogue root...` line and the terminator `"""` all survive unchanged (confirmed by re-reading the file before and after the edit).

**Files:** `cli/okf-cli.py:8-13` (docstring pointer), import block (added `textwrap`), `cli/okf-cli.py:2617-2637` (new `render_command_overview()`), `build_parser()` (21 registrations reordered + `ap.epilog` set) · `cli/test_okf_cli.py` (appended `import re` to the import block, plus classes `CommandDirectoryOrder` and `GroupedOverview`, 5 tests, before `if __name__ == "__main__":`).

## Test-Output

RED (Step 2, both classes failing for the stated reasons):

```
$ rm -rf cli/__pycache__ && python3 -m unittest cli.test_okf_cli.CommandDirectoryOrder cli.test_okf_cli.GroupedOverview -v
test_commands_are_listed_alphabetically ... FAIL
test_top_level_help_points_at_per_command_help ... FAIL
test_module_docstring_no_longer_lists_commands_by_hand ... FAIL
test_overview_covers_every_command ... ERROR
test_overview_names_every_group_that_has_commands ... FAIL

AssertionError: Lists differ: ['index', 'list', 'find', 'read', 'prime', ...] != ['build-index', 'check', 'find', 'fix-crosslinks', ...]
AssertionError: '<command> --help' not found in 'usage: okf-cli.py [-h] [--root ROOT] ...'
IndexError: list index out of range   # "commands by purpose:" not yet in the help text, so split()[1] has no element
(docstring test failed too: "okf-cli.py find" and "okf-cli.py merge-tags" were still literally present)

Ran 5 tests in 0.011s
FAILED (failures=4, errors=1)
```

GREEN (Step 7):

```
$ rm -rf cli/__pycache__ && python3 -m unittest cli.test_okf_cli.CommandDirectoryOrder cli.test_okf_cli.GroupedOverview -v
test_commands_are_listed_alphabetically ... ok
test_top_level_help_points_at_per_command_help ... ok
test_module_docstring_no_longer_lists_commands_by_hand ... ok
test_overview_covers_every_command ... ok
test_overview_names_every_group_that_has_commands ... ok

Ran 5 tests in 0.010s
OK
```

**SC-05 — full suite:**

```
$ rm -rf cli/__pycache__ && python3 -m unittest discover -s cli -p "test_*.py" 2>&1 | grep -E "^(Ran |OK|FAILED)"
Ran 272 tests in 17.961s
FAILED (failures=19, errors=2)
```

272 = 267 baseline (post-T03) + 5 new tests (`CommandDirectoryOrder` x2, `GroupedOverview` x3). `failures=19, errors=2` unchanged from baseline — no new failure introduced, none silenced.

## Reshuffle-preservation proof

Snapshotted the pre-task file with `git show 6e40b3f:cli/okf-cli.py > /tmp/before.py`, loaded both the snapshot and the working-tree module via `importlib.util`, built each parser, and compared the `dest` list of every non-help action per command:

```
before command count: 21
after command count: 21
command set equal: True
NO MISMATCHES — every command's argument dest list is byte-identical before/after reorder.
```

Full per-command `dest` lists confirmed identical, e.g. `find: ['query', 'limit', 'type', 'tag', 'scope', 'breakdown', 'expand_tags']`, `rewrite-path: ['old', 'new', 'scan_root', 'check']`, `tags: ['query', 'limit', 'singletons', 'register', 'validate']` — no argument lost, gained, or reattached to the wrong parser across the reorder.

## Smoke (SC-06 — Step 8, `python3 cli/okf-cli.py --help`, full output)

```
usage: okf-cli.py [-h] [--root ROOT]
                  {build-index,check,find,fix-crosslinks,fix-xml-tags,index,info,list,log,merge-tags,normalize-tags,prime,read,refs,reindex,remove-tags,rename,rewrite-path,tags,toc,visualize} ...

okf-cli.py — dependency-free navigation/search for an OKF Knowledge Catalogue.

Catalogue-aware fork inspired by Cole Medin's single-bundle okf-cli.py.
A *catalogue* is a directory whose immediate subdirectories (not starting with
'.' or '_') are OKF *bundles*. Standard library only — no install required.

Run `okf-cli.py --help` for the command directory (flat + grouped by purpose),
and `okf-cli.py <command> --help` for one command's options. Both are generated
from the parser — this file documents no command list by hand.

Run from the catalogue root, or pass --root <path>.

positional arguments:
  {build-index,check,find,fix-crosslinks,fix-xml-tags,index,info,list,log,merge-tags,normalize-tags,prime,read,refs,reindex,remove-tags,rename,rewrite-path,tags,toc,visualize}
    build-index         (re)build the FTS5 lexical search index at
                        <root>/.fts/fts.sqlite (local only, no network)
    check               conformance scan: §9 hard rules + local invariants
    find                hybrid ranked search: lexical FTS5/BM25 arm plus
                        semantic arm
    fix-crosslinks      rewrite links to catalogue-root-absolute form
                        (/bundle/subdir/concept.md)
    fix-xml-tags        wrap `<tag>`/`<tag>.<tag2>` placeholders in inline
                        code
    index               catalogue TOC (bundles, descriptions, concept counts),
                        or one bundle's index.md
    info                print catalogue schema docs (TYPES.md + PROPERTIES.md)
    list                list concepts filtered by frontmatter type and/or tag
    log                 render git history for the catalogue or a bundle as a
                        SPEC §7 changelog
    merge-tags          merge/rename one or more tags into a target tag across
                        concept frontmatter
    normalize-tags      convert inline `tags: [...]` fields to YAML block-list
                        form (local convention)
    prime               one-shot agent onboarding: CLAUDE.md guide + catalogue
                        TOC
    read                print one concept page
    refs                list inbound markdown references to a file
    reindex             (re)generate marker-bounded index.md listings
    remove-tags         remove one or more tags from concept frontmatter (no
                        merge target)
    rename              move a concept + rewrite every inbound/outbound link +
                        reindex (dry-run default)
    rewrite-path        literal path-string rewrite across text files
    tags                list all tags with usage counts, or fuzzy-search
                        candidate tags
    toc                 print a concept's headings (default: h2 only)
    visualize           write a self-contained viz.html graph for a bundle

options:
  -h, --help            show this help message and exit
  --root ROOT           catalogue root (default: auto-detect from cwd; hard-
                        fails if none found)

commands by purpose:
  navigation:
    index            catalogue TOC (bundles, descriptions, concept counts), or one bundle's
                     index.md
    info             print catalogue schema docs (TYPES.md + PROPERTIES.md)
    list             list concepts filtered by frontmatter type and/or tag
    log              render git history for the catalogue or a bundle as a SPEC §7 changelog
    prime            one-shot agent onboarding: CLAUDE.md guide + catalogue TOC
    read             print one concept page
    toc              print a concept's headings (default: h2 only)
    visualize        write a self-contained viz.html graph for a bundle
  search:
    build-index      (re)build the FTS5 lexical search index at <root>/.fts/fts.sqlite (local
                     only, no network)
    find             hybrid ranked search: lexical FTS5/BM25 arm plus semantic arm
    refs             list inbound markdown references to a file
  tags:
    merge-tags       merge/rename one or more tags into a target tag across concept frontmatter
    normalize-tags   convert inline `tags: [...]` fields to YAML block-list form (local
                     convention)
    remove-tags      remove one or more tags from concept frontmatter (no merge target)
    tags             list all tags with usage counts, or fuzzy-search candidate tags
  maintenance:
    check            conformance scan: §9 hard rules + local invariants
    fix-crosslinks   rewrite links to catalogue-root-absolute form (/bundle/subdir/concept.md)
    fix-xml-tags     wrap `<tag>`/`<tag>.<tag2>` placeholders in inline code
    reindex          (re)generate marker-bounded index.md listings
    rename           move a concept + rewrite every inbound/outbound link + reindex (dry-run
                     default)
    rewrite-path     literal path-string rewrite across text files

run `okf-cli.py <command> --help` for one command's options.
```

Alphabetical listing, then the grouped overview, then the `<command> --help` pointer — this is the replacement artefact for the one the PO rejected US-07 over.

Commit: `feat(cli): generated command directory in help` (`ecd2058`, 46 characters).

## Deviations

None. Implemented exactly per PLAN.md Task 4 Steps 1-9: same test names/bodies, same renderer, same alphabetical registration order, same docstring replacement range (`:8-45` only, `:46-48` verified unchanged before and after the edit).
