---
# okf-cli-asky
title: P6 — Integration tests at MCP->subprocess boundary
status: completed
type: task
priority: normal
created_at: 2026-07-25T18:13:10Z
updated_at: 2026-07-25T18:51:17Z
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


## Summary

Added `cli/test_okf_mcp.py`: integration tests that drive `okf_mcp.run_okf`
against the real `cli/okf-cli.py` subprocess (not importlib direct-call like
`test_okf_cli.py`), so a B01-class contract break in argv marshalling across
the process boundary is caught automatically. Covers all four
`supports_json=True` verbs end-to-end: `index` (no bundle + with bundle),
`list` (match + empty-filter), `check`, `refs`.

## Test-Output (RED -> GREEN)

RED (pre-P1 CLI, rev 47234f4, via ad-hoc script pointing OKF_CLI at that
revision's `okf-cli.py`):

```
list RAISED: RuntimeError okf-cli list failed: usage: okf-cli.py [-h] [--root ROOT] ...
okf-cli.py: error: unrecognized arguments: --json
index RAISED: RuntimeError okf-cli index failed: usage: okf-cli.py [-h] [--root ROOT] ...
okf-cli.py: error: unrecognized arguments: --json
```

This is the exact B01 failure (`--json` not accepted on `index`/`list`),
reproduced by calling `run_okf` the same way the test suite does.

GREEN (current, P1-fixed CLI):

```
$ python3 -m unittest cli.test_okf_mcp -v
test_check_json_over_subprocess ... ok
test_refs_json_over_subprocess ... ok
test_index_json_over_subprocess_no_bundle ... ok
test_index_json_over_subprocess_with_bundle ... ok
test_list_json_filters_by_type ... ok
test_list_json_over_subprocess ... ok

Ran 6 tests in 0.328s
OK
```

## Smoke

Baseline (main after P1, pre-existing): `python3 -m unittest cli.test_okf_cli`
-> Ran 104 tests, FAILED (failures=19, errors=2).

After (baseline + new suite): `python3 -m unittest cli.test_okf_cli cli.test_okf_mcp`
-> Ran 110 tests, FAILED (failures=19, errors=2) -- same 19 failures / 2 errors,
6 new tests all pass. No new failures or errors introduced.

## Deviations/ERRATA

- Plan's Step-1 snippet used a single `McpSubprocessBoundary` class; split
  into `McpIndexListBoundary` (SC-001) and `McpCheckRefsBoundary` (SC-002)
  sharing a `McpBoundaryTestBase` for setUp/tearDown -- clearer SC mapping,
  same coverage, no behavior change.
- RED proof (SC-003) was captured via an ad-hoc throwaway script pointing
  `OKF_CLI` at `git show 47234f4:cli/okf-cli.py` (the commit immediately
  before the B01 fix), rather than temporarily reverting the committed test
  file's `setUp`. Chosen so the committed test file's OKF_CLI pinning never
  had to be edited away and back -- the RED evidence is otherwise identical
  (same RuntimeError, same missing --json).
- Added 2 extra assertions beyond the plan's literal snippet
  (`test_list_json_filters_by_type`, `test_index_json_over_subprocess_with_bundle`)
  to also confirm empty-result JSON parses and bundle-scoped index shape --
  still within Task 6's stated scope (supports_json verb coverage), not
  scope creep.

## Notes for T(n+1)

- `cli/test_okf_mcp.py` pins `OKF_CLI` to this worktree's own
  `cli/okf-cli.py` in setUp (not the env default), so it is deterministic
  regardless of what `OKF_CLI` is set to outside the test run.
- Pre-existing baseline (19 failures + 2 errors in `test_okf_cli.py`) is
  unrelated to this task -- see P1's bean/commits for that history; not
  touched here per no-scope-creep.


## Deviations/ERRATA — correction 2026-07-25 (post-review, F01)

**The earlier "Notes for T(n+1)" claim below is WRONG and superseded:**
> "`cli/test_okf_mcp.py` pins `OKF_CLI` to this worktree's own
> `cli/okf-cli.py` in setUp (not the env default), so it is deterministic
> regardless of what `OKF_CLI` is set to outside the test run."

Reviewer (F01, blocking) found `okf_mcp.OKF_CLI` is bound from
`os.environ.get(...)` at **import time** as a module-level global
(`mcp/okf_mcp.py:47-48`), then read as a plain global inside `run_okf()` --
never re-read from `os.environ`. The test module's `importlib` load runs
before any `setUp`, so `os.environ["OKF_CLI"] = ...` in `setUp` was a no-op:
the 6 new tests were silently exercising whatever `OKF_CLI` the module
picked up at import (the installed/default path), NOT this worktree's CLI.
Reviewer proof: removing `--json` from the worktree's `list` subparser left
the old 6 tests green -- i.e. SC-003 ("would FAIL on pre-P1 CLI") was false.

**Fix (commit `5a25ac6`):** patch the module attribute directly --
`mcp.OKF_CLI = <worktree-cli-path>` in `setUp`, restored in `tearDown` --
instead of setting the environment variable. No change to `mcp/okf_mcp.py`.

**Mutation self-test (post-fix, proves the fix works):** removed `--json`
from `cli/okf-cli.py`'s `list` subparser (uncommitted), ran
`python3 -m unittest cli.test_okf_mcp -v`:

```
test_list_json_filters_by_type ... ERROR
test_list_json_over_subprocess ... ERROR
RuntimeError: okf-cli list failed: ... error: unrecognized arguments: --json
Ran 6 tests in 0.339s
FAILED (errors=2)
```

Then `git checkout -- cli/okf-cli.py` (byte-identical revert, `git status`
clean). Confirms the committed test file now genuinely targets the worktree
CLI and would have failed on the pre-fix bug.

**Full suite after fix:** `python3 -m unittest cli.test_okf_cli cli.test_okf_mcp`
-> Ran 110 tests, FAILED (failures=19, errors=2) -- same pre-existing 19/2,
all 6 new tests green.
