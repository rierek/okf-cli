---
# okf-cli-83vq
title: 'P1 — Fix B01: --json contract for index + list'
status: in-progress
type: task
priority: normal
tags:
    - to-review
created_at: 2026-07-25T18:13:09Z
updated_at: 2026-07-25T18:34:18Z
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


## Summary

Fixed B01: `okf-cli.py index` and `list` argparse subparsers lacked `--json`,
while `mcp/okf_mcp.py` marks both as `supports_json=True` and unconditionally
appends `--json` to argv. Every MCP call to `okf_index`/`okf_list` raised
`RuntimeError` (argparse rejected the unknown flag, non-zero exit). Added
`--json` to both parsers, plus a JSON branch in `cmd_index` (bundle arg:
`{bundle, concepts:[{id,title,type,description}]}`; no arg:
`{bundles:[{bundle, concepts:[...]}]}`) and in `cmd_list`
(`[{title,type,path,description}, ...]`). Non-JSON paths are untouched (early
return before the existing print logic).

## Test-Output

Baseline (before fix, full suite, pre-existing per Wave A briefing):
```
Ran 98 tests in 0.057s
FAILED (failures=19, errors=2)
```

RED (new tests, before implementation — 4/6 error with JSONDecodeError since
`args.json` / `--json` did not exist yet):
```
ERROR: test_json_output_is_parseable_array (test_okf_cli.CmdListJson...)
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
ERROR: test_json_output_with_bundle_is_parseable_object (test_okf_cli.CmdIndexJson...)
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
ERROR: test_json_output_without_bundle_is_parseable_object (test_okf_cli.CmdIndexJson...)
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
Ran 6 tests ... FAILED (errors=4)
```

GREEN (new tests, after implementation):
```
Ran 6 tests in 0.005s
OK
```

After (full suite, post-fix):
```
Ran 104 tests in 0.059s
FAILED (failures=19, errors=2)
```
Delta: +6 tests, all green; failures/errors unchanged (19/2) — same
pre-existing baseline, no new regressions.

## Smoke

Real catalogue, read-only (`~/Obsidian/Knowledge-Catalogue`):
```
$ python3 okf-cli.py --root ~/Obsidian/Knowledge-Catalogue list --type Concept --json | python3 -c "..."
parsed ok, count= 865
$ python3 okf-cli.py --root ~/Obsidian/Knowledge-Catalogue index dev-wiki --json | python3 -c "..."
parsed ok, bundle= dev-wiki concepts= 192
```
Also exercised the actual regression path through `mcp/okf_mcp.run_okf`
directly (not just the CLI):
```
r1 = okf_mcp.run_okf(root, 'list', {'type': 'Concept'})   -> list, len=865
r2 = okf_mcp.run_okf(root, 'index', {'bundle': 'dev-wiki'}) -> dict, keys=['bundle','concepts']
```
Both previously raised `RuntimeError: okf-cli {cmd} failed: ...` (argparse
`unrecognized arguments: --json`); now succeed end-to-end.

## Deviations/ERRATA

- Bean-closure status: dispatch instructions said `beans update -s completed`;
  the Implementer role definition (leaf-autonomy loop, D11) says the
  implementer must NOT set `completed` — only tag `to-review`, since the
  PO-Gate sits at Epic/Milestone review, not the leaf. Followed the role
  definition: tagged `to-review`, left status as `in-progress` (no valid
  `to-review` status enum value exists in `beans update -s`; only
  todo/in-progress/draft/completed/scrapped).
- Test helpers `_make_tmp_catalogue()`/`_capture_stdout()` sketched in
  PLAN.md Task 1 do not exist in `test_okf_cli.py`; used the repo's actual
  existing pattern instead (`tempfile.mkdtemp()` + `io.StringIO()` +
  `contextlib.redirect_stdout`, as used by `CmdPrimeBundleListing` and
  others) for consistency with the rest of the test file.
- No other deviations from bean SC-001/SC-002/SC-003 or PLAN.md Task 1 steps.

## Notes for T(n+1)

- `json` module was not previously imported in `cli/okf-cli.py` — added at
  the top of the import block (P6 / any future JSON-producing verb can rely
  on it now).
- The MCP-level regression (`okf_mcp.run_okf` raising `RuntimeError`) is now
  directly verified fixed, not just the CLI surface — useful groundwork for
  P6 (Integration tests at MCP->subprocess boundary), which can reuse the
  same `okf_mcp.run_okf(root, 'list'/'index', {...})` smoke pattern as a
  starting point.
- `index --json` and `list --json` shapes are stable per bean SC and PLAN.md
  Task 1 Interfaces section: `list` -> flat array of
  `{title,type,path,description}`; `index <bundle>` ->
  `{bundle, concepts:[{id,title,type,description}]}`; `index` (no bundle) ->
  `{bundles:[{bundle, concepts:[...]}]}`.
