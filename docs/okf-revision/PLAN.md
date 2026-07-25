# okf-cli + okf-mcp Reifegraderhöhung — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise the maturity of okf-cli/okf-mcp at its three weak edges (retrieval semantics, MCP→subprocess correctness, root-safety) with every retrieval change measured as a delta against a keyword baseline frozen *before* any optimization.

**Architecture:** Eval-first. A mechanical golden-file eval runner (Modus A) and hidden golden fixtures (S1–S4) are built *first*; the keyword-only baseline is frozen while `find` is still pure substring matching. Correctness (B01) and its missing integration-test layer land alongside. Only then does the hybrid-retrieval work begin, and its success is the metric delta re-measured by a dedicated Test-Coordinator gate. Documentation trails last, mirroring the shipped end-state.

**Tech Stack:** Python 3 stdlib only (no new deps in cli/ — dependency-freedom is a hard constraint). `unittest` for tests. FastMCP for the MCP surface. sqlite3 (stdlib) for reading the `.tagvec` embedding cache. Ollama bge-m3 / Voyage API only inside the offline producer script (never a runtime dep of `find`).

## Global Constraints

- **No new runtime dependencies in `cli/okf-cli.py`** — it is a single-file, dependency-free tool. Embedding *reads* use stdlib `sqlite3`; embedding *production* stays an offline script. `find` MUST degrade gracefully (keyword-only) when the `.tagvec` cache is absent — never hard-fail, never import a network client at runtime.
- **Artifact language English** — all git commit subjects/bodies and bean titles/bodies in English (global CLAUDE.md). Chat with the PO stays German.
- **Conventional Commits**, title ≤50 chars, no `Co-Authored-By` (git-enforce hook E1/E2). Commit autonomously after each task.
- **Baseline immutability** — once frozen (Task 5), the baseline metric file is never regenerated in-place. Re-measurement writes a *new* result file; the delta is baseline-vs-new.
- **Fixtures live in the real catalogue** (D11/Q06): hidden `_`-prefixed fake concepts seeded into real bundles of `/Users/erik/Obsidian/Knowledge-Catalogue/`. Every fixture is reachable by `find` (files, not `_`-dirs — `is_bundle_dir` only excludes `_`/`.`-prefixed *directories*, cli/okf-cli.py:76-77) and every seed has a matching teardown.
- **Catalogue root under test:** `/Users/erik/Obsidian/Knowledge-Catalogue/` (22 bundles). Pin its git rev when freezing the baseline.

---

## Decisions carried into this plan

| Dxx | Decision | Status |
|-----|----------|--------|
| D04 | Retrieval strategy = **hybrid**: keyword primary + semantic backstop in `find`; `.tagvec` provenance first (T08), then activate or extend to body-embeddings | 🟢 |
| D05 | MCP parity = only agent-relevant gaps. Candidates check/tags/refs — but check (okf_mcp.py:91-94) + refs (okf_mcp.py:101-104) are already registered; the real gap is `tags`. Write/admin verbs stay CLI-only by intent | 🟢 |
| D06 | B01 root cause = integration gap at MCP→subprocess boundary → plan adds a subprocess-level integration test layer (T09) | 🟢 |
| D07 | `okf-cli-mcp-overview.md` stays the canonical reference — de-stale it, do not replace with pure `--help` generation | 🟢 |
| D09 | **Eval-first**: keyword baseline (S1–S4, 2 query classes) frozen BEFORE WS1; success = metric delta; Modus A mechanical = metric basis | 🟢 |
| D11 | **Q06 → fixtures seeded into the real catalogue** (PO 2026-07-25): realism over isolation; requires pinned-rev baseline + reliable teardown | 🟢 |
| D12 | **Q07 → Modus A built+run by the implementer** (self-check + regression gate); **Modus B (agentic realism) runs in a separate agentic session**, not the implementer, during the Test-Coordinator phase — its own bean | 🟢 |

## Open, non-gating (defer to execution)

| Qxx | Question | Disposition |
|-----|----------|-------------|
| Q04 | Degree of doc auto-generation (partial verb tables vs. full) | Task 13 ships partial `--help`-derived verb tables; hand-written prose kept. PO may downscope to de-stale-only. |
| — | Ranking fusion keyword×semantic + fallback trigger threshold | Decided inside Task 8 as part of hybrid design, grounded on T08's embedding-scope finding. |

---

## File Structure

**Modified (correctness / retrieval):**
- `cli/okf-cli.py` — add `--json` to `index`/`list` argparse + JSON emission (Task 1); add semantic backstop + `--type`/`--tag`/`--scope`/`--bundle` filters + score breakdown to `find` (Task 9); root-safety in `catalogue_root` (Task 11).
- `mcp/okf_mcp.py` — register `okf_tags` (Task 10); no change needed for B01 (the fix is CLI-side making `--json` valid).

**Created (measurement):**
- `cli/eval/runner.py` — mechanical eval runner (Modus A): reads golden file, invokes `find`/`list`/`index`, scores, emits metric table (Task 4).
- `cli/eval/golden.json` — `query → expected concept path + threshold`, per fixture × {literal, paraphrase} (Task 3; JSON not YAML to stay stdlib-only).
- `cli/eval/fixtures.py` — seed/teardown of the S1–S4 hidden fake concepts in the real catalogue (Task 2).
- `cli/eval/results/baseline-<catalogue-rev>.json` — frozen keyword baseline (Task 5).
- `cli/eval/results/hybrid-<catalogue-rev>.json` — post-WS1 re-measurement (Task 12).

**Created (tests):**
- `cli/test_okf_mcp.py` — subprocess-level integration tests across the MCP→CLI boundary (Task 6).
- Additions to `cli/test_okf_cli.py` — unit tests for JSON emission, filters, semantic fallback, root-safety.

**Created (retrieval provenance):**
- `cli/embeddings/build_tagvec.py` — the `.tagvec` producer script pulled into the repo (Task 7), plus `cli/embeddings/README.md` documenting the offline pass.

**Modified (docs, trailing):**
- `/Users/erik/Obsidian/Knowledge-Catalogue/okf-meta-wiki/okf-cli-mcp-overview.md` — de-stale 18→20 verbs, drop "100%" (Task 14). Via `/okf`, not by hand-edit if it is an OKF concept.

---

## Sequencing (blocked_by → beans)

Labels below are **Plan-task numbers** (`Task N`, abbreviated `P<N>` in the diagram) — NOT the Think-collection `Txx` IDs (TASKS.md). Full Plan↔Think-ID mapping is in the Self-Review coverage table at the end.

```
Phase 1 (Grundlagen-A) ── all independent, parallelizable ────────────┐
  P1 B01-fix ─┐                                                        │
  P6 integ-tests (needs P1 to assert the fixed contract) ← P1         │
  P2 fixtures-seed ─┐                                                  │
  P3 golden-file  ← P2                                                 │
  P4 eval-runner  ─┘ (parallel to P2/P3, joins at P5)                 │
  P5 FREEZE baseline ← P2,P3,P4  ◄── hard gate: nothing in Phase 2    │
                                     may run until baseline frozen     │
                                                                       ▼
Phase 2 (Grundlagen-B) ── after P5 ──────────────────────────────────
  P7 .tagvec provenance ─┐
  P8 hybrid find        ← P7  (semantic fallback + filters + score breakdown)
  P10 MCP tags-parity   ── independent, parallel
  P11 root-safety       ── independent, parallel
                                                                       ▼
Phase 3 (Test-Coordinator) ── after P8 ──────────────────────────────
  P12 re-measure + regression gate ← P5,P8   (own bean)
  P13 Modus B agentic check ← P12            (own bean, SEPARATE session)
                                                                       ▼
Phase 4 (Docs, trailing) ── after P12 green ─────────────────────────
  P14 de-stale overview.md ← P8,P10,P11
```

Numbering below is task-execution order. The **baseline freeze (Task 5) is the pivot**: every retrieval change lives after it so its effect is a measurable delta (D09).

---

# PHASE 1 — Grundlagen-A: Measurement & Correctness Fundament

## Task 1: Fix B01 — `--json` contract for `index` + `list`

**Root cause (grounded):** `mcp/okf_mcp.py:11-12` marks `index`/`list` as `supports_json=True` (the `_COMMANDS` dict, okf_mcp.py:7-17), so `build_argv` appends `--json` (okf_mcp.py:39-40) and `run_okf` does `json.loads(out)` (okf_mcp.py:60-61). But the CLI argparse for `index` (okf-cli.py:1884-1888) and `list` (okf-cli.py:1889-1893) declares **no** `--json` flag → argparse exits non-zero → MCP raises `RuntimeError`. `check` (okf-cli.py:1970) and `refs` (okf-cli.py:1914) already have `--json`, so they are intact.

**Files:**
- Modify: `cli/okf-cli.py:1884-1893` (add `--json` to `index` + `list` parsers)
- Modify: `cli/okf-cli.py:482-502` (`cmd_index` — JSON branch)
- Modify: `cli/okf-cli.py:509-535` (`cmd_list` — JSON branch)
- Test: `cli/test_okf_cli.py`

**Interfaces:**
- Produces: `cmd_list` with `--json` emits `json.dumps([{title,type,path,description}, ...])`; `cmd_index` with `--json` emits `json.dumps({bundle: str, concepts: [{id,title,type,description}]})` (or catalogue-level `{bundles: [...]}` when no bundle arg). These shapes are what `okf_list`/`okf_index` MCP tools return to agents.

**Acceptance (seed for operationalize):**
- WHEN `okf-cli.py list --type X --json` is invoked, THE CLI SHALL print a single JSON array parseable by `json.loads`, one object per matching concept.
- WHEN `okf-cli.py index <bundle> --json` is invoked, THE CLI SHALL print a single JSON object with the bundle's concepts.
- WHEN the same commands run without `--json`, THE CLI SHALL emit the current human-readable output unchanged (no regression).

- [ ] **Step 1: Write failing test for `list --json`**

```python
class ListJson(unittest.TestCase):
    def setUp(self):
        self.root = _make_tmp_catalogue()  # helper: 1 bundle, 2 concepts w/ type/tag
    def tearDown(self):
        shutil.rmtree(self.root)

    def test_list_json_is_parseable_array(self):
        args = types.SimpleNamespace(type="Runbook", tag=None, scope=None, json=True)
        out = _capture_stdout(lambda: okf.cmd_list(self.root, args))
        data = json.loads(out)
        self.assertIsInstance(data, list)
        self.assertTrue(all("path" in r and "type" in r for r in data))
```

- [ ] **Step 2: Run it, verify it fails** — `python3 -m unittest test_okf_cli.ListJson -v` → FAIL (`cmd_list` has no `json` handling; `AttributeError`/no JSON on stdout).

- [ ] **Step 3: Add `--json` to argparse** for both parsers (okf-cli.py:1889-1893 `pls`, and okf-cli.py:1884-1888 `pi`):

```python
pls.add_argument("--json", action="store_true", help="machine-readable output")
# and on the index parser:
pi.add_argument("--json", action="store_true", help="machine-readable output")
```

- [ ] **Step 4: Add JSON branch to `cmd_list`** — before the human-print loop (okf-cli.py:524):

```python
    hits.sort(key=lambda x: x[0].casefold())
    if getattr(args, "json", False):
        print(json.dumps([
            {"title": t, "type": ty, "path": p, "description": d}
            for (t, ty, p, d) in hits
        ]))
        return
```

- [ ] **Step 5: Add JSON branch to `cmd_index`** — build a structured object instead of the markdown/synth print when `args.json` is set. For a bundle arg: `{"bundle": args.bundle, "concepts": [{"id":cid,"title":title,"type":t,"description":desc}, ...]}`. For no arg: `{"bundles":[{"bundle":b, ...}]}`. Guard `getattr(args,"json",False)` at the top of `cmd_index` and return early after `print(json.dumps(...))`.

- [ ] **Step 6: Run unit tests** — `python3 -m unittest test_okf_cli -v` → PASS.

- [ ] **Step 7: Commit** — `git add cli/okf-cli.py cli/test_okf_cli.py && git commit -m "fix(cli): honor --json on index and list verbs (B01)"`

---

## Task 2: Seed hidden golden fixtures S1–S4 into the real catalogue

**Design (grounded on EVAL-DESIGN.md:7-17, D11):** Fixtures are `_`-prefixed fake concept files seeded into *real* bundles so they compete with the ~1783 live concepts for ranking. A term string unlikely to collide with real content is used as the shared secret token (e.g. `zqxeval`). Each scenario isolates one retrieval property:

| Sz | Placement | Isolates | Keyword baseline expectation |
|----|-----------|----------|------------------------------|
| S1 | token in Title + one H2 + Body, correct bundle | ceiling/sanity | Top-1, score near max |
| S2 | as S1 but in the **wrong** bundle | location-sensitivity | `find` rank ≈ S1 (find is location-blind, okf-cli.py:544); `list --scope=<right>` misses |
| S3 | correct bundle, generic title, no matching tags, token **only in body** | field-weighting + semantic gap | literal query: low rank (body×1); paraphrase: zero-hit |
| S4 | correct bundle, `type`/`tag` frontmatter wrong/missing, findable only via index-walk / body | metadata- vs structure-retrieval | `list(type,tag)` miss; index-walk / `find`-body only path |

**Files:**
- Create: `cli/eval/fixtures.py` (seed + teardown functions and the fixture spec)
- Test: `cli/test_eval_fixtures.py`

**Interfaces:**
- Produces: `SEED_TOKEN: str`, `FIXTURES: list[Fixture]` (each `Fixture(sz, rel_path, title, type, tags, body, correct_bundle)`), `seed(catalogue_root) -> list[str]` (returns written abs paths), `teardown(catalogue_root) -> list[str]` (returns removed paths; idempotent), **and a `__main__` argparse CLI** `python3 fixtures.py --root <cat> {--seed|--teardown}` (default root = the canonical catalogue). Consumed by the golden file (Task 3), runner (Task 4), and invoked as a CLI from Tasks 5/12.

**Acceptance:**
- WHEN `seed(root)` runs, THE module SHALL write exactly one `.md` per fixture (S1–S4) under real bundles, each reachable by `iter_concepts` (okf-cli.py:89-98).
- WHEN `teardown(root)` runs after any partial seed, THE module SHALL remove every `_`-prefixed fixture file it owns and leave no fixture residue (idempotent).
- WHEN invoked as `python3 fixtures.py --root <cat> --seed` / `--teardown`, THE module SHALL run the matching function and print the affected paths (this is the entrypoint Tasks 5/12 call).
- THE seed token SHALL NOT appear in any real catalogue concept (verified by a pre-seed `find` returning zero hits for the token).

- [ ] **Step 1: Write failing test** — `test_seed_then_teardown_is_clean`: assert token has 0 hits before seed (via `okf.cmd_find`), 4 fixture files exist after `seed`, 0 fixture files after `teardown`.

- [ ] **Step 2: Run it, verify it fails** (`fixtures.py` does not exist → ImportError).

- [ ] **Step 3: Implement `fixtures.py`** — define `SEED_TOKEN`, the four `Fixture` records with the placement table above, `seed()` writing frontmatter+body, `teardown()` globbing the owned `_`-prefixed paths and unlinking. Choose real target bundles from `list_bundles(root)` deterministically (e.g. first two bundles for S1/S3/S4 correct-bundle, a different bundle for S2 wrong-bundle).

- [ ] **Step 4: Add the `__main__` CLI** — `argparse` with `--root` (default canonical catalogue) + mutually-exclusive `--seed`/`--teardown`; dispatch to the matching function and print affected paths. Add a test asserting `--teardown` after `--seed` leaves zero residue.

- [ ] **Step 5: Run test** → PASS.

- [ ] **Step 6: Commit** — `git commit -m "feat(eval): seed/teardown hidden golden fixtures S1-S4"`

---

## Task 3: Author the golden file (query → expected path + threshold)

**Design (EVAL-DESIGN.md:19-32):** Two query classes per fixture — **literal** (contains the exact token) and **paraphrase** (synonym/rewrite, keyword-zero-hit). The literal-vs-paraphrase zero-hit delta is the primary optimization signal.

**Files:**
- Create: `cli/eval/golden.json`
- Test: covered by the runner test (Task 4)

**Interfaces:**
- Produces: `golden.json` — a list of `{id, verb, query, class, expected_path, min_rank, min_score_ratio, expect}` rows. `expected_path` matches the `bundle/concept-id` form `find` prints (okf-cli.py:560,571); `expect` (`hit`/`miss`) applies to `list` rows.

**Acceptance:**
- THE golden file SHALL contain ≥2 rows per fixture (one `literal`, one `paraphrase`) plus the S4 index-walk and S1/S4 `list`-metadata rows from EVAL-DESIGN.md:27-32.
- THE golden file SHALL contain an explicit **S2 location row**: `list --scope=<correct-bundle>` expected to MISS the S2 fixture (it lives in the wrong bundle) — the comparative core of S2's location-blindness finding (EVAL-DESIGN.md:12,16-17). Each `list` row carries an `expect` field (`hit`/`miss`) so the runner can score location-correctness and metadata-hit.
- EACH row SHALL name the verb (`find`/`list`/`index`) and the expected concept path.

- [ ] **Step 1: Write `golden.json`** with the literal + paraphrase queries for S1–S4, the S4 index-walk row (verb `index`, expected concept listed in bundle TOC), the Ziel-3 `list` rows (S1 correct type/tag hit, S4 expected miss), and the **S2 `list --scope=<correct-bundle>` expected-miss row**. JSON (stdlib `json`, no PyYAML dependency — honors the no-deps constraint).

- [ ] **Step 2: Commit** — `git commit -m "feat(eval): add golden.json query set for S1-S4"`

---

## Task 4: Build the mechanical eval runner (Modus A)

**Design (EVAL-DESIGN.md:33-53, T10):** Deterministic. For each golden row: invoke the named verb against the catalogue root, parse the ranked output, locate the expected path, compute per-row rank + score-ratio + hit/zero-hit, then aggregate Recall@1, Recall@5, MRR, Zero-Hit-Rate (split literal vs paraphrase), and mean score-ratio. Emits a metric table (human) and a JSON result blob (machine, for freezing).

**Files:**
- Create: `cli/eval/runner.py`
- Test: `cli/test_eval_runner.py`

**Interfaces:**
- Consumes: `fixtures.seed/teardown` (Task 2), `golden.json` (Task 3).
- Produces: `run(catalogue_root, golden_path) -> dict` returning `{catalogue_rev, per_row:[...], metrics:{recall_at_1, recall_at_5, mrr, zero_hit_rate_literal, zero_hit_rate_paraphrase, mean_score_ratio, location_correct_rate, metadata_hit_rate}}`. `location_correct_rate` scores the S2 `list --scope` rows (expected miss counts as location-correct); `metadata_hit_rate` scores the Ziel-3 `list(type,tag)` rows (S1 hit / S4 miss, EVAL-DESIGN.md:31,41-42). `main()` CLI: `python3 runner.py --root <cat> --golden golden.json [--out results/x.json]`. Invokes `find`/`list`/`index` via `subprocess` against `okf-cli.py` (real process path — same boundary the MCP uses, so the runner doubles as a smoke of that path).

**Acceptance:**
- WHEN `run()` executes against a seeded catalogue, THE runner SHALL emit all eight metrics (six retrieval + `location_correct_rate` + `metadata_hit_rate`) and a per-row rank for every golden query.
- WHEN scoring a `list` row, THE runner SHALL compare actual hit/miss against the row's `expect` field and fold it into `location_correct_rate` (S2) or `metadata_hit_rate` (Ziel-3).
- THE runner SHALL record the catalogue git rev (`git -C <root> rev-parse --short HEAD`) into the result blob so a baseline is traceable to catalogue state.
- WHEN a query returns zero hits, THE runner SHALL record rank=∞ and count it toward the class-appropriate zero-hit-rate (never crash).

- [ ] **Step 1: Write failing test** — `test_runner_scores_literal_s1_top1`: seed fixtures, run, assert S1 literal row has rank 1 and `recall_at_1 > 0`.

- [ ] **Step 2: Run it, verify it fails** (`runner.py` absent).

- [ ] **Step 3: Implement `runner.py`** — subprocess-invoke `find --limit 10` (and `list --json`, `index`), parse the `------`-delimited blocks (or `--json` for list), map expected_path → rank, aggregate metrics, capture catalogue rev, write `--out` JSON.

- [ ] **Step 4: Run test** → PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(eval): mechanical golden-file eval runner (Modus A)"`

---

## Task 5: FREEZE the keyword baseline — the pivot (D09)

**This is a hard gate.** No retrieval change (Phase 2) may land before this task's artifact is committed. The baseline captures `find` while it is still pure keyword/substring (okf-cli.py:538-574, unchanged).

**Files:**
- Create: `cli/eval/results/baseline-<catalogue-rev>.json` (committed)
- Create/Modify: `docs/okf-revision/PLAN.md` — record the frozen rev + headline metrics here (or a `BASELINE.md` note)

**Acceptance:**
- THE baseline result file SHALL be produced by `runner.py` against the seeded catalogue at a recorded git rev, then committed unchanged.
- AFTER freeze, THE baseline file SHALL never be regenerated in place; re-measurement (Task 12) writes a new file.

- [ ] **Step 1: Seed fixtures** — `python3 cli/eval/fixtures.py --seed` (or via a `just eval-seed` recipe if a justfile exists — run `just --list` first).

- [ ] **Step 2: Run baseline** — `python3 cli/eval/runner.py --root ~/Obsidian/Knowledge-Catalogue --golden cli/eval/golden.json --out cli/eval/results/baseline-<rev>.json`.

- [ ] **Step 3: Record headline metrics** in this plan (zero-hit-rate literal vs paraphrase is the number WS1 must move).

- [ ] **Step 4: Teardown fixtures** — `python3 cli/eval/fixtures.py --teardown` (leave the real catalogue clean; the baseline JSON already captured the numbers).

- [ ] **Step 5: Commit the frozen baseline** — `git add cli/eval/results/baseline-*.json && git commit -m "chore(eval): freeze keyword baseline before WS1"`

---

## Task 6: Integration tests at the MCP→subprocess boundary (T09)

**Root cause (D06, Q03):** the existing suite loads `okf-cli.py` via importlib and calls functions directly (test_okf_cli.py:6-13) — it can never catch B01, which lives in argv marshalling across the process boundary. This task adds the missing layer.

**Files:**
- Create: `cli/test_okf_mcp.py`
- Depends on: Task 1 (asserts the *fixed* contract)

**Interfaces:**
- Consumes: `okf_mcp.build_argv`, `okf_mcp.run_okf` (okf_mcp.py:24,51), a tmp catalogue fixture.
- Produces: regression coverage for every `supports_json` verb through the real subprocess.

**Acceptance:**
- WHEN `run_okf(root, "index", {})` and `run_okf(root, "list", {"type": X})` execute against a tmp catalogue, THE call SHALL return parsed JSON without raising (the exact B01 failure, now guarded).
- THE test SHALL cover each `_COMMANDS` entry with `supports_json=True` (`index`, `list`, `check`, `refs`) end-to-end via subprocess.

- [ ] **Step 1: Write failing test** (would fail pre-Task-1):

```python
import importlib.util, os, json, unittest, tempfile, shutil
_H = os.path.dirname(os.path.abspath(__file__))
_s = importlib.util.spec_from_file_location("okf_mcp", os.path.join(_H, "..", "mcp", "okf_mcp.py"))
mcp = importlib.util.module_from_spec(_s); _s.loader.exec_module(mcp)

class McpSubprocessBoundary(unittest.TestCase):
    def setUp(self):
        self.root = _make_tmp_catalogue()      # shared helper
        os.environ["OKF_CLI"] = os.path.join(_H, "okf-cli.py")
    def tearDown(self):
        shutil.rmtree(self.root)
    def test_list_json_over_subprocess(self):
        out = mcp.run_okf(self.root, "list", {"type": "Runbook"})
        self.assertIsInstance(out, list)     # parsed JSON, no RuntimeError
    def test_index_json_over_subprocess(self):
        out = mcp.run_okf(self.root, "index", {"bundle": ""})
        self.assertIsInstance(out, (dict, list))
```

- [ ] **Step 2: Run** → PASS on the Task-1-fixed CLI (and would FAIL if reverted — note this in the commit body).

- [ ] **Step 3: Add coverage** for `check` and `refs` (already `--json`-valid) to lock the whole boundary.

- [ ] **Step 4: Commit** — `git commit -m "test(mcp): integration coverage at CLI subprocess boundary"`

---

# PHASE 2 — Grundlagen-B: Optimization (measured against the frozen baseline)

> **Gate:** Task 5 baseline MUST be committed before any task here.

## Task 7: `.tagvec` provenance — pull the producer into the repo (T08)

**Grounded (RET10/RET11):** the live cache `/Users/erik/Obsidian/Knowledge-Catalogue/.tagvec/tag_vectors.sqlite` has table `emb(key, tag, model, dim, vec BLOB)` — 627 bge-m3 + 650 voyage-3-large rows. Its producer is an ad-hoc offline SOP (`Knowledge-Catalogue/okf-meta-wiki/extensions/embedding-based-tag-consolidation.md`), a standalone Ollama/Voyage script *outside* the repo → not reproducible.

**This is a gating investigation task.** Its output decides Task 8's design: the embeddings are keyed on **tags** (`emb.tag`), not concept bodies. So the "semantic fallback" question is: do tag-embeddings suffice to rescue paraphrase queries, or must Task 8 extend embedding to concept titles/bodies?

**Files:**
- Create: `cli/embeddings/build_tagvec.py` (the producer, imported from the SOP script)
- Create: `cli/embeddings/README.md` (offline pass: how to run, model set, that it is NOT a runtime dep)

**Acceptance:**
- THE producer script SHALL live in-repo and regenerate a `tag_vectors.sqlite` with the same `emb` schema (RET10) from a catalogue root.
- THE README SHALL document embedded scope (**tags only**, confirmed by `emb.tag`) and state explicitly that `find` reads this cache at runtime but never produces it.
- THE task SHALL record a written finding: *tag-embeddings only vs. body-embeddings needed* — this decides Task 8's fallback surface.

- [ ] **Step 1: Query the live cache** — `sqlite3 .tagvec/tag_vectors.sqlite ".schema emb"` and a sample row; confirm scope = tags.
- [ ] **Step 2: Import the SOP script** into `cli/embeddings/build_tagvec.py`, parameterize root + output path, keep network calls behind an explicit `--produce` flag.
- [ ] **Step 3: Write `README.md`** with the finding + the tags-vs-body decision for Task 8.
- [ ] **Step 4: Commit** — `git commit -m "feat(embeddings): bring tagvec producer + provenance into repo"`

---

## Task 8: Hybrid `find` — semantic backstop + filter composition + score breakdown

**Consolidates WS1 (T06 hybrid, FIL03/04, SCO03).** Keyword stays the primary path (okf-cli.py:552-556 unchanged as the first pass); the semantic backstop fires only on weak/zero keyword results. Three sub-capabilities, each independently testable — split into 8a/8b/8c but committed as one Task-8 deliverable since they share `cmd_find`.

**Files:**
- Modify: `cli/okf-cli.py:538-574` (`cmd_find`) + argparse `pf` (okf-cli.py:1894-1896)
- Modify: `mcp/okf_mcp.py:67-69` (`okf_find` tool — expose new filter params) **AND** `mcp/okf_mcp.py:18-19` (`_FLAGS` dict — register `scope`/`bundle` so `build_argv` marshals them; `type`/`tag` already present at :19). Without the `_FLAGS` entry, `build_argv` (okf_mcp.py:33-35) silently drops `scope`/`bundle` — a silent-failure bug, not an exception.
- Test: `cli/test_okf_cli.py`, `cli/test_okf_mcp.py` (assert `scope`/`bundle` reach the CLI over subprocess)

**Interfaces:**
- Produces: `find` gains `--type`, `--tag`, `--scope`, `--bundle` (filter composition), `--breakdown` (per-field/term score), and a semantic fallback controlled by a threshold constant. `okf_find` MCP tool gains `type`, `tag`, `scope`, `bundle` optional params; `_FLAGS` extended with `"scope": "--scope", "bundle": "--bundle"` (okf_mcp.py:19).
- Consumes: `.tagvec` reader (stdlib sqlite3) — **graceful skip if cache absent** (Global Constraints).

### 8a — Search+filter composition (FIL03/FIL04)

**Grounded:** `find` iterates `list_bundles(root)` with no filter (okf-cli.py:544, FIL01/FIL04); `list` filters exact type/tag but cannot keyword-search (FIL03). Make them composable in one `find` call.

**Acceptance:**
- WHEN `find <q> --type T --tag G --scope B` runs, THE CLI SHALL keyword-rank only concepts matching the exact type/tag and within scope B (reusing `resolve_scopes`, okf-cli.py:514, and `extract_tags`, okf-cli.py:519).
- WHEN no filter flags are passed, THE CLI SHALL behave exactly as today (no regression — baseline queries still valid).

- [ ] **Step 1:** Failing test `test_find_scoped_by_type_excludes_other_types`.
- [ ] **Step 2:** Verify fail.
- [ ] **Step 3:** Add `--type/--tag/--scope/--bundle` to `pf`; in `cmd_find`, replace the bare `list_bundles(root)` loop (okf-cli.py:544) with a scope/type/tag pre-filter before scoring.
- [ ] **Step 4:** Register `scope`/`bundle` in `_FLAGS` (okf_mcp.py:19) and add the four params to the `okf_find` tool signature (okf_mcp.py:67); add a `test_okf_mcp.py` case asserting `--scope` reaches the CLI over subprocess.
- [ ] **Step 5:** Test → PASS. **Step 6:** hold commit until 8c (shared file).

### 8b — Score breakdown transparency (SCO03)

**Grounded:** only aggregate `score/max` is emitted (okf-cli.py:568, SCO03) — agent can't tell a title hit from a body hit.

**Acceptance:**
- WHEN `find <q> --breakdown` runs, THE CLI SHALL emit per-hit which field(s) (title/tags/body) and which term(s) contributed to the score.
- WHEN `--breakdown` is absent, THE output SHALL be byte-identical to today's format.

- [ ] **Step 1:** Failing test `test_find_breakdown_lists_contributing_fields`.
- [ ] **Step 2:** Verify fail.
- [ ] **Step 3:** Accumulate a per-hit `contrib` dict during the scoring loop (okf-cli.py:553-556); print it under `--breakdown`.
- [ ] **Step 4:** Test → PASS. **Step 5:** hold commit.

### 8c — Semantic backstop (D04, the core lever)

**Design keyed on Task 7's finding.** Keyword runs first; if the top keyword score-ratio is below a threshold (constant `SEMANTIC_FALLBACK_RATIO`, e.g. 0.5) OR zero hits, run the semantic pass: embed the query with the same model family as the cache, cosine-rank against `.tagvec` tag vectors, map matched tags → concepts, fuse into the result list (keyword hits keep priority; semantic hits appended/interleaved with a marked provenance). **If Task 7 found tag-embeddings insufficient for body-only fixtures (S3 paraphrase), 8c extends the offline producer to also embed titles/bodies and reads those** — that scope call is Task 7's recorded finding, not guessed here.

**Runtime dependency guard:** query-embedding needs a model call. To honor no-runtime-deps + graceful degradation: the semantic pass is **best-effort** — if no embedding backend is reachable (no Ollama/API), `find` logs a one-line stderr note and returns keyword-only results. The cache read itself is pure stdlib sqlite3.

**Acceptance:**
- WHEN a paraphrase query (keyword zero-hit, per baseline) is issued for fixture S3 AND an embedding backend is available, THE CLI SHALL surface the expected concept within top-5 (the delta WS1 must produce vs. baseline zero-hit).
- WHEN the `.tagvec` cache OR the embedding backend is absent, THE CLI SHALL return keyword-only results without error (graceful degradation).
- THE semantic pass SHALL run only as a backstop (below-threshold/zero keyword), never replacing a strong keyword top-hit (S1 literal stays Top-1).

- [ ] **Step 1:** Failing test `test_semantic_fallback_rescues_paraphrase` (skipped/xfail-guarded when no backend; asserts graceful keyword-only path when cache removed).
- [ ] **Step 2:** Verify fail.
- [ ] **Step 3:** Implement the sqlite3 cache reader, cosine ranking, tag→concept mapping, threshold-gated fusion in `cmd_find`; guard all model/network access behind availability checks.
- [ ] **Step 4:** Test → PASS.
- [ ] **Step 5: Commit the whole Task 8** — `git add cli/okf-cli.py mcp/okf_mcp.py cli/test_okf_cli.py && git commit -m "feat(cli): hybrid find — semantic backstop, filters, score breakdown"`

---

## Task 10: MCP parity — register `okf_tags` (T02, D05)

**Grounded (RET12, D05):** MCP already exposes find/read/toc/index/list/check/reindex/refs/rename (okf_mcp.py:65-115). Of the D05 candidates check/tags/refs, **check (okf_mcp.py:91-94) + refs (okf_mcp.py:101-104) are already registered** — the only real agent-relevant gap is `tags` (CLI-only, okf-cli.py:1939-1948). Write/admin verbs (merge-tags, normalize-tags, fix-*, rename-writes, log, visualize, prime, info) stay CLI-only by intent (documented in Task 14).

**Files:**
- Modify: `mcp/okf_mcp.py:7-17` (`_COMMANDS`) + `:65-115` (register tool)
- Test: `cli/test_okf_mcp.py`

**Acceptance:**
- THE MCP surface SHALL expose `okf_tags(root, query="", limit=8)` returning the CLI `tags` output (fuzzy candidate search or full audit dump).
- Write/admin verbs SHALL remain unregistered (parity is deliberate-subset, not 20/20).

- [ ] **Step 1:** Failing subprocess test `test_okf_tags_registered_and_runs`.
- [ ] **Step 2:** Verify fail. **Step 3:** add `"tags": (["query"], False)` to `_COMMANDS` (note `query` is `nargs="*"` — marshal a possibly-empty list; simplest: pass a single joined string or omit when empty) and register the `okf_tags` tool.
- [ ] **Step 4:** Test → PASS. **Step 5:** `git commit -m "feat(mcp): expose okf_tags to close agent-relevant parity gap"`

---

## Task 11: Root-safety — stop defaulting to the script dir (T03)

**Grounded (RET/REFERENCES, okf-cli.py:72-73):** `catalogue_root(explicit)` returns `os.path.dirname(__file__)` (the `cli/` dir) when no `--root` — a silent wrong root. `list_bundles` would then scan `cli/` as if it were a catalogue.

**Files:**
- Modify: `cli/okf-cli.py:72-73` (`catalogue_root`) + `:1981-1984` (root validation)
- Test: `cli/test_okf_cli.py`

**Acceptance:**
- WHEN no `--root` is passed AND no catalogue is auto-detectable, THE CLI SHALL hard-fail with a clear message naming `--root` (never silently scan the script dir).
- WHEN `--root` is passed, THE behavior SHALL be unchanged.
- Auto-detect: if the cwd (or an ancestor) contains catalogue markers (`SPEC.md` + `TYPES.md` at root, or a `.okf.toml`), use it; else fail.

- [ ] **Step 1:** Failing test `test_no_root_no_catalogue_hard_fails` (asserts `SystemExit`, message mentions `--root`).
- [ ] **Step 2:** Verify fail (current code silently returns the script dir).
- [ ] **Step 3:** Rewrite `catalogue_root` to: `explicit` → abspath; else walk cwd upward for a catalogue marker; else `None`. At okf-cli.py:1981-1984, if `None` → `sys.exit("ERROR: no catalogue found; pass --root <path>")`.
- [ ] **Step 4:** Test → PASS (and existing `--root` tests still green).
- [ ] **Step 5:** `git commit -m "fix(cli): fail on missing root instead of scanning script dir"`

---

# PHASE 3 — Test-Coordinator: Success Gate (own beans)

## Task 12: Re-measure + regression gate (own bean)

**The success proof (D09).** Re-run Modus A against the same seeded fixtures, diff against the frozen baseline (Task 5), assert the WS1 direction: zero-hit-rate (paraphrase) ↓↓, Recall@k / MRR ↑, no regression on literal S1.

**Files:**
- Create: `cli/eval/results/hybrid-<rev>.json`
- Create: `cli/eval/gate.py` — loads baseline + hybrid result, prints per-metric/per-scenario delta table, exits non-zero if any guard metric regressed.

**Acceptance:**
- THE gate SHALL compute per-metric delta (baseline vs hybrid) across all eight metrics — including `location_correct_rate` (S2) and `metadata_hit_rate` (Ziel-3) — and per-scenario delta (S1–S4 × literal/paraphrase).
- THE gate SHALL FAIL (exit non-zero) if paraphrase zero-hit-rate did not decrease OR if any literal S1 recall regressed.
- THE re-measurement SHALL write a NEW result file (baseline immutability, Global Constraints).

- [ ] **Step 1:** Seed fixtures, run `runner.py --out results/hybrid-<rev>.json`.
- [ ] **Step 2:** Write `gate.py`, produce the delta table, assert direction.
- [ ] **Step 3:** Teardown fixtures.
- [ ] **Step 4:** Commit results + gate — `git commit -m "feat(eval): regression gate — hybrid vs frozen baseline"`
- [ ] **Step 5:** Report the delta table to the PO (this is the maturity proof).

---

## Task 13: Modus B — agentic realism check (own bean, SEPARATE session)

**D12/Q07:** NOT the implementer. This bean is executed by a **separate agentic session** during the test phase: a test-agent is given only the okf MCP tools + a natural task ("find the runbook for X") and success is measured end-to-end (query formulation included). Non-deterministic → sanity signal, never a gate metric.

**Files:**
- Create: `cli/eval/modus-b-tasks.md` — the task prompts + success criteria for the test-agent session.

**Acceptance:**
- THE bean SHALL be tagged for execution in a separate agentic session (not `ce-implementer`).
- THE task set SHALL cover ≥1 paraphrase-style retrieval per scenario S1–S4 and record agent success/failure as qualitative sanity, explicitly excluded from the gate metric.

- [ ] **Step 1:** Author `modus-b-tasks.md` (task prompts + rubric).
- [ ] **Step 2:** Commit — `git commit -m "docs(eval): Modus B agentic realism task set"`
- [ ] **Step 3:** (Separate session) run the agentic check, record outcomes.

---

# PHASE 4 — Documentation (trailing, mirrors end-state)

## Task 14: De-stale the canonical overview (T04, D07)

**Grounded (REFERENCES:18-19):** `Knowledge-Catalogue/okf-meta-wiki/okf-cli-mcp-overview.md` (Stand 2026-07-12) lists 18 of 20 verbs (missing `prime`, `remove-tags`) and claims "100%". D07: keep it canonical, de-stale it — do not replace with pure `--help` generation.

**Files:**
- Modify: `Knowledge-Catalogue/okf-meta-wiki/okf-cli-mcp-overview.md` — **via `/okf`** (it is an OKF concept; never hand-edit).

**Acceptance:**
- THE overview SHALL list all 20 verbs (add `prime`, `remove-tags`), remove the "100%" claim, and reflect the new MCP surface (`okf_tags`) + `find` filters/breakdown/semantic backstop shipped in Phase 2.
- Hand-written prose/narrative SHALL be preserved (D07).

- [ ] **Step 1:** Re-read the current overview; enumerate drift vs shipped verbs.
- [ ] **Step 2:** Update via `/okf` (ingest/migrate path), covering the 20-verb table + new `find`/`okf_tags` capabilities.
- [ ] **Step 3:** Commit in the catalogue repo — `git commit -m "docs(okf): de-stale cli/mcp overview to 20 verbs"`

## Task 15 (optional, gated Q04): Partial `--help`-derived verb tables (T05, D07)

**Only if PO wants it.** Generate the verb *tables* from `argparse --help`; keep prose hand-maintained. If PO downscopes, drop this task.

**Acceptance:**
- WHEN run, THE generator SHALL emit the verb/flag table from `argparse` metadata; the narrative sections SHALL remain hand-authored (not overwritten).

- [ ] **Step 1:** Decide with PO (Q04). If yes: build a small generator that walks the argparse subparsers and emits a markdown table; splice into the overview between markers.
- [ ] **Step 2:** Commit.

---

## Self-Review

**Spec coverage (DESIGN.md phases → tasks):**
- Phase 1 Grundlagen-A: T11 fixtures → Task 2; golden-file authoring → Task 3; T10 eval-runner → Task 4; T12 freeze → Task 5; T01 B01 → Task 1; T09 integ-tests → Task 6. ✅
- Note (Q01): Think-collection TASKS.md skips T07 (IDs jump T06→T08); no plan task is missing as a result — QUESTIONS.md:9 references "T07/T09" but only T09 exists. Provenance quirk in the Think session, flagged not blocking.
- Phase 2 Grundlagen-B: T08 provenance → Task 7; WS1 hybrid (fallback+FIL03/04+SCO03) → Task 8; T02 parity → Task 10; T03 root-safety → Task 11. ✅
- Phase 3 Test-Coordinator: re-eval+gate → Task 12 (own bean); Modus B → Task 13 (own bean, separate session). ✅
- Phase 4 Docs: T04 → Task 14; T05 → Task 15 (optional). ✅
- Baseline frozen BEFORE WS1 (D09): Task 5 is a hard gate before all Phase 2. ✅
- Q06 seeded-in-catalogue (D11): Tasks 2/5 seed+teardown+pinned rev. ✅
- Q07 A-by-implementer / B-separate (D12): Tasks 4/12 implementer; Task 13 separate session. ✅

**Placeholder scan:** semantic-backstop code (8c) is design-level, not literal — deliberately, because its exact surface (tag-only vs body embeddings) is gated on Task 7's recorded finding. This is a real dependency, not a placeholder: Task 7 produces the decision, Task 8c documents both branches. No "TBD"/"handle edge cases" left.

**Type consistency:** `seed()/teardown()` (Task 2) ↔ used in Tasks 4/5/12. `run()` result shape (Task 4) ↔ consumed by `gate.py` (Task 12). `SEED_TOKEN`/`FIXTURES` (Task 2) ↔ golden.json (Task 3). `--json` shapes (Task 1) ↔ subprocess tests (Task 6). `find` filter params (Task 8) ↔ `okf_find` MCP params (Task 8). Consistent. ✅
