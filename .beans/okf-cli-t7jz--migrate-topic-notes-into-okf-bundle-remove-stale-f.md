---
# okf-cli-t7jz
title: Migrate topic notes into OKF bundle, remove stale files
status: completed
type: task
priority: normal
created_at: 2026-07-26T12:42:51Z
updated_at: 2026-07-26T14:26:05Z
parent: okf-cli-5uog
blocked_by:
    - okf-cli-80nb
    - okf-cli-g0gi
---

## Context

KM-cell audit (2026-07-26, ce-project-init audit mode, scope B-KM-1) found the bundle `docs/okf-tools-okf/` structurally conformant (`okf_check` scoped to bundle: 0 errors, 0 warnings) but content-thin — only GLOSSARY.md. Durable decisions/design facts from this epic's work sit in topic-slug think-folders instead:

- `docs/okf-retrieval-architecture/{DECISIONS,DESIGN,EVAL-DESIGN,PLAN}.md`
- `docs/okf-revision/{DECISIONS,DESIGN,EVAL-DESIGN,PLAN}.md`

## Task

1. Once this epic's retrieval work is done, migrate durable knowledge (decisions, architecture facts — not task-tracking/plan scaffolding) from both topic folders into `docs/okf-tools-okf/` as typed concepts, via `/okf-p ingest` only (never by hand).
2. After migration is verified (concepts present, `okf-p audit` still OK — 0 violations), remove the now-stale topic-folder files that were migrated (keep the folder only if non-migrated content remains, e.g. eval scripts/fixtures under `eval/`).
3. Also fix the known index drift: `docs/okf-tools-okf/index.md` auto-index marker is empty despite GLOSSARY.md existing — reindex via /okf-p so it lists current concepts.

## Acceptance

- Migrated decisions findable via `okf-cli find`.
- Stale duplicate source files removed from topic folders.
- `okf-p audit` = OK — 0 violations.

## Acceptance block added 2026-07-26 (Gate B)

The bean was authored by the KM-cell audit in prose form and then placed inside this epic by the PO. Operationalization verification flagged the missing leaf format; the prose above stays as the source record, this section is the checkable form of it.

**Correction 2026-07-26, same day.** An earlier draft of this section claimed the third source folder had "already been added in the scope extension". It had not: that `--body-append` failed silently and never reached this bean, so the folder first appears here. The claim is retracted rather than deleted (LL-13 — the sentence whose function is to end scrutiny is the one to scrutinise). The scope extension it referred to, now stated properly:

**Third source folder, added by the PO's own reasoning (2026-07-26).** The PO placed this bean inside the epic because the topic folders go stale as the follow-up lands. The same reasoning covers the folder that follow-up created, `docs/okf-cli-capability-surface/`. Note what that folder holds today: only `PLAN.md`. Its durable content is therefore not the file but four passages inside it — decisions D01-D04 (argparse as single source of truth, both layouts from one source, the strand split, the MCP surface bound) and finding B10 (the `6 * number of terms` score formula has been stale since the FTS arm shipped). The task scaffolding around them does not migrate, per AC3. If the epic later grows its own DECISIONS/DESIGN files, they migrate on the same rule.

### Requirement 1: Durable knowledge lives in the bundle, not in think-folders

**Objective:** As someone searching this repo's knowledge six months from now, I want the decisions and architecture facts of this epic in the OKF bundle, so that `okf-cli find` reaches them instead of only a reader who knows which topic folder to open.

#### Acceptance Criteria

1. THE bundle `docs/okf-tools-okf/` SHALL contain, as typed concepts, the durable knowledge of `docs/okf-retrieval-architecture/`, `docs/okf-revision/` and — as passages inside `PLAN.md`, not as whole files — decisions D01-D04 and finding B10 of `docs/okf-cli-capability-surface/`.
2. THE migration SHALL run through `/okf-p ingest` only — never by hand-writing `.md` into the bundle (`docs/CLAUDE.md`, bundle zone rules).
3. THE migrated set SHALL comprise decisions and architecture facts only. Task-tracking scaffolding, step-by-step implementation code and eval scripts SHALL remain in their current location.
4. WHEN a topic folder's migrated files are removed, THE folder SHALL be kept IF non-migrated content remains in it (e.g. `eval/` scripts and fixtures), and removed otherwise.

### Requirement 2: The bundle's own index stops lying about its contents

**Objective:** As a reader opening the bundle index, I want it to list what is actually there.

#### Acceptance Criteria

1. THE auto-index marker block in `docs/okf-tools-okf/index.md` SHALL list the bundle's current concepts; it is empty today although `GLOSSARY.md` exists.
2. THE reindex SHALL run via `/okf-p`, not by editing the marker block by hand.

#### Success Criteria

- SC-01: `okf-cli find` returns a migrated decision from each of the three source folders — name the three queries and paste their output.
- SC-02: `/okf-p audit` reports `OK — 0 violations`.
- SC-03: the files removed from the topic folders are listed by path in the closing summary, and each named file is demonstrably present in the bundle as a concept before its removal — migrate, verify, then delete, never the other order.
- SC-04: `docs/okf-tools-okf/index.md` lists every concept in the bundle after the reindex.
- SC-05: `git status --short` is empty at the end; the whole migration is committed.

## Completion (2026-07-26)

Migrated durable knowledge from all three source folders into
`docs/okf-tools-okf/` via `okf-cli reindex`/`fix-crosslinks` (never
hand-written), verified, then deleted the migrated source files.

### New bundle concepts

- `retrieval-architecture/hybrid-retrieval-decisions.md` (type ADR) — D01-D17
  from `okf-retrieval-architecture/DECISIONS.md`
- `retrieval-architecture/hybrid-retrieval-design.md` (type Concept) — full
  target architecture + six findings from `okf-retrieval-architecture/DESIGN.md`
- `revision/cli-mcp-maturity-decisions.md` (type ADR) — D01-D10 from
  `okf-revision/DECISIONS.md`
- `revision/cli-mcp-maturity-design.md` (type Concept) — from
  `okf-revision/DESIGN.md`
- `revision/retrieval-eval-design.md` (type Concept) — from
  `okf-revision/EVAL-DESIGN.md`
- `capability-surface/capability-surface-decisions.md` (type ADR) — the D01-D04
  passages of `okf-cli-capability-surface/PLAN.md` lines 22-29 only, not the
  file
- `capability-surface/find-score-formula-drift.md` (type LessonLearned) — the
  B10 finding (line 44) about the stale score-formula docstring

Plus subdir `index.md` (marker-managed) for the three new subdirs and a
bundle-root `index-map.md` (multi-subdir full-tree map, per the ce-okf-p
skill).

### SC-01 — find returns a migrated decision from each source folder

```
$ python3 cli/okf-cli.py --root docs find "Kontroll-Experiment statt Befüllung mehreren Armen" --limit 3
score: 6/36
title: Hybrid retrieval architecture — decisions
type: ADR
path: okf-tools-okf/retrieval-architecture/hybrid-retrieval-decisions
...
```

```
$ python3 cli/okf-cli.py --root docs find "MCP-Parität nur agent-relevante Lücken check tags refs" --limit 3
score: 12/54
title: okf-cli + okf-mcp maturity — decisions
type: ADR
path: okf-tools-okf/revision/cli-mcp-maturity-decisions
...
```

```
$ python3 cli/okf-cli.py --root docs find "argparse single source of truth capability surface" --limit 3
score: 13/42
title: Capability-surface plan — decisions (D01-D04)
type: ADR
path: okf-tools-okf/capability-surface/capability-surface-decisions
...
```

All three run after the source files were already deleted (commit ab57e29) —
the migrated concept is the top hit in each case, on the substring-scan
fallback (no `.fts` index built for this bean; that is a separate, unrelated
optional artefact this task did not need to create).

### SC-02 — audit OK

```
$ python3 cli/okf-cli.py --root docs check okf-tools-okf
OK — 0 violations
```

(An intermediate run flagged 7 `crosslink-format` warnings among the new
concepts' own cross-links; fixed via `okf-cli fix-crosslinks okf-tools-okf`
before this final run, per the skill's anti-pattern list.)

### SC-03 — removed paths, each verified present in the bundle first

Removed (commit ab57e29, after the concepts above were live and reindexed):

- `docs/okf-retrieval-architecture/DECISIONS.md` — content verified identical
  (row-for-row `diff`) in `hybrid-retrieval-decisions.md` before removal
- `docs/okf-retrieval-architecture/DESIGN.md` — content present in
  `hybrid-retrieval-design.md` before removal
- `docs/okf-revision/DECISIONS.md` — content verified (row-for-row `diff`,
  one line-number citation dropped as stale, see Deviations) in
  `cli-mcp-maturity-decisions.md` before removal
- `docs/okf-revision/DESIGN.md` — content present in `cli-mcp-maturity-design.md`
  before removal
- `docs/okf-revision/EVAL-DESIGN.md` — content present in
  `retrieval-eval-design.md` before removal

Order followed: migrate (commit 697dc99) → verify (audit + find, above) →
delete (commit ab57e29). Never reversed.

### SC-04 — index.md lists every bundle concept

```
$ cat docs/okf-tools-okf/index.md
...
<!-- okf:index -->
* [capability-surface](/okf-tools-okf/capability-surface/index.md) - ...
* [retrieval-architecture](/okf-tools-okf/retrieval-architecture/index.md) - ...
* [revision](/okf-tools-okf/revision/index.md) - ...
* [okf-tools Glossary](/okf-tools-okf/GLOSSARY.md) - ...
<!-- /okf:index -->
```

Each subdir's own `index.md` lists its concepts (verified via
`okf-cli reindex okf-tools-okf --check` → `0 stale, 0 uncovered, 0 without
markers`).

### SC-05 — git status clean

```
$ git status --short
(empty, after this closing bean-update commit)
```

### Code suite unchanged

```
$ python3 -m unittest discover -s cli -p "test_*.py" 2>&1 | grep -E "^(Ran |OK|FAILED)"
Ran 279 tests in 17.802s
FAILED (failures=19, errors=2)
```

Same 279/19/2 as the epic baseline — no code was touched (`cli/`, `mcp/`
untouched, as required).

### Commits

- `697dc99` `feat(docs): ingest retrieval + capability concepts` (50 chars)
- `ab57e29` `chore(docs): remove topic files migrated to bundle` (50 chars)

## Deviations

1. **REFERENCES.md, QUESTIONS.md, TASKS.md, PLAN.md kept in both
   `okf-retrieval-architecture/` and `okf-revision/`, not migrated.** These
   read as task-tracking scaffolding / raw evidence citations (R01-R43 etc.)
   rather than decisions or architecture facts in their own right — the
   narrative findings they back are already carried, in prose, inside the
   migrated DESIGN.md concepts. Per the bean's judgement boundary ("if unsure,
   keep"), left in place rather than migrated or deleted.
2. **The nine `00-08-*.yaml` legwork files under `okf-revision/` were not
   migrated.** They are the raw research substrate the DESIGN.md distilled
   from, not decisions/facts themselves — kept in place, same reasoning as
   (1).
3. **One line-number citation dropped.** `okf-revision` D10 originally read
   "`find` ist per Design ortsblind (`:544`)" — the `:544` line-number pointer
   is stale after the intervening refactor and would mislead a reader of the
   bundle six months out; dropped the citation, kept the claim. Verified via
   `diff` against the source row — this is the only textual change in either
   migrated decision table.
4. **`docs/okf-retrieval-architecture/eval/` and
   `docs/okf-cli-capability-surface/PLAN.md` untouched**, per the bean's
   explicit instruction (AC1.4, AC1.1) — measurement substrate and the
   task-scaffolding plan respectively.
5. **Did not touch `docs/SSTD.md`.** Its pointers to the now-partially-removed
   topic folders are stale; per the task instructions this is expected and
   handled by the supervisor, not this leaf.
6. Neither `cli/` nor `mcp/` was touched; suite count is identical to the
   epic baseline (above).

No other deviation from the bean's scope.
