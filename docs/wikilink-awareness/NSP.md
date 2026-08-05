# NSP — wikilink-awareness

Handover for a specialist picking this topic up cold. Written 2026-08-05 against verified state, not from memory.

## Mission

Close the remaining verification gaps in the wikilink-awareness feature so that every REQ code in `SPEC.md` withstands an adversarial reviewer. The feature itself is implemented and green; what is missing is assertion coverage on a set of guards, plus one deployment decision that only Erik can make.

Terminal condition: all 15 mutants in `mutants.py` are KILLED, the suite is green, the live figures still hold, and a fresh adversarial review finds no severity-1 defect.

## Verified state

The whole change is an **uncommitted working-tree diff** on `main` in `/Users/erik/dev/okf-tools`, baseline commit `a7770f0`. Four modified files (`cli/okf-cli.py` +887, `cli/test_okf_cli.py` +1321, `cli/test_okf_mcp.py` +67, `mcp/okf_mcp.py` +15) and one untracked directory (`docs/wikilink-awareness/`). Committing this is the first thing to agree with Erik — a session boundary with 2252 uncommitted lines is the largest single risk on this topic.

Tests: `test_okf_cli` 362 green, `test_okf_mcp` 26 green, whole repo 450 green.

Live catalogue, read-only: 2105 wikilink occurrences, 257 resolved, 0 ambiguous, 1848 unresolved; body 179 (162 resolved), frontmatter 1926 (95 resolved). Full-catalogue scan ~1 s against the 5 s NFR-01 budget. An integrity sweep over all 2777 rename-reachable files reports 0 length drifts, 0 span mismatches, 0 splice drift.

Mutation: 15 of 31 mutants survive, unchanged since run 4. These are the open work.

## Where things are

`cli/okf-cli.py` holds all feature code: the scanner (`WIKILINK_RE`, `_fenced_code_spans`, `_indented_code_spans`, `_blank`, `_dead_zone_mask`, `is_yaml_frontmatter_block`, `wikilink_regions`, `parse_wikilinks`), the resolver (`build_concept_basename_index`, `resolve_wikilink`), the reporting command (`cmd_wikilinks`), the check (`check_wikilink_resolvable`, `wikilink_checked_bundles`) and the rename half (`canonical_case_path`, `iter_rename_scan_md`, `_rewrite_wikilink_raw`, `plan_wikilink_rewrites`, `_index_after_move`, `_apply_wikilink_rewrites`, `cmd_rename`).

`docs/wikilink-awareness/SPEC.md` is the contract: 15 REQ, 2 NFR, ~80 AC, plus the amendment record (D01–D15, C01–C08, ASM-01–05, Q01–Q06) that explains why each rule reads the way it does. Read the D-codes before changing behaviour; several encode a defect that was already paid for once.

`docs/wikilink-awareness/mutants.py` is the mutation harness. Run `python3 docs/wikilink-awareness/mutants.py` from the repo root for the full set, or name ids to iterate: `python3 docs/wikilink-awareness/mutants.py Q80 Q82`. It copies `cli/` to a scratch directory and never writes to the repo.

## Open work

### T01 🟣 Close the 15 surviving mutants

Each row below names the weakening, why the guard exists, and the shape of the test that would kill it. Add the tests to the existing classes in `cli/test_okf_cli.py` (`WikilinkExtraction`, `WikilinkResolve`, `WikilinkCommand`, `RenameWikilinks`, `WikilinkCheck`).

| Id | Weakening | Why the guard exists | Test shape |
| --- | --- | --- | --- |
| Q09 | `_indented_code_spans` drops the `i == 0` guard | Without it, index `-1` wraps to the last line and the first line of a file can open a phantom code block | File whose very first line is `    [[A]]` and whose last line is non-blank prose; the link must still be scanned |
| Q23 | `is_yaml_frontmatter_block` requires every line to look like YAML, not just the first | 432 qm-wiki files carry a multi-line German description continued on unindented lines; the all-lines rule reclassified them as body and shifted 555 links between regions | Frontmatter whose first line is `key: value`, followed by an unindented continuation line with no colon and a block-list item; a link property must be reported as `frontmatter` |
| Q23b | an empty `---\n---` block counts as body | `split_frontmatter` cannot tell an empty head from a thematic rule; calling it body shifts the region of everything after it | File `---\n---\n\n[[A]]`; the occurrence must be region `body` and the head must not be scanned as prose |
| Q23c | an indented fence disqualifies a YAML block | An indented fence is the content of a block scalar (`example: \|`); rejecting the block for it hid every link property in the file | Frontmatter with `example: \|` and an indented ` ``` ` inside; a sibling link property must still be region `frontmatter` |
| Q38 | `keep` in `plan_wikilink_rewrites` no longer excludes `new_link` | Otherwise a `--force` overwrite reports the destination it is replacing as a collision with itself | `--force` overwrite of an existing destination; the disclosure must name the clobbered file but must not list it as a collision |
| Q47 | `_contains_path` compares case-sensitively | The resolver is case-insensitive (D06); an exact comparison drops case-variant candidates out of the `skipped-ambiguous` branch | Ambiguous inbound link whose stored candidate differs from `old_link` only in case; status must be `skipped-ambiguous` |
| Q52 | the `FILENAME_FORBIDDEN_CHARS` destination guard is dropped | A wikilink metacharacter in a filename makes the rewritten link unparseable (ASM-03) | `rename a/x.md a/y#z.md` must exit 2 with a message containing `forbidden char` — build the fixture so no other guard fires first |
| Q62 | `FENCE_START_RE` matches backticks only | Tilde fences are equally valid CommonMark; missing them lets an unindented `~~~` block be judged YAML | Block whose first line is key-like and which contains an unindented `~~~` fence; must be classified as body |
| Q63 | the `.md` guard is dropped | A non-markdown destination has no concept identity; every rewritten link would be dead on arrival | `rename a/x.md a/y.txt` must exit 2 with `both paths must be .md` |
| Q64 | the catalogue-root guard is dropped | A destination outside the root escapes every scan; the rewrite would point out of the catalogue | `rename a/x.md ../out.md` must exit 2 with `under the catalogue root` |
| Q65 | the bundle-depth guard is dropped | A root-level file is not a concept and is not in the resolution index | `rename a/x.md top.md` must exit 2 with `inside a bundle` |
| Q76 | `canonical_case_path` returns its argument unchanged | The caller's spelling is compared against the scan's in three places; without normalisation a case-variant source silently mismatches (D14) | Rename addressing the source as `A/X.MD` when the filesystem stores `a/x.md`, with a self-reference in the file; must not crash and must write outbound rewrites to the new path |
| Q78 | the outbound pass scans unmasked text | Plan and applier must use the same mask, or the plan reports rewrites the applier declines to make | Cross-bundle move of a file carrying a markdown link inside **inline code** (not a fence); the link must be neither reported nor rewritten |
| Q80 | the whitespace-basename guard is dropped | A leading or trailing space in the basename can never be matched again: the scanner strips the page part, the index does not strip filenames | `rename a/x.md "a/ y.md"` must exit 2 with a message containing `leading or trailing whitespace` |
| Q82 | inline code is exempted in the frontmatter region | A `---` thematic rule whose first line reads like `key: value` lands in the YAML branch, and its prose backticks would become rewritable | Frontmatter value carrying a backticked `` `[[X]]` ``; the occurrence must not be reported |

Two of these are known to pass **for the wrong reason** today and are the reason the whole set is listed rather than just patched: `test_whitespace_destination_basename_is_refused` and `test_control_character_destination_basename_is_refused` assert only that a `SystemExit` occurred, and the `turns-ambiguous` refusal fires first on their fixtures. Every new or amended test in this table must assert **the specific message**, and the fixture must contain no inbound link that could trigger a different refusal.

### T02 🟣 Deploy the D02 opt-in set

REQ-14 gates `check` behind `wikilink_checked_bundles` in `<root>/.okf.toml`. No such file exists in the live catalogue, so the check is inert in production and a reviewer flagged D02 as undeployed. Writing it is a **change to the Obsidian store** and needs Erik's explicit confirmation before it happens. Until then the feature ships switched off, which is defensible but must be stated, not glossed.

### T03 🟣 Dispatch review round 5

Four rounds have run with two independent adversarial reviewers each. Round 5 should be treated as the last: fix severity-1 findings, document everything below that as a known limit. Erik's standing preference on this point was recorded as "one more round, then cut".

### T04 🟡 ASM-01 subtree preference

The case-insensitivity half of ASM-01 is now established. The subtree-preference half — that Obsidian prefers a candidate in the linking note's own subtree on a basename collision — is still assumed at medium confidence. Falsifier: open `lean-stack-okf/improve-bean-canon-design.md` in Obsidian and see whether `[[GLOSSARY]]` resolves inside `lean-stack-okf`. This needs the app, not the CLI.

## Traps — already paid for, do not re-derive

Use `lower()`, never `casefold()`. Obsidian's resolution runs on JavaScript `toLowerCase()`; `casefold()` maps ß to ss and would resolve `[[STRASSE]]` to `Straße.md` while the app shows the link broken. There are 25 call sites and they must stay consistent.

Never mask by stash-and-restore. An earlier implementation replaced masked spans with placeholders and lost content whenever one masked span contained another's placeholder — `re.sub` does not rescan its replacement, so the inner token reached disk verbatim, and three live files carried exactly that shape. The current design blanks to NUL with the length preserved and splices by offset; keep both properties.

Fences are found line-based, not by regex pairing. A regex pairs backtick runs left to right with no notion of line start or fence width, so one four-backtick fence shifts every later pairing and exposes a real code block to the rewriter. `meta-bind-context-reference.md` in the live catalogue is the file that caught this.

A rename decides what it breaks by simulating resolution before and after the move (`_index_after_move`), not by comparing tokens. A basename-preserving move into a bundle where another concept shares the name turns a unique address ambiguous with no token changing at all; 81 basenames in this catalogue exist in more than one bundle.

New subcommands must be registered in alphabetical position or `CommandDirectoryOrder` fails.

Standard library only, CPython 3.11+, `unittest` only — there is no pytest on any interpreter here, and NFR-02 forbids adding one.

Live verification is read-only. The Obsidian store has never been written to by this work and must not be, other than through T02 once confirmed.

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

## Review history

Round 1 found `rename` fundamentally broken for wikilinks and the index case-sensitive. Round 2 found a half-applied case fix that would have orphaned the 96 links D06 exists to rescue, plus the nested-token loss above. Round 3 found the fence-pairing defect with a live file exposed, and a YAML heuristic so strict it reclassified 432 files. Round 4 found the token-comparison rename defect, the missing path canonicalisation, and the `casefold`/`lower` divergence.

Severity-1 counts per round were 2, 2, 4, 4 — flat, but the findings moved steadily outward: round 1 hit core mechanics, round 4 could only reach validation edges after 50 000 fuzz documents produced no byte error in the rewriter. That trajectory, not the raw count, is the argument for cutting after round 5.
