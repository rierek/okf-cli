# LESSONS-LEARNED — okf-tools

Additive log. Each entry: Symptom · Fix · Forward-Guard.

## LL-01 (2026-07-25, P6 okf-cli-asky) — env-var pinning dead due to import-time binding

- **Symptom:** Boundary tests pinned the CLI under test via `os.environ["OKF_CLI"]` in `setUp`, but `mcp/okf_mcp.py` binds `OKF_CLI = os.environ.get(...)` as a module global at import time — the tests silently exercised the main-repo CLI copy instead of the worktree copy; a broken worktree CLI kept them green.
- **Fix:** Patch the module attribute directly (`mcp.OKF_CLI = ...`) in `setUp`, restore in `tearDown` (commit `5a25ac6`).
- **Forward-Guard:** Every test that pins a target-under-test MUST prove itself with a mutation self-test (break the target, watch the test fail, revert byte-identically) before it counts as evidence. Reviewer caught this only because the review protocol mandates independent mutation probes.

## LL-02 (2026-07-25, P2 okf-cli-ez6f) — false "file does not exist" claim propagated into bean ERRATA

- **Symptom:** Implementer recorded in the bean that `EVAL-DESIGN.md` "does not exist anywhere" and suggested authoring it; the file exists at `~/Obsidian/Vault/okf-revision/EVAL-DESIGN.md` (exactly where the milestone bean's Think-collection pointer says). Follow-up task owners acting on that note would have duplicated the design doc.
- **Fix:** Reviewer verified the real path; supervisor appended a dated ERRATA correction to the P2 bean and preludes into P3/P4 beans.
- **Forward-Guard:** Negative existence claims ("X does not exist") in bean closures require the search scope quoted (where was looked). Consumers of a bean must treat un-scoped negative claims as unverified.

## LL-03 (2026-07-25, P5 okf-cli-5qmn) — stopped agent left fixture residue in the real catalogue

- **Symptom:** The P5 implementer was stopped by the user mid seed/teardown window; `_okfeval-s1..s4.md` stayed behind untracked in the live Knowledge-Catalogue.
- **Fix:** Supervisor ran `python3 cli/eval/fixtures.py --root ~/Obsidian/Knowledge-Catalogue --teardown` (idempotent by design, P2 acceptance) and verified `git status --short` clean.
- **Forward-Guard:** After ANY agent stop/abort in this repo, the supervisor runs the teardown + catalogue-clean check before dispatching the next agent. Transient fixtures must always ship with an idempotent teardown precisely for this crash-window case.

## LL-04 (2026-07-25, P5 review) — exact-value pin test can still be mutation-blind via symmetric fixtures

- **Symptom:** The pure 8-metric pin test asserts exact values, yet inverting the `recall_at_1` and `location_correct_rate` predicates passed unnoticed — the hand-built fixture splits those rows exactly 50/50, so the inverted predicate yields the same mean.
- **Fix:** Prelude on P12 (okf-cli-6gq6): widen fixture to asymmetric splits before re-measurement.
- **Forward-Guard:** Test fixtures for aggregate metrics must use asymmetric class splits so predicate inversions are never value-invariant; mutation probes belong to the review protocol for every metric added later.
