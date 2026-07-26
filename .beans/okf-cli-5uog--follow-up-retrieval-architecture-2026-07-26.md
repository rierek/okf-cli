---
# okf-cli-5uog
title: Follow-up Retrieval architecture 2026-07-26
status: todo
type: epic
priority: normal
tags:
    - accepted
created_at: 2026-07-26T12:22:18Z
updated_at: 2026-07-26T15:10:39Z
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



## Realization complete 2026-07-26 — handed to the PO gate

All seven leaves `completed`, each reviewed by `ce-specs-reviewer` with independent re-verification (own test runs, own snapshots, own mutation probes — never the implementer's quoted output). Status left at `todo` with tag `to-review`: closing an epic is the PO's call at the merge gate.

**Definition of Done, item by item.** `okf-cli --help` shows every one of the 21 commands with a description, alphabetically, plus the rendered grouped overview and the `<command> --help` pointer — verified live. `CommandHelpConformance` is green and has been seen failing: four separate invariants were broken and each produced its assertion, with byte-identical reverts confirmed by md5. `build-index`, `prime` and `info` are reachable over MCP. The topic-note migration `okf-cli-t7jz` has run.

**Evidence.** Suite `Ran 279 tests` with exactly `failures=19, errors=2` — the 19F/2E unchanged and pre-existing in the crosslink suites, zero new. The plan's own arithmetic resolves: 259 baseline + 2+4+2+5+3+4 per task = 279. Commits `67f7b3e` (T01), `4f6ac34` (T02), `ea18873` (T03), `ecd2058` (T04), `7dade90` (T05), `826fcbf` (T06), `697dc99`+`ab57e29` (migration).

**Two things for the PO to decide, neither of them defects in the shipped work.**

1. `okf-cli-x60r` (new bug, `low`, unscheduled): the conformance gate iterates the subcommand parsers and not the top-level parser, so an undocumented top-level option would pass it. Proven by mutation — `--root` stripped of its help text left the gate green. No live defect, and PLAN.md did not ask for that coverage. The epic's claim therefore holds for the 21 subcommands and their arguments, which is narrower than "every command and option".
2. Which of the remaining eight CLI commands belong on the MCP surface stays open by D04. `visualize` writes `viz.html` into the catalogue and `log --write` materialises `log.md`, so neither is the read-only addition it looks like; the six tag/fix/rewrite commands mutate catalogue content.

**The plan shipped two untrue passages and both were caught at the point of use, not in review.** Task 3's literal help string contradicted the plan's own test; Task 6's literal docstring promised a `provenance: lexical` line that `cmd_find` never prints. Corrected in place, re-established by the reviewer against the code, and written up as LL-15. Worth the PO's attention because the plan had passed two rounds of `ce-plan-reviewer` and three of `ce-verify-operationalization` before either defect surfaced.

Lessons LL-15, LL-16, LL-17 recorded in `docs/LESSONS-LEARNED.md`. Origin records `okf-cli-3suc`, `okf-cli-6zhw` and `okf-cli-4ws6` stay on `todo` and now each carry a table mapping their findings to the leaf and commit that fixed them.



## Review 2026-07-26

US-01 · find, index and read carry a description line in the top-level command directory; all 21 commands do · a
US-02 · find --help ends with a score lines: block naming the two scales, provenance and the stderr degradation notes · a
US-03 · find --limit renders with its description (max results to print, default 10) instead of an empty column · a
US-04 · find --expand-tags states the measurement result and why the flag stays off, instead of promising a pending decision · a

US-05 · the flat command listing in --help is alphabetical instead of registration order · a
US-06 · a rendered commands by purpose: overview plus the <command> --help pointer sit below it, both generated from the same registrations; the hand-maintained docstring block is gone · a
US-07 · dropping a help= from any subcommand argument turns CommandHelpConformance red, so an undocumented argument cannot merge; the gate covers the 21 subcommands and their arguments, not the top-level parser's own options (okf-cli-x60r) · a

US-08 · okf_build_index reaches the CLI over MCP and works — 2470 concepts indexed against the live catalogue, stale note gone afterwards, foreign repo left clean · a
US-09 · okf_prime and okf_info are on the agent surface; okf_info verified live against the live catalogue · a
US-10 · okf_find's description names both arms, the conditional handover and the provenance marker, with the plan's false provenance: lexical claim corrected before shipping · a
NB · MCP consumers never receive the stderr degradation notes, so the note that names build-index does not reach the audience it was written for → okf-cli-p9h5

Correction, same day: the NB line above points at okf-cli-p9h5, an ID written before the bean was created and therefore invented. The bean actually filed is **okf-cli-2o39** (bug, high), under the new follow-up epic okf-cli-iksi. The wrong pointer is left standing rather than edited, per the same rule that governs review records.

US-11 · the durable decisions of the three topic folders are in the bundle and reachable via okf-cli find; the five migrated source files were removed only after a line-by-line check confirmed every D-code survived · a
US-12 · docs/okf-tools-okf/index.md lists the bundle's actual contents (three subdirs plus the glossary) instead of an empty auto-index block; reindex --check reports 0 stale, 0 uncovered · a

### Outcome

12 stories reviewed, 12 accepted, 0 rejected. One side finding filed: okf-cli-2o39 (MCP drops stderr). Epic tagged accepted; the merge decision stays with the PO.
