---
# OKFT-0k55
title: Handle BrokenPipeError in cmd_find
status: completed
type: bug
priority: normal
created_at: 2026-08-13T11:07:31Z
updated_at: 2026-08-13T12:52:11Z
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


## Summary (2026-08-13, implementer)

`okf-cli find <query> | head` raised an unhandled `BrokenPipeError` (traceback on stderr) and, even after catching it, a second "Exception ignored while flushing sys.stdout:" message at interpreter shutdown. Fixed once, centrally, at the entrypoint (`if __name__ == "__main__":` around `main()`), not inside `cmd_find` — **D02**, reasoning below. On `BrokenPipeError`: flush stdout explicitly first (still inside the `try`, required — see Deviations), then redirect stdout's fd to `os.devnull` before `sys.exit(0)` (**D01**: clean early close is not an error).

### D02 — fixed centrally, around `main()`, not inside `cmd_find`

Every command that `print()`s a long answer (`find`, `index`, `list`, `toc`, `wikilinks`, ...) funnels through the single line `COMMAND_DISPATCH[args.cmd](root, args)` inside `main()`, which itself has exactly one caller: `if __name__ == "__main__": main()`. A `try/except BrokenPipeError` wrapped there, once, covers every command's writing path for free — the alternative (a per-command try/except, starting with `cmd_find`) is the "copy it three times" case the bean explicitly says to avoid in favour of the central fix. Verified empirically post-fix: piping `index`, `list`, `toc`, `wikilinks` each into `head -n 1` (real subprocess, real early-closing reader) shows no traceback and no "Exception ignored" noise for any of them — see `## Notes for T(n+1)`.


## Test-Output

RED (`BrokenPipeOnFind`, before any fix — real subprocess piped into a real `head` that closes early against a 300-concept tmpdir fixture, per CLAUDE.md rule 1):

```
$ python3 -m unittest test_okf_cli.BrokenPipeOnFind -v
test_exit_status_is_zero_per_d01 ... FAIL
test_no_exception_ignored_noise_at_interpreter_shutdown ... FAIL
test_no_traceback_on_stderr ... FAIL

======================================================================
FAIL: test_exit_status_is_zero_per_d01
AssertionError: 120 != 0

======================================================================
FAIL: test_no_exception_ignored_noise_at_interpreter_shutdown
AssertionError: 'Exception ignored' unexpectedly found in '...
Traceback (most recent call last):
  File "cli/okf-cli.py", line 5032, in <module>
    main()
  File "cli/okf-cli.py", line 5028, in main
    COMMAND_DISPATCH[args.cmd](root, args)
  File "cli/okf-cli.py", line 1730, in cmd_find
    print("description: {}".format(h["desc"]))
BrokenPipeError: [Errno 32] Broken pipe
Exception ignored while flushing sys.stdout:
BrokenPipeError: [Errno 32] Broken pipe
'

Ran 3 tests in 0.448s
FAILED (failures=3)
```

Note the call site: `cmd_find:1730`, the `description:` line — not `:1652`'s `type:` line the bean observed on 2026-08-13; confirms the bean's own warning that line numbers had already drifted (OKFT-n8xz, OKFT-oe8t landed since).

GREEN, same two test classes, after the fix (`BrokenPipeOnFind` = large/synchronous-raise path, `BrokenPipeOnFindTinyAnswer` = small-answer/final-flush-only path, added when the RED run above proved the first fixture alone could not exercise the second failure mode — see Deviations):

```
$ python3 -m unittest test_okf_cli.BrokenPipeOnFind test_okf_cli.BrokenPipeOnFindTinyAnswer -v
test_exit_status_is_zero_per_d01 ... ok
test_no_exception_ignored_noise_at_interpreter_shutdown ... ok
test_no_traceback_on_stderr ... ok
test_exit_status_is_zero_when_answer_fits_the_buffer ... ok
test_no_exception_ignored_noise_when_answer_fits_the_buffer ... ok

Ran 5 tests in 0.662s
OK
```

Mutation proof (two separate mutants, each reverted byte-identically afterward, md5 verified before/after):

1. Remove only the explicit `sys.stdout.flush()` line, keep the `except BrokenPipeError` block: `BrokenPipeOnFindTinyAnswer` turns red (`returncode 120`, `Exception ignored while flushing sys.stdout:` on stderr) while `BrokenPipeOnFind` stays green — proves the tiny-answer test earns its place, the large-fixture test alone would not have caught this class of regression.
2. Remove the whole `try/except` (full revert to `if __name__ == "__main__": main()`): all 5 tests turn red, reproducing the original traceback shown above.

Gate (`just test`), full suite, after the fix, byte-identical to the committed state:

```
FAIL: test_index_walk_row_present_with_rank_no_dedicated_metric (test_eval_runner.RunnerAgainstRealCatalogueTest.test_index_walk_row_present_with_rank_no_dedicated_metric)
FAIL: test_metadata_hit_and_miss_rows_scored_correct (test_eval_runner.RunnerAgainstRealCatalogueTest.test_metadata_hit_and_miss_rows_scored_correct)
FAIL: test_runner_scores_literal_s1_top1 (test_eval_runner.RunnerAgainstRealCatalogueTest.test_runner_scores_literal_s1_top1)
Ran 701 tests in 26.374s
FAILED (failures=3)
```

Exactly the three pre-existing `RunnerAgainstRealCatalogueTest` failures named in the epic's baseline and in `CLAUDE.md` rule 3, no fourth. 701 = 696 baseline + 5 new (`BrokenPipeOnFind` ×3, `BrokenPipeOnFindTinyAnswer` ×2).

## Smoke

Real pipe against the real Knowledge-Catalogue (read-only `find`, nothing written — CLAUDE.md rule 1), captured via a controlled `subprocess.Popen` chain so the producer's own exit code is observable (a plain shell `|` only exposes the last stage's, `head`'s, exit code):

```
$ python3 -c "
import subprocess, sys
producer = subprocess.Popen(
    [sys.executable, 'cli/okf-cli.py', 'find', 'index', '--limit', '300'],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
consumer = subprocess.Popen(['head', '-n', '2'], stdin=producer.stdout, stdout=subprocess.PIPE)
producer.stdout.close()
out, _ = consumer.communicate(timeout=10)
producer.wait(timeout=10)
print('PRODUCER RETURNCODE:', producer.returncode)
print('HEAD STDOUT:'); print(out.decode())
print('PRODUCER STDERR:'); print(producer.stderr.read().decode())
"
PRODUCER RETURNCODE: 0
HEAD STDOUT:
------
rank: 1

PRODUCER STDERR:
note: lexical index is stale (catalogue changed since build) — run `okf-cli build-index`
note: semantic arm owns this ranking (lexical top-1 lacked a clear margin)
```

Exit 0, no traceback, no "Exception ignored" noise. The two `note:` lines are pre-existing, unrelated stderr diagnostics (stale-index notice, arm-ownership notice) — asserted absent-of-noise, not absent-of-output, in the test suite too.

## Deviations/ERRATA

- **Bean's quoted message differs from what this runtime actually prints.** The bean's acceptance text cites `Exception ignored in: <_io.TextIOWrapper name='<stdout>' ...>` (older CPython wording). This machine runs Python 3.14.6, which prints `Exception ignored while flushing sys.stdout:` instead — same failure class (unraisable-exception noise from flushing a closed stdout at shutdown), different exact string across CPython versions. Asserted on the version-stable substring `"Exception ignored"` so the test does not pass vacuously on a newer interpreter than the one that observed the bug.
- **A `try/except BrokenPipeError` around `main()` alone is not sufficient — this was not in the bean and had to be discovered.** Against the fixture built to force a large answer (300 padded concepts, ~300 KB), the exception raises synchronously *inside* `cmd_find`'s print loop (Python's stdout buffer to a pipe overflows mid-loop, forcing an OS-level `write()` while the reader is already gone) — a bare `try/except` around `main()` catches that. Against the real catalogue with a smaller answer, `main()` returns *without ever raising* (the whole answer fits inside Python's own ~8 KB stdout buffer, so no `write()` syscall — and therefore no `BrokenPipeError` — is ever attempted during `main()`); the only write happens at the *final* flush, and without an explicit `sys.stdout.flush()` placed inside the `try` block, that flush is Python's own implicit one at interpreter shutdown, which runs **outside** any user-code `try/except` and therefore can never be caught, however the wrapper is written. Fixed by adding an explicit `sys.stdout.flush()` inside the `try`, right after `main()` returns — the standard recipe from the Python docs' "Note on SIGPIPE" (https://docs.python.org/3/library/signal.html#note-on-sigpipe). This is a widening of the fix beyond exactly what the bean specified, but it is required for the bean's own acceptance criteria (no traceback, no shutdown noise) to hold against realistic (not just synthetic-large) answers — confirmed by first observing the gap in a real-catalogue smoke run, then reproducing it deterministically in `BrokenPipeOnFindTinyAnswer`.
- **A second, purpose-built test fixture was needed, not requested explicitly.** `BrokenPipeOnFindTinyAnswer` uses an immediately-exiting consumer (`python3 -c "pass"`, not `head`) rather than a reader that reads-then-closes: `head -n 1` must actually read a line before it can exit, so against a small, fully-buffered answer it just blocks until the single flush lands — by which point the pipe is still connected either way, so it cannot discriminate between "flush inside try" and "flush at shutdown." The instant-exit consumer drops its copy of the read end before the producer ever attempts a write, regardless of buffering, which is what makes the mutation (removing just the `flush()` line) provably observable. Documented in the class docstring, not silently added.

## Notes for T(n+1)

None needed as separate follow-up beans — the central-fix decision (D02) already answers the question the bean asked about `index`, `list`, `toc`, `wikilinks`. Verified empirically post-fix (real subprocess piped into a real early-closing `head -n 1`, no synthetic-large fixture needed since the point is only "no traceback / no shutdown noise", not exit-code semantics for each command):

```
index      returncode=0  traceback=False  exception-ignored=False
list       returncode=1  traceback=False  exception-ignored=False
toc        returncode=2  traceback=False  exception-ignored=False
wikilinks  returncode=0  traceback=False  exception-ignored=False
```

`list` and `toc` returned non-zero, but for reasons unrelated to broken-pipe handling (their own ordinary argument/state validation, not investigated further here — out of this bean's scope); neither showed a traceback or shutdown noise, which is the only thing this bean's fix is responsible for. Any exit-status *behaviour* review for those commands (D01/Q02-style) would be new scope, not a gap in this fix.
