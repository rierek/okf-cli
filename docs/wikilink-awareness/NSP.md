# NSP — wikilink-awareness

Handover for a specialist picking this topic up cold. Written 2026-08-05 against verified state, replacing a version whose "verified state" had drifted in seven places.

## Mission

The feature is done. What remains is one deferred design decision with no live exposure, and the discipline not to reopen the rest.

Terminal condition met: all 39 mutants KILLED, suite green, live figures holding, D02 deployed and proven armed, review round 5 closed with zero severity-1 findings, ASM-01 confirmed against the app.

## Verified state

Committed on `main` in `/Users/erik/dev/okf-tools`, tree clean. Relevant commits: `4240159` (spec, handover, mutation stand), `d331d5f` (kill the 15 surviving mutants), plus the round-5 commit carrying `mutants.py`'s R-batch and the SPEC amendments. The catalogue side is one commit in its own repo: `Knowledge-Catalogue@2b16fc5` adds `.okf.toml`.

Tests: 400 green in ~5 s (`test_okf_cli` + `test_okf_mcp`).

Mutation: **39 mutants, killed=39, survived=0, botched=0.** Two further candidates are recorded inside `mutants.py` as equivalent-not-surviving, with the argument for each; do not re-add them as mutants.

Live catalogue, read-only: 2105 wikilink occurrences, 257 resolved, 0 ambiguous, 1848 unresolved; body 179 (162 resolved), frontmatter 1926 (95 resolved). Full-catalogue scan 0.9 s against the 5 s NFR-01 budget. Integrity sweep over all 2777 rename-reachable files: 0 length drifts, 0 span mismatches.

The check gate is armed and proven armed: `check` is byte-identical before and after `.okf.toml` (`OK — 0 violations`), and a synthetic dead-target occurrence warns in an opted-in bundle and stays silent in an opted-out one. A clean `check` on a clean catalogue proves nothing by itself — that probe is what separates "armed" from "misconfigured".

## Where things are

`cli/okf-cli.py` holds all feature code: the scanner (`WIKILINK_RE`, `_fenced_code_spans`, `_indented_code_spans`, `_blank`, `_dead_zone_mask`, `is_yaml_frontmatter_block`, `wikilink_regions`, `parse_wikilinks`), the resolver (`build_concept_basename_index`, `resolve_wikilink`), the reporting command (`cmd_wikilinks`), the check (`check_wikilink_resolvable`, `wikilink_checked_bundles`) and the rename half (`canonical_case_path`, `iter_rename_scan_md`, `_rewrite_wikilink_raw`, `plan_wikilink_rewrites`, `_index_after_move`, `_apply_wikilink_rewrites`, `cmd_rename`).

`docs/wikilink-awareness/SPEC.md` is the contract: 15 REQ, 2 NFR, ~80 AC, plus the amendment record (D01–D16, C01–C09, ASM-01–05, Q01–Q07). Read the D-codes before changing behaviour; several encode a defect that was already paid for once. The `Assertion coverage` section under Traceability is the newest part and the one most likely to be skipped — it is the reason to trust the AC table at all.

`docs/wikilink-awareness/mutants.py` is the mutation harness. `python3 docs/wikilink-awareness/mutants.py` for the full set, or name ids to iterate: `python3 docs/wikilink-awareness/mutants.py Q80 R11`. It copies `cli/` to a scratch directory and never writes to the repo.

## Open work

### T01 🟢 done — ASM-01 subtree preference confirmed

`[[GLOSSARY]]` at `lean-stack-okf/improve-bean-canon-design.md:112` has six candidates catalogue-wide; `obsidian links path="…"` against the open vault answers `lean-stack-okf/GLOSSARY.md`, the same target `resolve_wikilink` produces. Obsidian prefers the linking note's own subtree.

What it did NOT settle is Q02: source and winning candidate share folder and bundle, so a same-folder rule and a same-bundle rule predict the same answer. A discriminating occurrence would need differing folders inside one bundle, and the catalogue holds zero of them — so the two rules are indistinguishable here by measurement, not by oversight. Left open deliberately; nothing depends on it until a bundle grows a subdirectory duplicating a basename it already holds.

### T02 🟣 Decide Q07 — Unicode normalisation

A confirmed defect with zero live exposure, deferred on purpose. A concept stored NFD with a link written NFC reports `unresolved`, and `rename` then leaves that link behind — the silent-orphan class D06 exists to close, reached from a different direction. Reproduce it in four lines: create `<bundle>/<NFD "Qualität">.md`, then resolve the NFC spelling and the NFD spelling of the same word; the first is `unresolved`, the second `resolved`.

Zero exposure today: 2422 index keys, not one non-ASCII basename. That is what makes it deferrable, not what makes it fine.

The fix touches five key-deriving sites (`build_concept_basename_index`, `resolve_wikilink` twice, `plan_wikilink_rewrites`), which is the code four review rounds hardened. Add the mutant before the fix — drop the normalisation, expect SURVIVED — so the test is proven non-vacuous rather than assumed to be. Keep the D06 property that `[[STRASSE]]` stays unresolved against `Straße.md`: normalisation and case folding are separate axes and only one of them is Obsidian's.

### T03 🟡 D16 leaves the D02 contrast bundle out

`bew_BeWiki-Python-Download-okf` was to be opted in as the contrast case proving the check reports what it should. It is not, because its 11 unresolved links have no owner and a permanent warning costs `check` the clean run that makes it readable. The contrast is carried by a fixture instead. If that trade is wrong, the fix is one line in `.okf.toml` — but then accept that `check` warns on every run from now on.

## Do not reopen

Review is closed after round 5. Severity-1 counts per round were 2, 2, 4, 4, 0, and the findings moved steadily outward: round 1 hit core mechanics, round 4 could only reach validation edges after 50 000 fuzz documents produced no byte error in the rewriter, round 5 produced one unasserted guard (the reserved source), one deferred defect with no live exposure, one docstring that overstated its own case, and two equivalent mutants. That trajectory is the argument for the cut. Reopening costs more than it can find.

## Traps — already paid for, do not re-derive

Use `lower()`, never `casefold()`. Obsidian's resolution runs on JavaScript `toLowerCase()`; `casefold()` maps ß to ss and would resolve `[[STRASSE]]` to `Straße.md` while the app shows the link broken. There are 25 call sites and they must stay consistent.

Never mask by stash-and-restore. An earlier implementation replaced masked spans with placeholders and lost content whenever one masked span contained another's placeholder — `re.sub` does not rescan its replacement, so the inner token reached disk verbatim, and three live files carried exactly that shape. The current design blanks to NUL with the length preserved and splices by offset; keep both properties.

Fences are found line-based, not by regex pairing. A regex pairs backtick runs left to right with no notion of line start or fence width, so one four-backtick fence shifts every later pairing and exposes a real code block to the rewriter. `meta-bind-context-reference.md` in the live catalogue is the file that caught this.

A rename decides what it breaks by simulating resolution before and after the move (`_index_after_move`), not by comparing tokens. A basename-preserving move into a bundle where another concept shares the name turns a unique address ambiguous with no token changing at all; 81 basenames in this catalogue exist in more than one bundle.

`FENCE_START_RE` matches at most three spaces of indent. A fixture that indents a fence four spaces to test the indented-fence branch exercises nothing — that was a live example of a test asserting less than it claimed.

A guard test must assert the message, not just `SystemExit`. `cmd_rename` has ten refusals plus the turns-ambiguous one; dropping the guard a test names still produces an exit. Use `RenameWikilinks._rename_fails`.

New subcommands must be registered in alphabetical position or `CommandDirectoryOrder` fails.

Standard library only, CPython 3.11+, `unittest` only — there is no pytest on any interpreter here, and NFR-02 forbids adding one.

Live verification is read-only. The only write this work has ever made to the Obsidian store is `.okf.toml`.

## Verification recipes

Suite:

```
cd /Users/erik/dev/okf-tools/cli && python3 -m unittest test_okf_cli test_okf_mcp
```

Mutation:

```
cd /Users/erik/dev/okf-tools && python3 docs/wikilink-awareness/mutants.py
```

Live figures and NFR-01:

```
cd /Users/erik/dev/okf-tools && time python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue wikilinks --json > /tmp/wl.json
```

Integrity sweep — over every path from `iter_rename_scan_md`, assert `len(wikilink_scan_text(text)) == len(text)` and, for each record from `parse_wikilinks`, that `text[span[0]:span[1]] == rec["raw"]`. Any nonzero count means the mask or the offsets drifted and no rewrite may run.

Gate armed, not merely silent — build the index, then call `check_wikilink_resolvable` with a synthetic ctx carrying a dead target, once attributed to an opted-in bundle and once to an opted-out one. Expect one warning and none.
