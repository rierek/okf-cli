---
# okf-cli-iaxj
title: Rebuild a stale FTS index from a Stop hook
status: in-progress
type: task
priority: high
created_at: 2026-07-27T12:46:04Z
updated_at: 2026-08-03T19:46:37Z
---

## Context

`okf_find` (and `okf-cli find`) degrade to a substring scan when the FTS5 lexical
index at `<root>/.fts/fts.sqlite` is older than the catalogue. The degradation is
announced, never fatal — so it is easy to miss, and retrieval quality silently drops
to the fallback arm until someone notices the note and runs `build-index` by hand.

Observed 2026-07-27 against `~/Obsidian/Knowledge-Catalogue`:

```
note: lexical index is stale (catalogue changed since build) — run `okf-cli build-index`
```

A manual `okf_build_index` reindexed 2489 concepts in a few seconds. The cost of
rebuilding is small; the cost of not noticing is degraded search for a whole session.

## Objective

THE system SHALL rebuild the catalogue's lexical index automatically at the end of a
session, so that the next session starts from a fresh index without an agent or the
user having to react to a degradation note.

## Approach

Stop hook (`~/.claude/hooks/`, registered under `hooks.Stop` in `~/.claude/settings.json`
— currently unset). Existing hooks in that directory are the naming and style reference
(`git-enforce.py`, `precompact-sstd.sh`).

Open design point: whether the hook rebuilds unconditionally or only when the index is
actually stale. Unconditional is simpler; conditional needs a staleness probe the CLI
does not expose as a standalone verb today. Decide before implementing — see
`okf-cli-uumj` (make a stale `concept_emb` visible, like `.fts`), which touches the
same staleness-visibility question for the embedding side.

## Acceptance

- [ ] Hook script exists in `~/.claude/hooks/`, executable, follows local hook conventions
- [ ] Registered under `hooks.Stop` in the user settings
- [ ] Rebuilds the FTS index for `~/Obsidian/Knowledge-Catalogue`
- [ ] Runs unattended: no prompt, no blocking of session shutdown, non-zero exit never breaks the stop path
- [ ] Idempotent and cheap when the index is already current (skip, or a rebuild that is fast enough to be unnoticeable)
- [ ] Verified: touch a concept, end a session, confirm the next `find` reports no staleness note
- [ ] Decision recorded in the body: unconditional rebuild vs. staleness probe

## Notes

Which catalogue roots the hook covers is a scoping question — the KC is the obvious
first one; repo-local `docs/*-okf` bundles may or may not be worth the same treatment.


## PO decisions 2026-08-03 (D01-D03, supervisor session)

Recorded verbatim from the PO review gate. These close the open design point named in ## Approach.

**D01 — Event: SessionStart, conditional.** Not Stop, not SessionEnd. Grounds: `Stop` fires per turn ("when main agent considers stopping"), not per session — the bean's ## Approach names it, but its ## Objective says "at the end of a session"; the Approach wording is the error. SessionEnd cannot see the case that actually produced the 2026-08-03 symptom: the catalogue was edited in Obsidian *between* sessions. SessionStart with a cheap probe covers both agent-side and out-of-band edits. The rebuild runs backgrounded so session start never blocks.

**D02 — Mechanism: expose the probe as an okf-cli flag.** `build-index` gains `--if-stale`: it consults the existing `_fts_index_stale()` (cli/okf-cli.py:716, a stat()-only comparison of concept count and newest mtime against `fts_meta`) and skips the rebuild when the index is current. Grounds: the staleness logic then lives in the repo covered by the 295-test suite instead of in an untested shell script, and the hook collapses to a thin wrapper. Rejected alternatives: unconditional rebuild (cli/okf-cli.py:675 `build_fts_index` is always full with no no-op path — every trigger would re-read all 2489 concept bodies, contradicting the "idempotent and cheap when current" acceptance line); parsing the stderr note (cli/okf-cli.py:915 is prose with no contract — any rewording breaks the hook silently).

Side effect noted at decision time: this gives the FTS staleness state its first machine-readable surface. okf-cli-uumj and okf-cli-3520 want the same for the embedding side and should follow this shape rather than invent a second one.

**D03 — Scope: Knowledge-Catalogue only.** The hook covers the root named by `kc_root` in `.okf.toml` (docs/.okf.toml already documents that key as "single source for tooling (okf-cli / okf-MCP / hook)"). Repo-local `docs/*-okf` bundles stay out: covering them needs a discovery rule and makes the hook cwd-dependent, with no observed need. Revisit if a second case appears.

## Supervisor notes 2026-08-03

Cross-repo task. Two sinks: `cli/okf-cli.py` + tests in /Users/erik/dev/okf-tools, hook script in /Users/erik/.claude (which is its own git repo). `~/.claude/settings.json` is git-ignored there (.gitignore:41), so the registration is machine-local and cannot be versioned — same situation as the roster-gate hook, and the canon (OKF `lean-stack-okf/autonome-agent-kette`) already accepts manual per-machine wiring for it.

`hooks.SessionStart` is already populated (sessionstart.sh) — the new hook is appended, never replaces it.

The Knowledge-Catalogue is a SEPARATE git repo. The hook writes `<kc>/.fts/fts.sqlite` there. Confirm `.fts/` is ignored in that repo before shipping, otherwise the hook dirties an unrelated working tree on every session start.
