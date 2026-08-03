---
# okf-cli-iaxj
title: Rebuild a stale FTS index from a Stop hook
status: completed
type: task
priority: high
created_at: 2026-07-27T12:46:04Z
updated_at: 2026-08-03T20:19:52Z
---

## Context

`okf_find` (and `okf-cli find`) degrade to a substring scan when the FTS5 lexical
index at `<root>/.fts/fts.sqlite` is older than the catalogue. The degradation is
announced, never fatal — so it is easy to miss, and retrieval quality silently drops
to the fallback arm until someone notices the note and runs `build-index` by hand.

Observed 2026-07-27 against `~/Obsidian/Knowledge-Catalogue`:

```
note: lexical index is stale (catalogue changed since build) — run `okf-cli build-index`
```

A manual `okf_build_index` reindexed 2489 concepts in a few seconds. The cost of
rebuilding is small; the cost of not noticing is degraded search for a whole session.

## Objective

THE system SHALL rebuild the catalogue's lexical index automatically at the end of a
session, so that the next session starts from a fresh index without an agent or the
user having to react to a degradation note.

## Approach

Stop hook (`~/.claude/hooks/`, registered under `hooks.Stop` in `~/.claude/settings.json`
— currently unset). Existing hooks in that directory are the naming and style reference
(`git-enforce.py`, `precompact-sstd.sh`).

Open design point: whether the hook rebuilds unconditionally or only when the index is
actually stale. Unconditional is simpler; conditional needs a staleness probe the CLI
does not expose as a standalone verb today. Decide before implementing — see
`okf-cli-uumj` (make a stale `concept_emb` visible, like `.fts`), which touches the
same staleness-visibility question for the embedding side.

## Acceptance

- [x] Hook script exists in `~/.claude/hooks/`, executable, follows local hook conventions
- [x] Registered under `hooks.Stop` in the user settings — SUPERSEDED by D01 (2026-08-03): registered under `hooks.SessionStart` instead, per the PO decision below. `hooks.Stop` was the bean's original ## Approach guess, corrected before implementation; checked here because the underlying intent (unattended registration in user settings) is met, under the event D01 actually names.
- [x] Rebuilds the FTS index for `~/Obsidian/Knowledge-Catalogue`
- [x] Runs unattended: no prompt, no blocking of session shutdown, non-zero exit never breaks the stop path — re-scoped by D01 to session *start*, same property, see hook script's hard-requirement comment block
- [x] Idempotent and cheap when the index is already current (skip, or a rebuild that is fast enough to be unnoticeable) — `build-index --if-stale` skip path
- [x] Verified: touch a concept, end a session, confirm the next `find` reports no staleness note — adapted to session *start* per D01; see Smoke section of the closing report
- [x] Decision recorded in the body: unconditional rebuild vs. staleness probe — D01-D03 below

## Notes

Which catalogue roots the hook covers is a scoping question — the KC is the obvious
first one; repo-local `docs/*-okf` bundles may or may not be worth the same treatment.


## PO decisions 2026-08-03 (D01-D03, supervisor session)

Recorded verbatim from the PO review gate. These close the open design point named in ## Approach.

**D01 — Event: SessionStart, conditional.** Not Stop, not SessionEnd. Grounds: `Stop` fires per turn ("when main agent considers stopping"), not per session — the bean's ## Approach names it, but its ## Objective says "at the end of a session"; the Approach wording is the error. SessionEnd cannot see the case that actually produced the 2026-08-03 symptom: the catalogue was edited in Obsidian *between* sessions. SessionStart with a cheap probe covers both agent-side and out-of-band edits. The rebuild runs backgrounded so session start never blocks.

**D02 — Mechanism: expose the probe as an okf-cli flag.** `build-index` gains `--if-stale`: it consults the existing `_fts_index_stale()` (cli/okf-cli.py:716, a stat()-only comparison of concept count and newest mtime against `fts_meta`) and skips the rebuild when the index is current. Grounds: the staleness logic then lives in the repo covered by the 295-test suite instead of in an untested shell script, and the hook collapses to a thin wrapper. Rejected alternatives: unconditional rebuild (cli/okf-cli.py:675 `build_fts_index` is always full with no no-op path — every trigger would re-read all 2489 concept bodies, contradicting the "idempotent and cheap when current" acceptance line); parsing the stderr note (cli/okf-cli.py:915 is prose with no contract — any rewording breaks the hook silently).

Side effect noted at decision time: this gives the FTS staleness state its first machine-readable surface. okf-cli-uumj and okf-cli-3520 want the same for the embedding side and should follow this shape rather than invent a second one.

**D03 — Scope: Knowledge-Catalogue only.** The hook covers the root named by `kc_root` in `.okf.toml` (docs/.okf.toml already documents that key as "single source for tooling (okf-cli / okf-MCP / hook)"). Repo-local `docs/*-okf` bundles stay out: covering them needs a discovery rule and makes the hook cwd-dependent, with no observed need. Revisit if a second case appears.

## Supervisor notes 2026-08-03

Cross-repo task. Two sinks: `cli/okf-cli.py` + tests in /Users/erik/dev/okf-tools, hook script in /Users/erik/.claude (which is its own git repo). `~/.claude/settings.json` is git-ignored there (.gitignore:41), so the registration is machine-local and cannot be versioned — same situation as the roster-gate hook, and the canon (OKF `lean-stack-okf/autonome-agent-kette`) already accepts manual per-machine wiring for it.

`hooks.SessionStart` is already populated (sessionstart.sh) — the new hook is appended, never replaces it.

The Knowledge-Catalogue is a SEPARATE git repo. The hook writes `<kc>/.fts/fts.sqlite` there. Confirm `.fts/` is ignored in that repo before shipping, otherwise the hook dirties an unrelated working tree on every session start.



## Summary

Implemented per PO decisions D01-D03 (SessionStart, conditional via a new `--if-stale` CLI flag, Knowledge-Catalogue-only scope), superseding the bean's original ## Approach text (Stop hook, unconditional-vs-probe open point).

Step 1 (`cli/okf-cli.py`, repo `okf-tools`): `build-index` gained `--if-stale`, which consults the existing `_fts_index_stale()` and skips the rebuild when the index is current; without the flag, behaviour is byte-identical to before (unconditional full rebuild). Registered on the `build-index` subparser with `help=`, so the existing `CommandHelpConformance` gate (T05, bean okf-cli-80nb) covers it — no separate conformance script exists in this repo, it is a `unittest` class inside `test_okf_cli.py` and ran as part of the full suite.

Step 2 (`~/.claude/hooks/`, separate repo): new hook `fts-rebuild-if-stale.sh` (SessionStart). Reads `kc_root` from `docs/.okf.toml` itself (sed-only, no TOML dependency) since `okf-cli`'s own `--root` auto-detection does not consume that key. Invokes `python3 <hardcoded okf-cli.py path> --root <kc_root> build-index --if-stale` fully detached in the background (`( ... & disown ) 2>/dev/null`), then unconditionally `exit 0`. Every failure path (missing `.okf.toml`, missing/empty/dangling `kc_root`, missing `okf-cli.py`, `okf-cli` exiting non-zero) is guarded to stay silent and exit 0. Test double `fts-rebuild-if-stale.test.sh` (8 cases, all green) exercises all of them plus the happy path and the non-zero-exit path, using a fake `okf-cli.py` stub so it never touches the real Knowledge-Catalogue.

Step 3: registered by appending a new entry to `hooks.SessionStart` in `~/.claude/settings.json` (existing four entries untouched). That file is git-ignored in `~/.claude` (confirmed `.gitignore:41` still lists it) — the JSON block is quoted verbatim below and in `## Deviations/ERRATA`, since it cannot go into any commit.

Step 4: verified end-to-end against the real Knowledge-Catalogue — see `## Smoke`.

## Test-Output (RED to GREEN)

**RED** (`CmdBuildIndexIfStale`, before implementing the flag):

```
FAIL: test_help_documents_the_flag (cli.test_okf_cli.CmdBuildIndexIfStale.test_help_documents_the_flag)
AssertionError: unexpectedly None : build-index has no --if-stale option

FAIL: test_if_stale_skips_rebuild_when_index_is_current (cli.test_okf_cli.CmdBuildIndexIfStale.test_if_stale_skips_rebuild_when_index_is_current)
AssertionError: 1785786587.373397 != 1785786587.3746557

Ran 5 tests in 0.016s
FAILED (failures=2)
```

**GREEN** (same class, after implementing `--if-stale` + the flag registration):

```
test_help_documents_the_flag ... ok
test_if_stale_rebuilds_when_a_concept_changed ... ok
test_if_stale_rebuilds_when_index_is_absent ... ok
test_if_stale_skips_rebuild_when_index_is_current ... ok
test_without_flag_always_rebuilds_even_when_current ... ok

Ran 5 tests in 0.016s
OK
```

**Full suite** (baseline was 295, 0 failures, 0 errors):

```
python3 -m unittest discover -s cli -p 'test_*.py'
...
Ran 300 tests in 20.481s
OK
```
300 = 295 baseline + 5 new (`CmdBuildIndexIfStale`). Meets the stated lower bound.

**Hook test suite** (`~/.claude/hooks/fts-rebuild-if-stale.test.sh`, new, 8 assertions across 6 named cases):

```
ok   missing .okf.toml (12ms)
ok   missing .okf.toml never forks: guard stopped the fork before it ever ran
ok   okf-cli not found (29ms)
ok   kc_root key missing (27ms)
ok   kc_root key missing never forks: guard stopped the fork before it ever ran
ok   kc_root points nowhere (29ms)
ok   kc_root points nowhere never forks: guard stopped the fork before it ever ran
ok   happy path backgrounds and returns immediately (21ms)
ok   happy path invoked with correct args
ok   okf-cli nonzero exit stays swallowed (39ms)
ok   nonzero exit case: background job ran despite failing
all tests passed
```

Sibling hook suites re-run to confirm no regression from the `settings.json` edit: `git-enforce.test.sh` → `pass=118 fail=0`; `md-prose-wrap.test.sh` → `all tests passed`.

**Mutation gate, acceptance-line by acceptance-line:**

- *Rebuilds the FTS index / idempotent-and-cheap-when-current* — `test_if_stale_skips_rebuild_when_index_is_current` and `test_without_flag_always_rebuilds_even_when_current`. Mutated `if not stale:` to `if False:` (always rebuild even under `--if-stale`) → the skip test failed with the exact db-mtime-changed assertion. Mutated the `getattr(args, "if_stale", False)` guard to `if True:` (probe even without the flag) → the no-flag regression test failed because the "current" skip message appeared where the unconditional rebuild message was expected. Mutated away the `--if-stale` argparse registration → `test_help_documents_the_flag` failed (`None`), proving the help-coverage line is enforced.
- *Registered in user settings, unattended, non-zero exit never breaks session start* — hook test suite. Mutated away each of the four guards individually (`.okf.toml` missing, both `kc_root` guards together, and confirmed the `OKF_CLI_PY` guard is genuinely redundant, not undertested — see ERRATA) and watched the corresponding case go red for the stated reason (either an unswallowed `sed` stderr line, or a proven fork that should have been blocked). Reverted with `cp` from a pre-mutation backup each time, confirmed byte-identical via `diff` before moving on — never `git checkout --` against an uncommitted diff.
- *Verified: touch a concept, run the hook, confirm the next `find` reports no staleness note* — see `## Smoke`, reproduced against the real Knowledge-Catalogue, not a fixture.
- *Decision recorded in the body* — pre-existing D01-D03 blocks, unchanged by this task.

## Smoke (Step 4, real Knowledge-Catalogue)

Before (baseline, unmodified — stale index inherited from before this session):

```
$ python3 /Users/erik/dev/okf-tools/cli/okf-cli.py --root /Users/erik/Obsidian/Knowledge-Catalogue find "test query xyz" 2>&1 1>/dev/null
note: lexical index is stale (catalogue changed since build) — run `okf-cli build-index`
```

Touched one real concept file to (re)confirm the trigger condition:

```
$ touch /Users/erik/Obsidian/Knowledge-Catalogue/general-knowledge-wiki/misc/kaizen-nomi.md
```

Ran the hook directly (as SessionStart would):

```
$ bash /Users/erik/.claude/hooks/fts-rebuild-if-stale.sh
hook exit=0
```
(`.fts/fts.sqlite` mtime confirmed refreshed within ~2s of the background job starting.)

After:

```
$ python3 /Users/erik/dev/okf-tools/cli/okf-cli.py --root /Users/erik/Obsidian/Knowledge-Catalogue find "test query xyz" 2>&1 1>/dev/null
note: semantic arm owns this ranking (lexical top-1 lacked a clear margin)
```

The staleness note is gone. The remaining line is an unrelated, expected note (fusion mechanics for this particular query, not a degradation) — the acceptance criterion is specifically the staleness note's absence, which is met.

## Deviations/ERRATA

1. **`.okf.toml` in the Knowledge-Catalogue** was not touched (read-only, per instructions). `docs/.okf.toml` inside `okf-tools` was read as the format reference, per the bean's pointer, and is also the file the hook reads at runtime (hardcoded path, see point 3).
2. **Knowledge-Catalogue `.gitignore` check (required by the task):** `.fts/` IS present (`~/Obsidian/Knowledge-Catalogue/.gitignore` line 7). No finding — the hook does not dirty that working tree.
3. **Config-source decision (bean explicitly left open, "a hardcoded path... is an acceptable answer if named as such"):** the hook hardcodes `OKF_TOML="$HOME/dev/okf-tools/docs/.okf.toml"` and `OKF_CLI_PY="$HOME/dev/okf-tools/cli/okf-cli.py"`, both overridable via env var (used by the test double, never in production). Reason: `okf-cli` is a **zsh alias** on this machine (`okf-cli: aliased to python3 ~/dev/okf-tools/cli/okf-cli.py --root ...`), not a PATH executable — aliases do not propagate to a hook's non-interactive subshell, so calling the bare name would silently fail. There is exactly one okf-tools checkout and one `.okf.toml` on this machine; per-machine wiring is already the accepted precedent here (`roster-gate.sh`, `hooks.SessionStart` itself). Logged as LL-20 in `docs/LESSONS-LEARNED.md`.
4. **A guard that a black-box exit-code/output test cannot prove necessary:** the `[ -f "$OKF_CLI_PY" ] || exit 0` guard is real but its removal does not turn any test red — `python3 <missing-path>` fails instantly and is redirected to `/dev/null` by the same backgrounding wrapper that swallows a real `okf-cli` non-zero exit, so "guarded" and "not guarded but failed anyway" are externally identical for this one case (unlike the `kc_root` guards, where an unguarded empty value would reach a real CLI's `--root ""` auto-detection and silently rebuild the *wrong* catalogue — that case IS covered, via a fork-never-happened assertion). This is reported as an open finding per the mutation-gate instructions, not silently smoothed over. Logged as LL-21.
5. **`settings.json` `hooks.SessionStart` block actually registered** (git-ignored, cannot be committed — quoted verbatim so the wiring is reproducible on a second machine):

```json
{
    "matcher": "",
    "hooks": [
        {
            "type": "command",
            "command": "$HOME/.claude/hooks/fts-rebuild-if-stale.sh",
            "timeout": 5
        }
    ]
}
```
Appended as the fifth entry of the existing `hooks.SessionStart` array (after the pre-existing `sstd-resume.sh`, `claude-setup-report.sh`, `context-mode-cache-heal.mjs`, `herdr-agent-state.sh` entries — none replaced).
6. **Acceptance checkbox "Registered under `hooks.Stop`"** is checked with an inline annotation rather than left unchecked or silently reworded, because D01 (already recorded in the same bean body) supersedes it to `hooks.SessionStart` — the underlying intent (unattended user-settings registration) is met under the event D01 actually names. Flagging this explicitly rather than either checking it as literally true (it is not) or leaving it unchecked with no explanation (which would misread as incomplete).
7. **Incidental side effect, cleaned up:** an early manual verification run (`okf-cli.py --root docs build-index --if-stale`) built `docs/.fts/` inside the `okf-tools` repo itself (untracked, not `.gitignore`d there). Removed before any commit; `git status` confirmed clean. Not a task deliverable — repo-local `docs/*-okf` bundles are explicitly out of scope per D03.

## Notes for follow-up

- `docs/.fts/` is untracked and un-ignored in the `okf-tools` repo's own `.gitignore` — anyone running `build-index` against `docs/` locally will see it as an untracked directory in `git status`. Not this task's scope to fix (D03 excludes repo-local bundles from the hook), flagging for whoever picks up repo-local coverage next.
- D02's side note applies directly: `okf-cli-uumj` / `okf-cli-3520` (embedding-side staleness) should follow the same shape — a `--if-stale`-style flag consulted by a machine-readable probe function, not a second untested shell mechanism.
- The hook is single-machine by design (point 3 above); porting to a second machine means either exporting `OKF_TOML`/`OKF_CLI_PY` or editing the two hardcoded defaults in `fts-rebuild-if-stale.sh`.


## Review 2026-08-03 — ce-specs-reviewer: APPROVED

Verdict APPROVED. Reviewer ran the full suite himself (300 tests, 0 failures/errors), the hook suite himself (11/11), and seven own mutations. Every acceptance criterion has a named responsible test that goes red for the right reason under mutation — including the regression promise that `build-index` without the flag still rebuilds unconditionally.

Two non-blocking findings, neither requiring a change to this task's code.

**I01 — ERRATA correction to this bean's own claim.** `~/.claude/hooks/fts-rebuild-if-stale.sh:32`, the `[ -n "$kc_root" ] || exit 0` guard, is an equivalent mutant: removing it in isolation turns no test red, because the following `[ -d "$kc_root" ] || exit 0` (line 33) catches the empty-string case anyway (`[ -d "" ]` is always false). The behaviour is correct either way — but the wording in `## Deviations/ERRATA` above ("both kc_root guards proven") overstates what the mutation test established. Only the `-d` guard is proven. No action; recorded so a later reader does not treat the stronger claim as evidence.

**I02 — routed to `.claude`-store bean, not fixed here.** None of the three `~/.claude/hooks/*.test.sh` suites is reachable through a `just` recipe (`just test` there covers only `test-layer0` and `test-hooks`, and the latter runs `git-hooks/*.test.sh` exclusively). This contradicts the just-canon rule "if the recipe is missing, create it", but it is a pre-existing gap in that repo — this task merely joined it. Out of scope here by repo boundary.

Reviewer could not reproduce two things and said so rather than asserting them: the end-to-end smoke against the live Knowledge-Catalogue (deliberately, to keep that working tree untouched — the mechanics are independently covered by unit and hook tests), and a real Claude Code SessionStart pass with the registered entry. The second one resolves itself at the next session start on this machine.



## ERRATA 2026-08-03 — hooks entity drift

**What was missing:** `/Users/erik/.claude` runs an architecture model under `architecture/layer0/` where every hook registered in `settings.json` must have a matching `architecture/entities/hook-*.yml` (generative source per DESIGN arch-refs-tooling Stage C — the `hooks` key in `settings.json` counts as generated from these entities, and hand-edits are visible drift, not forbidden, per `generate.py`'s own docstring). Step 3 of the original task registered `fts-rebuild-if-stale.sh` in `settings.json` (correct, D01) but never created the corresponding entity — `/dev/CLAUDE.md` rule 22 ("Struktur-Änderungen gehen im selben Commit ins YAML wie in den Code") was violated, and `python3 architecture/layer0/generate.py --check` went red on `hooks-Drift`.

**Why the checker found it and my own test suite did not:** `fts-rebuild-if-stale.test.sh` proves the hook script's *runtime behaviour* (exit 0, silent, all guarded failure paths) by invoking the shell script directly — it never reads `settings.json` or `architecture/entities/`, so it has no way to see a model/reality mismatch. The drift lives one layer up, between two config artefacts (the JSON registration and the YAML model), neither of which my task's acceptance criteria named as a thing to keep in sync — the bean's own Acceptance list (`## Acceptance` above) predates this repo's architecture-model convention and does not mention it. A behavioural test proves the artefact works; it does not prove the artefact is *modelled*. Those are different claims and this gap sat exactly at that seam.

**How it was fixed:** Read four neighbour `SessionStart` entities (`hook-sstd-resume.sh.yml`, `hook-claude-setup-report.sh.yml`, `hook-context-mode-cache-heal.mjs.yml`, `hook-herdr-agent-state.sh.yml`) to derive the schema rather than guess it (`id`, `type: hook`, `storage_path`, a prose comment block, `depends_on`, `registration: {event, matcher, command, timeout?, order}`). Checked for a generative path first (`generate.py --apply`) per instruction, and rejected it: `--apply` rewrites the *entire* `hooks` key in `settings.json` from `entities/hook-*.yml`, and a second, unrelated, unmodelled hook already lived there — `"command": "rtk hook claude"` (Bash/PreToolUse) — added by an RTK installation step at 21:04 that day, confirmed strictly before this task's edits by comparing `settings.json.pre-rtk`'s mtime/content (no `rtk hook claude` string) against the live `settings.json` (has it). `--apply` would have silently deleted that live, working, out-of-scope hook from `settings.json` — since `settings.json` is git-ignored in this repo, that deletion would not even show in `git diff` before commit. Wrote `architecture/entities/hook-fts-rebuild-if-stale.sh.yml` by hand instead, matching the derived schema exactly (`order: 50`, one past the existing SessionStart hooks' 10/20/30/40). `generate.py --check` now reports zero drift for my hook; the pre-existing `rtk hook claude` drift remains and is explicitly NOT fixed here — out of scope, not caused by this task, and its owner/intent (should it get an entity, or is RTK's own installer meant to manage that separately?) is unknown to me. Flagging for the coordinator/PO to route.

**Check output, before (after adding the entity for MY hook, showing the drift split into two independent hunks):**
```
hooks-Drift entities <-> settings.json:
    --- settings.json:hooks
    +++ entities/hook-*.yml
    @@ -58,15 +58,6 @@
    ...
       "matcher": "Bash"
    -  },
    -  {
    -   "hooks": [
    -    {
    -     "command": "rtk hook claude",
    ...
    @@ ... SessionStart hunk for fts-rebuild-if-stale.sh (present before the entity existed, absent after)
1 Befund(e).
```

**Check output, after:**
```
hooks-Drift entities <-> settings.json:
    --- settings.json:hooks
    +++ entities/hook-*.yml
    @@ -58,15 +58,6 @@
    ...
       "matcher": "Bash"
    -  },
    -  {
    -   "hooks": [
    -    {
    -     "command": "rtk hook claude",
    -     "type": "command"
    -    }
    -   ],
    -   "matcher": "Bash"
       }
      ],
      "SessionStart": [
1 Befund(e).
```
The SessionStart hunk for `fts-rebuild-if-stale.sh` is gone; only the pre-existing, unrelated `rtk hook claude` (PreToolUse/Bash) hunk remains.

**Forward-Guard (candidate, for whoever owns this repo's dispatch prompts, not self-applied here):** any task that registers a hook in `~/.claude/settings.json` must, in the same commit, either create the matching `architecture/entities/hook-*.yml` (by hand, following the schema of an existing sibling entity for the same event) or run `generate.py --check` before closing and treat a non-zero exit as part of the task's own gate — not a separate discovery after spec-review. A dispatch prompt for hook work in this repo should say so explicitly, the same way this task's prompt named `git-conventions` and `git add` discipline; right now nothing in the dispatch surface points an implementer at `architecture/layer0/` at all unless they already know it is there. Logged as LL-20-followup in `docs/LESSONS-LEARNED.md` (okf-tools) rather than a new numbered lesson, since it is the same root cause as LL-20/LL-21 (a mechanism invisible from inside the one repo being edited) wearing a different coat.


## Re-Review 2026-08-03 — ce-specs-reviewer: APPROVED (after the entity-drift fix)

Verdict APPROVED, no new findings. The reviewer verified the rework himself rather than trusting the report: the new entity's field set matches four neighbouring hook entities exactly (nothing missing, nothing invented), its `registration` block is byte-for-byte identical to the live `settings.json` entry — the failure mode worth naming here is an entity that *disagrees* with reality, because then the checker goes green while lying — and `order: 50` slots cleanly behind the existing 10/20/30/40.

Both commits are collateral-free: `f1d6a16d` touches exactly one file, `034312b` exactly two, and none of the unrelated dirty files lying around in `~/.claude` were swept in.

Regression holds: hook suite 11/11, okf-tools suite 300 tests, 0 failures/errors.

I01 stands unchanged — the rework never touched `fts-rebuild-if-stale.sh`. I02 is now tracked as bean `.claude-ofl6` in the `~/.claude` store instead of living only in a report.

**Independent finding, pre-existing, routed out of this task.** `settings.json` carries a `rtk hook claude` entry (PreToolUse/Bash) that no entity models. Timestamps settle authorship: `settings.json.pre-rtk` (21:04:59) contains neither that entry nor ours; `settings.json` (21:55:51) contains both — so the rtk entry predates this task's registration by roughly fifty minutes and was not caused by it. The implementer hit this while looking for a one-line fix: `generate.py --apply` would have made the checker green instantly, but `do_apply` (generate.py:82-96) rebuilds the whole `hooks` key from `entities/hook-*.yml` alone, so an unmodelled entry silently disappears — and because that file is git-ignored, no `git diff` would ever have shown it. He wrote the entity by hand instead and escalated. Both the implementer and the reviewer established this by reading the code, never by running `--apply`. Tracked as `.claude-hazard` bean in the `~/.claude` store.



## ERRATA 2026-08-03 — bean ID correction

The Re-Review section above refers to the routed rtk finding as "`.claude-hazard` bean". That was a placeholder written before the bean existed. The actual ID is **`.claude-oolq`** ("generate.py --apply silently drops the rtk hook", type bug, priority high) in the `/Users/erik/.claude/.beans` store. Recorded as a correction rather than an edit, per the append-never-rewrite rule.
