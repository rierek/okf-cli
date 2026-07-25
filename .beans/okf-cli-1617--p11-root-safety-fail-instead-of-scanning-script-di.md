---
# okf-cli-1617
title: 'P11 — Root-safety: fail instead of scanning script dir'
status: todo
type: task
priority: normal
created_at: 2026-07-25T18:13:10Z
updated_at: 2026-07-25T18:13:10Z
parent: okf-cli-5hg4
blocked_by:
    - okf-cli-5qmn
---

## Objective (User Story)
As a user, I want okf-cli to refuse to run against an accidental root so that it never silently scans its own script directory as if it were a catalogue.

## EARS Acceptance
- WHEN no `--root` is passed AND no catalogue is auto-detectable, THE CLI SHALL hard-fail with a clear message naming `--root` (never silently scan the script dir).
- WHEN `--root` is passed, THE behavior SHALL be unchanged.
- Auto-detect: if cwd (or ancestor) contains catalogue markers (SPEC.md + TYPES.md at root, or a .okf.toml), use it; else fail.

## Success Criteria
- SC-001: no-root + no-catalogue -> SystemExit, message mentions `--root`.
- SC-002: `--root` path behavior unchanged (existing tests green).
- SC-003: marker auto-detect picks up a valid catalogue from cwd.

## Affected code
- `cli/okf-cli.py:72-73` rewrite `catalogue_root`; `:1981-1984` fail on None.
- Test: `cli/test_okf_cli.py`
Full steps: PLAN.md Task 11.
Commit: `fix(cli): fail on missing root instead of scanning script dir`
