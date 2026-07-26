---
# okf-cli-t7jz
title: Migrate topic notes into OKF bundle, remove stale files
status: todo
type: task
priority: normal
created_at: 2026-07-26T12:42:51Z
updated_at: 2026-07-26T13:03:40Z
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
