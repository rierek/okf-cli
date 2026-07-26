---
# okf-cli-2o39
title: MCP drops stderr, so agents never see degradation notes
status: completed
type: bug
priority: high
created_at: 2026-07-26T15:09:51Z
updated_at: 2026-07-26T16:52:00Z
parent: okf-cli-iksi
---

## Origin

Side finding (NB) from the PO review of epic okf-cli-5uog, 2026-07-26. Found live while testing US-08 over a restarted MCP server. The user stories were accepted; this was recorded as a separate defect to rework.

## The defect

`run_okf` (`mcp/okf_mcp.py:69-75`) passes only stdout back to the caller. On a successful run stderr is discarded:

    proc = subprocess.run([...], capture_output=True, text=True)
    if proc.returncode != 0 and command != "check":
        raise RuntimeError("okf-cli {} failed: {}".format(command, proc.stderr.strip()))
    out = proc.stdout
    ...
    return out

Every degradation note the CLI emits goes to stderr. An MCP consumer therefore receives none of them.

## Why it matters

This halves the fix that epic okf-cli-5uog shipped for B07. That finding read: an agent is told to run `okf-cli build-index` and cannot. Leaf okf-cli-g0gi made the command reachable, so the agent can now act — but it is no longer told to, because the note never arrives.

The same leaf shipped a docstring on `okf_find` stating "Degradations are announced on stderr and never fail the call". True of the CLI, and the reviewer verified it there. From inside MCP it points at a channel the consumer cannot observe, so as written it is a promise the interface does not keep.

## Live evidence, 2026-07-26

Direct CLI call against the live catalogue, stderr shown:

    $ python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue find "worktree isolation" --limit 1 2>&1 >/dev/null
    note: lexical index is stale (catalogue changed since build) -- run `okf-cli build-index`

The same query through `okf_find` in the same minute returned ranked hits and no note at all. The index was genuinely stale at that moment: `okf_build_index` then reported `indexed 2470 concept(s)`, and the direct call stopped emitting the note afterwards.

## Scope note

`run_okf` is pre-existing code. Leaf okf-cli-g0gi did not touch it and PLAN.md never raised it, so this is not a regression of that work — it is a gap the work made visible.

## Open design question for the fix

Where the notes should surface is not obvious and should not be decided by the implementer alone. Candidates: prepend them to the returned text, return a structured payload separating results from notes, or expose them only on the tools whose output is degraded. Whichever is chosen has to keep `--json` commands parseable — `run_okf` currently feeds stdout straight into `json.loads`, so anything mixed into stdout breaks them.

Note also that `check` is already special-cased (exit 1 is data, not a crash); a fix must not disturb that path.



## D01 — Design decision by the PO, 2026-07-26

The notes are prepended to the text result. The `--json` path stays untouched.

Concretely: for commands whose `supports_json` flag is false, `run_okf` prepends whatever the CLI wrote to stderr to the stdout text it returns. For commands that do support JSON, nothing changes — `run_okf` feeds their stdout straight into `json.loads`, and mixing anything in would break every consumer of those tools.

Rejected alternatives, with the reason: a structured `{results, notes}` payload for every tool was rejected as a breaking change for every existing MCP consumer and for the JSON paths. Wiring the notes only into `okf_find` was rejected because the rule would stop being uniform — any tool that can degrade should report it the same way.

Two constraints the fix must respect: `check` is special-cased today (exit 1 is data, not a crash) and that path must keep working; and the `--json` commands must remain parseable, which is the reason for the split above.



### Requirement 1: Degradation notes reach the MCP consumer

**Objective:** As an agent calling okf_find over MCP, I want the degradation notes the CLI emits, so that I can act on the remedy they name instead of silently working against a degraded index.

#### Acceptance Criteria

1. WHEN the CLI writes a note to stderr AND the invoked command does not support JSON output, THE MCP wrapper SHALL return that note to the caller together with the command's stdout.
2. THE note text SHALL precede the command's stdout in the returned string.
3. THE MCP wrapper SHALL leave the return value of every JSON-supporting command byte-identical to its current behaviour, so that json.loads keeps parsing it.
4. IF the CLI writes nothing to stderr THEN THE MCP wrapper SHALL return the stdout text unchanged.
5. THE existing special case for check SHALL keep working: an exit code of 1 from check is data, not a crash, and SHALL NOT raise.
6. WHEN a command exits non-zero and is not check, THE MCP wrapper SHALL keep raising RuntimeError with the stderr text, as it does today.

#### Success Criteria

- SC-01: A boundary test drives okf_find against a fixture catalogue with no lexical index and asserts that the returned value contains the stale-or-absent note. The test fails if the note is dropped — demonstrate this by observing it red before the fix.
- SC-02: A boundary test asserts that a JSON-supporting command still parses, with a note present on stderr during the same call.
- SC-03: The full suite reads exactly 19 failures and 2 errors plus the tests added by this leaf, all green.
- SC-04: The okf_find docstring's degradation sentence is re-read against the shipped behaviour and is true of it, or is corrected in the same commit.

_Requirements: R-01_

## Recommended Skills

- superpowers:test-driven-development
- superpowers:systematic-debugging

## Summary

`run_okf` (`mcp/okf_mcp.py`) now prepends the CLI's stderr text to the returned
stdout text for every command whose `supports_json` is false (D01). JSON-
supporting commands are untouched: their stdout still feeds `json.loads`
directly. The `okf_find` docstring's degradation sentence was corrected in
the same commit (SC-04) — see Deviations/ERRATA below.

Changed:
- `mcp/okf_mcp.py`: `run_okf` gains `if proc.stderr: return proc.stderr + out`
  right before the final `return out`, plus a docstring note explaining D01.
  `okf_find`'s docstring degradation sentence rewritten to point at the
  returned text instead of stderr.
- `cli/test_okf_mcp.py`: two new test classes,
  `McpFindDegradationNoteBoundary` (SC-01) and
  `McpJsonCommandParsesDespiteStderrNote` (SC-02).

Commit: `44720b6` — `fix(mcp): surface stderr degradation notes`.

## Test-Output

RED (SC-01, before the fix, `python3 -m unittest cli.test_okf_mcp.McpFindDegradationNoteBoundary -v`):

```
test_find_returns_absent_note_ahead_of_stdout (cli.test_okf_mcp.McpFindDegradationNoteBoundary.test_find_returns_absent_note_ahead_of_stdout) ... FAIL

======================================================================
FAIL: test_find_returns_absent_note_ahead_of_stdout (cli.test_okf_mcp.McpFindDegradationNoteBoundary.test_find_returns_absent_note_ahead_of_stdout)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/Users/erik/Obsidian/tools/okf-tools/cli/test_okf_mcp.py", line 194, in test_find_returns_absent_note_ahead_of_stdout
    self.assertIn("note: lexical index absent", out)
    ~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 'note: lexical index absent' not found in '------\nscore: 4/6\ntitle: One\ntype: Runbook\npath: b/one\ndescription: first\nbody-snippet: # One…\n------\n'

----------------------------------------------------------------------
Ran 1 test in 0.077s

FAILED (failures=1)
```

GREEN (same test, after the fix):

```
test_find_returns_absent_note_ahead_of_stdout (cli.test_okf_mcp.McpFindDegradationNoteBoundary.test_find_returns_absent_note_ahead_of_stdout) ... ok

----------------------------------------------------------------------
Ran 1 test in 0.077s

OK
```

Full boundary suite (`python3 -m unittest cli.test_okf_mcp -v`), all 18 green
(16 pre-existing + 2 new — SC-01 and SC-02):

```
Ran 18 tests in 1.245s

OK
```

Full-gate command (`python3 -m unittest discover -s cli -p "test_*.py" 2>&1 | grep -E "^(Ran |OK|FAILED)"`):

```
Ran 281 tests in 18.114s
FAILED (failures=19, errors=2)
```

281 = the baseline 279 plus the 2 new tests; failures=19/errors=2 is the
unchanged pre-existing count named in the epic's baseline (all in the
crosslink suites — `CheckCommand`, `FixCrosslinksCommand`, `RefMatrix`,
`RenameConcept`, `ResolveCrosslinkTarget`, `RewriteCrosslinksInBody` — none
of which touch `mcp/okf_mcp.py` or `run_okf`). Confirmed by listing the
failing/erroring test names with `-v` and diffing against the epic's stated
baseline scope; no new test appears among them. SC-03 met.

## Smoke

Manual end-to-end run against a real tmp catalogue (real subprocess to
`cli/okf-cli.py`, no mocks), reproduced live:

```
=== find (degraded, no index) ===
'note: lexical index absent — falling back to substring scan; run `okf-cli build-'
=== find (index built, fresh) ===
'note: semantic arm skipped (.tagvec cache/concept embeddings absent) — lexical r'
=== list --json ===
<class 'list'> [{'title': 'One', 'type': 'Runbook', 'path': 'b/one', 'description': 'first'}]
=== prime (no stderr expected) ===
'------\n(missing: CLAUDE.md)\n------\nbundles:\n(for description'
```

The `find`/degraded case shows the note prepended (AC-01/AC-02); the
`find`/index-built case shows a *different* degradation note still surfacing
correctly once the lexical arm is healthy but the semantic arm is not; the
`list --json` case shows the JSON path parses untouched (AC-03); the `prime`
case shows no note is added when the CLI writes nothing to stderr (AC-04).

## Deviations/ERRATA

SC-04: the `okf_find` docstring said "Degradations are announced on stderr
and never fail the call". That sentence was the defect this leaf fixes — it
was true of the CLI in isolation but false of the shipped MCP tool's
observable behaviour, since an MCP consumer never sees the wrapper's raw
stderr, only the tool's return value. After the fix the note is no longer
purely "on stderr" from the consumer's vantage point — it is folded into the
returned text. Corrected in the same commit to: "Degradations never fail the
call and are announced as a note prepended to the returned text (okf-cli-2o39,
D01 — the CLI itself writes them to stderr, which run_okf folds into this
tool's return value): ...". No other deviation from D01 or the task's scope
boundary — only `mcp/okf_mcp.py` (`run_okf` + the `okf_find` docstring) and
`cli/test_okf_mcp.py` were touched; `cli/okf-cli.py` was read for evidence
(confirming which JSON-supporting commands can/cannot emit stderr on a clean
exit) but not modified.

One note on SC-02's test design: no JSON-supporting command in the current
CLI both exits 0 and writes to stderr on a clean run (checked by reading the
full bodies of `cmd_check`, `cmd_list`, `cmd_index`, `cmd_refs` — `cmd_list`'s
only stderr write exits 1, `cmd_refs`'s only stderr write exits 2; neither is
a clean-exit path). SC-02's own wording ("byte-identical... behaviour") is a
guarantee about `run_okf`'s branching logic, not about a CLI behaviour that
exists today, so `McpJsonCommandParsesDespiteStderrNote` stubs
`subprocess.run` via `mock.patch.object(mcp, "subprocess", ...)` — patching
only the `mcp` module's own name binding, not the real `subprocess` module
(which `fastmcp` also imports) — rather than driving a real CLI code path
that does not exist. This is a deliberate, scoped exception to this repo's
usual "real subprocess, no mocks" boundary-test convention (see
`cli/test_okf_mcp.py`'s file docstring); flagging it explicitly rather than
letting it pass silently.

## Notes for T(n+1)

- The `okf_find` docstring correction (SC-04) is now current as of this
  commit. If `run_okf`'s note-surfacing mechanism changes again, re-check
  that sentence — this is exactly the LL-15 failure class (product-facing
  prose whose truth condition is the code).
- Out-of-scope finding, not fixed here (belongs in a separate bean if the PO
  wants it tracked): `mcp/okf_mcp.py`'s `run_okf` prepends stderr **verbatim**
  (no stripping/formatting), so if the CLI ever emits multiple stderr lines
  for one non-JSON call, all of them land in the return value in CLI order,
  with no separator guarantee beyond whatever the CLI itself already put
  between them (each `print(..., file=sys.stderr)` call ends in `\n`). This
  matches D01's literal instruction ("prepends whatever the CLI wrote to
  stderr") and every acceptance criterion, so it is not a defect against this
  leaf's spec — only naming it because a future consumer parsing the returned
  text programmatically (rather than reading it) would need to know the note
  is not delimited from stdout by anything more than the stderr text's own
  trailing newline.
