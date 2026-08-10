---
# OKFT-yixf
title: sharpen the archive precedence and staleness tests
status: completed
type: task
priority: low
created_at: 2026-08-09T20:46:14Z
updated_at: 2026-08-10T11:08:33Z
parent: OKFT-0xkj
---

Two non-blocking findings from the review of `OKFT-pnyf` (2026-08-09). Both are test-strength gaps, not behaviour defects — the current code is correct, it is just less protected than it looks.

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



## 2026-08-10 — I03 from the review of `OKFT-fu7o`: the AC4 guard is narrower than documented

`FtsIndexArchive.test_staleness_check_never_reads_a_concept_body` (cli/test_okf_cli.py:3143) enforces "the staleness check performs no concept-body reads" by monkeypatching the module attribute `okf.read_file` to a function that raises. That catches exactly one named helper.

The reviewer constructed the bypass and confirmed it: adding a raw `with open(ap, encoding="utf-8") as _f: _f.read()` inside `_fts_index_stale`'s active branch leaves the test **green** while a body-read path is live. `pathlib.Path.read_text` and `codecs.open` would be equally invisible.

No current defect — `_fts_index_stale` calls only `os.path.getmtime`, `list_bundles` and `iter_concepts`, so AC4 holds in the production code today, and `read_file()` is the codebase-wide idiom for reading concept bodies. The gap is in the regression protection, which is weaker than the bean text claims.

Reviewer's recommendation: patch at module level for the duration of the test (e.g. `builtins.open`) instead of the single named helper, so any read path trips it.

### Added acceptance

3. THE test suite SHALL enforce the no-body-read property of the staleness check against any read path, not only against the named `read_file` helper.


### Requirement 1: The precedence and staleness guards actually guard

**Objective:** As a maintainer of this test suite, I want each of the three named guards to fail when the property it protects is broken, so that a green suite is evidence rather than decoration.

#### Acceptance Criteria

1. THE test suite SHALL assert the resolved target of the bystander wikilink after an archive, not merely the absence of the `turns-ambiguous` line.
2. THE test suite SHALL cover an existing-but-empty `_archive/` directory.
3. THE test suite SHALL cover a `collisions` set holding an archived namesake alongside an active candidate.
4. THE test suite SHALL enforce the no-body-read property of the staleness check against any read path, not only against the named `read_file` helper.

#### Success Criteria

- SC-01: Inverting the precedence direction in `_apply_archive_precedence` turns the E2E bystander test red on its own, without relying on `MoveSimulationArchivePrecedence`.
- SC-02: Adding a raw `open(...).read()` of a concept body inside the active branch of `_fts_index_stale` turns the AC4 guard red.
- SC-03: Both new edge cases fail when the precedence rule is removed from the code path they exercise.

_Requirements: reviews of `OKFT-pnyf` (I01, T01) and `OKFT-fu7o` (I03), 2026-08-09/10_

## Recommended Skills

- `superpowers:test-driven-development` — every success criterion here is a mutation that must turn a named test red; writing the mutation first is the only way to know which test that is.


## Prelude 2026-08-10 — conventions carried through this epic

No behavioural findings route into this leaf. Three process obligations do, established by the reviews of `OKFT-mk7m`, `OKFT-gqss`, `OKFT-5436` and `OKFT-tk33`:

1. **`Refs: OKFT-yixf` on every commit**, including the one that closes the bean. It is style, not hook-enforced, which is exactly why three leaves in this epic dropped it before it became a prelude.
2. **Count every commit subject against the 50-byte soft target**, including the bean-closing one — that is the commit that escaped the count three times, because it gets written after the gate is already green. The 72-byte hard limit is hook-enforced and is not the issue.
3. **Mutation proofs cite `file:line` and the mutated expression verbatim**, not the semantic name of a branch. In `OKFT-mk7m` a mutation described as "the foreign-repo retry branch" matched two different `if` lines with different blast radii, and the reviewer had to work out which one had actually been run.

**Relevant precedent for this leaf specifically.** Every leaf of this epic so far produced at least one mutation that left the suite silently GREEN — and in each case the defect was in the proof, not in the production code. That is precisely what this bean is about: three named guards that are weaker than they look. Expect your own new assertions to be subject to the same failure mode, and mutate them too.

## Summary

Sharpened the three named guards this leaf's bean identifies as weaker than they look. No production-code behaviour change — `git diff --stat cli/okf-cli.py` against HEAD is empty; every mutation used to prove sensitivity was applied and reverted, never landed. All work is in `cli/test_okf_cli.py`, commit `e7d9f41`.

- SC-01: `ArchiveConcept.test_archive_does_not_falsely_flag_a_bystander_as_turning_ambiguous` (now `cli/test_okf_cli.py:5614`) gained the assertion the bean supplied — the resolved TARGET of the bystander link after archive, via `build_concept_basename_index` + `resolve_wikilink`, not merely the absence of `"turns-ambiguous"`.
- SC-02: `FtsIndexArchive.test_staleness_check_never_reads_a_concept_body` (`cli/test_okf_cli.py:3258`) now patches `builtins.open` AND `io.open` for the call's duration, not only the named `okf.read_file` helper — closing the `pathlib`/`codecs`/bare-`open` bypass the bean's I03 finding names.
- SC-03/AC3: new test `RenameWikilinks.test_rename_into_a_basename_held_by_an_archived_namesake_stays_resolved` pins the `collisions`-set-from-`iter_rename_scan_md` path through `_index_after_move`, which no prior test exercised (verified by grep — no test combined `_archive/` with a real rename-scan collision before this leaf).
- SC-03/AC2: new test `WikilinkArchiveResolution.test_existing_but_empty_archive_directory_does_not_crash_or_contribute` pins the existing-but-empty `_archive/` geometry. See Deviations — this one is **not** precedence-sensitive, and I am not claiming it is.

Suite: 631 -> 633 tests (2 new: AC2, AC3; SC-01/SC-02 strengthened existing tests in place).

## Test-Output

### SC-01 — `_apply_archive_precedence`, inverted (`cli/okf-cli.py:3388-3389`)

Mutated expression, verbatim:
```
-    active = [c for c in candidates if not c.lower().startswith("/_archive/")]
-    return sorted(active) if active else sorted(candidates)
+    archived = [c for c in candidates if c.lower().startswith("/_archive/")]
+    return sorted(archived) if archived else sorted(candidates)
```

BEFORE (weak test, mutation applied) — GREEN:
```
test_archive_does_not_falsely_flag_a_bystander_as_turning_ambiguous ... ok
Ran 1 test in 0.444s
OK
```

AFTER strengthening (same mutation re-applied) — RED, exact assertion:
```
AssertionError: Tuples differ: ('resolved', ['/_archive/a/old.md']) != ('resolved', ['/d/old.md'])
```
Reason: under inversion the bystander resolves to a single candidate too — just the wrong one, `/_archive/a/old.md` instead of `/d/old.md`. The new assertion checks the resolved TARGET (AC1's own wording), which the old `assertNotIn("turns-ambiguous", out)` could not distinguish.

Mutation reverted; `git diff --stat cli/okf-cli.py` empty after each round.

### SC-02 — raw read inside `_fts_index_stale`'s active branch (`cli/okf-cli.py:767-772`)

Mutated expression, verbatim (inserted after `n_active += 1`):
```
+            with open(ap, encoding="utf-8") as _f:
+                _f.read()
```

BEFORE (weak test, patches only `okf.read_file`, mutation applied) — GREEN:
```
test_staleness_check_never_reads_a_concept_body ... ok
Ran 1 test in 0.004s
OK
```

AFTER strengthening (patches `builtins.open` + `io.open`, same mutation re-applied) — RED:
```
File "cli/okf-cli.py", line 770, in _fts_index_stale
    with open(ap, encoding="utf-8") as _f:
AssertionError: staleness check opened a file: .../b/one.md
```
Reason: the raw `open(ap)` call bypasses the named `okf.read_file` helper entirely; patching `builtins.open`/`io.open` instead catches any read path (bare `open`, `codecs.open` -> `builtins.open`, `pathlib.Path.open`/`read_text` -> `io.open`). Both names patched because they are separate bindings to the same underlying C function — patching only one leaves the other's callers invisible, which would have been an allowlist reintroducing exactly the hole SC-02 exists to close.

Mutation reverted; `git diff --stat cli/okf-cli.py` empty after each round.

### SC-03/AC3 — precedence rule removed from `_apply_archive_precedence` (`cli/okf-cli.py:3388-3389`)

Mutated expression, verbatim:
```
-    active = [c for c in candidates if not c.lower().startswith("/_archive/")]
-    return sorted(active) if active else sorted(candidates)
+    return sorted(candidates)
```

BEFORE (full suite, my new tests stashed out via `git stash push -- cli/test_okf_cli.py`, mutation applied) — 4 pre-existing failures, none touching the rename-scan/archive-collision path:
```
ERROR: test_archive_does_not_falsely_flag_a_bystander_as_turning_ambiguous (ArchiveConcept)
FAIL: test_precedence_applied_to_the_slot_the_move_lands_in (MoveSimulationArchivePrecedence)
FAIL: test_active_candidate_wins_over_an_archived_one_of_the_same_name (WikilinkArchiveResolution)
FAIL: test_two_active_candidates_stay_ambiguous_even_with_an_archived_third (WikilinkArchiveResolution)
```
(This is a stronger mutation than SC-01's inversion — it also catches the still-weak bystander test, unlike inversion. Neither pre-existing failure list includes anything exercising `iter_rename_scan_md`'s walk into `_archive/`, confirmed separately by grep — no test combined `_archive/` fixtures with `cmd_rename`/`plan_wikilink_rewrites` before this leaf.)

AFTER adding the new test (same mutation re-applied) — RED, exact assertion:
```
AssertionError: 'turns-ambiguous' unexpectedly found in
'would move   a/old.md  ->  a/target.md
  wikilink-collision  new basename already taken by /_archive/z/target.md
  turns-ambiguous  b/x.md [body]  [[target]]  candidates after the move: /_archive/z/target.md, /a/target.md
  ...'
```
Reason: `_archive/z/target.md` lands in `plan_wikilink_rewrites`' `collisions` set because `iter_rename_scan_md` walks `_archive/` (`_prune_walk_dirs`, `cli/okf-cli.py:1872-1874`, excludes only `node_modules` and dot-dirs). `_index_after_move` (`cli/okf-cli.py:3892-3899`) merges `collisions` with the move's new active candidate and re-applies precedence to that slot; with the rule removed, both survive, the bystander's resolution goes from `resolved` to `ambiguous`, and `turns_ambiguous` fires.

Mutation reverted; `git diff --stat cli/okf-cli.py` empty after each round.

### Full suite, current HEAD, both directions

```
$ python3.11 -m unittest discover -p 'test_*.py'   # cli/
Ran 633 tests in 29.954s
OK
```
`git diff --stat cli/okf-cli.py` against HEAD: empty (no production change).

## Smoke

Not applicable. This leaf changes only test assertions and adds two tests; there is no behaviour change to demonstrate against a running instance, per the bean's own gate item 7.

## Deviations/ERRATA

1. **SC-03 does not literally bind AC2.** The bean's Success Criterion "Both new edge cases fail when the precedence rule is removed from the code path they exercise" cannot hold for AC2 (existing-but-empty `_archive/`, `list_bundles(archive_root) == []`) as a matter of arithmetic: with zero archived candidates for any basename in that scenario, `_apply_archive_precedence`'s active/archived filter is applied to a list that already contains only actives — removing or inverting the filter cannot change its output, because there is nothing archived to prefer active over. I verified this by construction (traced both the inversion and the full-removal mutation against the candidate set an empty-archive-dir test can ever produce) rather than asserting it and hoping. I wrote AC2's test to the bean's own literal AC2 wording ("SHALL cover an existing-but-empty `_archive/` directory") — a geometry/robustness pin — and said so in its docstring, rather than silently presenting non-existent precedence sensitivity as satisfied. **Escalating, not deciding**: if SC-03 was meant to also require AC2 to be precedence-sensitive, the scenario as described in the bean cannot satisfy that, and either the SC-03 wording or the AC2 scenario needs a PO/planner adjustment.
2. **Two mutation forms used across SC-01 and SC-03, both textually licensed by the bean/SPEC.** SC-01 uses the bean's own "inverting the precedence direction" wording (archived wins outright). SC-03/AC3 uses SPEC §7's own guard-reversal wording ("Entfernt man die Aktiv-vor-archiviert-Regel … muss A06 rot werden") — full removal, no active/archived distinction at all. I used the removal form for AC3 because it is the SPEC's own reversal proof and produces a cleaner, more attributable failure than inversion would have for this exact scenario; I ran the removal form against SC-01's scenario during design (not part of the committed test) and confirmed it also catches the weak bystander test, which the inversion form does not — noted above under SC-03's "BEFORE" evidence for transparency, not claimed as SC-01 proof.
3. **Environment note, not a production finding I'm certain of:** early in this session, `just test` (which resolves bare `python3` to the Homebrew-linked 3.14.6) showed 6 failures/errors, all in `RenameSourceUnderArchiveRefuses` (sibling leaf `OKFT-tk33`, out of scope for me), traced to `os.path.realpath(old_abs)` inside `cmd_rename` apparently receiving a stale/wrong `old_abs` value under CPython 3.14.6. Re-running the identical scenario under `python3.11` passed cleanly (matches the bean's stated `631 tests / OK` baseline), and re-running `just test` (3.14.6) several times afterward came back green every time — the failure did not reproduce again. I used `python3.11` for every mutation-proof run in this leaf specifically to avoid this noise, but flag it here rather than silently ignoring a failure I saw once and could not pin down: worth a look if `just test` is ever flaky again under the current default `python3` (3.14.6, `/opt/homebrew/bin/python3`).
4. No production code was changed. `cli/okf-cli.py` is byte-identical to HEAD `e399f82` (parent commit before my test-only commit `e7d9f41`).

## Notes for T(n+1)

- If AC2/SC-03 gets a PO ruling, the two live options I see: (a) accept the geometry-only reading and drop SC-03's "both" language for AC2 specifically; (b) if precedence sensitivity is actually wanted for the empty-archive-dir scenario, it would need a second basename with a real active/archived pair elsewhere in the same fixture — at which point it stops being "empty `_archive/`" in the sense the bean describes (`list_bundles(archive_root) == []` no longer holds) and becomes a variant of AC3's collision test instead.
- The `builtins.open`/`io.open` double-patch pattern in the AC4 test is reusable if another "no read path may run" guard shows up elsewhere in this codebase (e.g. any future staleness/index check).
