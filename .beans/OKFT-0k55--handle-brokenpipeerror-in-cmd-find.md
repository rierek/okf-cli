---
# OKFT-0k55
title: Handle BrokenPipeError in cmd_find
status: in-progress
type: bug
priority: normal
created_at: 2026-08-13T11:07:31Z
updated_at: 2026-08-13T12:38:29Z
parent: OKFT-wmbu
---

okf-cli find <query> | head aborts with an unhandled BrokenPipeError traceback at okf-cli.py:1652 (print("type: {}".format(h["type"]))). No SIGPIPE handling anywhere in the command.

A stacktrace is not an actionable error message. Observed 2026-08-13 while measuring global vs scoped output. Feeds the CLI-program conformance spec being drafted in lean-stack (docs/aca_capability-mcp/DECISIONS.md D20).


## Target behaviour 2026-08-13 (supervisor) — the bean did not specify one

Gate B flagged that this bean names the defect exactly but never says what "fixed" looks like, so a reviewer would have to invent the expectation. Pinning it here.

Verified 2026-08-13: `cli/` and `aca/` contain **no** existing `BrokenPipeError`, `SIGPIPE` or `EPIPE` handling at all. There is no in-repo precedent to follow, so this is a fresh convention rather than a lookup.

### Acceptance (hard — all three must hold)

- [ ] `okf-cli find <query> | head` prints no traceback on stdout or stderr.
- [ ] No `Exception ignored in: <_io.TextIOWrapper name='<stdout>' ...>` noise at interpreter shutdown. Flushing a closed stdout at exit produces this **after** any handler has run, so catching the exception alone is not sufficient — stdout has to be redirected to `os.devnull` before exit.
- [ ] A regression test pipes the command into a reader that closes early and asserts both of the above. It must fail if the handling is removed — show that mutation.

### D01 — exit status is 0, and this one is revisable

On a clean early close the command exits **0**, silently. Reasoning: the command did its work; the consumer stopped reading. Exiting 141 would break every `set -o pipefail` wrapper around a routine `okf-cli find x | head`.

The competing convention is 141 (128+SIGPIPE), and the CLI-program conformance spec being drafted in lean-stack (`docs/aca_capability-mcp/DECISIONS.md` D20) may well land on it. Raised to the PO as Q02 on the epic. Implement 0 now — if D20 says otherwise it is a one-line change plus a test constant, and the two hard criteria above are unaffected either way.

Handle the same failure on every writing path of `cmd_find`, not only the `type:` line at :1652 that happened to be observed.
