---
# okf-cli-mk7m
title: bug archive silently falls back to a non-git move
status: todo
type: task
priority: high
created_at: 2026-08-09T23:06:24Z
updated_at: 2026-08-09T23:16:20Z
parent: okf-cli-huow
---

Found by the real-catalogue run (`okf-cli-fv7y`, R-15) — no fixture could have found it, because fixtures build plain directories.

## What happens

Every project bundle in the real catalogue is a **symlink** into its project repo: `lean-stack-okf`, `vik-okf`, `devd2-okf`, `bew_BeWiki-Python-Download-okf`, `okf-tools-okf`, `vc-search-okf`.

`_git_mv` (cli/okf-cli.py:4048) runs `git -C <root> mv -f`. Git refuses and the code falls back to `os.rename`, reporting `moved (fs)`.

The exact git message was mis-attributed in the first draft of this bean: `fatal: pathspec ... is beyond a symbolic link` comes from `git add`, not from `git mv`. A reviewer rebuilt the layout in a temporary fixture — two repos, the bundle committed into the catalogue as mode `120000` — and got `fatal: not under version control, source=bundle/concept.md, destination=bundle/concept2.md` with exit 128. Do not grep for the wrong string when reproducing this.

Worse than either message: `_git_mv` (cli/okf-cli.py:4048-4059) captures `proc.stderr` and never reads it, so git's explanation never reaches the user at all. The caller (cli/okf-cli.py:4199) prints `moved (fs)` versus `moved (git mv)` — not wordless, but nothing says what `(fs)` costs or which repository actually received the write.

The consequence is that the move — and the crosslink rewrites that go with it — lands **untracked in the target project repo**, not in the catalogue repo. During the run, `git -C ~/Obsidian/Knowledge-Catalogue status` showed only `?? _archive/` while `git -C ~/dev/lean-stack status` showed `D`/`M` on three paths. The round trip restored everything byte-identically, so nothing was lost, but the mechanism is wrong.

## Why it matters

A02/A03 assume a git-tracked move. On the real catalogue that assumption does not hold for any project bundle — which is most of them. Two separate problems:

1. **The fallback is silent.** `moved (fs)` does not tell the user their move left git behind. Someone archiving a concept would reasonably believe it is versioned in the catalogue and could revert it there; it is not, and they cannot.
2. **The write lands in a repo the user did not name.** An operator pointing the tool at `~/Obsidian/Knowledge-Catalogue` gets writes in `~/dev/lean-stack`. That is surprising in a way that matters for any automated or agent-driven use.

## Requirement 1: A move that does not lie about what it did

**Objective:** As a catalogue maintainer, I want to know which repository actually received my move, so that I can revert it where it landed instead of where I assumed.

### Acceptance Criteria

1. WHEN `git mv` fails because the path lies beyond a symbolic link THE okf-cli SHALL resolve the real repository of the target and attempt the tracked move there, or state plainly that the move is untracked.
2. THE okf-cli SHALL name the repository that received the change in its report, whenever that repository is not the one at `--root`.
3. THE okf-cli SHALL NOT report a move as successful in a way that implies version control when `os.rename` was used.

### Success Criteria

- SC-01: Archiving a concept inside a symlinked bundle either produces a tracked move in the bundle target repository, or an output line that names both the fallback and the repository that received it.
- SC-02: A fixture reproduces the symlinked-bundle layout, so the case is covered without touching the real catalogue.
- SC-03: Removing the enforcement turns SC-01 red.

## Second, smaller finding from the same run

`archive` and `archive --restore` do not remove an `_archive/<bundle>/` directory that has become empty. Git does not track empty directories, so `git status` stays clean and the leftover is invisible — the operator of the R-15 run removed it by hand with `rmdir`. Worth folding into the same leaf or its own, but it should not be forgotten: an empty `_archive/` left behind makes a second archive run look like it resumed an existing archive.

_Blocks a production recommendation of `archive` on the real catalogue._
