---
# okf-cli-cskz
title: 'Retrieval architecture: FTS5 arm + conditional handover'
status: todo
type: feature
priority: high
created_at: 2026-07-25T23:21:47Z
updated_at: 2026-07-26T05:17:19Z
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
