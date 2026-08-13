---
# OKFT-az0k
title: Broken-pipe handling does not cover stderr
status: draft
type: bug
priority: low
created_at: 2026-08-13T13:02:21Z
updated_at: 2026-08-13T13:02:21Z
---

Found while reviewing OKFT-0k55, 2026-08-13. Fast-follow to that fix, not a regression from it.

OKFT-0k55 put a `BrokenPipeError` handler around the entry point (`okf-cli.py:5031-5066`): catch, redirect stdout to `os.devnull`, exit 0 silently. It protects **stdout (fd1) only**.

Under `okf-cli <cmd> 2>&1 | head`, stderr is merged into the same pipe. If enough stderr volume is produced, the write fails there instead, outside the handler's reach. Reproduced 5 runs out of 5 with a 5000-line stderr producer piped through `head -n 1`: `returncode: 120`, not 0.

It does not fire today. `cmd_find` writes one or two short `note:` lines to stderr, far below the threshold. The condition is latent and volume-dependent — it will surface the first time a command becomes chatty on stderr, or the first time someone pipes a `--verbose`-style stream.

Why it is worth fixing rather than filing and forgetting: OKFT-0k55's own acceptance criterion 1 reads "no traceback on stdout **or stderr**". The shipped architecture holds that promise only for the unmerged case. The gap is between what the criterion says and what the mechanism can deliver, which is exactly the shape that goes unnoticed until it bites.

Likely fix: wrap stderr the same way in the same handler, and extend the existing subprocess test to a `2>&1` variant with enough volume to cross the pipe buffer. The existing `BrokenPipeOnFind` / `BrokenPipeOnFindTinyAnswer` classes (`test_okf_cli.py:7736-7893`) are the right place — they already drive real subprocesses through real pipes.

Note the interaction with Q02 on OKFT-wmbu: if the PO settles broken-pipe exit status on 141 instead of 0, that decision applies here too. Do not fix this one in isolation without checking Q02's state.
