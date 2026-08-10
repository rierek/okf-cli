---
# OKFT-4vs3
title: find --scope drops the subdir segment on the substring arm
status: completed
type: bug
priority: normal
created_at: 2026-08-03T18:23:13Z
updated_at: 2026-08-03T18:23:13Z
---

Found while closing I01 (the filter-contract refactor), never reported by a user — the wrong path merely looks plausible.

`_substring_ranking` built each hit's path as `"{bundle}/{cid}"`, but `resolve_scopes()` returns the bundle NAME while `iter_concepts()` yields cids relative to the resolved scope DIRECTORY. Those two agree only when the scope is a whole bundle. With `--scope <bundle>/<subdir>` the subdir segment silently vanished:

```
okf-cli --root <kc> find "zebra" --scope b/sub
  path: b/y          <- wrong, file lives at b/sub/y
okf-cli --root <kc> find "zebra"
  path: b/sub/y      <- correct
```

The emitted path resolves to nothing, so a follow-up `okf-cli read` / `okf_read` on it fails. Only the substring arm was affected — it is the degradation target for a missing or unusable FTS index (D15), so the bug surfaced exactly when the tool was already running on its weaker arm.

- [x] path prefix derived from the scope's position under root, not from the bundle name
- [x] unscoped output byte-identical (the frozen eval baseline was recorded against this arm)
- [x] regression test at the cmd_find seam
- [x] mutation-tested: reinstating the old prefix turns the test red

## Summary

`cli/okf-cli.py` `_substring_ranking`: prefix is now `os.path.relpath(bp, root)` instead of the bundle name. Unscoped, `relpath(bp, root)` IS the bundle name, so that path stays byte-identical and the eval baseline holds.

Test: `cli/test_okf_cli.py` `FindFilterContract.test_scoped_substring_fallback_reports_the_real_path`, asserting the full expected path set under `--scope keep/inner` with the semantic arm silenced (otherwise the semantic arm supplies correct paths from `concept_emb` and covers for the bug).

## Test-Output

Mutation probe on a copy — old prefix reinstated (`prefix = _b`):

```
### M2: substring arm prefixes with bundle name (B04)
Ran 4 tests in 0.019s
FAILED (failures=2)
```

Fixed tree:

```
python3 -m unittest test_okf_cli   ->  Ran 212 tests, OK
python3 -m unittest test_okf_mcp   ->  Ran 21 tests, OK
```

## Smoke

Against a temporary catalogue with one concept at `b/sub/y.md`, no FTS index (forcing the substring arm): `--scope b/sub` reports `b/sub/y`, matching the unscoped run.

## Deviations/ERRATA

None. The fix is confined to the path expression; scoring, `contrib` breakdown and the `6*len(terms)` scale are untouched.

## Notes for T(n+1)

The first version of the regression test passed against the mutated code. With a `.tagvec` fixture present the semantic arm answered whenever the lexical arm produced nothing usable, reading its paths straight from `concept_emb` — so the arms covered for each other and the case passed for the wrong reason. Any future test that means to exercise ONE arm has to silence the others; `FindFilterContract._silence_semantic_arm` does this. Worth remembering before trusting a green single-arm test in this file.
