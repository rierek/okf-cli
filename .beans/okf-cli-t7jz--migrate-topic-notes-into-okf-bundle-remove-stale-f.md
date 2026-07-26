---
# okf-cli-t7jz
title: Migrate topic notes into OKF bundle, remove stale files
status: todo
type: task
priority: normal
created_at: 2026-07-26T12:42:51Z
updated_at: 2026-07-26T13:13:28Z
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
