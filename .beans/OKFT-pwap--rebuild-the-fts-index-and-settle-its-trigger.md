---
# OKFT-pwap
title: Rebuild the FTS index and settle its trigger
status: todo
type: task
created_at: 2026-08-13T11:07:31Z
updated_at: 2026-08-13T11:07:31Z
parent: OKFT-wmbu
blocked_by:
    - OKFT-n8xz
---

docs/.fts/fts.sqlite in lean-stack was last built 2026-07-29 - 15 days stale at time of measurement. Two topic folders created since (25 and 4 files) are absent from it, so every measurement taken against it understates the current state.

Settle what triggers a rebuild (Stop hook exists per OKFT-iaxj) and rebuild once the corpus scoping from OKFT-n8xz has landed, so the new baseline measures the fixed behaviour.
