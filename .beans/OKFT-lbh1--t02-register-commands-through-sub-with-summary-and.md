---
# OKFT-lbh1
title: T02 Register commands through _sub with summary and group
status: completed
type: task
priority: normal
created_at: 2026-07-26T13:02:44Z
updated_at: 2026-07-26T13:36:46Z
parent: OKFT-5uog
blocked_by:
    - OKFT-z0tt
---

Plan: `docs/okf-cli-capability-surface/PLAN.md` → **Task 2**, including **Step 4b**. Follow it step by step.

This is where the reported defect dies structurally: a command cannot be registered without a summary, because the helper takes it as a required positional.

### Requirement 1: Every command is documented at the place it is registered

**Objective:** As someone reading `okf-cli --help`, I want every command to carry a description, so that the CLI's primary command is not invisible in its own directory.

#### Acceptance Criteria

1. THE CLI SHALL register every subcommand through `_sub(sub, name, group, summary, **kwargs)`, which passes the summary as both `help=` and `description=` and records the group in `COMMAND_GROUPS`.
2. WHEN a group is not in `_GROUP_ORDER` THE helper SHALL raise `ValueError`.
3. THE commands `find`, `index` and `read` SHALL each carry a summary (they carry none today — `cli/okf-cli.py:2596`, `:2584`, `:2610`).
4. THE `find` subparser SHALL carry an epilog explaining both score scales, rendered verbatim.

### Requirement 2: The scoring explanation survives the docstring's deletion, corrected

**Objective:** As a user reading `find --help`, I want to know what `score: a/b` means on the arm that actually produced my result.

#### Acceptance Criteria

1. THE `find` epilog SHALL state that `a/100` covers the FTS5/BM25 lexical arm (relative to the run's own top hit) and the semantic arm (`round(100 * cosine)`), and that `a/(6 * n)` is the substring fallback.
2. THE epilog SHALL NOT repeat the docstring's claim that `6 * number of terms` is the maximum for every result — that has been false since the FTS arm shipped (`cli/okf-cli.py:912-928`, `:1140-1152`).

#### Success Criteria

- SC-01: `parsers[name].description` is non-empty for `find`, `index` and `read`.
- SC-02: `set(COMMAND_GROUPS) == set(subcommand_parsers(build_parser()))` — all 21, exactly once each, per the group table in Task 2 Step 4.
- SC-03: `parsers["find"].format_help()` contains `100`, `6 * number of terms` and `provenance`.
- SC-04: `read`'s summary appears in its own `--help` output (the summary reaches both levels).
- SC-05: full suite at `Ran 265 tests`, exactly 19 failures / 2 errors.
- SC-06: `okf-cli --help` is run by hand afterwards and its `positional arguments` block pasted into `## Smoke` — this is the artefact the PO rejected US-07 over.

**Files:** `cli/okf-cli.py` (new `_GROUP_ORDER`, `COMMAND_GROUPS`, `_sub()`, `_FIND_EPILOG` above `build_parser()`; all 21 registrations converted) · `cli/test_okf_cli.py` (append class `CommandDirectory`)

## Steps

- [x] Write the failing `CommandDirectory` tests (4 methods)
- [x] Run them, confirm `find has no summary` and the `COMMAND_GROUPS` AttributeError
- [x] Add `_GROUP_ORDER`, `COMMAND_GROUPS`, `_sub()`
- [x] Convert all 21 registrations; give `find`/`index`/`read` the summaries from the plan
- [x] Add `_FIND_EPILOG` and register `find` with it plus `RawDescriptionHelpFormatter` (Step 4b)
- [x] Full suite; look at `--help` with your own eyes; commit `fix(cli): every subcommand carries a summary` (`4f6ac34`)

## Recommended Skills

- superpowers:test-driven-development



## Prelude from the T01 review (2026-07-26, non-blocking I01)

For any before/after proof in this epic, snapshot with `git show <rev>:<path> > /tmp/<x>.py` and diff against the working tree. Do not use `git stash` (as PLAN.md Task 1 Step 5 prescribed): the stash is a shared-tree operation, and this repo has seen concurrent unrelated activity. The reviewer used the snapshot method to re-establish T01's byte-identical help output and it was strictly safer. No action needed on T01 itself, which was APPROVED.

## Summary

Implemented PLAN.md Task 2 exactly, including Step 4b. Added `_GROUP_ORDER` (a 4-tuple: `navigation`, `search`, `tags`, `maintenance`), the module-level `COMMAND_GROUPS` dict, and `_sub(sub, name, group, summary, **kwargs)` above `build_parser()` (`cli/okf-cli.py`). `_sub()` raises `ValueError` for a group outside `_GROUP_ORDER`, records `COMMAND_GROUPS[name] = group`, and calls `sub.add_parser(name, help=summary, description=summary, **kwargs)` — the summary is authored once and reaches both `okf-cli --help` (via `help=`) and `okf-cli <command> --help` (via `description=`).

All 21 `sub.add_parser(...)` call sites in `build_parser()` were converted to `_sub(...)`, registration order unchanged (Task 4's job, not this one). `find`, `index` and `read` — previously undocumented (B01) — gained the new summaries from the plan verbatim; the other 18 kept their existing `help=` string verbatim as the summary and only gained a group, per the plan's command→group table.

Step 4b: added `_FIND_EPILOG` above `build_parser()`, the corrected replacement for the stale docstring claim (`max = 6 * number of terms` for every result — false since the FTS arm shipped, B10). `find`'s registration passes `formatter_class=argparse.RawDescriptionHelpFormatter, epilog=_FIND_EPILOG` so the epilog renders verbatim.

**Files:** `cli/okf-cli.py` (`_GROUP_ORDER`, `COMMAND_GROUPS`, `_sub()`, `_FIND_EPILOG` inserted above `build_parser()`; all 21 registrations converted) · `cli/test_okf_cli.py` (appended class `CommandDirectory`, 4 tests).

## Test-Output

RED (Step 2 — three named failure reasons, all reproduced):

```
$ rm -rf cli/__pycache__ && python3 -m unittest cli.test_okf_cli.CommandDirectory -v
test_every_command_declares_a_group ... ERROR
test_find_help_explains_both_score_scales ... FAIL
test_find_index_read_are_no_longer_invisible ... FAIL
test_the_summary_reaches_both_help_levels ... ERROR

ERROR: test_every_command_declares_a_group
AttributeError: module 'okf_cli' has no attribute 'COMMAND_GROUPS'

FAIL: test_find_help_explains_both_score_scales
AssertionError: '100' not found in '...usage: okf-cli.py find...'

FAIL: test_find_index_read_are_no_longer_invisible
AssertionError: '' is not true : find has no summary

Ran 4 tests in 0.010s
FAILED (failures=2, errors=2)
```

GREEN after Steps 3-4b:

```
$ rm -rf cli/__pycache__ && python3 -m unittest cli.test_okf_cli.CommandDirectory cli.test_okf_cli.ParserExtraction -v
test_every_command_declares_a_group ... ok
test_find_help_explains_both_score_scales ... ok
test_find_index_read_are_no_longer_invisible ... ok
test_the_summary_reaches_both_help_levels ... ok
test_every_registered_command_is_dispatchable ... ok
test_parser_actions_skips_the_auto_help_action ... ok

Ran 6 tests in 0.012s
OK
```

**SC-05 — full suite:**

```
$ rm -rf cli/__pycache__ && python3 -m unittest discover -s cli -p "test_*.py" 2>&1 | grep -E "^(Ran |OK|FAILED)"
Ran 265 tests in 17.772s
FAILED (failures=19, errors=2)
```

265 = 261 (T01 baseline) + 4 new `CommandDirectory` tests. `failures=19, errors=2` unchanged — no new failure, none silenced.

**Step 6 — looked at with my own eyes:**

```
$ python3 cli/okf-cli.py find --help | head -5
usage: okf-cli.py find [-h] [--limit LIMIT] [--type TYPE] [--tag TAG]
                       [--scope TARGET] [--breakdown] [--expand-tags]
                       query

hybrid ranked search: lexical FTS5/BM25 arm plus semantic arm
```

`find --help`'s epilog (Step 4b, verified verbatim below `positional arguments`/`options`):

```
score lines:
  The two arms report on different scales, and `score: a/b` names the scale
  in use, not a confidence:
    a/100        the FTS5/BM25 lexical arm (relative to this run's own top
                 hit) and the semantic arm (round(100 * cosine)).
    a/(6 * n)    the substring fallback used when no FTS index is available:
                 per query term 3 for a title hit, 2 for a tag hit, 1 for a
                 body hit, capped at one per field per term — so the maximum
                 is 6 * number of terms.
  `provenance:` names the arm that produced the line; on a semantic hit it
  also prints the cosine. Degradations (index absent or stale, embedding
  backend unavailable) are announced on stderr, one note per degraded arm.
```

Commit: `fix(cli): every subcommand carries a summary` (`4f6ac34`).

## Smoke

SC-06 — `okf-cli --help`'s `positional arguments` block, run by hand after the commit (this is the artefact the PO rejected US-07 over):

```
$ python3 cli/okf-cli.py --help | sed -n '/^positional/,/^options/p'
positional arguments:
  {index,list,find,read,prime,info,toc,visualize,refs,rewrite-path,rename,build-index,reindex,log,tags,merge-tags,remove-tags,normalize-tags,check,fix-crosslinks,fix-xml-tags}
    index               catalogue TOC (bundles, descriptions, concept counts),
                        or one bundle's index.md
    list                list concepts filtered by frontmatter type and/or tag
    find                hybrid ranked search: lexical FTS5/BM25 arm plus
                        semantic arm
    read                print one concept page
    prime               one-shot agent onboarding: CLAUDE.md guide + catalogue
                        TOC
    info                print catalogue schema docs (TYPES.md + PROPERTIES.md)
    toc                 print a concept's headings (default: h2 only)
    visualize           write a self-contained viz.html graph for a bundle
    refs                list inbound markdown references to a file
    rewrite-path        literal path-string rewrite across text files
    rename              move a concept + rewrite every inbound/outbound link +
                        reindex (dry-run default)
    build-index         (re)build the FTS5 lexical search index at
                        <root>/.fts/fts.sqlite (local only, no network)
    reindex             (re)generate marker-bounded index.md listings
    log                 render git history for the catalogue or a bundle as a
                        SPEC §7 changelog
    tags                list all tags with usage counts, or fuzzy-search
                        candidate tags
    merge-tags          merge/rename one or more tags into a target tag across
                        concept frontmatter
    remove-tags         remove one or more tags from concept frontmatter (no
                        merge target)
    normalize-tags      convert inline `tags: [...]` fields to YAML block-list
                        form (local convention)
    check               conformance scan: §9 hard rules + local invariants
    fix-crosslinks      rewrite links to catalogue-root-absolute form
                        (/bundle/subdir/concept.md)
    fix-xml-tags        wrap `<tag>`/`<tag>.<tag2>` placeholders in inline
                        code

options:
```

All 21 commands now carry a summary; `find`, `index` and `read` — invisible before this task (B01) — are no longer invisible.

## Deviations

None. Implemented exactly per PLAN.md Task 2 Steps 1-7, including Step 4b, no scope beyond `cli/okf-cli.py` (`_GROUP_ORDER`/`COMMAND_GROUPS`/`_sub()`/`_FIND_EPILOG` plus the 21 registration call sites) and the one new test class. Registration order left untouched (Task 4), module docstring untouched (Task 4), no epilog/`render_command_overview()`/`textwrap` added beyond `_FIND_EPILOG` (Task 4), `--limit`/`--expand-tags` help text untouched (Task 3), the eight undocumented positionals untouched (Task 5), `mcp/` untouched.
