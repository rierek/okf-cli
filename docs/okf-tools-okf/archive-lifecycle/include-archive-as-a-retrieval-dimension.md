---
type: Concept
title: include_archive is a field of FindFilters, and the index needs two staleness counters
description: The archive is invisible by default across every retrieval arm; the flag became the fourth field of the FindFilters value object rather than a fifth loose argument, the SQL exclusion needs ESCAPE because _ is a LIKE wildcard, and fts_meta needs separate active/archived counters or the move goes unnoticed.
tags:
  - okf-cli
  - archive
  - hybrid-search
timestamp: 2026-08-10T12:10:00Z
---

# include_archive is a field of FindFilters, and the index needs two staleness counters

The archive is excluded from default retrieval (D05) and reachable via `--include-archive` on `find` and `list`. Three implementation facts carry that promise, and each of them has a failure mode that a green test suite does not show.

## The flag is a field, not a fifth argument

`FindFilters` documents finding I01 at its own head: the same filter dimension had been implemented three times, travelled through five signatures as a loose argument, and was missing entirely from the semantic arm — which is why a scoped query returned concepts from foreign bundles. Threading a fourth dimension alongside would have repeated exactly that. `include_archive` is therefore the fourth field of the value object, defaulting to `False`.

`path_in_scope` carries both rules, because they are the same rule:

- A path starting with `_archive/` is invisible unless `include_archive` is set.
- The scope comparison runs against the path **without** the leading `_archive/` segment. `--scope okf-meta-wiki --include-archive` therefore yields active and archived concepts of that bundle — this is what the preserved bundle name in the archive path is for (D14).

## `ESCAPE` is not optional

`sql_where` mirrors both rules in SQL. Without the flag it adds `AND path NOT LIKE '\_archive/%' ESCAPE '\'`. The escape is load-bearing: `_` is a single-character wildcard in SQL LIKE, so an unescaped predicate would also exclude a bundle named `xarchive`. That is a silent, data-dependent exclusion — nobody notices until such a bundle exists.

## Two staleness counters, and why one is worse than none

`build_fts_index` indexes `_archive/<bundle>/<cid>` under exactly that path. Without it `--include-archive` would be a prop: the default arm is FTS, and no predicate can surface what the index does not contain.

`_fts_index_stale` then needs **two separate counters** in `fts_meta`, active and archived, both compared. This is a failure-path argument, not a stylistic one:

- Index both sets but compare only the active count, and the index is permanently stale from the first archived entry onward — every `find` rebuilds it.
- Count both as one sum, and the sum stays constant across an archiving, while `git mv` preserves the file's mtime. The move becomes invisible, the index keeps the concept under its active path, and `find` shows archived material by default — precisely the state D05 rules out.

With two counters both diverge on a move, and detection stays stat-only.

The guard enforcing "the staleness check reads no concept body" originally monkeypatched the module attribute `read_file`. A raw `open(ap).read()` inside the checked function left it green; `pathlib.Path.read_text` and `codecs.open` would have been equally invisible. Patching one named helper enforces a coding convention, not a property — the patch has to sit at module level (`builtins.open`) so any read path trips it.

## The semantic arm says what it does not cover

Embeddings stay on the active catalogue: they cost API calls for material that never appears by default, and "I know this existed once" (D21) is a lexical search. So that this does not become a silent gap, a `find --include-archive` whose answer contains semantic hits writes exactly one stderr line saying the flag covers the lexical arm only — one note per arm per invocation, following the existing degradation-note rule. Without it the user searches an archive the answering arm never saw, and reads the empty result as an answer.

## MCP surface

`include_archive` goes into `_BOOL_FLAGS` and onto `okf_find` and `okf_list` — and nowhere else. A command that does not know the flag answers with an argparse error; the tool signature is where that is decided.
