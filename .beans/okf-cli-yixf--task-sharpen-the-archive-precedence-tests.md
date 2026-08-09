---
# okf-cli-yixf
title: task sharpen the archive precedence tests
status: todo
type: task
priority: low
created_at: 2026-08-09T20:46:14Z
updated_at: 2026-08-09T22:29:47Z
---

Two non-blocking findings from the review of `okf-cli-pnyf` (2026-08-09). Both are test-strength gaps, not behaviour defects — the current code is correct, it is just less protected than it looks.

## I01 — the E2E bystander test is not sharp

`ArchiveConcept.test_archive_does_not_falsely_flag_a_bystander_as_turning_ambiguous` (cli/test_okf_cli.py:4922-4933) asserts only `assertNotIn("turns-ambiguous", out)`. Under the inverted precedence mutation (archived wins over active) the result stays a single candidate — the wrong one — so no `turns-ambiguous` line is printed and the test stays green while resolving to `/_archive/a/old.md` instead of `/d/old.md`. It checks a necessary, not a sufficient condition. SC-01 currently rests on the accompanying unit test alone.

The reviewer supplied the assertion that makes it sharp — add after `self._archive("a/old.md", apply=True)`:

    after_index = okf.build_concept_basename_index(self.tmp)
    self.assertEqual(okf.resolve_wikilink(after_index, "a/other.md", "old"),
                     ("resolved", ["/d/old.md"]))

## T01 — two unpinned edge cases

1. An `_archive/` directory that exists but is empty — the `os.path.isdir(archive_root)` guard branch taken with `list_bundles()` returning `[]` (cli/okf-cli.py ~3251). Trivial geometrically, but no test names it.
2. A rename-scan `collisions` set that holds an archived namesake next to an active candidate. `iter_rename_scan_md` walks `_archive/` because `_prune_walk_dirs` only excludes `node_modules` and dot-dirs (cli/okf-cli.py:1738-1740, 3652-3660). The reviewer verified the current code handles it correctly — precedence is applied to the full merged set including `collisions` — but nothing pins it.

## Acceptance

1. THE test suite SHALL assert the resolved target of the bystander link after an archive, not merely the absence of the `turns-ambiguous` line.
2. THE test suite SHALL cover an existing-but-empty `_archive/` directory and a `collisions` set containing an archived namesake alongside an active candidate.

### Success Criteria

- SC-01: Inverting the precedence direction in `_apply_archive_precedence` turns the E2E bystander test red on its own, without relying on `MoveSimulationArchivePrecedence`.



## 2026-08-10 — I03 from the review of `okf-cli-fu7o`: the AC4 guard is narrower than documented

`FtsIndexArchive.test_staleness_check_never_reads_a_concept_body` (cli/test_okf_cli.py:3143) enforces "the staleness check performs no concept-body reads" by monkeypatching the module attribute `okf.read_file` to a function that raises. That catches exactly one named helper.

The reviewer constructed the bypass and confirmed it: adding a raw `with open(ap, encoding="utf-8") as _f: _f.read()` inside `_fts_index_stale`'s active branch leaves the test **green** while a body-read path is live. `pathlib.Path.read_text` and `codecs.open` would be equally invisible.

No current defect — `_fts_index_stale` calls only `os.path.getmtime`, `list_bundles` and `iter_concepts`, so AC4 holds in the production code today, and `read_file()` is the codebase-wide idiom for reading concept bodies. The gap is in the regression protection, which is weaker than the bean text claims.

Reviewer's recommendation: patch at module level for the duration of the test (e.g. `builtins.open`) instead of the single named helper, so any read path trips it.

### Added acceptance

3. THE test suite SHALL enforce the no-body-read property of the staleness check against any read path, not only against the named `read_file` helper.
