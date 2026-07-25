---
# okf-cli-83vq
title: 'P1 — Fix B01: --json contract for index + list'
status: todo
type: task
priority: normal
created_at: 2026-07-25T18:13:09Z
updated_at: 2026-07-25T18:13:10Z
parent: okf-cli-2lpu
---

## Objective (User Story)
As an agent using okf via MCP, I want `okf_index` and `okf_list` to return parseable JSON so that browsing the catalogue does not crash with a RuntimeError.

## EARS Acceptance
- WHEN `okf-cli.py list --type X --json` is invoked, THE CLI SHALL print a single JSON array parseable by `json.loads`, one object per matching concept.
- WHEN `okf-cli.py index <bundle> --json` is invoked, THE CLI SHALL print a single JSON object with the bundle's concepts.
- WHEN the same commands run WITHOUT `--json`, THE CLI SHALL emit the current human-readable output unchanged.

## Success Criteria
- SC-001: `list --json` output is `json.loads`-parseable (unit test).
- SC-002: `index --json` output is `json.loads`-parseable (unit test).
- SC-003: non-json output byte-identical to current (no regression).

## Affected code
- `cli/okf-cli.py:1884-1893` add `--json` to index+list parsers
- `cli/okf-cli.py:482-502` cmd_index JSON branch: `{bundle, concepts:[{id,title,type,description}]}` (bundle arg) / `{bundles:[...]}` (none)
- `cli/okf-cli.py:509-535` cmd_list JSON branch: `[{title,type,path,description}]`
- Test: `cli/test_okf_cli.py`
Root cause + full TDD steps: PLAN.md Task 1. Produces the JSON shapes consumed by P6.
Commit: `fix(cli): honor --json on index and list verbs (B01)`
