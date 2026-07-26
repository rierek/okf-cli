---
# okf-cli-2ljd
title: T03 Document --limit, correct the --expand-tags promise
status: completed
type: task
priority: normal
created_at: 2026-07-26T13:02:45Z
updated_at: 2026-07-26T13:44:46Z
parent: okf-cli-5uog
blocked_by:
    - okf-cli-lbh1
---

Plan: `docs/okf-cli-capability-surface/PLAN.md` → **Task 3**.

Two option texts on `find`. The second is the finding the PO did not raise.

### Requirement 1: `--limit` describes itself

**Objective:** As a user of `find`, I want every option to carry a description, so that no option renders with an empty help column.

#### Acceptance Criteria

1. THE `--limit` option of `find` SHALL carry help text naming its default (`cli/okf-cli.py:2598`, empty today).

### Requirement 2: `--expand-tags` states the measurement instead of promising one

**Objective:** As a reader of the help, I want a flag to tell me the state of the decision it depends on, so that I do not wait for a measurement that already happened.

#### Acceptance Criteria

1. THE `--expand-tags` help SHALL NOT contain the phrase `until measured`.
2. THE `--expand-tags` help SHALL state that the expansion was measured, found ineffective for the vocabulary-mismatch class it was built for, and therefore stays off (Q05/D17 of `docs/okf-retrieval-architecture/`).

#### Success Criteria

- SC-01: `find`'s `--limit` action help contains `default 10`.
- SC-02: `find`'s `--expand-tags` action help contains `measured` and not `until measured`.
- SC-03: full suite at `Ran 267 tests`, exactly 19 failures / 2 errors.

**Files:** `cli/okf-cli.py:2598` and `:2606-2609` · `cli/test_okf_cli.py` (append class `FindOptionHelp`)

## Steps

- [x] Write the failing `FindOptionHelp` tests
- [x] Run them, confirm both fail for the stated reason
- [x] Fix both help strings with the literal text from the plan
- [x] Full suite; commit `fix(cli): document --limit, correct --expand-tags` (`ea18873`)

## Recommended Skills

- superpowers:test-driven-development

## Summary

Two `find` option help strings fixed per PLAN.md Task 3. `--limit` (`cli/okf-cli.py:2673-2674`) gained `help="max results to print (default 10)"` — it previously rendered with an empty description column (B02). `--expand-tags` (`cli/okf-cli.py:2681-2686`) no longer promises `until measured`; it now states the flag was measured against the full catalogue and found ineffective for the vocabulary-mismatch class it was built for, so it stays off by default (Q05/D17) — closing B05.

**Files:** `cli/okf-cli.py:2673-2686` · `cli/test_okf_cli.py` (appended class `FindOptionHelp`, 2 tests, end of file, before `if __name__ == "__main__":`).

## Test-Output

RED (both failing for the stated reason):

```
$ rm -rf cli/__pycache__ && python3 -m unittest cli.test_okf_cli.FindOptionHelp -v
test_expand_tags_no_longer_promises_a_pending_measurement ... FAIL
test_limit_carries_help_text ... FAIL

AssertionError: 'until measured' unexpectedly found in 'expand the query with semantically near registered tags before lexical scoring (experimental, off by default until measured)'
AssertionError: 'default 10' not found in ''

Ran 2 tests in 0.005s
FAILED (failures=2)
```

GREEN:

```
$ rm -rf cli/__pycache__ && python3 -m unittest cli.test_okf_cli.FindOptionHelp -v
test_expand_tags_no_longer_promises_a_pending_measurement ... ok
test_limit_carries_help_text ... ok

Ran 2 tests in 0.004s
OK
```

**SC-03 — full suite:**

```
$ python3 -m unittest discover -s cli -p "test_*.py" 2>&1 | grep -E "^(Ran |OK|FAILED)"
Ran 267 tests in 17.398s
FAILED (failures=19, errors=2)
```

267 = 265 baseline (post-T02) + 2 new `FindOptionHelp` tests. `failures=19, errors=2` unchanged from baseline — no new failure introduced, none silenced.

**Isolated diff** (`git show ea18873~1:cli/okf-cli.py` vs `git show ea18873:cli/okf-cli.py`, confirming the change touches nothing outside the two option registrations):

```
2673c2673,2674
<     pf.add_argument("--limit", type=int, default=10)
---
>     pf.add_argument("--limit", type=int, default=10,
>                     help="max results to print (default 10)")
2683,2684c2684,2687
<                          "tags before lexical scoring (experimental, off by "
<                          "default until measured)")
---
>                          "tags before lexical scoring; measured against the "
>                          "full catalogue and found ineffective for the "
>                          "vocabulary-mismatch class it was built for, so it "
>                          "stays off by default (Q05/D17)")
```

Commit: `fix(cli): document --limit, correct --expand-tags` (`ea18873`, 49 characters).

## Deviations

1. The plan's literal Step 3 replacement text for `--expand-tags` opens a new sentence with capital `Measured` right after the period following `lexical scoring.`. That text does not satisfy the plan's own Step 1 test (`assertIn("measured", ...)`, lowercase) or SC-02 (`contains measured`): Python string containment is case-sensitive, so `"measured"` is not a substring of `"Measured against ..."`. Fix applied: joined the two clauses with a semicolon instead of a period, keeping `measured` lowercase mid-sentence and preserving the exact remaining wording and meaning of the plan's text. Confirmed green via `test_expand_tags_no_longer_promises_a_pending_measurement` after the change.

No other deviation. Implemented exactly per PLAN.md Task 3 Steps 1-5, no scope beyond `cli/okf-cli.py`'s `--limit`/`--expand-tags` registrations and the one new `FindOptionHelp` test class.

## Prelude from the T01/T02 reviews (2026-07-26, non-blocking)

1. The 50-character subject cap applies to EVERY commit, including the bean-close meta commit. T02's close commit `1fb3463` ("chore(beans): close lbh1, commands registered via _sub") was 54 characters and nothing caught it: there is no `commit-msg` hook in `.git/hooks/`, so the cap is a discipline, not a guard. Count the subject before committing.
2. For any before/after proof, snapshot with `git show <rev>:<path> > /tmp/<x>.py` and diff against the working tree. Do not use `git stash` — it is a shared-tree operation and this repo sees concurrent activity.
