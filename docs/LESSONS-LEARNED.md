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

## LL-05 (2026-07-25, P8 / supervisor) — two committers in one workdir: staged-work capture + orphaning reset

- **Symptom:** While a solo implementer worked main-direct in the shared workdir, the supervisor committed a bean update (`git add .beans && git commit`) and unknowingly swept the implementer's already-staged 825-line work into a mislabeled commit. The implementer's subsequent history cleanup (`reset --hard`) then orphaned that supervisor commit; one file (the PF-1 anchor) had to be recovered from the orphan by full-diff comparison.
- **Fix:** Implementer diffed against the orphaned commit before completion, recovered the missing content as its own commit, verified zero remaining diff (reviewer confirmed via `git fsck` + empty `bc4feda..358ba01` diff).
- **Forward-Guard:** "One committer per repo at a time" applies to the SUPERVISOR too. While an implementer runs main-direct in the main workdir, the supervisor makes NO commits there — bean lifecycle updates wait until the implementer reports, or the task runs in a worktree. If an urgent anchor commit is unavoidable: `git stash --staged` around it, never bare `git commit` after `git add`.

## LL-06 (2026-07-25, P8 review) — absolute score-ratio gates misclassify legitimate partial matches

- **Symptom:** Semantic-backstop trigger used absolute `score/max_score < 0.5` as "weak top-hit" signal; the repo's own golden fixtures (S1 0.417, S2 0.333) sat below it, so an unrelated semantic candidate at ordinary cosine (~0.7) displaced correct literal rank-1 hits. Dormant only because concept_emb was not yet populated — would have surfaced as a P12 gate failure.
- **Fix:** Margin-based confidence check (top-1 vs runner-up) plus an unconditional rank-1 pin for the keyword top hit (`c646605`).
- **Forward-Guard:** Fusion/trigger thresholds must be validated against the project's own golden fixtures BEFORE merge (the data was in-repo and contradicted the constant). Rank-guarantees belong in structure (pin), not in threshold tuning.

## LL-07 (2026-07-25, P12 inline) — stale bytecode cache silently falsifies mutation proofs

- **Symptom:** During mutation self-tests, a predicate inversion appeared "still green" and later the reverted file appeared "still mutated": mutation and revert had the same file size and landed within the same mtime second, so Python kept serving the stale `__pycache__` .pyc for a module loaded via `spec_from_file_location`.
- **Fix:** All mutation/revert cycles re-run with `rm -rf __pycache__` before every test invocation.
- **Forward-Guard:** Any mutation-proof protocol on this repo clears `__pycache__` between runs (same-size single-character edits are exactly the blind spot of mtime+size cache invalidation).

## LL-08 (2026-07-26, retrieval-architecture experiment) — a single HTTP 400 destroys a whole embedding pass

- **Symptom:** A full-catalogue `concept_emb` pass (title+body, 2437 concepts) died at ~550 rows on a plain `HTTP Error 400: Bad Request` from Ollama while three workers shared the host. `build_tagvec.py`'s `embed_bge_m3()` has no retry, no skip and no per-item isolation, so the exception propagated out of the run; every vector computed since the last 50-row batch write was lost with it. The offending concept could not even be identified afterwards, because the crash reports the exception but not the input. Re-embedding the same candidate in isolation succeeded — i.e. the failure was transient/load-related, not a poisoned document.
- **Fix:** In the experiment harness only: retry with exponential backoff, then progressive halving of the input (a 400 on this endpoint is usually over-long input), then skip the item with a logged path. `cli/embeddings/build_tagvec.py` is **still unguarded** — this entry is the record, not a shipped fix.
- **Forward-Guard:** Any long-running producer pass over the whole catalogue must be resumable and item-isolating: never let one item's transport error end the pass, always log the failing identity, and make the delta-reuse gate (`existing_concept_keys`) the resume mechanism. A pass that costs hours must not be all-or-nothing.

## LL-09 (2026-07-26, retrieval-architecture experiment) — unbatched embedding is 10–35× slower and shapes what is maintainable

- **Symptom:** `embed_bge_m3()` issues one HTTP request per text, `embed_voyage()` sends the whole list in one request. Measured on the same catalogue: Ollama 1.5–5.4 vectors/s (three workers, two hosts), Voyage **55 vectors/s** single-threaded. A full three-arm local pass takes ~45 minutes; the same work against the batching backend takes minutes.
- **Fix:** None yet. The experiment batches only on the Voyage path, because that is what the existing function already supported.
- **Forward-Guard:** Ollama's `/api/embed` accepts a list for `input` — batch it. This is not only a speed nicety: re-embedding after catalogue changes is an operational cost that decides whether a semantic layer stays current or silently rots. Evaluate an embedding design's *maintenance* cost (full re-embed wall clock) alongside its retrieval quality, before choosing it.
