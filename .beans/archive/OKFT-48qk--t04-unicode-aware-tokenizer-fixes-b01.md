---
# OKFT-48qk
title: T04 Unicode-aware tokenizer (fixes B01)
status: completed
type: task
priority: high
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-26T05:36:01Z
parent: OKFT-cskz
---

Plan: `docs/okf-retrieval-architecture/PLAN.md` → **Task 4**. Follow it step by step; it carries the literal code and tests.

Finding B01: `tokenize()` splits on `[^a-z0-9]+` (`cli/okf-cli.py:598-599`), so every umlaut tears a German word in two — `qualitätsmanagement` becomes `qualit` + `tsmanagement`. The measured FTS arm tokenized on word characters (`eval/fts_arm.py:56`). Without this fix the shipped lexical arm is not the arm that was measured.

### Requirement 1: Unicode-aware query tokenization

**Objective:** As a user searching a German catalogue, I want query words with umlauts to stay whole, so that the lexical arm searches for the word I typed.

#### Acceptance Criteria

1. THE tokenizer SHALL keep non-ASCII letters inside their token.
2. THE tokenizer SHALL continue to treat punctuation and the underscore as separators.
3. THE tokenizer SHALL continue to lowercase its output and drop empty tokens.

#### Success Criteria

- SC-01: `tokenize("Qualitätsmanagement") == ["qualitätsmanagement"]` and `tokenize("Straßenbahn") == ["straßenbahn"]`.
- SC-02: `tokenize("build_tagvec") == ["build", "tagvec"]` and `tokenize("mockup, tailscale!") == ["mockup", "tailscale"]`.
- SC-03: `python3 -m unittest discover -s cli -p 'test_*.py'` stays at exactly 19 failures / 2 errors. If a different test now fails, it was asserting the old broken split — read it, and change the assertion only if it encoded the bug.

_Requirements: PLAN.md Task 4 · finding B01 · REFERENCES R41 (unicode61 folds ä to a, not ae)_

## Steps

- [ ] Write the failing `TokenizeUnicode` tests
- [ ] Run them, confirm the `['qualit','tsmanagement']` failure
- [ ] Replace the split with `re.split(r"[\W_]+", s.lower(), flags=re.UNICODE)`
- [ ] Tests pass; suite still 19F/2E
- [ ] Commit `fix(cli): tokenize unicode words, not just ascii`

## Recommended Skills

- `superpowers:test-driven-development`


## Summary

Fixed B01: `tokenize()` split on `[^a-z0-9]+`, tearing every non-ASCII word
(umlauts, ß) in two. Replaced with `re.split(r"[\W_]+", s.lower(), flags=re.UNICODE)`,
which matches the FTS arm tokenization measured in `eval/fts_arm.py:56`
(`[^\wäöüÄÖÜß]+`) — `\w` is Unicode-aware in Python 3, so any Unicode letter
(not only German umlauts) now stays inside its token, while punctuation and
`_` still separate. Signature unchanged.

## Test-Output

RED (`python3 -m unittest cli.test_okf_cli.TokenizeUnicode -v`, before fix):

```
test_umlaut_word_stays_one_token ... FAIL
AssertionError: Lists differ: ['qualit', 'tsmanagement'] != ['qualitätsmanagement']
test_sharp_s_stays_one_token ... FAIL
AssertionError: Lists differ: ['stra', 'enbahn'] != ['straßenbahn']
test_non_latin_script_stays_whole ... FAIL
AssertionError: Lists differ: ['system'] != ['知識管理', 'system']
Ran 7 tests in 0.003s
FAILED (failures=3)
```

GREEN (same command, after fix):

```
test_digits_survive ... ok
test_mixed_case_lowercased ... ok
test_non_latin_script_stays_whole ... ok
test_punctuation_still_separates ... ok
test_sharp_s_stays_one_token ... ok
test_umlaut_word_stays_one_token ... ok
test_underscore_still_separates ... ok
Ran 7 tests in 0.000s
OK
```

Full baseline at commit point (`python3 -m unittest discover -s cli -p 'test_*.py'`):
before this task 197 tests / 19 failures / 2 errors; after this task
**204 tests / 19 failures / 2 errors** (added 7 tests, 0 new failures).

## Smoke

Mutation probe: reverted the regex to the old `[^a-z0-9]+` in place, reran
`TokenizeUnicode` — 3 of 7 tests failed with the same diffs as the original
RED proof, confirming the tests actually detect the regression. Reverted the
mutation back to the fix, `git diff cli/okf-cli.py` showed byte-identical
state to the pre-mutation diff before committing.

Manual check:
```
python3 -c "
import importlib.util
spec = importlib.util.spec_from_file_location('okf', 'cli/okf-cli.py')
okf = importlib.util.module_from_spec(spec); spec.loader.exec_module(okf)
print(okf.tokenize('Qualitätsmanagement'))
print(okf.tokenize('mockup, tailscale!'))
"
```
→ `['qualitätsmanagement']`, `['mockup', 'tailscale']`.

## Deviations/ERRATA

None. Implemented the plan's literal code and literal test class verbatim
(PLAN.md Task 4, Step 1/Step 3). Added three tests beyond the plan's literal
five, per the dispatch instruction to make tests "genuinely adversarial":
`test_mixed_case_lowercased` and `test_non_latin_script_stays_whole` (CJK,
proves the fix is Unicode-general, not just umlaut/ß-specific as the plan's
docstring implies). No pre-existing test referenced `tokenize()` before this
task, so there was no old-broken-split assertion to read/reconcile (Step 4's
contingency did not apply).

## Notes for T05

- `tokenize()` at `cli/okf-cli.py:598` is now `re.split(r"[\W_]+", s.lower(), flags=re.UNICODE)`
  — safe to reuse for any lexical-side query tokenization T05 needs; it now
  matches the FTS arm's `unicode61` folding intent at the Python level (though
  FTS5's own `unicode61` tokenizer inside SQLite does its own thing per
  REFERENCES R41 — ä folds to a there, this Python tokenizer does NOT fold,
  it only avoids splitting).
- Full-suite baseline going into T05: 204 tests, 19 failures / 2 errors,
  all pre-existing in the crosslink suites (unchanged by this task).
- Commit: `4ee120d fix(cli): tokenize unicode words, not just ascii`.
