# Wikilink Awareness in okf-cli

- Status: accepted; amended 2026-08-05 during implementation — see D06 to D13, C07, C08 and the ASM-01/ASM-02/C03 verdicts. Every amendment records a measurement, not a preference; where an earlier draft of an amendment was itself a rationalisation, D07 and C07 say so and record what replaced it.
- Grounded at: okf-tools `main` @ `a7770f0`; Knowledge-Catalogue `main` @ `7e0d766`, clean tree
- Snapshot caveat: five of the 21 bundles are symlinks into other repositories, whose content the catalogue commit does not pin. Every catalogue figure below is a snapshot taken 2026-08-05 and drifts when a mounted repository advances; `lean-stack-okf` alone moved from 138 to 147 occurrences within a day. Acceptance criteria therefore avoid counts that a mount can change.
- Scope: okf-cli recognises Obsidian wikilinks (`[[…]]`) in body text and in frontmatter as first-class references — it reports them, resolves them, and keeps them intact across `rename`.

## Problem

okf-cli's link model is markdown-only: four separate scanners in `cli/okf-cli.py` iterate a markdown-link pattern, and no wikilink pattern exists anywhere in the file. The catalogue nevertheless holds 2105 wikilinks, 257 of which resolve to a real catalogue concept today, and none of them is visible to `check`, `refs`, `fix-crosslinks`, `rename` or the bundle graph. The consequence is a silent data-loss path: `rename` moves a concept, rewrites every inbound markdown link, reindexes, prints `rewrote N inbound link(s)`, and leaves every inbound wikilink pointing at a name that no longer exists — unreported, before and after.

The population splits sharply by region. Body text carries 179 wikilinks of which 162 resolve, concentrated in `lean-stack-okf` (145) — a working wikilink graph that any `rename` can break today. Frontmatter carries 1926 wikilinks of which 95 resolve; the unresolved remainder sits almost entirely in `qm-wiki` and `general-knowledge-wiki` as Obsidian link-type properties left behind by a Vault import, and 11 are one repeated target, `[[bew_BeWiki-Python-Download]]`, in a mounted repository's own docs bundle.

## Non-Goals

- Converting wikilinks into markdown links — `lean-stack-okf` uses wikilinks as its native form, and converting the unresolved population would fabricate targets that do not exist.
- Cleaning up the 1848 unresolved wikilinks — a content migration, driven by the report this SPEC specifies, not by the CLI itself.
- Resolving heading (`#`) and block (`#^`) suffixes to positions inside the target file — zero occurrences of either were measured; parsing them into fields is in scope, resolving them is not.
- Special handling for a wikilink target that is not a markdown concept — zero occurrences with a binary or asset extension exist catalogue-wide, and the two `![[assets/…png]]` examples in `linear-design-system` sit inside code fences and are therefore masked out. Such a target resolves like any other page part and reports `unresolved` under REQ-05 when no concept matches.
- Wikilink edges in the bundle graph — `bundle_graph` drops every `[[…]]` edge, so `visualize` under-reports; correcting that is a separate topic with its own output contract.
- External HTTP(S) link checking — a distinct topic with a distinct failure model (network, timeouts, rate limits).
- Anchor validation for markdown links — 3 internal anchor links exist catalogue-wide, below the threshold that justifies a rule.
- Wikilinks in the Obsidian working vault (`~/Obsidian/Vault`) — a different store with different tooling.
- Wikilinks inside `_`-prefixed staging directories for the reporting and check surfaces — `iter_all_md` already excludes them by convention.

## Context (as-is)

- `cli/okf-cli.py` (`CROSSLINK_RE`) — `\[([^\]]+)\]\(([^)]+)\)`, the module's only compiled link pattern; drives `rewrite_crosslinks_in_body` and `plan_rename`'s outbound pass.
- `cli/okf-cli.py` (`bundle_graph`) — inline pattern `\[[^\]]+\]\(([^)]+)\)`; builds the node/edge set behind `visualize`, and drops every wikilink edge.
- `cli/okf-cli.py` (`build_ref_matrix`) — the same inline pattern again; the single source of inbound references for both `refs` and `plan_rename`; walks with `_prune_walk_dirs`, which drops only dot-directories and `node_modules`, so it does traverse `_`-prefixed staging directories.
- `cli/okf-cli.py` (`check_crosslink_format`) — the same inline pattern a third time; flags relative and non-resolving catalogue-absolute markdown targets; returns early for reserved files and for symlinked bundles.
- `cli/okf-cli.py` (`iter_all_md`) — prunes dot-directories, `_`-prefixed directories and `assets/`, and yields reserved files; the traversal behind `check` and `fix_crosslinks`. Its pruning is asymmetric to `_prune_walk_dirs`.
- `cli/okf-cli.py` (`plan_rename`) — inbound rewrites come exclusively from `build_ref_matrix`, the outbound pass from `CROSSLINK_RE`. A wikilink is therefore neither discovered nor planned.
- `cli/okf-cli.py` (`_apply_link_rewrites`) — rewrites by replacing the literal `](old_raw)` with `](new_raw)`; the `](` anchor makes it structurally incapable of touching `[[…]]`.
- `cli/okf-cli.py` (`_mask_code_spans`) — masks fenced and inline-code spans; its docstring states that frontmatter is already split off by the caller, so it is defined over a body, not over a whole file.
- `cli/okf-cli.py` (`gather_file_context`) — hands every registered check `ctx["body"]` from `split_frontmatter`, plus `ctx["fm"]` and the whole `ctx["text"]`. No check scans frontmatter for link patterns, but the access path exists: `check_tag_registered` reads raw frontmatter through `extract_tags(ctx["text"])`, which walks the frontmatter block itself because `split_frontmatter` keeps only single-line values.
- `cli/okf-cli.py` (`FILENAME_FORBIDDEN_CHARS`) — `#^[]|\:?*"<>%`; a conformant concept filename can contain no wikilink metacharacter.
- `cli/okf-cli.py` (`load_okf_config`) — parses `<root>/.okf.toml` with `tomllib` (arrays supported), returns `{}` when the file is absent. No `.okf.toml` exists at the catalogue root today.
- `cli/okf-cli.py` (`_sub`) — subcommand registration requires a summary and a group from `_GROUP_ORDER` (`navigation`, `search`, `tags`, `maintenance`); the summary feeds both help levels.
- `cli/okf-cli.py` (`resolve_scopes`) — maps a `<bundle>` or `<bundle>/<subdir>` argument, or `None`, onto the list of scopes every scanning command iterates.
- `cli/okf-cli.py` (`cmd_check`) — exits 1 when errors exist, and `--strict` promotes warnings to errors, so a warning-level check can gate.
- `cli/test_okf_cli.py` (`CommandHelpConformance`) — asserts that every registered command carries help text; a command cannot ship undocumented.
- `mcp/okf_mcp.py` (`_COMMANDS`) — maps a CLI verb to `(positional param names, supports --json)`; a command absent from it is invisible to agents. Boolean flags are carried separately in `_BOOL_FLAGS`.
- Measured catalogue state, snapshot 2026-08-05 and subject to mount drift — roughly 2700 markdown files across 21 bundles, 5 of them symlinked. 2105 wikilink occurrences outside dead zones: 257 resolved, 0 ambiguous, 1848 unresolved; by region, 179 in body text (162 resolved) and 1926 in frontmatter (95 resolved). Resolved by bundle: `lean-stack-okf` 147, `general-knowledge-wiki` 59, `qm-wiki` 32, `bew_BeWiki-Python-Download-okf` 7, `ai-wiki` 4, `agent-memory` 3, `dev-wiki` 3, and one each in `devd2-okf` and `okf-meta-wiki`. Unresolved by bundle: `qm-wiki` 1026, `general-knowledge-wiki` 794, `bew_BeWiki-Python-Download-okf` 11, `dev-wiki` 8, `linear-design-system` 8 and `dev-arch-wiki` 1. A full scan takes 0.5 to 1.1 s depending on cache state; the rename scan reaches 2777 files, more than the reporting surface, per C07.
- Two syntax variants are specified but unexercised by the catalogue: the embed marker `![[…]]` has zero occurrences outside code fences, and under the same-bundle tie-break of REQ-03 no ambiguous occurrence exists either — the sole collision candidate, `[[GLOSSARY]]` in `lean-stack-okf/improve-bean-canon-design.md` against five `GLOSSARY.md` files, resolves to its own bundle. Both are therefore verified by fixtures only.
- The largest unresolved sub-population is not a typo class: 32 of `qm-wiki`'s 1058 frontmatter targets are ISO 9001 clause numbers such as `[[8.3.3]]` and `[[7.1.5.1]]`, which address a norm document rather than any note. What the remaining targets address is not established from the code and is carried by ASM-02, not asserted here.

## Constraints and Decisions

- D01 Both regions are in scope. The scanner reads whole file text, and every record carries the region it was found in, because Obsidian treats a frontmatter link property as a real link and updates it on rename; a body-only tool would leave that data-loss path open.
- D02 The opt-in set for the check at introduction is exactly `lean-stack-okf` and `bew_BeWiki-Python-Download-okf`: the first carries 0 unresolved wikilinks and must stay at 0, the second carries 11 and is the contrast case proving the check reports what it should. A clean `check` run is therefore not expected while the contrast bundle is opted in. Rollout to the remaining bundles follows once both behave as specified.
- D03 Symlinked bundles owned by other repositories are in scope for every surface here. The catalogue's rules govern what is mounted into it, so `check_crosslink_format`'s early return for symlinked bundles is not precedent.
- D04 Reserved files participate in every wikilink surface. `iter_all_md` already yields them; `check_crosslink_format`'s early return for reserved files is markdown-link-specific and is not inherited.
- D05 🔴 retired — an extension-based exclusion of non-markdown targets. It was drafted against a population that does not exist: a scan for binary and asset extensions over every page part in the catalogue returns zero hits, and the 32 occurrences the draft rule actually removed are ISO 9001 clause numbers in `qm-wiki` frontmatter, not assets. A literal reading of the retired wording would additionally have dropped 61 further page parts whose text merely contains a dot — 42 in `general-knowledge-wiki`, such as `Claude Code 2.0 Has Arrived (It's Insane) - Youtube - 2026-03-12`, and 19 in `qm-wiki`. Every target now goes through the same lookup, and REQ-05 reports what does not match.
- C01 Single-file, dependency-free CLI: all logic lands in `cli/okf-cli.py` against the CPython standard library, matching the module docstring's "Standard library only — no install required".
- C02 The inbound wikilink scan for `rename` uses the same traversal as `build_ref_matrix`, so it sees `_`-prefixed staging directories, unlike the reporting and check surfaces which use `iter_all_md`. The asymmetry is inherited deliberately: `rename` must not leave a stale reference behind in staging.
- C03 🔴 falsified by D07, superseded by C08. It read: "a wikilink carries no path in its resolvable form, so only a change of basename can invalidate it". True of `[[name]]`, false of `[[dir/name]]` — once a path-qualified target is honoured, a pure directory move breaks it. The basename short-circuit this constraint justified has been removed.
- C08 A move invalidates an inbound wikilink when the token the move would produce differs from the token on disk. That covers a basename change for every form and a directory change for the path-qualified form, and it costs a catalogue scan on every rename, including the ones that turn out to rewrite nothing.
- C04 Test harness is stdlib `unittest`, invoked as `python3 -m unittest test_okf_cli` from `cli/`; no pytest is installed on any interpreter on this machine.
- C05 Enabling the check surface requires creating `<root>/.okf.toml`, which does not exist today; absent that file `load_okf_config` returns `{}`.
- C06 A mount that does not resolve is not a bundle: `vik-okf` is a dangling symlink at the catalogue root, `list_bundles` skips it because `os.path.isdir` is False, and no surface in this SPEC can see it. Unexercised as of 2026-08-05 — the dangling mount no longer exists.
- C07 Both halves of a rename — the markdown pass and the wikilink pass — share one traversal and one dead-zone mask. The traversal is a root-level walk under `_prune_walk_dirs` plus a second pass over each symlinked bundle; either half alone leaves a stale reference behind, since the root walk cannot enter the five mounts and a per-bundle walk cannot see root-level staging. It is deliberately wider than the reporting surfaces: staging, root-level files and `assets/` are all rewritten, because a stale reference there is still stale. Two earlier drafts of this constraint were rationalisations of whatever the code happened to do — one pruned `assets/` from the wikilink pass only, the other claimed the markdown pass already reached the mounts when `build_ref_matrix` walked only the root. Each produced the same defect from opposite ends: a file with one link form updated and the other dangling in the same line. Sharing the traversal is what makes the claim true rather than asserted. The markdown half also matches a link whose target is spelled in a different case than the disk, confirmed through `samefile` so the behaviour stays correct on a case-sensitive filesystem; without it a live `[x](/b/OLD.md)` was left dead beside a correctly updated `[[OLD]]`. `plan_rename`'s outbound pass uses the same mask as its applier, or it reports rewrites the applier then declines to make.
- D06 Resolution is case-insensitive, both when the index is keyed and when it is queried, folding with `lower()` rather than `casefold()`. Obsidian folds with JavaScript's `toLowerCase()`, which leaves ß alone where `casefold()` maps it to ss: under casefold `[[STRASSE]]` would resolve to `Straße.md` here and stay broken in the app, and on a case-sensitive checkout `Straße.md` and `Strasse.md` would collapse into one key and shadow each other. Measured on the catalogue: both foldings produce 2422 index keys, 0 merged basenames and the same 96 rescued links, so the choice costs nothing here and is correct where it matters. The store's filesystem is itself case-insensitive — `open("types.MD")` reaches `TYPES.md` — and Obsidian follows it, so `[[YAML]]` opens `yaml.md`. A case-sensitive table declared 96 live links dead and would have let `rename` orphan them unannounced, which is the failure this SPEC exists to close. Measured effect of the correction: resolved rose from 161 to 257, no previously resolved link changed verdict, and no new ambiguity appeared.
- D07 A path-form target (`[[dir/name]]`) narrows the candidate set to those whose own path ends in that path, and is `unresolved` when nothing matches. Without the narrowing the resolver contradicts the link: `[[a/old]]` resolved to `/z/deep/old.md` via the bundle tie-break, and `rename` then rewrote that link to address a different file while every surface reported `resolved`. A fallback to the bare basename was drafted and removed — it reproduced exactly that failure whenever the spelled-out directory was one the index does not cover, such as `[[_plan/old]]` landing on `a/old.md`.
- D08 One dead-zone mask governs both link forms: fenced code, inline code, `%%…%%` Obsidian comments, `<!--…-->` HTML comments, and 4-space-indented blocks that are not list continuations. Obsidian indexes none of them. Fences are found line-based rather than by regex — a regex pairs backtick runs left to right with no notion of line start or fence width, so one prose ``` mention or a 4-backtick fence shifted every later pairing by one and left the next real code block exposed to the rewriter; one live catalogue file carried exactly that shape, and 4-backtick fences are this project's own convention. An unclosed fence runs to end of file, as Obsidian renders it. The mask is applied in stages over its own output, so no construct inside a masked span can open another. It is length-preserving and blanks to NUL rather than stashing and restoring text: a stash lost content whenever one masked span contained another's placeholder. The frontmatter region skips only the indented-code stage, because YAML indentation is structure — a block list under a blank line is not a code block. Inline code is masked in both regions: exempting it in frontmatter cost more than it bought, since a `---` thematic rule whose first line happens to read like `key: value` lands in that region and its prose backticks were then rewritable, while a genuine link property wrapped in backticks has zero occurrences catalogue-wide and would only be under-reported, never corrupted.
- D11 Whether a `---`-delimited head is YAML frontmatter or a thematic rule opening the body is decided by its first non-blank line: a `key:` line means YAML, anything else means body, and an UNINDENTED code fence anywhere in the block means body regardless. An empty block is frontmatter. The fence test ignores indented fences, which may be the content of a block scalar (`example: |`) — rejecting the whole block for one hid every link property in the file. `split_frontmatter` cannot make this distinction and getting it wrong costs bytes in both directions — body rules over YAML swallow a link property, YAML rules over prose expose a fenced example to the rewriter. Two stricter drafts were measured and discarded: requiring every line to look like YAML rejected 432 `qm-wiki` files whose German descriptions continue unindented, and an ASCII-only key pattern rejected keys such as `Übersicht dokumentierter Informationen ISO 9001:2015:`. Measured effect of the final rule: 0 frontmatter blocks rejected catalogue-wide.
- D09 `rename` refuses, without `--force`, any move that leaves an inbound wikilink ambiguous — whether the link is rewritten, is a bystander pointing at the concept whose name is being taken, or is neither and merely changes meaning (D15). The set is derived from the before/after resolution, so the same-bundle tie-break is honoured on both sides: counting rewrites blindly refused renames that broke nothing, and looking only at rewrites missed the ones that break without being rewritten. Collisions are looked for across the rename scan's own reach, not the resolution index, which skips staging, assets and root-level files that the rename rewrites and Obsidian indexes. Everything is disclosed in dry-run and under `--force` either way, including what a `--force` overwrite clobbers.
- D14 The source path is canonicalised to the filesystem's own spelling on entry to `rename`, and the destination's directory part with it. Every downstream comparison — the basename index, the markdown ref matrix, the self-reference check — then compares identical strings, which is what allows those comparisons to stay exact rather than case-folded, and a folded comparison would be wrong on a case-sensitive filesystem. Without it a differently-cased source path crashed the run mid-move with `FileNotFoundError` when the moved file linked to itself, and split the two halves of the rename otherwise.
- D15 What a move breaks is decided by resolving each candidate occurrence against the catalogue as it is AND as it will be, not by comparing link tokens. A token that does not change can still change meaning: a basename-preserving move into a bundle where another concept shares that name turns a unique address ambiguous with nothing to rewrite and nothing to report. 81 basenames in the live catalogue exist in more than one bundle, so this is the shape a real move takes. The simulated index folds in the collisions found across the rename's wider reach, since a same-named draft in staging is invisible to the resolution index and visible to Obsidian.
- D12 `rename` refuses a destination whose basename is reserved, empty, surrounded by whitespace, or carrying a control character. Nothing can resolve to `index.md`, so every inbound wikilink would be rewritten to an address dead on arrival while the run reported success. The other three produce a token no later scan can match: the scanner strips the page part while the index does not strip filenames, and `WIKILINK_RE` cannot span a newline.
- D13 The rewrite path reads and writes verbatim — line endings preserved, undecodable files skipped with a note. `read_file` translates CRLF to LF and substitutes U+FFFD for undecodable bytes, and `write_file` then persists that translation across the whole file rather than the one link it was asked to change.
- D10 Every bundle-name comparison is case-insensitive, not only the link resolution of D06: the opt-in gate keyed on the exact string let `check A` reach bundle `a` and silently switch off this one check while every other check kept firing.

## Requirements

### REQ-01 Wikilink extraction

The okf-cli wikilink scanner shall emit, for the whole text of a markdown file with its dead zones masked per D08, one record per `[[…]]` occurrence carrying the page part with any trailing `.md` stripped, the alias, the heading-or-block suffix, the embed flag, the region and the occurrence's offsets in the original text.

- AC-01.1 test: `WikilinkExtraction.test_shapes` in `cli/test_okf_cli.py` asserts that `[[a]]`, `[[a|b]]`, `[[a#h]]`, `[[a#^blk]]`, `![[a]]` and `[[dir/a]]` yield six records with page parts `a, a, a, a, a, dir/a`, aliases `None, b, None, None, None, None`, suffixes `None, None, h, ^blk, None, None`, and embed flags `False, False, False, False, True, False`.
- AC-01.2 test: `WikilinkExtraction.test_region_is_tagged` asserts that a file with `[[a]]` in a frontmatter list value and `[[b]]` in prose yields two records with regions `frontmatter` and `body` (D01).
- AC-01.3 test: `WikilinkExtraction.test_code_spans_are_not_links` asserts that a body containing `[[x]]` inside a triple-backtick fence, inside a `~~~` fence and inside inline backticks yields zero records.
- AC-01.4 test: `WikilinkExtraction.test_md_suffix_is_stripped` asserts that `[[a.md]]` and `[[a]]` both yield a record with page part `a`, while `[[8.3.3]]` yields a record with page part `8.3.3` (D05).
- AC-01.5 test: `WikilinkExtraction.test_unclosed_is_not_a_link` asserts that `[[a`, `[a]]` and a `[[a` whose `]]` follows only after a newline each yield zero records.
- AC-01.6 test: `WikilinkExtraction.test_comments_are_not_links`, `…test_indented_code_block_is_not_a_link` and `…test_leading_thematic_rule_does_not_expose_a_fence` assert zero records for `[[…]]` inside an HTML comment, a `%%…%%` comment, a 4-space-indented block, and a fence sitting in the pseudo-frontmatter region a leading `---` thematic rule creates (D08).
- AC-01.7 test: `WikilinkExtraction.test_hash_in_an_alias_is_not_a_suffix` asserts `[[dotnet|C#]]` yields alias `C#` and suffix `None`, and `WikilinkExtraction.test_frontmatter_end_agrees_with_split_frontmatter` asserts the region split is byte-identical to `split_frontmatter`'s across six adversarial inputs including CRLF, a BOM and an unclosed block.
- AC-01.8 test: `WikilinkExtraction.test_list_continuation_is_not_code` asserts an indented paragraph under a bullet still yields its link; `…test_comment_regexes_do_not_span_two_comments`, `…test_fence_pattern_does_not_span_two_fences` and `…test_comment_inside_a_fence_does_not_break_the_fence` assert the dead zones neither over-reach nor let an inner marker end an outer span; `…test_frontmatter_keeps_a_link_property_containing_backticks` asserts the narrower frontmatter mask; `…test_mask_preserves_length_so_spans_address_the_original` asserts the mask is length-preserving and each record's span addresses its own `raw` (D08).
- AC-01.9 test: `WikilinkExtraction.test_four_backtick_fence_masks_its_contents` asserts a prose ``` mention followed by a 4-backtick fence, and a fence nested in a wider one, both mask their contents — the pairing defect that left one live catalogue file's code sample rewritable; `…test_unclosed_fence_runs_to_end_of_file` and `…test_info_string_with_a_backtick_is_not_a_fence` pin the two remaining fence edges (D08).
- AC-01.10 test: `WikilinkExtraction.test_thematic_rule_region_gets_body_rules` asserts inline code and indented code in a `---`-opened body region are masked; `…test_yaml_block_with_umlaut_and_colon_keys_is_frontmatter` asserts a key carrying spaces, umlauts and an internal colon still reads as YAML; `…test_fence_in_a_key_like_block_still_means_body` asserts a fence overrides a key-like first line; `…test_nested_dead_zone_does_not_leak_into_raw` asserts `raw` is cut from the original text so no NUL can enter a record; `…test_region_boundary_is_exclusive_at_fm_end` pins the boundary (D11).
- AC-01.12 test: `WikilinkExtraction.test_fence_closing_rules` asserts each closing condition separately (closer at least as wide, same character, marker only), `…test_indented_fence_is_recognised` the three-space allowance, and `…test_wikilink_pattern_rejects_newlines_and_brackets` the pattern D12 depends on (D08).
- AC-01.13 test: `WikilinkExtraction.test_indented_fence_in_a_block_scalar_keeps_the_block_yaml` asserts an indented fence does not disqualify a YAML block; `…test_empty_frontmatter_block_is_frontmatter` and `…test_md_suffix_is_stripped_case_insensitively` pin the two remaining edges (D11, D06).
- AC-01.11 test: `WikilinkExtraction.test_indented_line_without_a_blank_line_is_not_code`, `…test_nested_list_continuation_is_not_code`, `…test_second_indented_paragraph_after_a_list_is_not_code`, `…test_indented_block_after_two_blank_lines_is_still_list_continuation`, `…test_indented_code_span_stops_at_the_last_indented_line` and `…test_blank_line_inside_an_indented_block_does_not_end_it` pin each condition of the indented-code rule separately (D08).

### REQ-02 Unique resolution

If a wikilink page part matches the basename of exactly one non-reserved concept file in the catalogue, then the resolver shall return that file's catalogue-root-absolute path.

- AC-02.1 test: `WikilinkResolve.test_unique_basename` builds a two-bundle fixture and asserts that `[[y]]` in `b/x.md` resolves to `/other/sub/y.md` when `y.md` exists exactly once.
- AC-02.2 test: `WikilinkResolve.test_alias_and_suffix_do_not_affect_resolution` asserts `[[y|Label]]`, `[[y#Heading]]`, `[[y#^blk]]` and `[[y.md]]` all resolve to the same path as `[[y]]`.
- AC-02.3 command: `python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue wikilinks lean-stack-okf` reports 0 unresolved and 0 ambiguous, every occurrence resolved, with both regions represented. The absolute count is deliberately not asserted: `lean-stack-okf` is a mounted repository and its total drifts.
- AC-02.4 test: `WikilinkResolve.test_resolution_is_case_insensitive` asserts that `[[YAML]]` resolves to `a/yaml.md` AND `[[glossary]]` resolves to `a/GLOSSARY.md` — both directions, because folding only the lookup side satisfies the first and fails the second (D06).
- AC-02.5 test: `WikilinkResolve.test_case_folding_matches_obsidian_not_unicode_casefold` asserts `[[straße]]` reaches `Straße.md` while `[[STRASSE]]` does NOT — the fold must match Obsidian's, not Unicode's; `…test_tie_break_compares_bundles_case_insensitively` asserts the same-bundle tie-break folds too, so one file does not resolve from one spelling of its own bundle and go ambiguous from another (D06, D10).

### REQ-03 Same-bundle tie-break

If a wikilink page part matches more than one concept basename and exactly one of those candidates lies in the source file's own bundle, then the resolver shall return that candidate.

- AC-03.1 test: `WikilinkResolve.test_same_bundle_wins` places `g.md` in bundles `a` and `b` and asserts that `[[g]]` in `a/x.md` resolves to `/a/g.md`.
- AC-03.2 command: `python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue wikilinks lean-stack-okf --json` shows the `[[GLOSSARY]]` occurrence in `improve-bean-canon-design.md` with status `resolved` and candidate `/lean-stack-okf/GLOSSARY.md`.

### REQ-04 Ambiguity

If a wikilink page part matches more than one concept basename and the same-bundle tie-break does not yield exactly one candidate, then the resolver shall classify the link as `ambiguous` and carry every candidate path in the record.

- AC-04.1 test: `WikilinkResolve.test_ambiguous_across_foreign_bundles` places `g.md` in bundles `a` and `b`, links `[[g]]` from `c/x.md`, and asserts status `ambiguous` with both candidates listed in sorted order.
- AC-04.2 test: `WikilinkResolve.test_ambiguous_within_one_bundle` places `g.md` twice inside bundle `a` and asserts status `ambiguous` for a link from `a/x.md` — the tie-break is bundle-level, not directory-level.

### REQ-05 Unresolved

If a wikilink page part matches no concept basename in the catalogue, then the resolver shall classify the link as `unresolved`.

- AC-05.1 test: `WikilinkResolve.test_missing_target` asserts status `unresolved` and an empty candidate list for `[[ghost]]`.
- AC-05.2 test: `WikilinkResolve.test_path_form_target_uses_last_segment` asserts that `[[800 Bank/Claude Code Skills]]` is looked up under `Claude Code Skills` and reported `unresolved` when no such concept exists.
- AC-05.3 test: `WikilinkResolve.test_non_concept_target_is_unresolved` asserts that `[[8.3.3]]` and `[[diagram.png]]` are reported `unresolved` rather than skipped, when no concept of that name exists (D05).
- AC-05.4 test: `WikilinkResolve.test_path_form_target_is_honoured_when_it_matches` asserts that `[[a/old]]` resolves to `/a/old.md` and not to `/z/deep/old.md`, and `…test_path_form_that_matches_nothing_is_unresolved` asserts a path prefix matching nothing — including `[[_plan/old]]` against an unindexed staging draft — is `unresolved` rather than falling back to the bare basename (D07).
- AC-05.5 test: `WikilinkResolve.test_reserved_file_is_not_a_resolution_target` and `…test_staging_concept_is_not_a_resolution_target` assert that `index.md` and a concept inside a `_`-prefixed staging directory are never candidates — the set of resolution targets is the set of files the reporting surfaces scan. `…test_reserved_file_participates_as_a_source` asserts the converse for D04: a reserved file's own links ARE reported. `…test_candidate_order_is_deterministic` asserts candidates come back sorted, which AC-04.1 rests on.
- AC-05.6 test: `WikilinkResolve.test_path_form_tail_is_compared_case_insensitively` asserts the path narrowing folds BOTH sides — the link's spelling and the candidate's on-disk spelling (D06, D07).

### REQ-06 Reporting command

When invoked as `okf-cli wikilinks [target]`, the CLI shall print one line per wikilink occurrence carrying the source path relative to the catalogue root, the region, the raw target and the status.

- AC-06.1 command: `python3 cli/okf-cli.py --root <fixture> wikilinks` exits 0 and prints one line per occurrence, each matching `^(resolved|ambiguous|unresolved)\s+(body|frontmatter)\s+\S+\s+\[\[.*\]\]`.
- AC-06.2 command: the final output line matches `wikilinks: <n> link(s), <r> resolved, <a> ambiguous, <u> unresolved`.
- AC-06.3 test: `WikilinkCommand.test_exit_code_is_zero_with_findings` asserts exit code 0 on a fixture containing unresolved links — the report is not a gate.
- AC-06.4 test: `WikilinkCommand.test_embed_is_visible_in_the_report` asserts an embed prints an `(embed)` marker; `raw` starts at `[[` so the report would otherwise not distinguish `![[a]]` from `[[a]]`.

### REQ-07 Unresolved filter

Where `--unresolved` is given, `okf-cli wikilinks` shall restrict its per-occurrence output to links with status `unresolved` or `ambiguous`.

- AC-07.1 command: `python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue wikilinks lean-stack-okf --unresolved` prints no occurrence lines and a summary reporting 0 unresolved.
- AC-07.2 test: `WikilinkCommand.test_unresolved_filter_keeps_summary_totals` asserts that the summary line reports the unfiltered totals while the occurrence list is filtered.

### REQ-08 Machine-readable output

Where `--json` is given, `okf-cli wikilinks` shall emit a single JSON object carrying a `links` array of per-occurrence records and a `by_bundle` object of per-bundle status counts.

- AC-08.1 command: `python3 cli/okf-cli.py --root <fixture> wikilinks --json | python3 -m json.tool` exits 0.
- AC-08.2 test: `WikilinkCommand.test_json_shape` asserts each `links` entry carries the keys `source`, `region`, `raw`, `page`, `alias`, `suffix`, `embed`, `status`, `candidates`, and that the `by_bundle` counts sum to `len(links)`.
- AC-08.3 test: `WikilinkCommand.test_by_bundle_never_contradicts_the_link_list` asserts the sum still equals `len(links)` under `--unresolved`, that `totals` stays unfiltered and that a `filtered` flag says which of the two the caller is reading.

### REQ-09 Scope argument

When a `target` argument naming a bundle or a `<bundle>/<subdir>` is given, `okf-cli wikilinks` shall scan only the files that `resolve_scopes` yields for that target.

- AC-09.1 command: `python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue wikilinks qm-wiki` reports 1058 links, every one frontmatter, of which 1026 unresolved and 32 resolved — `qm-wiki` is a native bundle covered by the catalogue pin. The 32 are case-only spelling differences that a case-sensitive resolver called dead (D06); the pre-implementation snapshot of this AC read "every one unresolved" and recorded the defect, not the requirement. The same command with no target reports strictly more links than the `qm-wiki` run and includes occurrences from at least two other bundles.
- AC-09.2b test: `WikilinkCommand.test_target_must_name_a_bundle` asserts exit 1 for `wikilinks ..` and `wikilinks _plan` — a target must name a bundle, or the scan walks out of the catalogue and into staging the reporting surface excludes.
- AC-09.2 command: `python3 cli/okf-cli.py --root <fixture> wikilinks nosuchbundle` exits 1 with a message on stderr naming the missing target.

### REQ-10 Rename rewrites inbound wikilinks

When a concept whose basename changes is moved under `--apply`, `okf-cli rename` shall rewrite every inbound wikilink that resolves to that concept in both regions, preserving the alias, the heading-or-block suffix and the embed marker verbatim.

- AC-10.1 test: `RenameWikilinks.test_inbound_plain_is_rewritten` renames `a/old.md` to `a/new.md` and asserts a source file containing `[[old]]` reads `[[new]]` afterwards.
- AC-10.2 test: `RenameWikilinks.test_alias_and_suffix_survive` asserts `[[old|Label]]`, `[[old#Heading]]`, `[[old#^blk]]` and `![[old]]` become `[[new|Label]]`, `[[new#Heading]]`, `[[new#^blk]]` and `![[new]]`.
- AC-10.3 test: `RenameWikilinks.test_frontmatter_property_is_rewritten_and_stays_parseable` asserts a source whose frontmatter carries `related:` with a block-list item `- "[[old]]"` reads `- "[[new]]"` afterwards, and that the rewritten frontmatter still parses through `split_frontmatter` with the same key set (D01).
- AC-10.4 test: `RenameWikilinks.test_directory_only_move_rewrites_nothing` moves `a/x.md` to `a/sub/x.md` and asserts every inbound wikilink is byte-identical afterwards (C03).
- AC-10.5 test: `RenameWikilinks.test_code_spans_are_not_rewritten` asserts a `[[old]]` inside a fenced block and inside inline backticks is byte-identical afterwards, and `…test_applier_masking_is_exercised_on_a_mixed_file` asserts the same for a file that ALSO carries a real link, so the rewrite path actually runs (the planner alone protects the first case).
- AC-10.6 test: `RenameWikilinks.test_inbound_wikilink_in_staging_dir_is_rewritten` asserts both `a/_intake/` and root-level `_inbox/` are rewritten (C02, C07); `…test_rename_reaches_every_file_its_markdown_half_reaches` asserts `a/assets/` and a root-level file get BOTH their markdown link and their wikilink updated; `…test_symlinked_bundle_inbound_is_rewritten` asserts a mounted bundle is reached (ASM-05); `…test_path_form_inbound_keeps_its_prefix` asserts `[[a/old]]` becomes `[[a/new]]`; `…test_self_reference_is_rewritten_at_the_new_location` asserts a self-link in the moved file is rewritten at its new path.
- AC-10.7 test: `RenameWikilinks.test_case_variant_inbound_is_rewritten` asserts `[[OLD]]` and `[[old]]` are both rewritten and both land on the file's actual spelling (D06); `…test_nested_masked_spans_survive_byte_identical` asserts five nested dead-zone shapes are byte-identical after an applied rename; `…test_pre_existing_nul_is_preserved` asserts a file already containing NUL is not corrupted (D08).
- AC-10.8 test: `RenameWikilinks.test_cross_bundle_move_repoints_a_path_form_link` asserts `[[a/old]]` becomes `[[b/new]]` when the concept moves bundles, not the non-existent `[[a/new]]`; `…test_directory_move_repoints_a_path_form_link` asserts a pure directory move rewrites the path form and leaves the plain form alone (C08); `…test_md_suffix_is_preserved_by_the_rewrite` pins the explicit `.md`.
- AC-10.9 test: `RenameWikilinks.test_case_only_rename_still_rewrites`, `…test_uppercase_source_basename_is_matched` and `…test_differently_cased_source_path_still_matches` assert the three places a casing difference used to drop the whole wikilink pass silently (D06, D10).
- AC-10.10 test: `RenameWikilinks.test_crlf_line_endings_survive` and `…test_undecodable_file_is_skipped_not_mangled` assert the rewrite is byte-faithful outside the link it changes (D13); `…test_markdown_pass_does_not_rewrite_inside_a_fence`, `…test_symlinked_bundle_markdown_link_is_rewritten_too`, `…test_differently_cased_markdown_link_is_rewritten_too` and `…test_outbound_pass_masks_like_the_applier` assert both halves of one rename share one traversal, one mask and one notion of path identity (C07, D14).

### REQ-11 Rename dry-run discloses wikilinks

While `--apply` is absent, `okf-cli rename` shall list each inbound wikilink rewrite it would perform, one line per occurrence with its region, alongside the existing inbound and outbound markdown-link lines.

- AC-11.1 test: `RenameWikilinks.test_dry_run_lists_and_writes_nothing` asserts the dry-run output contains a `wikilink` line for each affected occurrence and that every file on disk is byte-identical afterwards.
- AC-11.2 test: `RenameWikilinks.test_summary_counts_wikilinks_separately` asserts the closing summary reports the wikilink count as its own figure, not folded into the inbound markdown-link count.

### REQ-12 Rename discloses what it will not rewrite

If an inbound wikilink whose page part matches the renamed concept's basename is classified `ambiguous`, then `okf-cli rename` shall list it as `skipped-ambiguous` with its candidate paths in both dry-run and `--apply` output.

- AC-12.1 test: `RenameWikilinks.test_ambiguous_inbound_is_reported_not_rewritten` builds two concepts sharing a basename across bundles, renames one, and asserts the foreign-bundle `[[…]]` occurrence is listed as `skipped-ambiguous` and is byte-identical on disk afterwards.
- AC-12.2 test: `RenameWikilinks.test_renaming_into_an_occupied_basename_is_refused` asserts exit 2 and an untouched tree when the destination basename is already held by another concept and inbound wikilinks would be rewritten to it; `…test_occupied_basename_is_disclosed_in_the_dry_run` asserts the dry-run names the colliding path; `…test_occupied_basename_proceeds_under_force` asserts `--force` performs the move and still discloses; `…test_collision_counts_links_already_pointing_at_the_other_concept` asserts the refusal also fires when the only affected links are pre-existing ones the rename never rewrites (D09).
- AC-12.4 test: `RenameWikilinks.test_case_variant_ambiguity_is_disclosed` asserts `[[G]]` against `a/g.md` and `b/g.md` is listed as `skipped-ambiguous` — the case-sensitive planner filter dropped it silently (D06).
- AC-12.5 test: `RenameWikilinks.test_collision_sees_a_staging_file_the_index_skips` and `…test_collision_lookup_is_case_insensitive` assert the collision search covers the rename's own reach and folds case; `…test_collision_the_tie_break_absorbs_is_not_refused` asserts a bystander the tie-break keeps unique does not block the move (D09).
- AC-12.6 test: `RenameWikilinks.test_reserved_destination_is_refused`, `…test_empty_destination_basename_is_refused`, `…test_whitespace_destination_basename_is_refused` and `…test_control_character_destination_basename_is_refused` assert every unresolvable destination is rejected before anything is written (D12).
- AC-12.7 test: `RenameWikilinks.test_basename_preserving_move_that_turns_a_link_ambiguous_is_refused` asserts a move that rewrites nothing but changes a link's meaning is refused and disclosed — the before/after resolution, not the token, decides (D15).
- AC-12.8 test: `RenameWikilinks.test_force_overwrite_discloses_what_it_clobbers` asserts a `--force` overwrite names the destination it destroyed and how many references now address different content (D09).
- AC-12.3 test: `RenameWikilinks.test_foreign_same_named_concept_is_not_rewritten` asserts a `[[old]]` that resolves to a DIFFERENT concept of the same basename via the bundle tie-break is left byte-identical — the guard that keeps a rename inside its own target's inbound set.

### REQ-13 Conformance check

While a bundle is listed in `wikilink_checked_bundles`, `okf-cli check` shall emit one `wikilink-resolvable` warning per markdown file in that bundle that contains at least one `unresolved` or `ambiguous` wikilink, naming every such target in the message.

- AC-13.1 test: `WikilinkCheck.test_warns_for_opted_in_bundle` asserts a fixture with `wikilink_checked_bundles = ["a"]` produces a warning tuple whose check name is `wikilink-resolvable` and whose path is the offending file.
- AC-13.2 test: `WikilinkCheck.test_one_warning_per_file_lists_every_target` asserts a file with three unresolved wikilinks yields exactly one warning whose message contains all three targets.
- AC-13.3 test: `WikilinkCheck.test_frontmatter_only_file_is_flagged` asserts a file whose sole unresolved wikilink sits in a frontmatter property produces the warning (D01).
- AC-13.4 test: `WikilinkCheck.test_reserved_file_participates` places an unresolved wikilink in `a/index.md` and asserts a `wikilink-resolvable` warning naming that path (D04).
- AC-13.5 test: `WikilinkCheck.test_symlinked_bundle_participates` opts in a bundle whose directory is a symlink and asserts the warning is emitted (D03).
- AC-13.6 command: `python3 cli/okf-cli.py --root <fixture> check --strict` exits 1 when the opted-in bundle carries an unresolved wikilink.
- AC-13.7 demo: on a scratch clone of the catalogue, write `wikilink_checked_bundles = ["lean-stack-okf", "bew_BeWiki-Python-Download-okf"]` to `.okf.toml`, run `check --json`, and observe zero `wikilink-resolvable` entries for `lean-stack-okf` and a non-zero count for `bew_BeWiki-Python-Download-okf`, each naming `[[bew_BeWiki-Python-Download]]`; the clone is discarded afterwards, leaving the live catalogue untouched (D02).

### REQ-14 Opt-in gate

While a bundle is absent from the `wikilink_checked_bundles` array in `<root>/.okf.toml`, `okf-cli check` shall emit no `wikilink-resolvable` finding for that bundle.

- AC-14.1 test: `WikilinkCheck.test_absent_config_is_silent` asserts that a fixture with no `.okf.toml` produces zero `wikilink-resolvable` findings despite unresolved wikilinks being present — the state the live catalogue is in today (C05).
- AC-14.2 test: `WikilinkCheck.test_partial_optin_is_scoped` asserts that a fixture opting in bundle `a` produces findings for `a` and none for bundle `b`, which carries unresolved wikilinks of its own.
- AC-14.3 test: `WikilinkCheck.test_dotted_target_does_not_defeat_the_gate` asserts `check ./a` still fires and `…test_case_variant_bundle_name_does_not_defeat_the_gate` asserts `check A` does — an unnormalised or differently-cased target yielded a bundle name no rule matched, and silently switched this one check off while every other check kept firing (D10). `ResolveScopesTargets` pins the shared normalisation for every other `resolve_scopes` caller, including that an absolute target still addresses its own directory and that `.` means the whole catalogue.
- AC-14.6 test: `WikilinkCheck.test_ambiguous_wikilink_also_warns` asserts an ambiguous occurrence warns, not only an unresolved one — REQ-13 names both and only the first half was asserted.
- AC-14.7 test: `WikilinkCheck.test_staging_subdir_target_is_not_checked` asserts `check <bundle>/_plan` and `check <bundle>/assets` produce no finding — `iter_all_md` prunes those names from `dirnames`, never from the directory it is handed; `…test_unknown_bundle_note_respects_case` asserts the diagnostic agrees with the gate it describes; `…test_missing_target_directory_is_not_a_clean_run` asserts a typo'd target exits 1 instead of reporting a clean scan of nothing.
- AC-14.4 test: `WikilinkCheck.test_non_array_config_is_announced_not_swallowed` and `…test_unknown_bundle_in_config_is_announced` assert a stderr note for a config value the gate cannot honour, and `…test_malformed_config_fails_with_a_message_not_a_traceback` asserts a malformed `.okf.toml` exits 1 naming the file rather than raising.
- AC-14.5 test: `WikilinkCheck.test_severity_is_warning_not_error` asserts the finding lands in `warnings`, not `errors`, and that a plain `check` still exits 0; `…test_index_is_not_built_without_an_opt_in` asserts the catalogue-wide index is built zero times with no opt-in, once with one, and zero times when the scope excludes the opted-in bundle.

### REQ-15 MCP reachability

The okf-MCP server shall expose `wikilinks` as a tool accepting a root, an optional target and an unresolved flag, returning the command's JSON object.

- AC-15.1 test: `test_okf_mcp.py` asserts `_COMMANDS["wikilinks"]` equals `(["target"], True)`.
- AC-15.2 test: `test_okf_mcp.py` asserts `build_argv` emits `--unresolved` when the flag is set and omits it when unset, which requires the flag to be registered in `_BOOL_FLAGS`.
- AC-15.3 test: an MCP-level test asserts `okf_wikilinks(root=<fixture>)` returns a dict carrying the `links` and `by_bundle` keys of REQ-08.

### NFR-01 Scan runtime

The okf-cli wikilink scanner shall complete a full-catalogue scan within 5 seconds on the reference machine, at the catalogue's snapshot size of roughly 2700 markdown files.

- AC-NFR-01.1 command: `time python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue wikilinks --json > /dev/null` reports a real time below 5 s.

### NFR-02 Dependency surface

The okf-cli wikilink implementation shall import only CPython 3.11+ standard-library modules.

- AC-NFR-02.1 inspection: the diff of `cli/okf-cli.py` and `mcp/okf_mcp.py` introduces no import outside the standard library.
- AC-NFR-02.2 command: `python3 -m unittest test_okf_cli` from `cli/` exits 0 in an environment with no third-party packages installed.

## Interfaces and Contracts

Wikilink record — the value type every surface consumes:

```
{
  "source":     "bundle/sub/concept.md",   # rel to catalogue root
  "region":     "body" | "frontmatter",
  "raw":        "[[page|alias#suffix]]",   # verbatim occurrence including brackets
  "page":       "page",                    # page part, trailing .md stripped
  "alias":      "alias" | null,
  "suffix":     "suffix" | null,           # heading, or "^blk" for a block ref
  "embed":      true | false,
  "status":     "resolved" | "ambiguous" | "unresolved",
  "candidates": ["/bundle/sub/page.md"],   # 1 resolved, >1 ambiguous, [] unresolved
  "span":       [start, end]               # offsets of raw in the ORIGINAL text
}
```

CLI surface, registered via `_sub` in group `maintenance`:

```
okf-cli.py wikilinks [target] [--unresolved] [--json]
```

Exit codes: `0` on a completed scan regardless of findings, `1` when `target` names no existing directory, `2` left to argparse for usage errors.

Configuration key read from `<root>/.okf.toml`; absent file or absent key means the empty list:

```toml
wikilink_checked_bundles = ["lean-stack-okf", "bew_BeWiki-Python-Download-okf"]
```

## Assumptions

- ASM-01 Obsidian resolves a plain `[[name]]` by unique basename across the vault and prefers a candidate in the linking note's own subtree on collision — the case-insensitivity half is now established rather than assumed: the store's filesystem resolves `types.MD` to `TYPES.md`, so a basename simply is case-insensitive here (D06). The subtree-preference half stays at medium confidence — falsified if: opening `lean-stack-okf/improve-bean-canon-design.md` in Obsidian resolves `[[GLOSSARY]]` to a `GLOSSARY.md` outside `lean-stack-okf`.
- ASM-02 🔴 falsified for 96 of the population, retained for the remaining 1848. The claim was that the unresolved frontmatter wikilinks point at Vault notes that were never migrated, not at concepts that exist under a trivially different spelling; its own falsifier named "case" first. Building the index case-insensitively resolved 96 of them against existing concepts — 59 in `general-knowledge-wiki`, 32 in `qm-wiki`, 4 in `ai-wiki`, 1 in `devd2-okf`. For the 1848 that remain the assumption stands at medium confidence, with hyphenation and umlaut transcription untested.
- ASM-03 No conformant concept filename contains a wikilink metacharacter, so `[[…]]` parsing needs no escaping rules — confidence: high, anchored on `FILENAME_FORBIDDEN_CHARS` — falsified if: `okf-cli check` reports a `filename-chars` violation involving `[`, `]`, `|`, `#` or `^`.
- ASM-04 Every frontmatter wikilink sits inside a scalar or list value, so a token-level replacement of `[[old]]` by `[[new]]` cannot break the YAML — confidence: medium — falsified if: a frontmatter occurrence is found in an unquoted value whose new text would introduce a YAML control character, or `split_frontmatter` fails on any file after a `rename --apply`.
- ASM-05 The 157 wikilinks in symlinked bundles benefit from the same reporting and rewriting as native ones — confidence: medium — falsified if: a symlinked bundle's owning repository rewrites wikilinks on its own schedule and a `rename` here produces a conflicting edit.

## Open Questions

- Q01 🟡 non-blocking — Should `refs` list inbound wikilinks alongside markdown links? Doing so changes an established output shape and pulls `build_ref_matrix`'s `_`-directory traversal into a reporting surface — needed for: nothing in this SPEC; `rename` gets its wikilink scan without touching `refs`.
- Q02 🟡 non-blocking — Is the same-bundle tie-break of REQ-03 identical to Obsidian's own rule? No ambiguous occurrence exists in the catalogue once the tie-break applies, so a divergence is currently unobservable — needed for: REQ-03, carried by ASM-01.
- Q03 🟢 resolved — Which bundles go into `wikilink_checked_bundles` at introduction? See D02.
- Q04 🟢 resolved — Do wikilinks inside reserved files participate? See D04.
- Q05 🟢 resolved — Are frontmatter wikilinks in scope? See D01.
- Q06 🟢 resolved — What happens to a wikilink whose target is not a markdown concept? Nothing special: it is looked up like any other page part and reports `unresolved`. See D05 and AC-05.3.

## Traceability

| Requirement | Criteria | Verified by |
| --- | --- | --- |
| REQ-01 | AC-01.1, AC-01.2, AC-01.3, AC-01.4, AC-01.5, AC-01.6, AC-01.7, AC-01.8, AC-01.9, AC-01.10, AC-01.11, AC-01.12, AC-01.13 | `cli/test_okf_cli.py` (`WikilinkExtraction`) |
| REQ-02 | AC-02.1, AC-02.2, AC-02.3, AC-02.4, AC-02.5 | `cli/test_okf_cli.py` (`WikilinkResolve`), live catalogue command |
| REQ-03 | AC-03.1, AC-03.2 | `cli/test_okf_cli.py` (`WikilinkResolve`), live catalogue command |
| REQ-04 | AC-04.1, AC-04.2 | `cli/test_okf_cli.py` (`WikilinkResolve`) |
| REQ-05 | AC-05.1, AC-05.2, AC-05.3, AC-05.4, AC-05.5, AC-05.6 | `cli/test_okf_cli.py` (`WikilinkResolve`) |
| REQ-06 | AC-06.1, AC-06.2, AC-06.3, AC-06.4 | `cli/test_okf_cli.py` (`WikilinkCommand`), fixture command |
| REQ-07 | AC-07.1, AC-07.2 | `cli/test_okf_cli.py` (`WikilinkCommand`), live catalogue command |
| REQ-08 | AC-08.1, AC-08.2, AC-08.3 | `cli/test_okf_cli.py` (`WikilinkCommand`), fixture command |
| REQ-09 | AC-09.1, AC-09.2, AC-09.2b | live catalogue command, fixture command, `cli/test_okf_cli.py` (`WikilinkCommand`) |
| REQ-10 | AC-10.1, AC-10.2, AC-10.3, AC-10.4, AC-10.5, AC-10.6, AC-10.7, AC-10.8, AC-10.9, AC-10.10 | `cli/test_okf_cli.py` (`RenameWikilinks`) |
| REQ-11 | AC-11.1, AC-11.2 | `cli/test_okf_cli.py` (`RenameWikilinks`) |
| REQ-12 | AC-12.1, AC-12.2, AC-12.3, AC-12.4, AC-12.5, AC-12.6, AC-12.7, AC-12.8 | `cli/test_okf_cli.py` (`RenameWikilinks`) |
| REQ-13 | AC-13.1, AC-13.2, AC-13.3, AC-13.4, AC-13.5, AC-13.6, AC-13.7 | `cli/test_okf_cli.py` (`WikilinkCheck`), fixture command, scratch-clone demo |
| REQ-14 | AC-14.1, AC-14.2, AC-14.3, AC-14.4, AC-14.5, AC-14.6, AC-14.7 | `cli/test_okf_cli.py` (`WikilinkCheck`) |
| REQ-15 | AC-15.1, AC-15.2, AC-15.3 | `cli/test_okf_mcp.py` |
| NFR-01 | AC-NFR-01.1 | live catalogue timing |
| NFR-02 | AC-NFR-02.1, AC-NFR-02.2 | diff inspection, `python3 -m unittest test_okf_cli` |
