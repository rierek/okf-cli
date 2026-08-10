---
# OKFT-gpcx
title: Superseded decisions are not marked
status: completed
type: task
priority: normal
created_at: 2026-08-10T12:59:09Z
updated_at: 2026-08-10T15:05:43Z
parent: OKFT-hkze
---

## Objective (User Story)
As an agent answering from the catalogue, I want to see that a decision has been superseded, so that I do not report an overturned decision as current.

## Evidence (MODUS-B-REPORT Q01)
Run R4 retrieved a decision to consolidate the memory layer onto one database. A later concept in the same bundle, `decisions/memory-db-layer-teardown`, tears that layer down again. Nothing in the retrieved document says so; the agent noticed only because it had walked the bundle index first. Modus A cannot see this failure mode at all — the retrieval was formally correct and the answer was stale.

## Open question (Q01)
Should supersession become explicit in the catalogue — a frontmatter relation or a status field on decision-type concepts — and should `find`/`read` surface it?

## Note
Draft on purpose: this is a catalogue-schema decision (OKF properties), not an okf-tools change. It needs a PO decision before it is an implementable task. Scope guard: whatever the answer, it must not turn every concept into a workflow-state machine.

## Done 2026-08-10 (commit df84710)
D01 (PO, 2026-08-10) implemented: `superseded_by` is a frontmatter relation, optional, only meaningful on `type: Decision`, value a catalogue-root-absolute path — same form a crosslink uses. No status field, no workflow automaton.

Schema documented in `~/Obsidian/Knowledge-Catalogue/PROPERTIES.md` under Kern-Properties (catalogue commit `bbccab3`), visible in the Vault too via its existing symlink.

`cli/okf-cli.py`: `find` prints `superseded_by` in the hit block (between `type` and `path`) when the concept carries it — a hit without the field is byte-identical to before, proven by `FindSupersededByField.test_hit_without_superseded_by_is_byte_identical`. `check` gates two new rules: `superseded-by-resolves` (ERROR — dead target, same class as a dangling crosslink) and `superseded-by-scope` (WARNING — the field used on a non-`Decision` concept). TDD: RED shown for all three test classes before the implementation (`FindSupersededByField`, `CheckSupersededBy`), then GREEN. Each of the three rules has its own counter-mutation in production code, run and reverted, that turns exactly one test red — reproducible via `git show 7118ab4` plus the mutation lines documented inline as `MUTATION-PROOF-{1,2,3}` in the session transcript (not left in the tree). `just test`: 669 tests, OK (was 662 baseline).

Applied to the real case (`memory-layer-wiki/decisions/`, catalogue commit `ec5cc72`): read all five sibling decisions individually against `memory-db-layer-teardown`'s own carve-out ("Analyse- und Entscheidungs-Seiten … unabhängig vom abgebauten Code"). Marked superseded: `evaluation-and-decision-path` (asserts SQLite-vec is "seitdem aktiv" — false since the teardown), `upgrade-memory-system-level-6` (upgrade plan for the now-deleted `~/.claude/memory.db`, never executed), `2026-06-02-mem-27-sprint-plan-backend-consolidation` (the exact "consolidate onto one database" decision the bean's Evidence names — superseded by outright deletion instead of the planned `devd.db` merge). Left unmarked: `decision-against-neo4j-graph` — its conclusion (no graph DB at this scale) is independent of the deleted vector-store code and nothing has since revised it; this is the exception case, not a blanket "leave it alone".

Catalogue-wide sweep (`okf-cli list --type Decision`, 40 concepts) named two further plausible-but-out-of-scope candidates without touching them: `memory-layer-wiki/memory-analyses/.../2026-05-26-context-management-foundation-plan-and-decisions` (same bundle, outside `decisions/`, likely hit by the same teardown) and `devd2-okf/decisions/context-engineering-status` (plausibly superseded by the separate DevD-2.0-archived decision — different bundle, different task). Full writeup: `docs/okf-revision/Q01-SUPERSEDED-DECISIONS.md`.

`okf-cli check` against the real catalogue: `OK — 0 violations` after the frontmatter edits. `okf-cli build-index` rebuilt (2590 concepts) since concept content changed. Explicit deviation, named per the rule: `.tagvec` (semantic index) was NOT rebuilt — `build-semantic-index` only fills missing paths, not content-changed ones, which is the pre-existing bug `OKFT-3520`; the three marked concepts carry a stale semantic embedding until that bug is fixed. Left as-is, per the task's own instruction to name and not fix it here.

Commits: okf-tools `7118ab4` (feat(cli)) + `df84710` (docs(okf-revision)); Knowledge-Catalogue `bbccab3` (schema) + `ec5cc72` (content) — split into two catalogue commits rather than one, named explicitly since the task text allowed either and asked for the choice to be stated.
