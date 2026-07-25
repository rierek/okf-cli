---
# okf-cli-asky
title: P6 — Integration tests at MCP->subprocess boundary
status: todo
type: task
priority: normal
created_at: 2026-07-25T18:13:10Z
updated_at: 2026-07-25T18:13:10Z
parent: okf-cli-2lpu
blocked_by:
    - okf-cli-83vq
---

## Objective (User Story)
As a maintainer, I want tests that exercise the real CLI subprocess through the MCP marshalling layer so that B01-class contract breaks are caught automatically.

## EARS Acceptance
- WHEN `run_okf(root, "index", {})` and `run_okf(root, "list", {"type": X})` execute against a tmp catalogue, THE call SHALL return parsed JSON without raising.
- THE test SHALL cover each `_COMMANDS` entry with supports_json=True (index, list, check, refs) end-to-end via subprocess.

## Success Criteria
- SC-001: list + index subprocess calls return parsed JSON, no RuntimeError.
- SC-002: check + refs subprocess coverage present.
- SC-003: would FAIL on the pre-P1 CLI (note in commit body).

## Affected code
- Create `cli/test_okf_mcp.py`: import `okf_mcp.build_argv`/`run_okf` (okf_mcp.py:24,51), set `OKF_CLI`, tmp catalogue fixture.
Depends on P1 (asserts the fixed contract). Full steps: PLAN.md Task 6.
Commit: `test(mcp): integration coverage at CLI subprocess boundary`
