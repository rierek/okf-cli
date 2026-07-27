---
# okf-cli-iksi
title: Follow-up capability surface 2026-07-26
status: todo
type: epic
priority: normal
tags:
    - accepted
created_at: 2026-07-26T15:09:34Z
updated_at: 2026-07-26T17:08:42Z
parent: okf-cli-wuiv
---

Follow-up epic for findings raised during the PO review of okf-cli-5uog on 2026-07-26. Holds side findings (NB) and rejects that no existing leaf covers.



## Requirements

**R-01 — An MCP consumer receives the degradation notes the CLI emits.** The CLI announces a degraded run on stderr (lexical index absent or stale, embedding backend unavailable). Those notes exist to make the caller act; the MCP wrapper discards them on a successful run, so the audience that most needs them never sees one. Source: PO review of okf-cli-5uog, 2026-07-26, side finding.

**R-02 — The conformance gate covers every option the CLI exposes, including the top-level parser's own.** The gate shipped by okf-cli-80nb iterates the subcommand parsers only. The epic's claim is that an undocumented option cannot merge; as built, that holds for the 21 subcommands and not for the top level. Source: ce-specs-reviewer during the okf-cli-80nb review, 2026-07-26, confirmed by mutation.

## Shared context for both leaves

**Repo:** `/Users/erik/dev/okf-tools`, branch `main`, main-direct (repo Worktree-Weiche: solo).

**Test baseline, measured live on 2026-07-26 after the predecessor epic landed:** `python3 -m unittest discover -s cli -p "test_*.py"` gives `Ran 279 tests` with exactly `failures=19, errors=2`. All 19F/2E are pre-existing in the crosslink suites. A leaf is done only when the count is still exactly 19F/2E plus its own new tests, all green. The suite prints stdout noise, so `tail` hides the summary — use `| grep -E "^(Ran |OK|FAILED)"`.

**Constraints binding both leaves:**

- Standard library only, no install, no external CLI framework. This is the CLI's defining constraint.
- Artifact language English: commit subjects and bodies, bean titles and bodies, code comments, docstrings. Chat with the PO stays German.
- Commits: `<type>(<scope>): <subject>`, subject max 50 characters, no `Co-Authored-By` trailer. Explicit paths in `git add`, never `-A`. Note that no `commit-msg` hook exists in `.git/hooks/` — the cap is discipline, not a guard.
- `~/Obsidian/Knowledge-Catalogue` is a separate git repo: read from it, never commit into it. Its `.fts/` is gitignored, so building an index there touches nothing versioned.
- No network in any test.

**Evidence discipline (LL-13, LL-17).** A claim of the form "verified" or "behaviour-preserving" is the one to check, not the one to skip. State the command executed and quote its observed output. Two further shapes carry the same risk and are just as unwatched: the mechanism claim ("done via X" — name the tool that actually produced the artefact) and the completeness claim ("the only change" — a quantifier that requires an enumeration).

**One lesson from the predecessor epic that applies directly here (LL-15).** Prose that becomes product text — help strings, docstrings, error messages — is a claim about the code, and its truth condition is the code. The defect this epic's R-01 fixes was created exactly this way: a docstring promised "degradations are announced on stderr" and nobody checked whether that channel reaches the reader. Verify any such text against the code before shipping it.


## Non-blocking findings from the okf-cli-2o39 review, 2026-07-26

Raised by ce-specs-reviewer while reviewing okf-cli-2o39 (verdict APPROVED). Neither
is a defect against that leaf's acceptance criteria; both are recorded here for the PO
to prioritise at the review gate rather than scheduled by an agent.

**I01 — The MCP wrapper prepends stderr verbatim, with no delimiter.** mcp/okf_mcp.py:82-83
returns `proc.stderr + out`. A human reader can tell note from result; a programmatic
consumer of the returned string cannot, except by relying on the CLI's own trailing
newline. This is exactly what D01 asked for — neither AC-2 nor D01 requires a separator —
so it is a future design question, not a bug. A fixed separator line would be the fix if a
structured consumer ever emerges.

**I02 — SC-02 is covered by a stubbed subprocess, by necessity.** The test
McpJsonCommandParsesDespiteStderrNote (cli/test_okf_mcp.py:204-223) patches
subprocess.run, which departs from the convention that file states for itself at
cli/test_okf_mcp.py:2-8 ("shells out to the REAL cli/okf-cli.py"). The reason is
structural and was verified independently by the reviewer, by reading cmd_check, cmd_list,
cmd_index and cmd_refs in full: no JSON-supporting CLI command today exits 0 while writing
to stderr, so the path cannot be driven for real. If the CLI ever grows a JSON command
that can degrade on a clean exit, replace the stub with a real subprocess-driven fixture.


## Epic closure record, 2026-07-26 — ready for the PO gate

Both leaves are `completed`, each after its own green full gate and each independently
`APPROVED` by ce-specs-reviewer with a fresh mutation probe of its own (the reviewers did
not rely on the implementers' test runs). Tag `to-review` set. The epic itself is NOT
`completed` — that is the PO's call at the gate, together with the merge decision.

**R-01 — okf-cli-2o39 (high), commits `44720b6` + `bfd6f5e`.** `run_okf`
(mcp/okf_mcp.py:82-83) now prepends whatever the CLI wrote to stderr to the returned text,
for commands whose `supports_json` flag is false. JSON-supporting commands return before
that branch is reached, so their return values are byte-identical to before — verified by
control-flow reading and by a mutation that moves the branch above the early return, which
reddens the JSON test with a `JSONDecodeError`. The `check` special case (exit 1 is data)
and the RuntimeError path for other non-zero exits are untouched. Per SC-04 the `okf_find`
docstring, which had promised "announced on stderr", now describes the channel the MCP
consumer actually reads.

**R-02 — okf-cli-x60r (low), commits `8267fdb` + `807b3c8`.** `CommandHelpConformance`
gained a separate method `test_top_level_option_has_help` (cli/test_okf_cli.py:2719-2726);
the three pre-existing assertions are byte-for-byte unchanged. Stripping `--root` of its
help text now turns the suite red with `AssertionError: Lists differ: ['root'] != []`,
naming the offender; the whitespace-only case behaves identically. No option beyond
`--root` was found undocumented, so `cli/okf-cli.py` was not modified at all
(md5 unchanged at `9147b341e630be011f15ff8965b022e1`).

**Evidence.** Full suite, run by the supervisor after both leaves landed:
`python3 -m unittest discover -s cli -p "test_*.py"` gives `Ran 282 tests` with exactly
`failures=19, errors=2`. The arithmetic reconciles: 279 baseline + 2 (R-01) + 1 (R-02).
The 19F/2E were confirmed by name in the reviews to be the pre-existing crosslink-suite
failures, none of them touching the files this epic changed. Working tree clean.

**One further non-blocking finding, from the okf-cli-x60r review.** `parser_actions()`
(cli/okf-cli.py:2569-2573) still filters only `argparse._HelpAction`; the new top-level
coverage required an extra `_SubParsersAction` exclusion local to the test rather than in
the shared helper. Assessed as no real impact: `_SubParsersAction` is only ever produced by
`add_subparsers()` and never by `add_argument()`, so no genuine option can hide behind the
exclusion, and a future reuse of the unfiltered helper on the top-level parser would fail
loudly on `cmd` rather than pass silently.

**Lessons recorded:** LL-18 (a channel claim is true only where its reader stands) and
LL-19 (widening a gate re-opens the exemption list tuned for the narrower collection) in
docs/LESSONS-LEARNED.md.


## PO review, 2026-07-26 — accepted

The PO reviewed the epic at the gate and accepted both leaves without exception
("T01: all accepted"). No rework ordered, no finding reclassified. The three
non-blocking findings recorded above (I01 missing delimiter, I02 stub-tested SC-02,
I03 test-local `_SubParsersAction` filter) stay as they are — the PO's standing rule
for this epic was that only findings with real runtime or gate-integrity impact get
fixed, and all three were assessed as having none.

Tag moved from `to-review` to `accepted`. The merge decision remains the PO's; this
repo runs main-direct, so the work is already on `main` and nothing is pending a merge.
