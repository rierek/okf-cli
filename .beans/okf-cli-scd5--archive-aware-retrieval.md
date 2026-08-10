---
# okf-cli-scd5
title: archive-aware retrieval
status: todo
type: feature
priority: normal
tags:
    - accepted
created_at: 2026-08-09T19:13:45Z
updated_at: 2026-08-10T08:05:29Z
parent: okf-cli-huow
---

`--include-archive` for `find` and `list` (D21), carried as the fourth dimension of `FindFilters` rather than as a loose argument — the class documents at its own head (cli/okf-cli.py:761) what happened last time a dimension travelled loose through five signatures (I01/B01).

Covers R-08 … R-14 of `docs/okf-archive-lifecycle/SPEC.md`.


## Review 2026-08-10

- US-08 · `find` omits archived concepts by default and returns them under their `_archive/…` path with `--include-archive` · a
- US-09 · `--scope <bundle> --include-archive` reaches the archived concepts of that bundle, and the bundle name is matched literally · a
- US-10 · `list --type X` follows the same rule through the shared scope resolution · a

US-08 was evaluated on a fixture whose FTS index was rebuilt *after* archiving (`indexed 7 concept(s)`), so the two archived concepts were provably in the index and still absent from the default answer. That is what separates a filter decision at query time from a hole in the index.

US-09 was run against two deliberately adversarial bundle names. `--scope mein_bundle --include-archive` returned only `_archive/mein_bundle/unterstrich-konzept`, never `_archive/meinXbundle/wildcard-falle` — the SQL single-character wildcard in the scope name is masked. The counter-run on `--scope meinXbundle` returned only its own concept. Third case: a bundle named `xarchive` survives the default exclusion. These are the A10/A11 cases the two `CHANGES_REQUIRED` rounds on `okf-cli-pn72` were about, now confirmed by the PO on live data rather than in a unit test.

No embedding call was possible in any of these runs: the fixture carries no `.tagvec` cache, and `semantic_ranking` (cli/okf-cli.py:1387) returns before embedding the query when that cache is absent.


- US-11 · after an archive move the lexical index reports itself stale, although the total concept count and the file mtime both stay unchanged · a
- US-12 · with `--include-archive` and a semantically owned ranking, exactly one stderr note declares that the semantic arm does not cover the archive; without the flag it stays silent · a
- US-13 · the MCP layer emits `--include-archive` for `find` and `list` only; the six other commands checked keep their previous argv · a

US-11 was evaluated on the case the split counters exist for: seven concepts before and after, and `git mv` preserving the mtime, so a summed counter would have missed the move on both signals at once.

US-12 was run against the real catalogue, the only store carrying an embedding cache. Two read-only `find` calls with the same paraphrase query, costing two query embeddings. Both printed the pre-existing `semantic arm owns this ranking` note; only the `--include-archive` run added `note: --include-archive covers the lexical arm only; embeddings stay on the active catalogue`. The index rebuild that preceded it touched nothing tracked — `.fts/` and `.tagvec/` are both gitignored (.gitignore:6-7).

US-13 was evaluated on the generated argv for eight commands side by side, with `--apply` visible in every row as the contrast: `_BOOL_FLAGS` is iterated unconditionally, so the new flag needed its own allowlist rather than an entry there. That is the correction the implementer made against the hand-off note, which had recommended the plain `_BOOL_FLAGS` entry.
