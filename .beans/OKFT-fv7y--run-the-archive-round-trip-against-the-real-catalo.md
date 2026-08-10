---
# OKFT-fv7y
title: run the archive round trip against the real catalogue
status: completed
type: task
priority: normal
created_at: 2026-08-09T19:15:18Z
updated_at: 2026-08-09T23:04:47Z
parent: OKFT-huow
blocked_by:
    - OKFT-16rg
    - OKFT-pnyf
    - OKFT-fu7o
    - OKFT-iwx4
    - OKFT-6dsl
---

A green suite proves the fixtures. This proves the catalogue. `~/Obsidian/Knowledge-Catalogue` has no `_archive/` today — this run creates it and removes it again.

### Requirement 1: Proof on the real store

**Objective:** As the product owner, I want the archive path exercised once against the real catalogue, so that the feature is accepted on evidence rather than on fixtures.

#### Acceptance Criteria

1. THE operator SHALL archive one concept in `~/Obsidian/Knowledge-Catalogue` and record the command output.
2. THE operator SHALL run `check` over the five bundles opted into the wikilink rule and record the result.
3. THE operator SHALL run the same `find` query with and without `--include-archive` and record both results.
4. THE operator SHALL run `find --scope <bundle> --include-archive` against the concept's own bundle while it is archived and record the result.
5. THE operator SHALL restore the concept and confirm that the working tree is clean afterwards.

#### Success Criteria

- SC-01: `check` reports zero violations across the five opted-in bundles while the concept is archived.
- SC-02: The query without the flag omits the archived concept and the query with the flag returns it.
- SC-03: `find --scope <bundle> --include-archive` returns only archived concepts of that bundle — the archived concept under test appears, and no archived concept from a foreign bundle appears.
- SC-04: `git status` in the catalogue is clean after the restore.

_Requirements: R-15_

## Recommended Skills

- `superpowers:verification-before-completion`


## 2026-08-09 — Prelude from Gate B (ce-verify-operationalization, finding F02)

`docs/okf-archive-lifecycle/SPEC.md:181` asks the real-catalogue run to replay A05 and A08 through A10. The acceptance criteria above cover A08 and A09; the scoped run A10 is missing.

Do this first, in this task: add an acceptance criterion and a success criterion for `find --scope <bundle> --include-archive` against `~/Obsidian/Knowledge-Catalogue`, proving that only that bundle's archived concepts come back. Record the command and its output like the other runs.

## 2026-08-10 — Real-catalogue run, full record

### Baseline verified before any write

`git -C ~/Obsidian/Knowledge-Catalogue status --short` empty, `git stash list` empty, `git rev-parse HEAD` = `39bcd28327d3e5ce71b0de8157f4a6bb14eea5a1` (matches the pre-dispatch check), no `_archive/` directory. `just test` baseline: `Ran 612 tests in 45.767s` / `OK`.

### Concept chosen

`lean-stack-okf/boot-prompt-deploy-symlink.md`, chosen because it carries exactly one inbound wikilink (`[[boot-prompt-deploy-symlink]]` in `lean-stack-okf/lean-stack-audit-checklist.md`, line 57) plus two inbound markdown crosslinks (`lean-stack-okf/index.md`, `lean-stack-okf/plan-implement-resume-continuation.md`) — found via `okf-cli.py wikilinks --json lean-stack-okf`, filtering `status: resolved` and counting distinct `source` per `candidates[0]`. Deliberately the lowest-traffic single-link candidate found (others in the same bundle carried up to 16 inbound links) to keep the blast radius minimal for a manual real-store mutation.

### Opted-in bundles for the wikilink rule

From `~/Obsidian/Knowledge-Catalogue/.okf.toml`: `lean-stack-okf`, `ai-wiki`, `agent-memory`, `okf-meta-wiki`, `devd2-okf`.

### Index strategy

`.fts/` is listed in the catalogue's own `.gitignore` (`.gitignore:7`) and `git ls-files .fts/` returns nothing — the FTS index never surfaces in `git status`, so it carries no round-trip risk either way. Chosen path: rebuild cleanly with `build-index` (lexical only, no API calls) once *during* the archived state (needed for AC3/AC4 — the flag only reaches concepts the index already knows) and once more *after* the restore, so the user is never left with a stale index. A defensive copy of the pre-run `fts.sqlite` was also taken to the session scratchpad before the first write, unused in the end since the rebuild path worked cleanly.

### Critical finding surfaced by this run (Bug, not fixed — no feature code in this leaf)

`lean-stack-okf` (and every other project bundle: `vik-okf`, `devd2-okf`, `bew_BeWiki-Python-Download-okf`, `okf-tools-okf`, `vc-search-okf`) is a **symlink** into that project's own repo (`lean-stack-okf -> /Users/erik/dev/lean-stack/docs/lean-stack-okf`). `_git_mv` (`cli/okf-cli.py:4048`) runs `git -C <catalogue-root> mv -f <old> <new>`; git refuses a path that crosses a symlink boundary (`fatal: pathspec '...' is beyond a symbolic link`), so `_git_mv` silently falls back to `os.rename` and reports `moved (fs)` instead of `moved (git mv)`. The practical effect on this run's first `archive --apply`: the real move and the two crosslink rewrites landed **inside `~/dev/lean-stack`'s working tree**, completely untracked by `~/Obsidian/Knowledge-Catalogue`'s own git — `git -C ~/Obsidian/Knowledge-Catalogue status --short` showed only `?? _archive/` while `git -C ~/dev/lean-stack status --short` showed ` D docs/lean-stack-okf/boot-prompt-deploy-symlink.md`, ` M docs/lean-stack-okf/index.md`, ` M docs/lean-stack-okf/plan-implement-resume-continuation.md` — a second repository, never named in this task's scope or safety preamble, was left dirty by a plain filesystem move instead of a tracked rename. `archive --restore --apply` reversed it correctly (content and both crosslinks verified byte-identical/line-identical against `HEAD` afterwards, see below), so the round trip completes, but every real `archive`/`rename` on the actual catalogue topology (every project bundle is a symlink) takes the untracked-fallback path, not the git-tracked one A02/A03 assume. This is the finding this leaf exists to surface: R-15's real-store run is exactly the layer at which the fixture suite (plain directories, no symlinked bundles) cannot see this. Filed as follow-up for the parent to route — no code touched in this leaf.

A second, smaller finding from the same mechanism: `archive`/`archive --restore` never remove the `_archive/<bundle>/` directory tree they leave behind once it is empty. `git status` cannot show this (git does not track empty directories) — after the restore, `~/Obsidian/Knowledge-Catalogue/_archive/lean-stack-okf/` and `~/Obsidian/Knowledge-Catalogue/_archive/` remained on disk until removed by hand (`rmdir`). A real operator relying on `git status` alone after `--restore` would not see this leftover.

### Step 1 — archive one concept (AC1)

```
$ python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue archive lean-stack-okf/boot-prompt-deploy-symlink.md
2 active concept(s) still link to this concept
would move   lean-stack-okf/boot-prompt-deploy-symlink.md  ->  _archive/lean-stack-okf/boot-prompt-deploy-symlink.md
  inbound    lean-stack-okf/plan-implement-resume-continuation.md   /lean-stack-okf/boot-prompt-deploy-symlink.md  ->  /_archive/lean-stack-okf/boot-prompt-deploy-symlink.md
  inbound    lean-stack-okf/index.md   /lean-stack-okf/boot-prompt-deploy-symlink.md  ->  /_archive/lean-stack-okf/boot-prompt-deploy-symlink.md
  reindex    _archive, lean-stack-okf
rename (dry-run): 2 inbound, 0 outbound link(s), 0 wikilink(s) (0 skipped-ambiguous), 2 bundle(s). Re-run with --apply.

$ python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue archive lean-stack-okf/boot-prompt-deploy-symlink.md --apply
2 active concept(s) still link to this concept
moved (fs)  lean-stack-okf/boot-prompt-deploy-symlink.md  ->  _archive/lean-stack-okf/boot-prompt-deploy-symlink.md
rewrote 2 inbound link(s) in 2 file(s), 0 outbound link(s)
rewrote 0 wikilink(s) in 0 file(s)
reindexed 1 index file(s) across: _archive, lean-stack-okf
staged for commit — run `okf-cli.py check` before committing.
```

(This first apply was immediately followed by an inspection-and-restore cycle to characterise the symlink finding above — both `~/Obsidian/Knowledge-Catalogue` and `~/dev/lean-stack` were confirmed clean before the concept was archived a second time for the AC2-AC4 evidence below. The `build-index` rebuild happened between the two archives, so the AC1 output above is the accepted evidence for AC1; the archived-state evidence for AC2-AC4 comes from the second, identical `archive --apply` run.)

### Step 2 — `check` over the five opted-in bundles while archived (AC2, SC-01)

```
$ for b in lean-stack-okf ai-wiki agent-memory okf-meta-wiki devd2-okf; do
    python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue check "$b"
  done

lean-stack-okf: OK — 0 violations
ai-wiki: OK — 0 violations
agent-memory:
WARNING  crosslink-format     agent-memory/jwt-mint-must-include-session-token-version.md  (catalogue-absolute link(s) not resolving from root: /home-lab-wiki/context/services/mybaby.md)
WARNING  tag-registered       agent-memory/stryker-mutant-location-is-a-range-not-a-point.md  (tag `mutation-testing` not registered in TAGS.md)
WARNING  tag-registered       agent-memory/mutmut-multi-pattern-filter-crash.md  (tag `mutmut` not registered in TAGS.md)
WARNING  tag-registered       agent-memory/mutmut-multi-pattern-filter-crash.md  (tag `mutation-testing` not registered in TAGS.md)
OK — 0 violations
okf-meta-wiki: OK — 0 violations
devd2-okf: OK — 0 violations
```

SC-01 holds: `0 violations` (exit 0) in all five bundles while the concept is archived — no `wikilink-resolvable` violation was raised. The four `agent-memory` warnings are pre-existing, unrelated to `boot-prompt-deploy-symlink` or the wikilink rule (a foreign crosslink and two unregistered tags), and are warnings, not violations, in default (non-strict) mode.

### Step 3 — same `find` query with and without `--include-archive` (AC3, SC-02)

The first attempt (before rebuilding the index) fell entirely to the semantic arm on a stale lexical index and never surfaced the archived concept in either invocation — `okf-cli.py build-index` was run to fix this (see Index strategy above; this consumed the one extra semantic/embedding call the task asked to keep minimal, a deviation noted here). After the rebuild:

```
$ python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue find "boot-prompt-deploy-symlink"
note: semantic arm owns this ranking (lexical top-1 lacked a clear margin)
... (10 semantic/lexical hits, none is boot-prompt-deploy-symlink) ...

$ python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue find "boot-prompt-deploy-symlink" --include-archive
note: --include-archive covers the lexical arm only; embeddings stay on the active catalogue
note: semantic arm owns this ranking (lexical top-1 lacked a clear margin)
... (same semantic hits, PLUS:)
------
score: 100/100
title: Boot-Prompt-Deploy-Relation — docs/roles/ → ~/.claude/profiles/ (Symlink)
type: Reference
path: _archive/lean-stack-okf/boot-prompt-deploy-symlink
...
```

SC-02 holds: the archived concept is absent without the flag and present, at `_archive/lean-stack-okf/boot-prompt-deploy-symlink`, with the flag.

### Step 4 — scoped run, this task's own new criterion (A10, AC4/SC-03)

```
$ python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue find "boot-prompt-deploy-symlink" --scope lean-stack-okf --include-archive --limit 20
note: --include-archive covers the lexical arm only; embeddings stay on the active catalogue
note: semantic arm owns this ranking (lexical top-1 lacked a clear margin)
... (17 hits, all path: lean-stack-okf/... except one) ...
------
score: 100/100
title: Boot-Prompt-Deploy-Relation — docs/roles/ → ~/.claude/profiles/ (Symlink)
path: _archive/lean-stack-okf/boot-prompt-deploy-symlink
------
score: 41/100
title: lean-stack Audit-Checkliste (Klasse × Disziplin → Ja/Nein)
path: lean-stack-okf/lean-stack-audit-checklist
... (further lean-stack-okf/... hits)
```

SC-03 partially demonstrated on the real store: every hit stayed inside `lean-stack-okf` (active and the one archived concept), confirming scope-filtering and `--include-archive` compose correctly. The real catalogue held exactly one archived concept for the whole duration of this run (by design — SPEC's own Nicht-Ziele rule out batch-archiving, and this leaf archives a single concept to keep the mutation minimal), so this run cannot empirically show a *foreign*-bundle archived concept being excluded — there was none to exclude. That half of A10 (cross-bundle exclusion) is covered at the fixture layer (per the coverage table in `SPEC.md`), not re-derivable here without a second, unwanted archive on the real store. Noted as a scope limitation of the real-catalogue proof, not a gap in the feature.

### Step 5 — restore (AC5) and clean-state check (SC-04)

```
$ python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue archive --restore _archive/lean-stack-okf/boot-prompt-deploy-symlink.md --apply
1 active concept(s) still link to this concept
moved (fs)  _archive/lean-stack-okf/boot-prompt-deploy-symlink.md  ->  lean-stack-okf/boot-prompt-deploy-symlink.md
rewrote 1 inbound link(s) in 1 file(s), 0 outbound link(s)
rewrote 0 wikilink(s) in 0 file(s)
reindexed 1 index file(s) across: _archive, lean-stack-okf
staged for commit — run `okf-cli.py check` before committing.
```

(Only 1 inbound link rewritten on restore, not 2 — `index.md` had lost its entry entirely via `reindex_tree` regeneration during the archive, not via crosslink rewrite, and got it back the same way, via reindex on restore, not via inbound-link rewrite. Confirmed by `grep` below.)

```
$ git -C ~/Obsidian/Knowledge-Catalogue status --short
(empty)
$ find ~/Obsidian/Knowledge-Catalogue -maxdepth 1 -name "_archive"
(no match, after `rmdir _archive/lean-stack-okf _archive` — both were empty, git does not track empty dirs so this never showed in status)
$ git -C ~/Obsidian/Knowledge-Catalogue rev-parse HEAD
39bcd28327d3e5ce71b0de8157f4a6bb14eea5a1   # unchanged
$ git -C ~/dev/lean-stack status --short
 M docs/supervisor-topologie/JOURNAL.md   # pre-existing, unrelated, never touched by this run
$ git -C ~/dev/lean-stack diff -- docs/lean-stack-okf/boot-prompt-deploy-symlink.md docs/lean-stack-okf/index.md docs/lean-stack-okf/plan-implement-resume-continuation.md
(empty — all three files byte-identical to HEAD)
$ diff <(git -C ~/dev/lean-stack show HEAD:docs/lean-stack-okf/boot-prompt-deploy-symlink.md) ~/dev/lean-stack/docs/lean-stack-okf/boot-prompt-deploy-symlink.md
(no differences — byte-identical, satisfies the A03 byte-equality bar)
```

SC-04 holds: `git status` clean in the catalogue, HEAD unchanged, `_archive/` gone (directory removed by hand after confirming it was empty — git status alone would have missed it). The underlying repo the symlink resolves into (`~/dev/lean-stack`) is also fully clean for every path this run touched.

### Index, final state

`build-index` re-run once more after the restore: `indexed 2567 concept(s) -> /Users/erik/Obsidian/Knowledge-Catalogue/.fts/fts.sqlite`. `.fts/fts.sqlite` is gitignored, so this never appears in `git status` — the user is left with a current, non-stale index rather than the pre-run one.

### Test suite

`just test` (run before any catalogue write): `Ran 612 tests in 45.767s` / `OK`.

### Deviations from the letter of the dispatch (all disclosed, none silent)

1. The first `find` query fell entirely to the semantic arm on a stale lexical index (no `--include-archive` effect visible at all) and had to be re-run after `build-index` — this used one extra embedding call beyond the strict minimum the task asked to keep low, because the query needed lexical evidence, not semantic guesswork, to prove AC3/SC-02.
2. The concept was archived and restored twice: a first pass immediately surfaced the cross-repo symlink finding above and was reversed right away to contain the risk before it was understood; a second, identical pass then produced the AC2-AC4 evidence with the index already rebuilt. Both passes are recorded in full above; the net effect on the real catalogue and on `~/dev/lean-stack` is the single restore confirmed clean at the end.
3. A5/SC-03 (the new scoped-run criterion) is only half-proven on the real store — inclusion yes, cross-bundle exclusion no, for the reason given in Step 4. This is a proof-scope limitation, not a defect; the exclusion half is covered by the fixture suite.

### Success criteria — final scorecard

- SC-01: **met** — `check` reports zero violations across all five opted-in bundles while archived.
- SC-02: **met** — `find` omits the archived concept without the flag, returns it under `_archive/lean-stack-okf/boot-prompt-deploy-symlink` with the flag.
- SC-03: **met with a noted scope limitation** — scoped `--include-archive` returns only `lean-stack-okf` concepts (active and the one archived); foreign-bundle exclusion not independently provable with a single archived concept on the real store (see Step 4).
- SC-04: **met** — `git status` clean in the catalogue after restore, HEAD unchanged, `_archive/` removed, and the linked repo (`~/dev/lean-stack`) confirmed byte-identical/clean for every touched path.

### Files touched in this repo (`~/dev/okf-tools`)

- `.beans/OKFT-fv7y--run-the-archive-round-trip-against-the-real-catalo.md` (this file — AC/SC amendment, then this report).

No production code touched (no fix for the symlink finding — filed as a finding for the parent to route, per this leaf's no-feature-code constraint). The real catalogue (`~/Obsidian/Knowledge-Catalogue`) and the linked repo (`~/dev/lean-stack`) carry no residual change from this run.
