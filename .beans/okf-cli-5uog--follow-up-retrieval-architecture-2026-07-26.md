---
# okf-cli-5uog
title: Follow-up Retrieval architecture 2026-07-26
status: todo
type: epic
priority: normal
created_at: 2026-07-26T12:22:18Z
updated_at: 2026-07-26T13:01:48Z
parent: okf-cli-wuiv
---

## Origin

PO review of feature `okf-cli-cskz` on 2026-07-26: seven user stories accepted, two rejected. US-07 was rejected not for the flag it tested but for what `--help` tells a user about the CLI's capabilities; the PO additionally asked for a self-documenting help system, and then surfaced the MCP gap while checking whether `--help` and `prime` were reachable over MCP.

This epic is **strand A** of the follow-up: the part that needs no measurement. Strand B (the unreachable zero-hit branch, `okf-cli-snxj`) was deliberately separated by the PO on 2026-07-26 and ships only a measurement mandate.

## Plan

`docs/okf-cli-capability-surface/PLAN.md` — reviewed by `ce-plan-reviewer` over two rounds (round 2: APPROVED, with the argparse mechanics executed rather than reasoned about), PO-accepted 2026-07-26. Every leaf below names its task number in that file; the plan carries the literal code, the literal commands and the expected output.

## Shared context for every leaf

**The root cause all three origin beans share.** The CLI's capability surface is described three times by hand — the `Commands:` prose block in the module docstring (`cli/okf-cli.py:8-45`), argparse's `add_parser(help=...)` registrations (`:2584-2692`), and `_COMMANDS` plus the tool docstrings in `mcp/okf_mcp.py:7-17`. All three have already drifted: `find` is documented in the first, missing from the second, and described pre-feature in the third.

**The fix direction (D02/D03, PO 2026-07-26).** argparse becomes the single source of truth. One registration helper takes each command's summary and its purpose group; that one authored string reaches both help levels. The flat listing stays alphabetical (the PO's literal request) and a purpose-grouped overview is *rendered* into the epilog, so two views cannot drift. A conformance test turns the whole class from "notice it in a review" into "cannot merge it".

**Constraints that bind every leaf:**

- Standard library only, no install, no external CLI framework. This is the CLI's defining constraint (`cli/okf-cli.py:1-6`).
- Test baseline, measured live on `main` 2026-07-26: `python3 -m unittest discover -s cli -p "test_*.py"` gives `Ran 259 tests` / `FAILED (failures=19, errors=2)`. All 19F/2E are pre-existing in the crosslink suites. A leaf is done only when the count is still exactly 19F/2E plus its own new tests, all green.
- `~/Obsidian/Knowledge-Catalogue` is a separate git repo: read from it, never commit into it.
- No network in any test. Nothing in this epic touches the embedding path.
- Commits: `<type>(<scope>): <subject>`, subject max 50 chars, no `Co-Authored-By` (hook-enforced). Explicit paths in `git add`, never `-A`.
- Work main-direct (repo Worktree-Weiche: solo).

**Evidence discipline (LL-13, five occurrences in the predecessor feature).** A claim of the form "behaviour-preserving, verified" is the one that must be checked, not the one that may be skipped. Every leaf that says "verify" means: run the command, quote its observed output in the bean. State what was executed, not the conclusion drawn from it.

## Definition of Done

All leaves completed; `okf-cli --help` shows every command with a description, alphabetically, plus the grouped overview and the `<command> --help` pointer; `CommandHelpConformance` is green and has been seen failing; `build-index`, `prime` and `info` are reachable over MCP; the topic-note migration (`okf-cli-t7jz`) has run. Then `to-review` for the PO.
