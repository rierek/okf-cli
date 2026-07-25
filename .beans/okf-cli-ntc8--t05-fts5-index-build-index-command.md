---
# okf-cli-ntc8
title: T05 FTS5 index + build-index command
status: todo
type: task
priority: high
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-25T23:25:11Z
parent: okf-cli-cskz
blocked_by:
    - okf-cli-48qk
---

Plan: `docs/okf-retrieval-architecture/PLAN.md` → **Task 5**. Follow it step by step; it carries the literal code and tests.

The lexical arm of the measured architecture is FTS5 + BM25 (`DESIGN.md`), with `porter unicode61 remove_diacritics 2` and prefix matching — the best measured variant (R32). This task builds and persists the index; Task 6 queries it.

### Requirement 1: A persistent, optional lexical index

**Objective:** As a user of the CLI, I want a search index I can rebuild with one command, so that lexical retrieval is fast and reproducible without becoming a precondition for using the catalogue.

#### Acceptance Criteria

1. THE CLI SHALL expose a `build-index` command that writes `<root>/.fts/fts.sqlite`.
2. THE index SHALL hold, per concept, its path, its frontmatter type, its title, its tags and its body.
3. THE builder SHALL write into a temporary sibling file and atomically replace the target, so that an interrupted build never leaves a half-written index in place of a working one.
4. THE builder SHALL be idempotent — rebuilding SHALL NOT duplicate rows.
5. THE builder SHALL make no network call.
6. THE staleness check SHALL report stale WHEN the catalogue's concept count differs from the indexed count OR any concept file is newer than the newest file seen at build time, and SHALL do so using file metadata only, never by reading concept bodies.
7. IF the index metadata is missing or unreadable THEN THE staleness check SHALL report stale.

#### Success Criteria

- SC-01: `build_fts_index(root)` on a two-concept fixture returns `(2, "<root>/.fts/fts.sqlite")` and the file exists.
- SC-02: the `docs` table maps `b/one -> Runbook` and `b/two -> Konzept`.
- SC-03: a second build still yields 2 rows total.
- SC-04: a freshly built index is not stale; adding one concept file makes it stale.
- SC-05: `okf-cli --root ~/Obsidian/Knowledge-Catalogue build-index` reports `indexed 2437 concept(s)`.
- SC-06: `python3 -m unittest discover -s cli -p 'test_*.py'` stays at exactly 19 failures / 2 errors.

_Requirements: PLAN.md Task 5 · DECISIONS D14, D15 · TASKS.md T13 · REFERENCES R32_

## Steps

- [ ] Add the five module-level test imports (deliberate departure from the file's local-import style — see the plan)
- [ ] Write the failing `FtsIndexBuild` tests
- [ ] Run them, confirm they fail for the stated reason
- [ ] Add the lexical-index section: constants, `_fts_db_path`, `build_fts_index`, `_fts_index_stale`, `cmd_build_index`
- [ ] Register the `build-index` subparser and its dispatch entry (`cli/okf-cli.py:2321-2328`)
- [ ] Tests pass; suite still 19F/2E
- [ ] Build the live index; check whether the catalogue's `.gitignore` needs a `.fts/` line — report it, do NOT commit in that repo
- [ ] Commit `feat(cli): add fts5 lexical index + build-index`

## Recommended Skills

- `superpowers:test-driven-development`
