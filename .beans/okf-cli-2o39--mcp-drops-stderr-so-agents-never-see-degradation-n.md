---
# okf-cli-2o39
title: MCP drops stderr, so agents never see degradation notes
status: todo
type: bug
priority: high
created_at: 2026-07-26T15:09:51Z
updated_at: 2026-07-26T16:43:26Z
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
