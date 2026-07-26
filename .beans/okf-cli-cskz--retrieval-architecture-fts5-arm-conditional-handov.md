---
# okf-cli-cskz
title: 'Retrieval architecture: FTS5 arm + conditional handover'
status: todo
type: feature
priority: high
tags:
    - to-review
created_at: 2026-07-25T23:21:47Z
updated_at: 2026-07-26T12:23:05Z
parent: okf-cli-wuiv
---

Ships the measured target architecture of `docs/okf-retrieval-architecture/DESIGN.md`.

Today `okf-cli find` finds **1 of 48** paraphrase queries (zero-hit 0.979, R42). The defect is not the embedding unit — it is the fusion rule: the tool collects semantic candidates and then ranks them away, because normalised BM25 values at ranks 2-10 sit near 0.9 while a good cosine sits near 0.6 (R36).

Two arms, and a per-query decision about **which arm owns the ranking**:

- lexical: FTS5 + BM25 over a persistent `<root>/.fts/fts.sqlite` (porter + unicode61 + prefix, field weights title 3 / tags 2 / body 1)
- semantic: one `voyage-3-large` vector per concept over `title+body`, in `concept_emb`
- fusion: conditional handover — the lexical arm owns the ranking only when its top-1 leads the runner-up by 1.5x; otherwise the semantic arm owns it and lexical hits are appended behind, never in front

Both artefacts are optional: absent or unusable, `find` degrades (FTS to substring scan; voyage to lexical only) with one stderr note, never a hard fail.

## Plan

`docs/okf-retrieval-architecture/PLAN.md` — 13 tasks, ce-plan-reviewer GREEN after 2 rounds (commits `1614f86`, `3e236f3`, `3c0f17f`).

## Decisions carried in

| Dxx | Decision |
|-----|----------|
| D11 | Document embedding (`title+body`), not chunking, not title-only |
| D12 | Fusion rule = conditional handover |
| D13 | `voyage-3-large` is the productive semantic model |
| D14 | FTS5 arm and conditional handover ship together — R43's 0.437 was measured with FTS5 as the lexical arm, never with the substring scorer |
| D15 | `.fts` and `.tagvec` are persistent but optional artefacts; absent/stale degrades with an stderr note |
| D16 | Query-side degradation is two-stage (voyage to lexical); `concept_emb` holds voyage rows only |
| D17 | Scope includes T03, T05, T07; T05 ships flag-gated until measured |

## Global constraints for every leaf

- No new runtime dependencies in `cli/okf-cli.py` — stdlib only.
- Never hard-fail on a missing or unusable artefact.
- Artifact language English; commit subjects max 50 chars; no `Co-Authored-By`.
- Work on `main` (solo repo, main-direct allowed).
- Test baseline: `python3 -m unittest discover -s cli -p 'test_*.py'` must stay at exactly 19 failures / 2 errors, all pre-existing in the crosslink suites.
- Live catalogue root `~/Obsidian/Knowledge-Catalogue` is a SEPARATE git repo — never commit there.

## Success measure for the whole feature

Measured through the shipped CLI against `eval/queries_v2.json + queries_real.json` (n=48):
zero-hit ≤ 0.30 (was 0.979) · MRR ≥ 0.35 (was 0.021) · real-query zero-hit ≤ 0.25 (was 0.875) · p50 latency ≤ 2.0 s.


## Reading the task numbers

Two numbering schemes meet here, deliberately:

- **Bean title `Txx`** = this plan's task order (`PLAN.md` Task 1..13), which is also the execution order.
- **Footer `TASKS.md Txx`** = the pre-existing think-collection numbering in `docs/okf-retrieval-architecture/TASKS.md`, which predates the plan.

They do not line up, and that is intended: e.g. bean "T01 Producer batching" implements `TASKS.md` T11, and bean "T12 Failure taxonomy" implements `TASKS.md` T03. Follow the bean title for order, the footer for provenance.



## PF-1 — supervisor ruling (plan author) 2026-07-26: serial execution, no worktree

Question raised: run chain B (48qk...) in an isolated git worktree so it can proceed while
chain A is mid-task?

**Ruling: (a) serial, NO worktree.** Rationale from the plan author (supervisor pane w2B:pG),
NOT a PO decision — the PO was not consulted on this and it stays revisable:

1. The parallelism would be nominal. This is ONE session; dispatching two ce-implementers
   back-to-back or in two worktrees changes little — the critical path runs
   T07 -> T08 -> T09 -> T13, and chain B is not the bottleneck in it.
2. The price is disproportionate. `.beans/` is this repo's work-state authority. Two branches
   both writing bean status produce merge conflicts in exactly the files that define progress —
   more expensive than the time saved, and the kind of state damage that is not cleanly undone.
3. Repo convention (tools/CLAUDE.md, docs/CLAUDE.md): worktree isolation exists for PARALLEL
   AGENTS, not so a single agent can dodge a test-baseline collision. main-direct is expressly
   allowed here.
4. The 19F/2E baseline exists to catch cross-module regressions. Isolating it away defeats its
   purpose.

**Clarification that resolves the open part of the question:** chain B waits on **T01 only**,
not on all of chain A. As soon as `okf-cli-pean` is green and committed, the tree is clean and
`okf-cli-48qk` starts immediately — `okf-cli-c922` (the long production run) does NOT block
chain B.

**Test cadence for every leaf (supersedes nothing, adds precision):** while working INSIDE a
task, module-scoped runs are fine and encouraged for fast cycles —
`python3 -m unittest cli.test_embeddings_tagvec` or `python3 -m unittest cli.test_okf_cli`.
The full `python3 -m unittest discover -s cli -p 'test_*.py'` run belongs at the COMMIT POINT,
where the tree is clean anyway, and must show exactly 19 failures / 2 errors.



## Attribution rule for this feature (recorded 2026-07-26)

Two humans-shaped authorities speak into this realization session, and their weight differs.
Label them correctly in every bean:

- **"PO"** — Erik himself, answering in the chat of this session. Carries real authority: the
  PO sits at the merge gate, and anything logged as a PO decision is later treated as
  human-decided and is not re-litigated. Write "PO" ONLY when Erik answered.
- **"supervisor (plan author)"** — the plan author working in pane w2B:pG, reachable via
  `herdr pane run w2B:pG`. Makes process decisions; these are revisable and must never be
  logged as PO decisions.

Correction applied this date: PF-1 above was first written as a "PO ruling" with "verbatim
rationale from the PO". Wrong — the PO was not consulted on the worktree question. Relabelled
to supervisor/plan author.

Provenance of the one genuine PO decision so far, stated precisely: the c922 spend approval
($0.71 voyage-3-large run) was given through an AskUserQuestion modal in this session's chat;
the plan author confirmed on 2026-07-26 that this answer came from Erik. It stands as a PO
decision. Note for honesty: this session cannot itself distinguish who typed into the chat
channel — the attribution rests on that confirmation, not on independent evidence.

Escalation channel from here on: `herdr pane run w2B:pG "FRAGE <bean-id>: <text>"`, never a
blocking modal, and keep working on everything that does not depend on the answer.



## Lessons pending (write to docs/LESSONS-LEARNED.md at epic close)

- **LL-pending-01 — reviewer verdict line missing.** The ce-specs-reviewer report on
  `okf-cli-pean` (2026-07-26) started directly with the findings table; the mandatory first
  line `APPROVED` / `CHANGES_REQUIRED` was absent. Both findings were self-declared
  non-blocking, so the supervisor scored it APPROVED — but that was an interpretation, and the
  verdict line exists precisely so the control signal is not interpreted.
  *Forward-guard:* dispatch prompts for ce-specs-reviewer must say "first line EXACTLY
  APPROVED or CHANGES_REQUIRED, nothing before it"; if it is missing, demand it via
  SendMessage instead of inferring.
- **LL-pending-02 — plan grounded against a moving foreign repo.** PLAN.md SC-03 names
  "2437 concept(s)"; the live catalogue had grown to 2443 by realization time, so a literal
  success criterion was unmeetable while its intent was met.
  *Forward-guard:* success criteria that quote a count from a separate, live repo should state
  the count as ">= N as of <date>" or name the invariant instead of the number.



- **LL-pending-03 — stale rule in the registered agent definition (B, medium).** The T02
  implementer left its leaf `in-progress` + tag `to-review` and cited "D11 loop". It was
  obeying its own definition: `~/.claude/agents/ce-implementer.md:42` says "bean auf
  `to-review` taggen (kein `completed` durch den Implementierer)". That contradicts the
  canonical close rule in the OKF playbook `lean-stack-okf/autonome-agent-kette`, which
  declares itself the single source and records a PO decision of 2026-07-25 (bean `LES-bjc8`)
  resolving exactly this duplication: the LEAF agent sets `completed` itself once its own gate
  is green; `to-review` is the CONTAINER tag. The agent definition was never brought in line.
  Every implementer dispatched from this chain will repeat it.
  *Forward-guard (two parts):* (1) fix `~/.claude/agents/ce-implementer.md` lines 22 and 42 to
  point at the playbook instead of restating a contradicting rule — outside this repo, so it
  needs the PO/plan author, not this session; (2) until then, every ce-implementer dispatch
  prompt from this chain states the lifecycle explicitly: "set status `completed` yourself
  once your full gate is green; do NOT tag the leaf `to-review`".



## PF-2 — supervisor ruling (plan author) 2026-07-26: bean lifecycle for this feature

Ratifies the resolution of the rule collision recorded as LL-pending-03. The plan author read
both sources and confirms the playbook wins. NOT a fresh PO decision — it rests on the PO
decision of 2026-07-25 (bean `LES-bjc8`) already cited inside the playbook.

Authority: `lean-stack-okf/autonome-agent-kette`, section "Close-Regel (kanonisch — hier,
nicht anderswo)". `~/.claude/agents/ce-implementer.md:22,42` is simply STALE — not a
deliberately more conservative rule.

**Binding for every leaf of okf-cli-cskz:**

- Leaf (`task` / `bug`) -> the task agent sets `completed` ITSELF once its own full gate is
  green. `completed` means "gate green", not "reviewed by someone else". Waiting on a
  reviewer would cost the leaf its autonomy and force a foreign sync per task.
- Leaf is NEVER tagged `to-review`. That tag belongs to containers only.
- Container (`okf-cli-cskz`, and the milestone above it) -> NEVER `completed` by any agent.
  When all 13 leaves are through: tag `to-review`, then the PO decides accepted/rejected.
- `CHANGES_REQUIRED` on an already-`completed` leaf -> supervisor flips it back to
  `in-progress` and the fix happens in the SAME bean, never a new one.

**Standing instruction:** this lifecycle goes verbatim into EVERY ce-implementer dispatch
prompt of this chain — and stays there even after the agent definition is fixed, because a
subagent reads its dispatch prompt reliably and a file it never opens not at all.

The agent definition itself is owned by the plan author, not this session: it lives in
`~/.claude/agents/`, is global user config affecting all projects, and needs Erik's approval.
Not touched from here.



## PF-3 — commit invocation form (supervisor ruling, plan author, 2026-07-26)

**Binding for every agent in this chain: commit SINGLE-LINE.**

    git commit -m "subject"                 # correct
    git commit -m "subject" -m "body"        # correct
    git commit -m \ <newline> "subject"      # WRONG - silently defeats the guard

Never put a backslash line-continuation between `-m` and its message.

Why (root cause, established by test, not inference): `~/.claude/hooks/git-enforce.py`
tokenises the command with `shlex(punctuation_chars=True)` in NON-POSIX mode. That mode does
not resolve `backslash + newline`; it emits a literal backslash token, so the argv seen by the
hook is `[git, commit, -m, \, "subject"]`. `check_commit` takes `args[j+1]` after `-m`
— the BACKSLASH — as the message. Title = `\`, length 1, E1 passes, and the real message is
never inspected.

Verified both ways:
- `git commit --dry-run -m \ <newline> "<55-char subject>"` -> passes, exit 0, no E1.
- Same subject single-line -> `E1: Commit-Title >50 Zeichen (55). Kuerzen.`

Scope: **E1 and E2 are defeated** by this form (a `Co-Authored-By` trailer is likewise not
seen). E3/E4 are NOT affected — they do not read the value token. This is also NOT the
knowingly accepted D11 gap ("no `-m` -> allow"): here `-m` IS present, the hook just mistakes
the backslash for the message.

**Retracted supervisor claim:** an earlier note in bean `okf-cli-2a1w` concluded that
"PreToolUse hooks do not fire for Agent-tool subagents". That is WRONG and is withdrawn. The
plan author disproved it by having a general-purpose subagent attempt the same 55-character
commit in a throwaway repo: it was blocked verbatim with E1 and never executed. Hooks fire for
subagents. The defect was always the parser, and the tell was the backslash continuation.

*Forward-guard:* this rule goes into EVERY ce-implementer dispatch prompt of this chain, since
the subagents author most of the commits. The hook fix itself (strip continuations before
tokenising) is owned by the plan author and needs Erik's approval — `~/.claude/` is global
user config and is not touched from this session.



## PF-4 — supervisor ruling (plan author) 2026-07-26: no silent degradation

**Every degradation path emits exactly one stderr note. When in doubt whether a path needs
one: it does.**

Origin: T06 (`okf-cli-17y7`) asked whether the absent-index branch was deliberately silent.
It was not — the plan's CODE contradicted its own decision D15 ("absent or unusable ->
degradation with an stderr note", no exception). PLAN.md corrected in commit `daac681`; the
absent branch now prints
`note: lexical index absent — falling back to substring scan; run \`okf-cli build-index\` for
BM25 ranking`. Recorded as a PLAN defect owned by the plan author, NOT as an implementer
deviation.

Three reasons the note belongs there, reusable as a test for similar cases:
1. D15 admits no exception.
2. Asymmetry is worse than verbosity: the semantic arm already notes its absent case
   (`note: semantic arm skipped (.tagvec cache/concept embeddings absent)`). Two degradation
   contracts for one class of event in one tool is the inconsistency a later reader mistakes
   for intent.
3. The noise objection does not carry: notes go to **stderr**, so SC-04 (stdout byte-identical)
   is untouched and MCP consumers never see them. For a human, a line that names the state AND
   the fixing command disappears the moment they act on it — same property as the stale note,
   which was never contested.

**Rationale, project-wide:** silent degradation is the most expensive failure class here. Three
instances in a single day, each one where silence was indistinguishable from success:
- an agent reporting "working" while actually blocked on a modal question;
- a `grep` whose shell-level abort looked exactly like a genuine negative result, and was
  written up as a defect;
- a commit hook that mistook a backslash continuation for the commit message and passed
  everything.

Applies to every remaining leaf, not just T06.



## PF-5 — supervisor ruling (plan author) 2026-07-26: claims that end scrutiny must be scrutinised

**A claim of the form "behaviour-preserving, verified" is the one that must be checked, not the
one that may be skipped — because its function is to end further checking.**

Origin: T07 (`okf-cli-8j7l`) shipped a `cmd_find` shim whose ERRATA read "preserving 100%
prior observable behaviour... verified". The plan author read that sentence and approved the
shim ("right bridge") without looking at the five lines that were directly available. The
reviewer then reproduced a real behaviour change live: the shim ranks and slices semantic
candidates to `limit` BEFORE excluding already-lexical paths, so excluded paths consume slots
in the window and lower-ranked candidates are silently dropped. Verified against
`git 91e2604^`: the predecessor `semantic_backstop` excluded INSIDE the `sorted()` generator
(line 1037, `if path not in exclude_paths`), i.e. before the `[:limit]` cut. The shim filters
an already-cut list.

Ruling: fix the shim (exclude before ranking/slicing, plus a regression test for the overlap
case) AND correct the ERRATA to the true statement — not delete it. Explicitly rejected as a
shortcut: "T08 removes the shim anyway". T08 has not landed, can come back for rework, and
until then wrong behaviour would sit on `main` documented as verified-correct — the worse
variety of wrong.

**Pattern, third occurrence in this chain — this is the one to carry into LESSONS-LEARNED:**
each time the substance was roughly right and the *justification* did not hold.
1. T02: a mutation probe recorded in the bean could not be reproduced by the reviewer.
2. T06: "restored byte-identically, verified by size match" — `os.rename` never copies bytes,
   so the size check verified nothing about the actual risk (exception-safety).
3. T07: "preserving 100% prior observable behaviour... verified" — it did not preserve it.
*Forward-guard:* reviewers must treat any "verified"/"equivalent"/"no behaviour change" phrase
in a bean as a REVIEW TARGET, re-deriving the property from the pre-change code rather than
reading the sentence. Implementers must state what was actually executed, not the conclusion
drawn from it.

**Counter-example of the standard wanted (same task, same agent):** SC-NET was proven by a
socket-level guard patching `socket.socket.connect` to raise on any non-localhost address,
across the full 233-test run, under three environment conditions (valid key, invalid key, no
key) — zero real `connect()` calls in all three. That proves a negative instead of asserting
it. That is the bar.


## Review 2026-07-26

US-01 · `find "mockup tailscale"` surfaces `serve-excalidraw-drafts` (rank 3, `provenance: semantic`, cosine 0.55) although the word "mockup" appears nowhere in it — the R12 counter-probe that previously returned nothing · a
US-02 · `find "konvention"` matches inflected forms ("Konventionen") via the stemming, prefix-matching lexical arm instead of requiring an exact substring · a
US-03 · `find "größe"` treats the umlaut word as one token; the Unicode-aware tokenizer no longer splits at the diacritic · a

US-05 · Every result line names the arm that produced it (`provenance: lexical` / `provenance: semantic (cosine=…)`), and the handover to the semantic arm is announced on stderr · a
US-06 · Zero-hit queries offer the nearest registered tags instead of silent emptiness · r: "US-06 > rejected" — verdict given without further prose; the observation behind it is that `find "tailscael"` and `find "zzzzqqqq"` both return ten semantic results at cosine 0.40-0.46 instead of the `(no matches …)` line plus suggestion → okf-cli-snxj

US-04 · `build-index` builds the persistent FTS5 index on demand and the `lexical index is stale` note disappears on the next query · a
US-08 · Against a catalogue that never had an index, `find` still returns results and names both degradations on stderr (`lexical index absent — falling back to substring scan`, `semantic arm skipped …`), each exactly once · a

US-07 · A `--expand-tags` flag exists, is documented, ships off by default, and changes nothing when passed · r: "US-07: rejected" — not about the expansion behaviour, which was as specified, but about what `--help` tells a user about the CLI's capabilities: `--limit` undocumented, `find` absent from the command listing, no `<command> --help` pointer, listing unsorted, plus the systemic request for a self-documenting help system → okf-cli-3suc (bug), okf-cli-6zhw (feature), follow-up epic okf-cli-5uog
US-09 · The producer writes each batch before starting the next, retries then halves then skips a failing batch, and left the live catalogue at full coverage (2443/2443 voyage-3-large rows) · a
