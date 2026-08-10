---
# OKFT-g0gi
title: T06 Reach build-index, prime and info over MCP
status: completed
type: task
priority: normal
created_at: 2026-07-26T13:03:25Z
updated_at: 2026-07-26T14:11:10Z
parent: OKFT-5uog
blocked_by:
    - OKFT-z0tt
---

Plan: `docs/okf-cli-capability-surface/PLAN.md` → **Task 6**. Independent of T01-T05 except for the parity test, which consumes `COMMAND_DISPATCH` from T01.

`find` prints `run 'okf-cli build-index'` on a stale or absent index, and the audience that note was written for cannot execute it. Reproduced live at plan time against `~/Obsidian/Knowledge-Catalogue`: the stale note printed on a real query, while `mcp/okf_mcp.py:7-17` whitelists ten commands without `build-index` among them.

### Requirement 1: The remedy the tool prescribes is reachable by the audience it addresses

**Objective:** As an agent working over MCP, I want to execute the command the degradation note names, so that a note meant as a remedy is not a dead end.

#### Acceptance Criteria

1. THE MCP surface SHALL expose `build-index`, `prime` and `info` — and nothing further; the wider surface question stays open (D04, PO 2026-07-26).
2. THE `okf_build_index` tool SHALL state in its docstring that it is the remedy for the absent/stale note, local only, no network, no change to catalogue content.
3. THE `okf_find` docstring SHALL describe the two arms, the per-query ownership, the `provenance:` lines and the stderr degradations, replacing the pre-feature keyword-search text at `mcp/okf_mcp.py:79-80`.

#### Success Criteria

- SC-01: `run_okf(root, "build-index", {})` creates `<root>/.fts/fts.sqlite` and its output contains `indexed`.
- SC-02: `run_okf(root, "prime", {})` and `run_okf(root, "info", {})` return non-empty output. Both exit 0 on a catalogue lacking `CLAUDE.md`/`TYPES.md` (probed at plan time: they print `(missing: CLAUDE.md)` / `(missing: TYPES.md)`, rc=0), so no fixture seeding is needed.
- SC-03: `set(mcp._COMMANDS) - set(okf.COMMAND_DISPATCH) == set()` — every whitelisted MCP command is a real CLI command.
- SC-04: full suite at `Ran 279 tests`, exactly 19 failures / 2 errors.

**Files:** `mcp/okf_mcp.py:7-17` (`_COMMANDS`), `:79-80` (`okf_find` docstring), `_register()` (three tools) · `cli/test_okf_mcp.py` (append classes `McpAgentRemedyBoundary`, `McpSurfaceParity`)

## Steps

- [x] Write the failing `McpAgentRemedyBoundary` + `McpSurfaceParity` tests
- [x] Run them, confirm `ValueError: unsupported okf command: build-index`
- [x] Add the three `_COMMANDS` entries and the three tool wrappers
- [x] Rewrite `okf_find`'s docstring (corrected one claim against the code, see Deviations)
- [x] Full suite; commit `fix(mcp): expose build-index, prime, info` (826fcbf)

## Recommended Skills

- superpowers:test-driven-development

## Sequencing note

`blocked_by: OKFT-z0tt` is deliberate although the plan calls this task otherwise independent: `McpSurfaceParity` consumes `COMMAND_DISPATCH`, which T01 introduces. The plan permits writing the other three tests first and adding the parity class later; the stricter dependency was chosen so no leaf ever ships with a weakened test. If T01 stalls, relax this and add `McpSurfaceParity` in a follow-up commit — do not replace it with a hardcoded command list.



## Prelude from the T01-T05 reviews (2026-07-26, non-blocking)

1. **If plan text and plan test disagree, adapt the text and keep the test.** T03 hit this: PLAN.md's literal replacement string started a sentence with capital `Measured` while the plan's own test asserted the case-sensitive substring `"measured"`. The implementer joined the clauses with a semicolon and left the test untouched. Weakening a plan-authored test to accept plan-authored text is a defect, not a fix.
2. **Your Step 1 has an ordering condition the plan states explicitly.** `McpSurfaceParity` consumes `COMMAND_DISPATCH` from Task 1. Task 1 HAS landed (commit 67f7b3e, reviewed APPROVED), so write the class as the plan wrote it. Do not weaken it to a hardcoded command list.
3. **Task 5's gate has a known hole and it is already filed** as bug `OKFT-x60r` (top-level parser options escape `CommandHelpConformance`). Do not fix it here and do not treat it as your finding — it is out of your scope.
4. The 50-character subject cap applies to EVERY commit, the bean-close meta commit included. No `commit-msg` hook exists in `.git/hooks/`; nothing catches an overrun.
5. For any before/after proof, snapshot with `git show <rev>:<path> > /tmp/<x>.py` and diff. Do not use `git stash`.



## Summary

`_COMMANDS` in `mcp/okf_mcp.py:7-20` gained three entries — `build-index`, `prime`, `info`, all `([], False)` since none takes a positional or supports `--json`. `_register()` (`mcp/okf_mcp.py:152-173`, after the change) gained the three tool wrappers `okf_build_index`, `okf_prime`, `okf_info`, added byte-for-byte from the plan's Step 4. `okf_find`'s docstring at `mcp/okf_mcp.py:80-92` was replaced (Step 5), with one correction against the plan's literal text — see Deviations. `cli/test_okf_mcp.py` gained `McpAgentRemedyBoundary` (3 tests) and `McpSurfaceParity` (1 test), both byte-for-byte from the plan's Step 1.

## Test-Output

Step 2 — RED, observed failures match the plan's prediction literally:

```
$ rm -rf cli/__pycache__ mcp/__pycache__
$ python3 -m unittest cli.test_okf_mcp.McpAgentRemedyBoundary -v
test_build_index_reaches_the_cli_and_writes_the_index ... ERROR
test_info_reaches_the_cli ... ERROR
test_prime_reaches_the_cli ... ERROR

ValueError: unsupported okf command: build-index
ValueError: unsupported okf command: info
ValueError: unsupported okf command: prime

FAILED (errors=3)
```

Step 6 — GREEN, module suite:

```
$ rm -rf cli/__pycache__ mcp/__pycache__
$ python3 -m unittest cli.test_okf_mcp -v 2>&1 | tail -5
Ran 16 tests in 1.334s

OK
```

SC-04 — full suite:

```
$ python3 -m unittest discover -s cli -p "test_*.py" 2>&1 | grep -E "^(Ran |OK|FAILED)"
Ran 279 tests in 18.597s
FAILED (failures=19, errors=2)
```

279 = 275 baseline (post-T05) + 4 new tests (3 `McpAgentRemedyBoundary` + 1 `McpSurfaceParity`). 19 failures / 2 errors unchanged from baseline — no new failure, none silenced.

Smoke test of the real remedy loop, against a disposable temp catalogue (never the live one): `find` on an absent index prints on stderr `note: lexical index absent -- falling back to substring scan; run okf-cli build-index for BM25 ranking`; `mcp.run_okf(root, "build-index", {})` then created `<tmp>/.fts/fts.sqlite` and returned `indexed 1 concept(s) -> <tmp>/.fts/fts.sqlite`. The note-and-remedy loop the requirement targets is closed and reachable end to end through the MCP wrapper.

Live-catalogue non-interference check: `~/Obsidian/Knowledge-Catalogue/.fts/fts.sqlite` mtime was `2026-07-26 16:08:26` both before and after the full suite run and the smoke test (a concurrent, unrelated process had already written it earlier in the session — confirmed by `ps aux` showing a separate long-running supervisor process, and by `grep -rn Knowledge-Catalogue cli/ mcp/` finding no test that operates on that literal path, only one config-string assertion in `test_okf_cli.py` that never touches disk there). `git -C ~/Obsidian/Knowledge-Catalogue status --short` printed nothing; that repo received no write from this task.

Commit: `fix(mcp): expose build-index, prime, info` (826fcbf, 41 characters).

## Deviations

One correction against the plan's literal Step 5 text, made because the task instructions required verifying the new `okf_find` docstring against the code before shipping it (the epic already caught one stale claim of this kind, B10). The plan's sentence "Every result line names its origin as `provenance: lexical` or `provenance: semantic (cosine=...)`" is not true of `cmd_find`'s print loop (`cli/okf-cli.py:1221-1238`): every hit dict carries an internal `provenance` field (`_hydrate_hit`, `cli/okf-cli.py:809-825`), but the loop only ever prints a `provenance:` output line `if h.get("provenance") == "semantic"` (`:1229-1230`) — a lexical hit never gets a printed provenance line at all. Shipping the plan's sentence unchanged would have put a false claim into the contract an MCP consumer relies on. Replaced with: "A semantic-arm result line carries `provenance: semantic (cosine=...)`; a line with no such marker came from the lexical arm." — true of the code as it stands, and it still lets a consumer distinguish the two arms per result line, which is what the requirement (AC3) asks for.

No other deviation. D04's boundary (`build-index`, `prime`, `info`, nothing further) was kept exactly; no fourth command was added. `cli/okf-cli.py` was not touched.
