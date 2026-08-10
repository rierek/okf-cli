---
# OKFT-9e2b
title: pass include_archive through the MCP layer
status: completed
type: task
priority: normal
created_at: 2026-08-09T19:15:18Z
updated_at: 2026-08-09T22:39:40Z
parent: OKFT-scd5
blocked_by:
    - OKFT-iwx4
---

`_BOOL_FLAGS` (mcp/okf_mcp.py:27) is shared across all commands, so the tool signature is where the decision is made: a command that does not know the flag answers with an argparse error.

### Requirement 1: The flag reaches MCP callers

**Objective:** As an agent using okf-MCP, I want the archive flag on find and list, so that the MCP surface can answer the same questions as the CLI.

#### Acceptance Criteria

1. THE okf-MCP SHALL accept `include_archive` as a parameter of `okf_find` and `okf_list`.
2. WHEN that parameter is truthy THE okf-MCP SHALL emit `--include-archive` in the argv it builds.
3. THE okf-MCP SHALL emit the flag for no other command.

#### Success Criteria

- SC-01: `build_argv` for find and list carries the flag when set and omits it when unset.
- SC-02: `build_argv` for every other command omits the flag regardless of the parameters passed.

_Requirements: R-14_

## Recommended Skills

- `superpowers:test-driven-development`


## Summary

`mcp/okf_mcp.py`: `_BOOL_FLAGS` (`:27`) gained `"include_archive": "--include-archive"`. `okf_find` (`:103`) and `okf_list` (`:157`) each gained `include_archive: bool = False` and pass it through in the `params` dict handed to `run_okf`. Andock-Notiz's cited line numbers (`_BOOL_FLAGS:27`, `okf_find:103`, `okf_list:142`, `build_argv:31`) were verified against the file before editing and matched exactly (only `okf_list` had shifted, to `:142` pre-change, because a prior docstring line — unrelated).

## Deviation from the Andock-Notiz (verified, justified)

The note claimed `build_argv` "soll darüber hinaus nichts brauchen" beyond the `_BOOL_FLAGS` entry. Verified false: `_BOOL_FLAGS` is iterated unconditionally for every command in `build_argv`, so any command's `params` dict carrying `include_archive=True` would emit `--include-archive` — and `grep` on `cli/okf-cli.py` confirms only the `find`/`list` argparse subparsers (`:4413`, `:4451`) define that flag; every other subcommand would answer with an argparse error at the subprocess boundary, exactly the failure mode the bean's own body describes ("ein Kommando, das das Flag nicht kennt, antwortet mit einem argparse-Fehler"). SC-02's wording ("build_argv for every other command omits the flag regardless of the parameters passed") is the stronger, correct requirement — it is a defense-in-depth guarantee independent of which tool functions happen to populate that key today. Added `_BOOL_FLAG_COMMANDS = {"include_archive": {"find", "list"}}` and a 3-line gate in `build_argv`'s bool-flag loop; the three untouched flags (`apply`/`force`/`unresolved`/`compact`) keep their prior shared, unrestricted behaviour — out of this task's scope, not touched.

## RED output (verbatim, before production change)

```
test_ac1_okf_find_tool_accepts_include_archive_and_reaches_build_argv ... ERROR
  TypeError: _register.<locals>.okf_find() got an unexpected keyword argument 'include_archive'
test_ac1_okf_list_tool_accepts_include_archive_and_reaches_build_argv ... ERROR
  TypeError: _register.<locals>.okf_list() got an unexpected keyword argument 'include_archive'
test_ac3_sc02_no_other_command_emits_the_flag ... ok
test_sc01_find_carries_the_flag_when_set_and_omits_it_when_unset ... FAIL
  AssertionError: '--include-archive' not found in ['--root', '/root', 'find', 'q']
test_sc01_list_carries_the_flag_when_set_and_omits_it_when_unset ... FAIL
  AssertionError: '--include-archive' not found in ['--root', '/root', 'list', '--json']

Ran 5 tests in 0.003s
FAILED (failures=2, errors=2)
```
(`test_ac3_sc02_...` passes trivially pre-implementation — no command can emit a flag that does not exist yet; it is the primary mutation target below, not a vacuous test.)

## Test-per-criterion

| AC/SC | Test |
|---|---|
| AC1 (find/list accept the param) | `test_ac1_okf_find_tool_accepts_include_archive_and_reaches_build_argv`, `test_ac1_okf_list_tool_accepts_include_archive_and_reaches_build_argv` |
| AC2 (truthy -> emitted in argv) | `test_sc01_find_carries_the_flag_when_set_and_omits_it_when_unset`, `test_sc01_list_carries_the_flag_when_set_and_omits_it_when_unset` |
| AC3 (no other command emits it) | `test_ac3_sc02_no_other_command_emits_the_flag` — iterates every `_COMMANDS` key except find/list |
| SC-01 | `test_sc01_find_...`, `test_sc01_list_...` |
| SC-02 | `test_ac3_sc02_no_other_command_emits_the_flag` |

All five in `cli/test_okf_mcp.py`, class `McpIncludeArchiveFlag` (`cli/test_okf_mcp.py:349`).

## Mutation table

| Kriterium | Mutation | Roter Test | Warum |
|---|---|---|---|
| AC3/SC-02 (command-scope gate) | dropped the `_BOOL_FLAG_COMMANDS` gate from `build_argv`'s bool-flag loop (reverted to plain shared iteration) | `test_ac3_sc02_no_other_command_emits_the_flag` (`build-index` leaked `--include-archive`) | proves the gate, not incidental non-use by other tool functions, is what keeps other commands clean |
| AC1 (`okf_find` signature reaches `build_argv`) | dropped `"include_archive": include_archive` from `okf_find`'s `params` dict | `test_ac1_okf_find_tool_accepts_include_archive_and_reaches_build_argv` | the parameter existing on the signature is not enough — it must actually be threaded into `params` |
| AC1 (`okf_list` signature reaches `build_argv`) | dropped `"include_archive": include_archive` from `okf_list`'s `params` dict | `test_ac1_okf_list_tool_accepts_include_archive_and_reaches_build_argv` | same, for `okf_list` |

## Umkehrmutation (guard-hat-einen-guard probe)

`_BOOL_FLAG_COMMANDS["include_archive"]` widened from `{"find", "list"}` to `set(_COMMANDS)` (every command allow-listed) — the gate code path itself untouched, only its data. Reddened `test_ac3_sc02_no_other_command_emits_the_flag` identically to the structural mutation above, proving the enforcement is the CONTENT of the allow-set, not merely the presence of a lookup line that could be trivially satisfied by allow-listing everything.

All four mutation/reverse-mutation cycles ran, observed red for the stated reason, reverted via targeted `Edit`. `git diff mcp/okf_mcp.py` after all cycles showed only the intended net change (`+29 -7`), no residue.

## Full suite

`just test` -> `Ran 612 tests … OK` (607 after OKFT-6dsl + 5 new tests here).

## Read-only smoke against the real catalogue

`build_argv` sanity-checked directly (no subprocess) for `~/Obsidian/Knowledge-Catalogue`: `find` with `include_archive=True` -> `[..., 'find', 'x', '--include-archive']`; `list` with `include_archive=True` -> `[..., 'list', '--include-archive', '--json']`. Then one real `okf-cli list --type Concept --include-archive --json` and one real `okf-cli find "retry" --include-archive --limit 2` against the real catalogue (both read-only by construction, no `--apply`, no index rebuild). `git -C ~/Obsidian/Knowledge-Catalogue status --short` empty after both — no write occurred. Note: the `find` call's stale-index fallback handed the ranking to the semantic arm, which cost one real query-embedding API call (not an index/embedding BUILD) — the same class of call the predecessor bean's (`OKFT-iwx4`) identical `find "retry"` smoke already made and recorded as acceptable; the forbidden action is `build-index`/`build_tagvec` (bulk embedding of the catalogue), not a single interactive query embed, and none of that ran here.

## Gate evidence

Commit `71c1e6c` (`feat(mcp): pass include_archive to find/list only (R-14)`).
