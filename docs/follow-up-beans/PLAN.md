---
type: Plan
title: Follow-up beans implementation plan
status: approved-autonomous
beans:
  - OKFT-epil
  - OKFT-uctf
  - OKFT-eyla
  - OKFT-az0k
---

# Follow-up beans implementation plan

## Decisions

- D01 (`OKFT-epil`): Add `--include-topics` to both `find` and `build-index`; it widens the existing corpus rather than creating a second index. Default retrieval remains restricted to the declared `bundle`; topic folders are returned only when the caller explicitly opts in.
- D02 (`OKFT-epil`): The FTS index records whether it was built with topic folders. `find --include-topics` reports a precise stderr degradation when that corpus is absent, rather than silently pretending that a narrow index searched topics. Semantic embeddings retain their existing broad producer corpus, but default `find` filters topic-folder paths out of both ranking arms.
- D03 (`OKFT-eyla`): Content-rewriting maintenance commands repair `_`-staging: tag operations, `fix-crosslinks`, `fix-xml-tags`, and `rewrite-path`. Generated published-corpus material (`reindex`) and retrieval remain pruned. Explicit lifecycle operations (`rename`, `archive`) retain their existing broad scans so references into staging are repaired during an explicit move.
- D04 (`OKFT-az0k`): Preserve the already shipped clean early-close exit status `0`; redirect both stdout and stderr to `/dev/null` after a caught `BrokenPipeError`, then exit silently.

## Task 1 — Add an explicit topic-folder corpus to FTS and hybrid retrieval (`OKFT-epil`)

Files: `cli/okf-cli.py`, `cli/test_okf_cli.py`.

1. Add `list_search_bundles(root, include_topics=False)`: it returns `list_indexable_bundles(root)` by default and `list_bundles(root)` only for explicit topic inclusion. Do not change `list_bundles` or `list_indexable_bundles`; link resolution, integrity checks, and presentation must retain their current wide behavior.
2. Extend `build_fts_index(root, db_path=None, include_topics=False)` and `_fts_index_stale(root, include_topics=False)` to enumerate `list_search_bundles`. Persist `includes_topics` as `"0"` or `"1"` in `fts_meta`, alongside the active/archive counts and newest mtime. `cmd_build_index` forwards `args.include_topics`; `--if-stale` compares the requested corpus flag as well as counts and mtime.
3. Add `include_topics` to `FindFilters`. The lexical SQL and semantic cache SQL receive a corpus predicate composed from the allowed active bundle prefixes when the root declares `bundle` and the flag is false. The substring fallback uses `list_search_bundles` too. This keeps default results canonical even when a previously built FTS database and the semantic cache contain topic records.
4. On `find --include-topics`, inspect FTS metadata before querying. When the FTS database exists but has `includes_topics != "1"`, emit exactly one stderr note telling the caller to run `okf-cli build-index --include-topics`; still return any canonical lexical hits and eligible semantic hits. A missing/corrupt FTS database retains the current generic degradation message and substring fallback, which can search topics directly.
5. Add `--include-topics` to the `build-index` and `find` argparse parsers with help text stating that the default respects `.okf.toml`'s declared `bundle` and the flag widens to topic folders. Do not add the flag to `list`, `check`, `wikilinks`, or semantic-index production.
6. Write focused fixture tests that first demonstrate each failure: default `find` must exclude a uniquely matching topic concept from a broad FTS database and from semantic candidates; `find --include-topics` must return it after a broad FTS build; a narrow FTS build followed by `find --include-topics` must include the rebuild note; `_fts_index_stale(..., include_topics=True)` must reject narrow metadata; and parser/help tests must expose both new flags.

## Task 2 — Make the repo-local wikilink gate meaningful (`OKFT-uctf`)

Files: `docs/.okf.toml`, `docs/okf-tools-okf/archive-lifecycle/index.md`, `docs/okf-tools-okf/archive-lifecycle/active-beats-archived-in-wikilink-resolution.md`, `cli/test_okf_cli.py`.

1. Add `wikilink_checked_bundles = ["okf-tools-okf"]` to `docs/.okf.toml`; no CLI behavior changes belong in this task.
2. Replace the two illustrative unresolved `[[...]]` examples with inline-code literals so the prose retains its exact example text but no longer creates an Obsidian wikilink record. Replace the cross-catalogue wikilink with an explicit catalogue-root-absolute Markdown link if the target is local; otherwise retain it as a code literal and explain that cross-catalogue resolution is out of scope. The resulting declared bundle must have zero unresolved wikilinks.
3. Add `test_wikilink_from_outside_the_declared_bundle_resolves` next to `BundleKeyDoesNotNarrowResolution`: construct a root whose config declares one bundle, create the source in a non-declared topic directory and target inside the declared bundle, and assert `resolve_wikilink_records` reports it resolved. This pins the source-side direction independently of the existing reverse test.
4. Add a configuration fixture asserting that `run_checks` reports a deliberately dead wikilink under the declared bundle and still does not report the same link under a non-declared topic folder.

## Task 3 — Apply the deliberate staging policy consistently (`OKFT-eyla`)

Files: `cli/okf-cli.py`, `cli/test_okf_cli.py`.

1. Change `iter_all_md(bundle_path)` to `iter_all_md(bundle_path, prune_staging=True)`, mirroring `iter_concepts`; its false branch must retain `_` directories while continuing to prune dot-directories and `assets`.
2. Pass `prune_staging=False` from `fix_xml_like_tags` and `fix_crosslinks`. Change `rewrite_path` to use the same explicit content-repair traversal or an equivalent false-pruning walk; it must rewrite matching path text beneath `_intake` as well as published content.
3. Keep `reindex`, retrieval, `check`, `wikilinks`, and default `iter_all_md` calls unchanged, so generated indexes and integrity reports still ignore staging. Keep `iter_rename_scan_md`, `archive`, and `rename` unchanged because their traversal is a targeted lifecycle operation with existing staging-reference tests.
4. Add one fixture per content-repair command with a published file and `_intake/staged.md`: `merge-tags`, `remove-tags`, and `normalize-tags` continue to mutate both; `fix-crosslinks`, `fix-xml-tags`, and `rewrite-path` newly mutate both. Add paired assertions that `reindex` output and `check` output do not list `_intake/staged.md`.

## Task 4 — Handle closed stderr pipes centrally (`OKFT-az0k`)

Files: `cli/okf-cli.py`, `cli/test_okf_cli.py`.

1. Extract the current post-catch redirection into a small `_silence_broken_pipe_streams()` helper that opens `/dev/null` once and `os.dup2`s it onto both `sys.stdout.fileno()` and `sys.stderr.fileno()`. Call it from the existing top-level `except BrokenPipeError`, then `sys.exit(0)`. Keep the handler at the single CLI entrypoint; MCP subprocess capture is not a pipe consumer and must not be changed.
2. Extend the existing real-subprocess BrokenPipe test helper to generate enough stderr lines to exceed the pipe buffer, invoke a command whose output is merged through `2>&1 | head -n 1`, and assert return code `0`, no traceback, and no `Exception ignored` shutdown noise. Preserve the stdout-only and tiny-answer tests as regression coverage for both existing paths.

## Verification

1. Run the focused `unittest` classes for corpus scoping, wikilink resolution/checks, staging mutations, and BrokenPipe handling after each red-green cycle.
2. Run `just test`; record the three pre-existing live-catalogue failures separately and require no new failure.
3. Run `just check root=docs` and verify the declared `okf-tools-okf` wikilink guard is active with no unresolved wikilinks.
4. Run concrete smoke commands against a temporary root: narrow `build-index` then `find --include-topics` emits its rebuild note; broad `build-index --include-topics` then `find --include-topics` returns a topic-only hit; default `find` does not.
