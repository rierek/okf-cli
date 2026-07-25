---
# okf-cli-48qk
title: T04 Unicode-aware tokenizer (fixes B01)
status: todo
type: task
priority: high
created_at: 2026-07-25T23:25:05Z
updated_at: 2026-07-25T23:25:05Z
parent: okf-cli-cskz
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
