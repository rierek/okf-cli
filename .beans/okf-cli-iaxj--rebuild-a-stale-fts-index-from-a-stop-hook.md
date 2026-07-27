---
# okf-cli-iaxj
title: Rebuild a stale FTS index from a Stop hook
status: todo
type: task
created_at: 2026-07-27T12:46:04Z
updated_at: 2026-07-27T12:46:04Z
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
