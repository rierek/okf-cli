---
# okf-cli-ji5g
title: Retire okf-cli log command and delete log.md
status: todo
type: task
created_at: 2026-07-26T13:02:10Z
updated_at: 2026-07-26T13:02:10Z
---

Retire the `log` command from okf-cli and delete `log.md` from the Knowledge Catalogue. The command is a thin wrapper around `git log` that materialises a snapshot file nobody reads, and the file drifts stale. Git is already the single source of truth for change history; commit bodies already carry the per-change rationale.

Filed from a think session on 2026-07-26 (no full TPIC chain needed — this bean carries everything required to resume).

## Background — why retire instead of improve

The session started from the opposite question: "`log.md` grows over time, querying concrete topics in it is hard — could YAML help?" Investigation reversed the premise.

**`log.md` is a derivative, not a store.** `cmd_log` (`cli/okf-cli.py:1854`) runs `git log --date=short --format=%ad	%s`, path-scoped, and splices the result between `<!-- okf:log -->` markers. It holds no state of its own. Its own header says: *"History lives in git. This file is a portability snapshot, not the source of truth."*

**Nobody reads it.** Last materialised 2026-07-04 at 103 lines. Since then ~125 commits landed and were never spliced in. The drift went unnoticed for 22 days — evidence the file has no reader.

**Commit-body discipline already replaced it.** 172 of 191 catalogue commits carry a substantive body (trailers stripped). `ce-okf/SKILL.md:92` already mandates "Changelog = git, not hand-edited. Do NOT append to `log.md`."

**Growth is real but irrelevant once the file goes.** 191 commits over 24 days (~8/day) would project to ~3000 log lines/year in the root scope.

## Decisions (from the think session, 2026-07-26)

| ID | Decision | Rationale |
|----|----------|-----------|
| D01 | The `log` derivative is obsolete; git is the SSoT | Block stale 22 days, 125 commits never spliced |
| D02 | YAML output rejected | Wrong axis — format is not the query surface. House convention for machine output is `--json` (`cli/okf-cli.py:2589`, `:2595`, `:2627`, `:2686`); YAML appears nowhere in okf-cli |
| D03 | `--write` is removed | It is the drift generator |
| D04 | The whole `log` command is removed, not just `--write` | The stdout variant is only date-grouping over `git log` — no added value |
| D05 | `log.md` is deleted, the frozen hand-authored archive is not rescued | PO ruling: archive relevance decays with age. Load-bearing remnants (open dedup items from the general-knowledge-wiki migration) are duplicated in `general-knowledge-wiki/_intake/` (`ingest-lessons-learned.md`, `migration-report.tsv`, `slug-map.tsv` — all verified present) |
| D06 | `log.md` STAYS in `RESERVED` (`cli/okf-cli.py:64`) | SPEC §3.1 reserves the name independently of our command. The "never give this a `type`" guard remains correct for foreign catalogues |
| D07 | `obs-orphans/SKILL.md:153` must be fixed in the same pass | It actively hand-appends bullets to `log.md`, contradicting `ce-okf/SKILL.md:92`. Without the fix, the next orphan run recreates the file |

**Not decided here, out of scope:** whether the *query* need ("find concrete topics in the history") deserves any replacement surface. The think session concluded it does not — `okf-cli find` covers the concepts themselves, and `git log --grep` covers the history. Do not build a replacement query interface as part of this task.

## Removal scope — okf-cli (`cli/okf-cli.py`, single source, no deployed copy)

- [ ] `cmd_log` — `:1854`
- [ ] `render_git_log` — `:1821`
- [ ] `splice_log` — `:1834`
- [ ] `LOG_START` / `LOG_END` constants — `:68-69`
- [ ] `LOG_NOTICE` — `:73`
- [ ] Usage line in the module docstring — `:23`
- [ ] Argparse subparser `pl` — `:2653-2656`
- [ ] Dispatch entry `"log": cmd_log` — `:2707`
- [ ] KEEP `log.md` in `RESERVED` — `:64` (D06)

## Removal scope — tests (`cli/test_okf_cli.py`)

- [ ] `:267` — `render_git_log` with rows
- [ ] `:280` — `render_git_log` with empty rows
- [ ] `:294` — `splice_log` replaces existing marker block
- [ ] `:302` — `splice_log` creates header + freezes prior content

## Removal scope — catalogue (`~/Obsidian/Knowledge-Catalogue/`)

- [ ] Delete `log.md` (root; it is the only `log.md` in the catalogue — verified by `find . -name log.md`)
- [ ] Do NOT touch `SPEC.md` (`:84`, `:107`, `:314`, `:362`) — verbatim canonical OKF v0.1
- [ ] Ignore `_inbox/_done/okf-cli-mcp-overview.md` and `_plan/*` — historical documents

## Reference updates outside okf-cli (the actual blast radius)

- [ ] `~/.claude/skills/obs-orphans/SKILL.md:153` — remove the "append a bullet under today's `## YYYY-MM-DD` in `log.md`" instruction; replace with rationale-in-commit-body per the `ce-okf/SKILL.md:99` pattern. **Highest priority — this is a live writer to the file.**
- [ ] `~/.claude/skills/claude-setup/PROCEDURE_FULL.md:368` — core-files health check asserts `log.md` exists; it would fail after the delete. Drive-by: the same check also asserts `okf-cli.py` at the catalogue root, which is ALREADY absent (the CLI lives at `~/dev/okf-tools/cli/okf-cli.py`) — so this line is already broken. Fix both names.
- [ ] `~/.claude/skills/claude-setup/PROCEDURE_FULL.md:371` — "Reserved `index.md`/`log.md` carry no `type`" stays valid per D06; verify wording still reads correctly with no `log` command.
- [ ] `~/.claude/skills/ce-okf/SKILL.md` — four sites: `:92`, `:99`, `:122`, `:178`. Drop all `log.md` / `okf-cli.py log --write` prose; the skill gets shorter, its rule ("rationale in the commit body") already stands on its own.
- [ ] `~/.claude/skills/ce-okf-p/references/init-procedure.md:111` — the `LOG.md` → `log.md` lowercase-rename convention now rests on SPEC fidelity only, no okf-cli reference. Adjust if it implies our command.
- [ ] `docs/okf-revision/05-cli-docs.yaml:41` — claim about the `log` verb becomes stale
- [ ] `docs/okf-revision/04-skills.yaml:4` — `log` listed among ce-okf's okf-cli subcommands
- [ ] `docs/okf-cli-capability-surface/PLAN.md:859` — D04 there (which CLI commands belong on the MCP surface) loses one blast-radius candidate; note that `log --write` is gone
- [ ] No MCP change needed — `log` was never registered; `docs/okf-revision/PLAN.md:436` records write/admin verbs as "CLI-only by intent"

## Acceptance

- [ ] `python3 cli/okf-cli.py log` exits with an unknown-command error (verb gone from argparse)
- [ ] `grep -n "cmd_log\|render_git_log\|splice_log\|LOG_START\|LOG_NOTICE" cli/okf-cli.py` returns nothing
- [ ] `grep -n "log.md" cli/okf-cli.py` returns only the `RESERVED` line `:64`
- [ ] Full test suite green after removing the four log tests
- [ ] `ls ~/Obsidian/Knowledge-Catalogue/log.md` → not found
- [ ] `grep -rn "log.md" ~/.claude/skills/` returns no instruction to write to it
- [ ] Catalogue conformance scan: `okf-cli --root ~/Obsidian/Knowledge-Catalogue check` → `OK — 0 violations`
- [ ] Two commits: one in okf-tools (`refactor(okf-cli): retire log command`), one in the catalogue (`chore: delete derived log.md`). Skill edits under `~/.claude/skills/` commit in that repo.
