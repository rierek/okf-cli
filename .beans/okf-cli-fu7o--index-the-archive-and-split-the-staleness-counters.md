---
# okf-cli-fu7o
title: index the archive and split the staleness counters
status: in-progress
type: task
priority: normal
created_at: 2026-08-09T19:15:04Z
updated_at: 2026-08-09T22:07:21Z
parent: okf-cli-scd5
blocked_by:
    - okf-cli-pn72
---

Without the archive in the FTS index the flag is a decoration: FTS is the default arm, and no predicate can surface what the index never saw. The counter split is not style. If the index counts both sets and `_fts_index_stale` (cli/okf-cli.py:717) counts only the active one, the index is permanently stale. If both are counted as one sum, that sum stays constant across an archive move and `git mv` preserves the file mtime, so the move goes unnoticed, the index keeps serving the concept under its active path, and `find` shows archived material by default.

### Requirement 1: An index that knows the archive

**Objective:** As a searcher, I want the archive present in the lexical index and its movements detected, so that `--include-archive` returns real results and the default view never leaks archived material.

#### Acceptance Criteria

1. WHEN building the FTS index THE okf-cli SHALL index every concept under `_archive/<bundle>/` at that path.
2. THE okf-cli SHALL record separate counts of active and archived concepts in `fts_meta`.
3. THE okf-cli SHALL compare both counts in the staleness decision.
4. THE okf-cli SHALL keep the staleness check free of concept-body reads, using file metadata only.

#### Success Criteria

- SC-01: After archiving one concept, the staleness check reports the index as stale.
- SC-02: Immediately after a build, the staleness check reports the index as current, with archived concepts present.

_Requirements: R-11_

## Recommended Skills

- `superpowers:test-driven-development`


## 2026-08-09 — Prelude: incoming `cmd_index` guard from a parallel branch

A parallel session added a bundle-existence guard to `cmd_index` and `cmd_visualize` on branch `fix/b01-b02-bundle-validation` (commit `b5a9f1d`, based on `3310656`). It is **not on `main` yet** — it rebases onto this chain afterwards, so you implement against `main` without it. Know it anyway, because it lands on top of your work:

- The guard is a helper `require_bundle_dir(root, bundle)` placed directly below `is_bundle_dir` in `cli/okf-cli.py`. It checks `os.path.isdir` only, deliberately **not** `is_bundle_dir()` — the latter rejects `_`-prefixed names and would have broken `index _archive`. A `_archive/` directory that exists on disk passes the guard.
- That property is pinned by their test `test_the_gate_is_existence_not_bundle_eligibility`, verified by mutation. Anyone tightening the guard later gets a red test rather than silently breaking this leaf.

What this means for you: if your indexing path needs to accept a path that does **not** exist as a directory (for instance indexing an archive before any concept has been archived into it), the parallel assumption is wrong and their helper needs an exception. Record that in `## Notes` and report it — the supervisor relays it to the other session. If your path only ever indexes an archive directory that exists, nothing to do.



## 2026-08-09 — incoming guard from the parallel Rust-rewrite session (final)

That session has closed. Its branch `fix/b01-b02-bundle-validation` @ `b5a9f1d` (base `3310656`, suite 559 green) is the only one of theirs that touches `cli/` and will need a rebase onto whatever `main` looks like after this chain. It is not merged yet — the merge gate is mutual and the PO decides.

What it adds, verbatim from their handover:

- Helper `require_bundle_dir(root, bundle)`, placed under `is_bundle_dir`.
- Called in `cmd_index` and `cmd_visualize`.
- It checks `os.path.isdir` and deliberately **not** `is_bundle_dir()` — precisely so that `_archive/` paths pass through it.
- Test class `BundleArgumentIsValidated`.

Consequence for this task: the guard is archive-compatible by design, so indexing `_archive/<bundle>/**` does not have to fight it. But this task and that branch both edit `cmd_index`, in the same file, from different bases. Whoever rebases second resolves the conflict. Keep the edit here as small and as local as it can be, and do not restructure `cmd_index` beyond what R-11 requires — a large refactor here turns their rebase into a rewrite.

They also report that `cmd_archive` (cli/okf-cli.py:4163) already implements `--apply` exactly the way their cross-cutting rules COM-29/COM-30 require, and cite it as precedent in their `log.md`.
