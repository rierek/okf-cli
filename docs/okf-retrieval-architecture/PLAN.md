# okf-cli Retrieval Architecture — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the measured target architecture of `DESIGN.md` — an FTS5/BM25 lexical arm and a `voyage-3-large` document-embedding semantic arm, fused by *conditional handover* instead of score blending — so that `okf-cli find` stops failing on paraphrase queries (today: 1 hit in 48, R42).

**Architecture:** Two independent ranking arms plus a per-query decision about **which arm owns the ranking**. The lexical arm is a persistent FTS5 index (`<root>/.fts/fts.sqlite`, porter + unicode61 + prefix, BM25 field weights title 3 / tags 2 / body 1). The semantic arm is one `voyage-3-large` vector per concept over `title+body`, stored in the existing `concept_emb` table of `<root>/.tagvec/tag_vectors.sqlite`. Fusion: the lexical arm owns the ranking only when its top-1 has a clear margin over the runner-up; otherwise the semantic arm owns it and the lexical hits are appended behind — never in front. Both artefacts are optional: absent or unusable, `find` degrades down the chain (FTS → substring scan; voyage → lexical only) with one stderr note, never a hard fail.

**Tech Stack:** Python 3 stdlib only in `cli/okf-cli.py` (`sqlite3` incl. FTS5, `urllib.request`, `struct`, `math`). `unittest` for tests. Voyage AI HTTP API and Ollama only inside the offline producer `cli/embeddings/build_tagvec.py` and in the *query* path of `find` (voyage only, guarded by the degradation chain). No numpy, no third-party client anywhere in `cli/`.

## Global Constraints

- **No new runtime dependencies in `cli/okf-cli.py`.** Single-file, dependency-free tool. Reads use stdlib `sqlite3`; production stays offline. Verbatim from the predecessor plan and unchanged (D15).
- **Never hard-fail on a missing or unusable artefact.** Missing/corrupt `.fts` → substring scan + one stderr note. Missing `concept_emb`, missing `VOYAGE_API_KEY`, unreachable API → lexical only + one stderr note. This is the standing graceful-skip rule (R05) and the explicit condition attached to D13.
- **Semantic model is `voyage-3-large`, embedding unit is `title + "\n\n" + body`** (D13, D11). `bge-m3` is NOT a runtime fallback (D16) — the query path knows exactly one model.
- **Artifact language English** — all git commit subjects/bodies, bean titles/bodies, and code comments in English (global CLAUDE.md). Chat with the PO stays German.
- **Commits:** `<type>(<scope>): <subject>`, subject max 50 characters, no `Co-Authored-By` trailer (hook-enforced E1/E2). Commit after every task. Explicit paths in `git add` — a parallel session may own other files in this worktree.
- **Branch:** work directly on `main` (repo worktree switch: main-direct allowed, solo repo — `docs/CLAUDE.md` "Worktree-Weiche").
- **Test baseline:** `python3 -m unittest discover -s cli -p 'test_*.py' -v` from the repo root. 187 tests today with **exactly 19 failures / 2 errors**, all pre-existing in the crosslink suites and verified as such before the repo extraction. A task is done only when the failure count is still exactly 19F/2E — every new failure is yours.
- **Live catalogue root:** `~/Obsidian/Knowledge-Catalogue` (2437 concepts, 2581 `.md` files). It is a **separate git repo** — never commit in it from this plan; report intended changes to the PO instead.
- **No network at import time and none under test.** `cli/test_embeddings_tagvec.py` is network-free by construction; keep it that way by injecting fakes, never by reaching out.

## Decisions this plan implements

| Dxx | Decision | Source |
|-----|----------|--------|
| D11 | Document embedding (`title+body`), not chunking, not title-only | DECISIONS.md |
| D12 | Fusion rule = conditional handover | DECISIONS.md |
| D13 | `voyage-3-large` is the productive semantic model | DECISIONS.md |
| D14 | FTS5 lexical arm and conditional handover ship together — R43's 0.437 was measured with FTS5 as the lexical arm (`eval/hybrid_eval.py:139-159`), never with the substring scorer | this plan, PO 2026-07-26 |
| D15 | `.fts/fts.sqlite` and `.tagvec` are persistent but optional artefacts; absent/stale → degradation with an stderr note, never a hard fail | this plan, PO 2026-07-26 (closes Q09) |
| D16 | Query-side degradation is two-stage (voyage → lexical). `concept_emb` holds voyage rows only | this plan, PO 2026-07-26 |
| D17 | Scope = core (T10/T11/T12/T13 + fill + gate) **plus** T03, T05, T07. T05 ships flag-gated until measured | this plan, PO 2026-07-26 |

## Findings this plan fixes (discovered while grounding)

| Code | Severity | Finding | Location |
|------|----------|---------|----------|
| B01 | high | `tokenize()` splits on `[^a-z0-9]+`, so every umlaut splits a German word (`qualitätsmanagement` → `qualit`, `tsmanagement`). The measured FTS arm used `[^\wäöüÄÖÜß]+` (`eval/fts_arm.py:56`) — without this fix the shipped lexical arm is not the measured one | `cli/okf-cli.py:598-599` |
| B02 | high | `embed_voyage()` sends **every** text in one request and `main()` writes rows only after the whole model pass returns — a 2437-concept run is structurally undoable (this is LL-08 in the field) | `cli/embeddings/build_tagvec.py:223-245, 343-351` |
| B03 | medium | `embed_bge_m3()` loops one HTTP call per text although `/api/embed` accepts a list — measured 10–35× slower (LL-09) | `cli/embeddings/build_tagvec.py:208-220` |
| I01 | low | `docs/CLAUDE.md:12` mandates `plans/<beans-id>-<slug>/`, while the governing `/tools/CLAUDE.md` forbids a separate `/plans/` and requires the plan to live beside its think collection. Global wins; the local file must be corrected | `docs/CLAUDE.md:12` |

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `cli/okf-cli.py` | The whole runtime. New lexical-index section (build + query + staleness), rewritten semantic section (voyage), rewritten `cmd_find` fusion, `build-index` subcommand | Modify |
| `cli/embeddings/build_tagvec.py` | Offline producer. Batching, resilience, incremental writes | Modify |
| `cli/test_okf_cli.py` | Unit tests for tokenize, FTS index, fusion, degradation, zero-hit output | Modify |
| `cli/test_embeddings_tagvec.py` | Unit tests for batching/resilience — network-free | Modify |
| `cli/eval/runner.py` | Fixture eval runner. Must build the FTS index before scoring, else it measures the fallback path | Modify |
| `docs/okf-retrieval-architecture/eval/remeasure.py` | New: re-measures the **shipped** `okf-cli find` against `queries_v2.json + queries_real.json` on the live catalogue | Create |
| `docs/okf-retrieval-architecture/eval/taxonomy.md` | New: T03 failure taxonomy of the remaining zero-hits | Create |
| `cli/embeddings/README.md` | Producer contract documentation | Modify |
| `docs/okf-retrieval-architecture/{DECISIONS,QUESTIONS,TASKS,REFERENCES}.md` | Think collection kept truthful about what shipped | Modify |
| `docs/CLAUDE.md` | I01 fix | Modify |

The runtime stays a single file. `cli/okf-cli.py` is 2333 lines and organised as flat sections; follow that — do **not** introduce a package or a new runtime module. The producer stays a separate offline script, as today.

---

### Task 1: Producer batching (T11, fixes B02/B03)

**Files:**
- Modify: `cli/embeddings/build_tagvec.py:208-220` (`embed_bge_m3`), `:223-245` (`embed_voyage`), `:299-355` (`main`)
- Test: `cli/test_embeddings_tagvec.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `batches(items, max_items, max_chars)` → generator of lists; `BATCH_LIMITS: dict[str, tuple[int, int]]` mapping model name to `(max_items, max_chars)`. `embed_bge_m3(texts: list[str]) -> list[list[float]]` and `embed_voyage(texts: list[str]) -> list[list[float]]` keep their signatures — only their internals and their callers change.

- [ ] **Step 1: Write the failing tests**

Add to `cli/test_embeddings_tagvec.py`:

```python
class Batches(unittest.TestCase):
    """T11 — a 2437-concept run must be cut into API-sized pieces, by item
    count AND by payload size (Voyage caps a request by token budget, not by
    document count)."""

    def test_splits_by_item_count(self):
        items = [("p{}".format(i), "text", "k{}".format(i)) for i in range(5)]
        got = list(bt.batches(items, max_items=2, max_chars=10 ** 6))
        self.assertEqual([len(b) for b in got], [2, 2, 1])

    def test_splits_by_char_budget(self):
        items = [("p{}".format(i), "x" * 40, "k{}".format(i)) for i in range(4)]
        got = list(bt.batches(items, max_items=100, max_chars=100))
        self.assertEqual([len(b) for b in got], [2, 2])

    def test_single_oversized_item_is_not_dropped(self):
        items = [("p0", "x" * 500, "k0")]
        got = list(bt.batches(items, max_items=100, max_chars=100))
        self.assertEqual(len(got), 1)
        self.assertEqual(len(got[0]), 1)

    def test_empty_input_yields_nothing(self):
        self.assertEqual(list(bt.batches([], max_items=10, max_chars=100)), [])


class BgeBatchPayload(unittest.TestCase):
    """B03 — /api/embed accepts a list; one call per text was measured 10-35x
    slower (LL-09). Network is faked: this test must never touch Ollama."""

    def test_sends_all_texts_in_one_request(self):
        calls = []

        class _Resp:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

            def read(self_inner):
                return json.dumps(
                    {"embeddings": [[0.1], [0.2], [0.3]]}).encode("utf-8")

        def _fake_urlopen(req, timeout=None):
            calls.append(json.loads(req.data.decode("utf-8")))
            return _Resp()

        orig = bt.urllib.request.urlopen
        bt.urllib.request.urlopen = _fake_urlopen
        try:
            vecs = bt.embed_bge_m3(["a", "b", "c"])
        finally:
            bt.urllib.request.urlopen = orig

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["input"], ["a", "b", "c"])
        self.assertEqual(vecs, [[0.1], [0.2], [0.3]])
```

Add `import json` to the test module's imports if it is not already there.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest cli.test_embeddings_tagvec -v`
Expected: FAIL — `AttributeError: module 'build_tagvec' has no attribute 'batches'`, and `BgeBatchPayload` fails with 3 recorded calls instead of 1.

- [ ] **Step 3: Implement batching**

In `cli/embeddings/build_tagvec.py`, add below `MODELS` (line 61):

```python
# T11 (LL-09) — batch limits per model: (max items per request, max payload
# chars per request). Voyage caps a request by token budget, so the char
# budget is the binding one there; Ollama has no documented list cap, but a
# smaller batch keeps a single failure cheap to retry.
BATCH_LIMITS = {
    "bge-m3": (32, 90000),
    "voyage-3-large": (128, 90000),
}
```

Add next to the other pure helpers (below `plan_concept_delta`, line 190):

```python
def batches(items, max_items, max_chars):
    """Cut `items` — (identity, text, key) triples — into request-sized
    pieces, bounded by BOTH item count and total text length. A single item
    that alone exceeds max_chars is still yielded (truncation is the embed
    layer's job, dropping it would leave a concept unfindable)."""
    cur, chars = [], 0
    for item in items:
        if cur and (len(cur) >= max_items or chars + len(item[1]) > max_chars):
            yield cur
            cur, chars = [], 0
        cur.append(item)
        chars += len(item[1])
    if cur:
        yield cur
```

Replace `embed_bge_m3` (lines 208-220) with:

```python
def embed_bge_m3(texts):
    """Local Ollama bge-m3 embed call. NETWORK — only reached under --produce.
    /api/embed takes a LIST; the former one-call-per-text loop measured 10-35x
    slower on the same hardware (LL-09)."""
    req = urllib.request.Request(
        MODELS["bge-m3"]["endpoint"],
        data=json.dumps({"model": "bge-m3", "input": list(texts)}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["embeddings"]
```

- [ ] **Step 4: Wire the callers to batch and write incrementally**

In `main()`, replace the tag production block (lines 326-334) with:

```python
            if args.produce and delta:
                max_items, max_chars = BATCH_LIMITS[model]
                written = 0
                for batch in batches(
                        [(tag, text, key) for tag, text, key in delta],
                        max_items, max_chars):
                    vectors = _embed(model, [t for _tag, t, _key in batch])
                    rows = [
                        (key, tag, model, MODELS[model]["dim"], pack_vec(vec))
                        for (tag, _text, key), vec in zip(batch, vectors)
                    ]
                    write_rows(output, rows)
                    written += len(rows)
                    print("{}: wrote {}/{} tag row(s)".format(
                        model, written, len(delta)), flush=True)
```

and the concept production block (lines 343-351) with:

```python
            if args.produce and cdelta:
                max_items, max_chars = BATCH_LIMITS[model]
                written = 0
                for batch in batches(cdelta, max_items, max_chars):
                    vectors = _embed(model, [t for _path, t, _key in batch])
                    rows = [
                        (key, path, model, MODELS[model]["dim"], pack_vec(vec))
                        for (path, _text, key), vec in zip(batch, vectors)
                    ]
                    write_concept_rows(output, rows)
                    written += len(rows)
                    print("{}: wrote {}/{} concept row(s)".format(
                        model, written, len(cdelta)), flush=True)
```

Writing per batch is the point: an interrupted run keeps everything already embedded, and the next invocation's delta plan (`plan_concept_delta`, line 170) skips it automatically.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m unittest cli.test_embeddings_tagvec -v`
Expected: PASS, all tests in the module.

Run: `python3 -m unittest discover -s cli -p 'test_*.py' 2>&1 | tail -5`
Expected: still exactly 19 failures, 2 errors.

- [ ] **Step 6: Verify the dry-run stays offline**

Run: `python3 cli/embeddings/build_tagvec.py --root ~/Obsidian/Knowledge-Catalogue --target concepts --model voyage-3-large`
Expected: prints `voyage-3-large: 2437 concept(s) need title+body embedding` and `(dry-run — no network calls, no writes.)`. No traffic, no writes.

- [ ] **Step 7: Commit**

```bash
git add cli/embeddings/build_tagvec.py cli/test_embeddings_tagvec.py
git commit -m "perf(embeddings): batch embed calls, write per batch"
```

---

### Task 2: Producer resilience (T10, fixes LL-08)

**Files:**
- Modify: `cli/embeddings/build_tagvec.py` (add `embed_resilient`, call it from both production blocks)
- Test: `cli/test_embeddings_tagvec.py`

**Interfaces:**
- Consumes: `batches()` and `BATCH_LIMITS` from Task 1.
- Produces: `embed_resilient(fn, texts, label, sleep=time.sleep) -> list[list[float]] | None` — returns `None` when a batch is unrecoverable, which the caller treats as "skip this batch and keep going", never as an abort.

- [ ] **Step 1: Write the failing tests**

Add to `cli/test_embeddings_tagvec.py`:

```python
class EmbedResilient(unittest.TestCase):
    """T10/LL-08 — a single HTTP failure must not throw away a 2437-concept
    pass. Retry with backoff, then halve the inputs (a 400 on these endpoints
    is usually an over-long text), then skip with a log line."""

    def test_returns_vectors_when_first_attempt_succeeds(self):
        got = bt.embed_resilient(lambda ts: [[1.0]] * len(ts), ["a", "b"],
                                 "batch-1", sleep=lambda _s: None)
        self.assertEqual(got, [[1.0], [1.0]])

    def test_retries_then_succeeds(self):
        state = {"n": 0}

        def _flaky(texts):
            state["n"] += 1
            if state["n"] < 2:
                raise RuntimeError("HTTP 400")
            return [[2.0]] * len(texts)

        got = bt.embed_resilient(_flaky, ["a"], "batch-1", sleep=lambda _s: None)
        self.assertEqual(got, [[2.0]])
        self.assertEqual(state["n"], 2)

    def test_halves_texts_before_the_last_attempt(self):
        seen = []

        def _record(texts):
            seen.append([len(t) for t in texts])
            raise RuntimeError("HTTP 400")

        bt.embed_resilient(_record, ["x" * 4000], "batch-1", sleep=lambda _s: None)
        self.assertEqual(seen[0], [4000])
        self.assertLess(seen[-1][0], 4000)

    def test_returns_none_after_exhausting_attempts(self):
        def _always_fails(texts):
            raise RuntimeError("HTTP 500")

        got = bt.embed_resilient(_always_fails, ["a"], "batch-1",
                                 sleep=lambda _s: None)
        self.assertIsNone(got)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest cli.test_embeddings_tagvec.EmbedResilient -v`
Expected: FAIL — `AttributeError: module 'build_tagvec' has no attribute 'embed_resilient'`.

- [ ] **Step 3: Implement `embed_resilient`**

Add `import time` to the imports of `cli/embeddings/build_tagvec.py` (line 37-45 block), then add below `batches()`:

```python
def embed_resilient(fn, texts, label, sleep=time.sleep):
    """Vectors for `texts`, or None when the batch is unrecoverable.

    LL-08: an unguarded arm died on a single plain HTTP 400 and threw away
    ~550 already-embedded concepts. The guarded run logged 4 retries and
    completed 2437/2437 (R31). Strategy: retry with exponential backoff, then
    progressively halve every text (a 400 on these endpoints is usually an
    over-long input), then give up on THIS batch only and report it — the run
    continues, and the missing rows simply reappear in the next delta plan.

    `sleep` is injected so tests exercise the retry ladder without waiting."""
    delay = 2
    for attempt in range(3):
        try:
            return fn(texts)
        except Exception as exc:
            print("    retry {} ({} texts) {}: {}".format(
                attempt + 1, len(texts), label, exc), flush=True)
            sleep(delay)
            delay *= 2
            if attempt >= 1:
                texts = [t[: max(len(t) // 2, 500)] for t in texts]
    print("    SKIPPED {} — {} text(s) left unembedded".format(label, len(texts)),
          flush=True)
    return None
```

- [ ] **Step 4: Route both production blocks through it**

In `main()`, in the tag block from Task 1 replace

```python
                    vectors = _embed(model, [t for _tag, t, _key in batch])
```

with

```python
                    vectors = embed_resilient(
                        lambda ts, m=model: _embed(m, ts),
                        [t for _tag, t, _key in batch],
                        "{} tags {}..".format(model, batch[0][0]))
                    if vectors is None:
                        continue
```

and in the concept block replace

```python
                    vectors = _embed(model, [t for _path, t, _key in batch])
```

with

```python
                    vectors = embed_resilient(
                        lambda ts, m=model: _embed(m, ts),
                        [t for _path, t, _key in batch],
                        "{} concepts {}..".format(model, batch[0][0]))
                    if vectors is None:
                        continue
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m unittest cli.test_embeddings_tagvec -v`
Expected: PASS.

Run: `python3 -m unittest discover -s cli -p 'test_*.py' 2>&1 | tail -5`
Expected: still exactly 19 failures, 2 errors.

- [ ] **Step 6: Commit**

```bash
git add cli/embeddings/build_tagvec.py cli/test_embeddings_tagvec.py
git commit -m "fix(embeddings): survive batch failures, skip not abort"
```

---

### Task 3: Fill `concept_emb` on the live catalogue (D13)

**Files:**
- No repo files change. This task produces `~/Obsidian/Knowledge-Catalogue/.tagvec/tag_vectors.sqlite` rows.

**Interfaces:**
- Consumes: Tasks 1 and 2 (batching + resilience are the precondition — an unbatched run cannot complete).
- Produces: 2437 rows in `concept_emb` with `model = 'voyage-3-large'`. Every later task's semantic arm depends on them.

**This task spends money and mutates a catalogue outside this repo.** Estimated cost ~$0.71 (measured during the eval session for the same corpus). Get the PO's go-ahead in chat before Step 3 and report the outcome afterwards.

- [ ] **Step 1: Verify the starting state**

Run:
```bash
sqlite3 ~/Obsidian/Knowledge-Catalogue/.tagvec/tag_vectors.sqlite \
  "SELECT model, COUNT(*) FROM concept_emb GROUP BY model;
   SELECT model, COUNT(*) FROM emb GROUP BY model;"
```
Expected: `concept_emb` empty (R10); `emb` has ~752 `bge-m3` and ~650 `voyage-3-large` rows (R09). Record the exact numbers — the `emb` table must be unchanged at the end.

- [ ] **Step 2: Dry-run the plan**

Run:
```bash
python3 cli/embeddings/build_tagvec.py \
  --root ~/Obsidian/Knowledge-Catalogue \
  --target concepts --model voyage-3-large
```
Expected: `voyage-3-large: 2437 concept(s) need title+body embedding` plus the dry-run notice. No writes.

- [ ] **Step 3: Produce**

`VOYAGE_API_KEY` must be present in the environment. Note from the producer docstring: a context-mode sandbox does not inherit it — use a plain bash subprocess.

```bash
python3 cli/embeddings/build_tagvec.py \
  --root ~/Obsidian/Knowledge-Catalogue \
  --target concepts --model voyage-3-large --produce
```
Expected: incremental `wrote N/2437 concept row(s)` lines, retries logged if any, run completes.

- [ ] **Step 4: Verify the end state**

Run:
```bash
sqlite3 ~/Obsidian/Knowledge-Catalogue/.tagvec/tag_vectors.sqlite \
  "SELECT model, COUNT(*), MIN(dim), MAX(dim) FROM concept_emb GROUP BY model;
   SELECT model, COUNT(*) FROM emb GROUP BY model;"
```
Expected: exactly one `concept_emb` group, `voyage-3-large`, count 2437, dim 1024/1024. `emb` counts identical to Step 1 — the tag scope must be untouched.

If the count is below 2437, re-run Step 3: the delta plan embeds only what is missing, so a partial run is resumable by construction.

- [ ] **Step 5: Report, do not commit**

Nothing to commit in this repo. Report to the PO: rows written, retries logged, actual cost if visible in the Voyage dashboard.

---

### Task 4: Unicode-aware tokenizer (fixes B01)

**Files:**
- Modify: `cli/okf-cli.py:598-599`
- Test: `cli/test_okf_cli.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `tokenize(s: str) -> list[str]` — unchanged signature, now keeping non-ASCII letters inside a token. Every later task's lexical query terms come from here.

- [ ] **Step 1: Write the failing test**

Add to `cli/test_okf_cli.py` (near the other pure-helper tests):

```python
class TokenizeUnicode(unittest.TestCase):
    """B01 — the catalogue is German. Splitting on [^a-z0-9]+ tore every
    umlaut word in two ('qualitätsmanagement' -> 'qualit', 'tsmanagement'),
    which silently changed what the lexical arm searches for. The measured
    FTS arm tokenized on word characters (eval/fts_arm.py:56); the shipped
    one must match it or it is not the arm that was measured."""

    def test_umlaut_word_stays_one_token(self):
        self.assertEqual(okf.tokenize("Qualitätsmanagement"),
                         ["qualitätsmanagement"])

    def test_sharp_s_stays_one_token(self):
        self.assertEqual(okf.tokenize("Straßenbahn"), ["straßenbahn"])

    def test_punctuation_still_separates(self):
        self.assertEqual(okf.tokenize("mockup, tailscale!"),
                         ["mockup", "tailscale"])

    def test_underscore_still_separates(self):
        self.assertEqual(okf.tokenize("build_tagvec"), ["build", "tagvec"])

    def test_digits_survive(self):
        self.assertEqual(okf.tokenize("bge-m3 2437"), ["bge", "m3", "2437"])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest cli.test_okf_cli.TokenizeUnicode -v`
Expected: FAIL — `['qualit', 'tsmanagement'] != ['qualitätsmanagement']`.

- [ ] **Step 3: Implement**

Replace `cli/okf-cli.py:598-599` with:

```python
def tokenize(s):
    """Lowercased word tokens. `\\w` is Unicode-aware in Python 3, so umlauts
    and ß stay inside their token (B01); `_` is kept as a separator, matching
    the previous behaviour for identifiers like build_tagvec."""
    return [t for t in re.split(r"[\W_]+", s.lower(), flags=re.UNICODE) if t]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest cli.test_okf_cli.TokenizeUnicode -v`
Expected: PASS.

Run: `python3 -m unittest discover -s cli -p 'test_*.py' 2>&1 | tail -5`
Expected: still exactly 19 failures, 2 errors. If a *different* test now fails, it was asserting the old broken split — read it, and fix the assertion only if it was encoding the bug.

- [ ] **Step 5: Commit**

```bash
git add cli/okf-cli.py cli/test_okf_cli.py
git commit -m "fix(cli): tokenize unicode words, not just ascii"
```

---

### Task 5: FTS5 index — build and `build-index` command (T13 part 1)

**Files:**
- Modify: `cli/okf-cli.py` — add a lexical-index section directly above the semantic section (before line 647), add the subparser next to `reindex` (around line 2261), add the dispatch entry (around line 2321)
- Test: `cli/test_okf_cli.py`

**Interfaces:**
- Consumes: `tokenize()` from Task 4; existing `list_bundles(root)`, `iter_concepts(bundle_path)`, `read_file(ap)`, `split_frontmatter(text)`, `extract_tags(text)`, `_dequote(s)`.
- Produces:
  - `FTS_DIRNAME = ".fts"`, `FTS_FILENAME = "fts.sqlite"`, `FTS_TOKENIZER`, `FTS_BM25_WEIGHTS`
  - `_fts_db_path(root) -> str`
  - `build_fts_index(root, db_path=None) -> tuple[int, str]` returning `(n_concepts, db_path)`
  - `_fts_index_stale(root, conn) -> bool`
  - `cmd_build_index(root, args) -> None`

- [ ] **Step 1: Write the failing tests**

Add to `cli/test_okf_cli.py`. Reuse whatever temp-catalogue helper the module already provides; if none fits, this self-contained one works:

```python
class FtsIndexBuild(unittest.TestCase):
    """D15 — the lexical index is a persistent artefact under <root>/.fts/."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "b"))
        with open(os.path.join(self.root, "b", "one.md"), "w",
                  encoding="utf-8") as f:
            f.write("---\ntype: Runbook\ntitle: Serve Excalidraw drafts\n"
                    "description: d\ntags: [excalidraw, tailscale]\n---\n"
                    "Render the drawing to PNG and expose it over the tunnel.\n")
        with open(os.path.join(self.root, "b", "two.md"), "w",
                  encoding="utf-8") as f:
            f.write("---\ntype: Konzept\ntitle: Qualitätsmanagement\n"
                    "description: d\ntags: [qm]\n---\nProzesse und Audits.\n")
        with open(os.path.join(self.root, "b", "index.md"), "w",
                  encoding="utf-8") as f:
            f.write("# B\n")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_build_creates_the_artefact_and_counts_concepts(self):
        n, db = okf.build_fts_index(self.root)
        self.assertEqual(n, 2)
        self.assertTrue(os.path.isfile(db))
        self.assertEqual(db, os.path.join(self.root, ".fts", "fts.sqlite"))

    def test_index_holds_path_type_and_tags(self):
        okf.build_fts_index(self.root)
        conn = sqlite3.connect(okf._fts_db_path(self.root))
        rows = dict(conn.execute("SELECT path, ctype FROM docs").fetchall())
        conn.close()
        self.assertEqual(rows, {"b/one": "Runbook", "b/two": "Konzept"})

    def test_rebuild_is_idempotent(self):
        okf.build_fts_index(self.root)
        n, _db = okf.build_fts_index(self.root)
        self.assertEqual(n, 2)
        conn = sqlite3.connect(okf._fts_db_path(self.root))
        total = conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
        conn.close()
        self.assertEqual(total, 2)

    def test_fresh_index_is_not_stale(self):
        okf.build_fts_index(self.root)
        conn = sqlite3.connect(okf._fts_db_path(self.root))
        try:
            self.assertFalse(okf._fts_index_stale(self.root, conn))
        finally:
            conn.close()

    def test_new_concept_makes_the_index_stale(self):
        okf.build_fts_index(self.root)
        with open(os.path.join(self.root, "b", "three.md"), "w",
                  encoding="utf-8") as f:
            f.write("---\ntype: Konzept\ntitle: Three\ndescription: d\n"
                    "tags: []\n---\nbody\n")
        conn = sqlite3.connect(okf._fts_db_path(self.root))
        try:
            self.assertTrue(okf._fts_index_stale(self.root, conn))
        finally:
            conn.close()
```

**Import convention — a deliberate departure.** `cli/test_okf_cli.py` imports only `importlib.util`, `os` and `unittest` at module level today; every other test imports `tempfile`/`shutil` locally inside the method that needs them (e.g. `cli/test_okf_cli.py:1372-1374`). The new suites in Tasks 5, 6, 7 and 11 need `tempfile`, `shutil`, `sqlite3`, `struct` and `json` across many methods. Add those five at module top level once and accept the style break — repeating five local imports in ~25 methods is worse. Do it here, in Task 5, so the later tasks find them already present.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest cli.test_okf_cli.FtsIndexBuild -v`
Expected: FAIL — `AttributeError: module 'okf_cli' has no attribute 'build_fts_index'`.

- [ ] **Step 3: Implement the index section**

Insert into `cli/okf-cli.py` immediately above the semantic-backstop comment block at line 647:

```python
# ── Lexical index (D14/D15) ──────────────────────────────────────────────
# FTS5 + BM25 is the lexical arm of the measured target architecture
# (DESIGN.md). The index is a PERSISTENT but OPTIONAL artefact: when it is
# absent or unusable, find falls back to the substring scan with one stderr
# note — never a hard fail (D15). Field weights title 3 / tags 2 / body 1 are
# the same ratios the substring scorer used, so the comparison isolates the
# retrieval model, not the weighting (eval/fts_arm.py:52-55).
FTS_DIRNAME = ".fts"
FTS_FILENAME = "fts.sqlite"
# unicode61 folds diacritics (a German catalogue needs ä/ö/ü to match a/o/u);
# porter stems English morphology. Measured best variant: porter + prefix
# (R32).
FTS_TOKENIZER = "porter unicode61 remove_diacritics 2"
FTS_SCHEMA = (
    "CREATE VIRTUAL TABLE docs USING fts5("
    "path UNINDEXED, ctype UNINDEXED, title, tags, body, tokenize='{}')"
).format(FTS_TOKENIZER)
FTS_META_SCHEMA = "CREATE TABLE IF NOT EXISTS fts_meta(k TEXT PRIMARY KEY, v TEXT)"
# bm25() weight per column, in declaration order: path, ctype, title, tags, body.
FTS_BM25_WEIGHTS = "0.0, 0.0, 3.0, 2.0, 1.0"


def _fts_db_path(root):
    return os.path.join(root, FTS_DIRNAME, FTS_FILENAME)


def build_fts_index(root, db_path=None):
    """(Re)build the FTS5 lexical index from the catalogue. Returns
    (n_concepts, db_path). Local I/O only — no network, stdlib sqlite3.
    Builds into a .tmp sibling and os.replace()s it, so an interrupted build
    never leaves a half-written index in place of a working one."""
    db_path = db_path or _fts_db_path(root)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    tmp = db_path + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    conn = sqlite3.connect(tmp)
    n = 0
    newest = 0.0
    try:
        conn.execute(FTS_SCHEMA)
        conn.execute(FTS_META_SCHEMA)
        for b in list_bundles(root):
            bp = os.path.join(root, b)
            for cid, ap in iter_concepts(bp):
                raw = read_file(ap)
                fm, body = split_frontmatter(raw)
                title = _dequote(fm.get("title", "")) or cid
                conn.execute(
                    "INSERT INTO docs(path, ctype, title, tags, body)"
                    " VALUES (?, ?, ?, ?, ?)",
                    ("{}/{}".format(b, cid), fm.get("type", ""), title,
                     " ".join(extract_tags(raw)), body))
                n += 1
                mt = os.path.getmtime(ap)
                if mt > newest:
                    newest = mt
        conn.executemany(
            "INSERT OR REPLACE INTO fts_meta(k, v) VALUES (?, ?)",
            [("n_concepts", str(n)), ("newest_mtime", repr(newest))])
        conn.commit()
    finally:
        conn.close()
    os.replace(tmp, db_path)
    return n, db_path


def _fts_index_stale(root, conn):
    """True when the catalogue gained/lost concepts or any concept file is
    newer than the newest one seen at build time. stat()-only — it never
    reads a concept body, which is exactly what makes it cheaper than the
    full scan it replaces. An unreadable/missing meta table counts as stale."""
    try:
        meta = dict(conn.execute("SELECT k, v FROM fts_meta").fetchall())
        n_idx = int(meta["n_concepts"])
        newest_idx = float(meta["newest_mtime"])
    except (sqlite3.DatabaseError, KeyError, ValueError, TypeError):
        return True
    n = 0
    newest = 0.0
    for b in list_bundles(root):
        for _cid, ap in iter_concepts(os.path.join(root, b)):
            n += 1
            mt = os.path.getmtime(ap)
            if mt > newest:
                newest = mt
    return n != n_idx or newest > newest_idx


def cmd_build_index(root, args):
    n, db = build_fts_index(root)
    print("indexed {} concept(s) -> {}".format(n, db))
```

- [ ] **Step 4: Register the subcommand**

Next to the `reindex` subparser (line 2261), add:

```python
    sub.add_parser("build-index",
                   help="(re)build the FTS5 lexical search index at "
                        "<root>/.fts/fts.sqlite (local only, no network)")
```

In the dispatch dict (`cli/okf-cli.py:2321-2328`, the `[args.cmd](root, args)` call closes it on 2328), add `"build-index": cmd_build_index,`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m unittest cli.test_okf_cli.FtsIndexBuild -v`
Expected: PASS.

Run: `python3 -m unittest discover -s cli -p 'test_*.py' 2>&1 | tail -5`
Expected: still exactly 19 failures, 2 errors.

- [ ] **Step 6: Build the live index and check the catalogue's .gitignore**

Run:
```bash
python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue build-index
grep -n "tagvec\|\.fts" ~/Obsidian/Knowledge-Catalogue/.gitignore
```
Expected: `indexed 2437 concept(s) -> …/.fts/fts.sqlite`.

If `.tagvec/` is ignored there but `.fts/` is not, the catalogue's `.gitignore` needs a `.fts/` line. **Do not commit in that repo** — report the one-line change to the PO and let them apply it.

- [ ] **Step 7: Commit**

```bash
git add cli/okf-cli.py cli/test_okf_cli.py
git commit -m "feat(cli): add fts5 lexical index + build-index"
```

---

### Task 6: `find` ranks lexically via FTS5, with degradation (T13 part 2)

**Files:**
- Modify: `cli/okf-cli.py:788-899` (`cmd_find`), plus a new `_fts_ranking()` and a shared `_hydrate_hit()` in the lexical section from Task 5
- Test: `cli/test_okf_cli.py`

**Interfaces:**
- Consumes: everything from Task 5, plus `resolve_scopes(root, target)` (`cli/okf-cli.py:1943`) and `make_snippet(body, terms)`.
- Produces:
  - `_fts_ranking(root, query, limit, type_filter=None, tag_filter=None, scope=None) -> list[tuple[str, float]] | None` — `(path, positive_bm25)` best first; `None` means "index unusable, fall back".
  - `_hydrate_hit(root, path, terms, score, provenance, cosine=None) -> dict | None`
  - `_substring_ranking(root, query, terms, limit, type_filter, tag_filter, scope) -> list[dict]` — today's scan, extracted verbatim from `cmd_find` so both paths are callable side by side.
  - Output contract: when the FTS arm serves the query, `max_score` is `100` and each hit's `score` is `round(100 * s / top_s)`. On the fallback path the old `6 * len(terms)` semantics are kept byte-for-byte.

**Note on the frozen eval baseline:** `cli/eval/gate.py:56-81` gates on `zero_hit_rate_paraphrase` and on literal S1 ranks only. `mean_score_ratio` is reported but never gated, so the score-scale change shifts a reported number without weakening the gate. Say so in the commit body.

- [ ] **Step 1: Write the failing tests**

Add to `cli/test_okf_cli.py`:

```python
class FtsRanking(unittest.TestCase):
    """T13 — the lexical arm is BM25 over the index, and it degrades to the
    substring scan rather than failing when the artefact is missing (D15)."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "b"))
        with open(os.path.join(self.root, "b", "one.md"), "w",
                  encoding="utf-8") as f:
            f.write("---\ntype: Runbook\ntitle: Serve Excalidraw drafts\n"
                    "description: d\ntags: [excalidraw, tailscale]\n---\n"
                    "Render the drawing to PNG and expose it over the tunnel.\n")
        with open(os.path.join(self.root, "b", "two.md"), "w",
                  encoding="utf-8") as f:
            f.write("---\ntype: Konzept\ntitle: Tunnel basics\n"
                    "description: d\ntags: [tailscale]\n---\nA tunnel primer.\n")
        with open(os.path.join(self.root, "b", "index.md"), "w",
                  encoding="utf-8") as f:
            f.write("# B\n")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_returns_none_without_an_index(self):
        self.assertIsNone(okf._fts_ranking(self.root, "tunnel", 10))

    def test_ranks_title_match_above_body_match(self):
        okf.build_fts_index(self.root)
        ranked = okf._fts_ranking(self.root, "tunnel", 10)
        self.assertEqual(ranked[0][0], "b/two")

    def test_type_filter_narrows(self):
        okf.build_fts_index(self.root)
        ranked = okf._fts_ranking(self.root, "tunnel", 10, type_filter="Runbook")
        self.assertEqual([p for p, _s in ranked], ["b/one"])

    def test_tag_filter_matches_whole_tags_only(self):
        okf.build_fts_index(self.root)
        ranked = okf._fts_ranking(self.root, "tunnel", 10, tag_filter="tail")
        self.assertEqual(ranked, [])

    def test_scope_filter_narrows_to_a_bundle(self):
        okf.build_fts_index(self.root)
        self.assertNotEqual(okf._fts_ranking(self.root, "tunnel", 10, scope="b"), [])
        self.assertEqual(okf._fts_ranking(self.root, "tunnel", 10, scope="zz"), [])

    def test_corrupt_index_degrades_to_none(self):
        okf.build_fts_index(self.root)
        with open(okf._fts_db_path(self.root), "wb") as f:
            f.write(b"not a database")
        self.assertIsNone(okf._fts_ranking(self.root, "tunnel", 10))


class FindDegradesWithoutIndex(unittest.TestCase):
    """D15 — no artefact, no crash: the substring path still answers, and
    its output shape is unchanged from before this plan."""

    def test_find_without_index_still_prints_a_hit(self):
        root = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(root, "b"))
            with open(os.path.join(root, "b", "one.md"), "w",
                      encoding="utf-8") as f:
                f.write("---\ntype: Runbook\ntitle: Tunnel\ndescription: d\n"
                        "tags: [net]\n---\nbody\n")
            with open(os.path.join(root, "b", "index.md"), "w",
                      encoding="utf-8") as f:
                f.write("# B\n")
            out = _run_find(root, "tunnel")
            self.assertIn("path: b/one", out)
            self.assertIn("score: 3/6", out)
        finally:
            shutil.rmtree(root, ignore_errors=True)
```

**`_run_find` does not exist yet — define it in this task.** The file's existing
CLI-level `find` tests use a per-class in-process helper (`cli/test_okf_cli.py:1376-1387`):
`types.SimpleNamespace` args, `okf.cmd_find(root, args)` under
`redirect_stdout`/`redirect_stderr`. Tasks 10 and 11 reuse it, so lift that
pattern to module level once, right above the first new test class:

```python
def _run_find(root, query, **kw):
    """Module-level twin of the per-class _run() helper at
    cli/test_okf_cli.py:1376 — same in-process convention (SimpleNamespace
    args, cmd_find, redirected streams), but parameterised by root so the new
    suites can each use their own temp catalogue. Returns stdout."""
    import io
    import contextlib
    import types
    args = types.SimpleNamespace(
        query=query, limit=10, type=None, tag=None, scope=None,
        breakdown=False,
    )
    for k, v in kw.items():
        setattr(args, k, v)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        okf.cmd_find(root, args)
    return buf.getvalue()
```

In-process, not subprocess: that is the file's convention and it keeps the
suite fast. The argument parser and the dispatch entry are covered separately
by the subprocess smoke check in Task 5, Step 6.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest cli.test_okf_cli.FtsRanking -v`
Expected: FAIL — `AttributeError: module 'okf_cli' has no attribute '_fts_ranking'`.

- [ ] **Step 3: Add `_fts_ranking` and `_hydrate_hit`**

Append to the lexical section from Task 5:

```python
def _fts_ranking(root, query, limit, type_filter=None, tag_filter=None,
                 scope=None):
    """[(path, positive_score), ...] best first, or None when the index is
    unusable (absent or corrupt) — None is the caller's signal to degrade to
    the substring scan (D15). bm25() is lower-is-better, so it is negated.
    Filters run inside SQL against the UNINDEXED ctype/path columns and the
    indexed tags column, so filtering never re-reads a concept file."""
    db = _fts_db_path(root)
    if not os.path.isfile(db):
        return None
    terms = tokenize(query)
    if not terms:
        return []
    expr = " OR ".join('"{}"*'.format(t.replace('"', "")) for t in terms)
    sql = ("SELECT path, bm25(docs, {}) AS r FROM docs WHERE docs MATCH ?"
           .format(FTS_BM25_WEIGHTS))
    params = [expr]
    if type_filter:
        sql += " AND ctype = ?"
        params.append(type_filter)
    if tag_filter:
        # whole-tag match: tags is a space-joined slug list, so pad both sides
        # rather than substring-matching (a "tail" query must not hit
        # "tailscale").
        sql += " AND instr(' ' || tags || ' ', ' ' || ? || ' ') > 0"
        params.append(tag_filter)
    if scope:
        sql += " AND (path = ? OR path LIKE ?)"
        params.extend([scope.rstrip("/"), scope.rstrip("/") + "/%"])
    sql += " ORDER BY r LIMIT ?"
    params.append(limit)
    try:
        conn = sqlite3.connect(db)
        try:
            if _fts_index_stale(root, conn):
                print("note: lexical index is stale (catalogue changed since "
                      "build) — run `okf-cli build-index`", file=sys.stderr)
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        print("note: lexical index unusable — falling back to substring scan",
              file=sys.stderr)
        return None
    return [(p, -r) for p, r in rows]


def _hydrate_hit(root, path, terms, score, provenance, cosine=None):
    """Build the hit dict cmd_find prints, reading the concept file itself.
    Only ever called for the <= limit paths that actually rank, which is what
    makes the FTS path cheaper than the full scan. Returns None when the path
    no longer resolves (index or embedding cache newer than the file tree)."""
    ap = os.path.join(root, path + ".md")
    if not os.path.isfile(ap):
        return None
    fm, body = split_frontmatter(read_file(ap))
    hit = {
        "score": score,
        "path": path,
        "title": _dequote(fm.get("title", "")) or path.rsplit("/", 1)[-1],
        "type": fm.get("type", ""),
        "desc": _dequote(fm.get("description", "")),
        "snip": make_snippet(body, terms),
        "provenance": provenance,
    }
    if cosine is not None:
        hit["cosine"] = cosine
    return hit
```

- [ ] **Step 4: Extract today's scan into `_substring_ranking`**

Move the loop currently at `cli/okf-cli.py:801-837` into a function, leaving its arithmetic and its `contrib` bookkeeping untouched:

```python
def _substring_ranking(root, query, terms, limit, type_filter=None,
                       tag_filter=None, scope=None):
    """The pre-FTS lexical arm, unchanged: substring matching with field
    weights title 3 / tags 2 / body 1 over a full scan. It stays in the tool
    as the degradation target for a missing or unusable index (D15) — its
    scoring, its `contrib` breakdown and its 6*len(terms) scale must remain
    byte-identical, because the frozen eval baseline was recorded against it."""
    hits = []
    for b, bp in resolve_scopes(root, scope):
        for cid, ap in iter_concepts(bp):
            text = read_file(ap)
            fm, body = split_frontmatter(text)
            t = fm.get("type", "")
            if type_filter and t != type_filter:
                continue
            if tag_filter and tag_filter not in extract_tags(text):
                continue
            title = fm.get("title", cid)
            tags = fm.get("tags", "")
            hay_title = title.lower()
            hay_tags = tags.lower()
            hay_body = body.lower()
            score = 0
            contrib = {"title": [], "tags": [], "body": []}
            for term in terms:
                if hay_title.count(term):
                    score += 3
                    contrib["title"].append(term)
                if hay_tags.count(term):
                    score += 2
                    contrib["tags"].append(term)
                if hay_body.count(term):
                    score += 1
                    contrib["body"].append(term)
            if score:
                hits.append({
                    "score": score, "path": "{}/{}".format(b, cid),
                    "title": title, "type": t,
                    "desc": _dequote(fm.get("description", "")),
                    "snip": make_snippet(body, terms), "contrib": contrib,
                    "provenance": "lexical",
                })
    hits.sort(key=lambda h: -h["score"])
    return hits[:limit]
```

- [ ] **Step 5: Rewrite the lexical half of `cmd_find`**

Put the arm selection in its own function, so it can be called more than once (Task 11 needs a second pass) and so the two score scales travel with the branch that chooses them:

```python
def _rank_lexically(root, query, terms, limit, type_filter=None,
                    tag_filter=None, scope=None):
    """(hits, max_score) — the FTS arm when the index is usable, otherwise the
    substring scan (D15). The two arms report on different scales, so the
    scale is returned with the result instead of being recomputed by the
    caller: 0..100 for BM25 (relative to this run's own top hit), and
    6*len(terms) for the substring fallback, which keeps that path
    byte-identical to pre-plan output."""
    ranked = _fts_ranking(root, query, limit, type_filter, tag_filter, scope)
    if ranked is None:
        return (_substring_ranking(root, query, terms, limit, type_filter,
                                   tag_filter, scope),
                6 * len(terms))
    top = ranked[0][1] if ranked else 1.0
    hits = []
    for path, s in ranked:
        hit = _hydrate_hit(root, path, terms,
                           int(round(100 * s / top)) if top else 0, "lexical")
        if hit is not None:
            hits.append(hit)
    return hits, 100
```

Then replace `cmd_find`'s body from line 801 down to the `max_score = 6 * len(terms)` line with:

```python
    hits, max_score = _rank_lexically(root, args.query, terms, args.limit,
                                      type_filter, tag_filter, target)
```

`--breakdown` prints `contrib` (line 894-898). FTS hits have no `contrib`, so add the branch there:

```python
        if breakdown:
            if h.get("provenance") == "semantic":
                print("contrib: semantic-only (cosine={:.2f}, no keyword field match)".format(h["cosine"]))
            elif "contrib" in h:
                print("contrib: {}".format(_format_contrib(h["contrib"])))
            else:
                print("contrib: bm25 (fts5 index; field-level breakdown not "
                      "available)")
```

Leave the semantic block untouched in this task — Tasks 7 and 8 replace it. It already operates on the name `hits`, which is what `_rank_lexically` now supplies, so the tool keeps working in between with no bridging variable.

**Interfaces (added):** `_rank_lexically(root, query, terms, limit, type_filter=None, tag_filter=None, scope=None) -> tuple[list[dict], int]`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m unittest cli.test_okf_cli -v 2>&1 | tail -5`
Expected: the new classes pass; total still exactly 19 failures, 2 errors.

- [ ] **Step 7: Verify against the live catalogue**

Run:
```bash
python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue find "data-ui konvention namensschema" --limit 5
time python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue find "tailscale" --limit 5 >/dev/null
```
Expected: literal queries still answer, and the timed run is not slower than before the change (the scan of 2581 files is gone; only `limit` files are read).

- [ ] **Step 8: Commit**

```bash
git add cli/okf-cli.py cli/test_okf_cli.py
git commit -m "feat(cli): rank lexically via fts5 bm25"
```

Body (why): the substring scan stays as the degradation target; score scale becomes 0..100 on the FTS path while the fallback keeps `6*len(terms)`; `mean_score_ratio` in the eval report shifts accordingly and is not a gated metric (`cli/eval/gate.py:56-81`).

---

### Task 7: Semantic arm on `voyage-3-large` (D13/D16)

**Files:**
- Modify: `cli/okf-cli.py:647-785` (the semantic section)
- Test: `cli/test_okf_cli.py:1487-1690` (the existing semantic suite monkeypatches `_embed_query_bge_m3`)

**Interfaces:**
- Consumes: `_hydrate_hit()` from Task 6; `concept_emb` rows produced in Task 3.
- Produces:
  - `SEMANTIC_MODEL = "voyage-3-large"`, `VOYAGE_EMBED_URL`, `VOYAGE_EMBED_TIMEOUT`
  - `_embed_query_voyage(text: str) -> list[float]` — replaces `_embed_query_bge_m3`; raises on any failure so the caller degrades
  - `semantic_ranking(root, query, limit) -> list[tuple[float, str]]` — replaces `semantic_backstop()`; `(cosine, path)` best first, `[]` on any degradation. No `exclude_paths` parameter: under conditional handover the two lists are deduplicated during fusion, not before ranking.
  - `_semantic_hit_dicts(root, query, limit) -> list[dict]` — signature loses `exclude_paths` and `max_score`; semantic scores are now `round(100 * cosine)`.

- [ ] **Step 1: Write the failing tests**

Add to `cli/test_okf_cli.py`:

```python
class VoyageQueryEmbedding(unittest.TestCase):
    """D13/D16 — the query path speaks voyage-3-large with input_type=query
    (the asymmetric form the measurement used, eval/hybrid_eval.py:73-80),
    and it degrades to lexical-only on any failure. Network is faked."""

    def setUp(self):
        self.orig_env = os.environ.get("VOYAGE_API_KEY")
        os.environ["VOYAGE_API_KEY"] = "test-key"

    def tearDown(self):
        if self.orig_env is None:
            os.environ.pop("VOYAGE_API_KEY", None)
        else:
            os.environ["VOYAGE_API_KEY"] = self.orig_env

    def test_request_uses_query_input_type_and_bearer_auth(self):
        seen = {}

        class _Resp:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

            def read(self_inner):
                return json.dumps(
                    {"data": [{"embedding": [0.5, 0.5]}]}).encode("utf-8")

        def _fake_urlopen(req, timeout=None):
            seen["payload"] = json.loads(req.data.decode("utf-8"))
            seen["auth"] = req.get_header("Authorization")
            return _Resp()

        orig = okf.urllib.request.urlopen
        okf.urllib.request.urlopen = _fake_urlopen
        try:
            vec = okf._embed_query_voyage("mockup tailscale")
        finally:
            okf.urllib.request.urlopen = orig

        self.assertEqual(vec, [0.5, 0.5])
        self.assertEqual(seen["payload"]["model"], "voyage-3-large")
        self.assertEqual(seen["payload"]["input_type"], "query")
        self.assertEqual(seen["payload"]["input"], ["mockup tailscale"])
        self.assertEqual(seen["auth"], "Bearer test-key")

    def test_missing_api_key_raises_so_the_caller_can_degrade(self):
        os.environ.pop("VOYAGE_API_KEY", None)
        with self.assertRaises(RuntimeError):
            okf._embed_query_voyage("x")


class SemanticRankingDegradation(unittest.TestCase):
    """R05/D16 — every failure mode returns [] plus one stderr note, and none
    of them raises."""

    def test_absent_cache_returns_empty(self):
        root = tempfile.mkdtemp()
        try:
            self.assertEqual(okf.semantic_ranking(root, "x", 10), [])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_unreachable_backend_returns_empty(self):
        root = tempfile.mkdtemp()
        try:
            db = okf._tagvec_db_path(root)
            os.makedirs(os.path.dirname(db))
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE concept_emb(key TEXT, path TEXT, "
                         "model TEXT, dim INT, vec BLOB)")
            conn.execute("INSERT INTO concept_emb VALUES(?,?,?,?,?)",
                         ("k", "b/one", "voyage-3-large", 2,
                          struct.pack("<2f", 1.0, 0.0)))
            conn.commit()
            conn.close()

            def _raise(_text):
                raise RuntimeError("no network")

            orig = okf._embed_query_voyage
            okf._embed_query_voyage = _raise
            try:
                self.assertEqual(okf.semantic_ranking(root, "x", 10), [])
            finally:
                okf._embed_query_voyage = orig
        finally:
            shutil.rmtree(root, ignore_errors=True)
```

`struct` and `json` were added to the module's top-level imports in Task 5, Step 1.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest cli.test_okf_cli.VoyageQueryEmbedding -v`
Expected: FAIL — `AttributeError: module 'okf_cli' has no attribute '_embed_query_voyage'`.

- [ ] **Step 3: Replace the model constants and the embed function**

In `cli/okf-cli.py`, replace lines 673-675 with:

```python
# D13 — voyage-3-large is the productive semantic model: MRR 0.452 vs 0.150
# for bge-m3 on the unbiased query set, zero-hit 0.167 vs 0.646 (R42). That is
# the difference between usable and not, not a tuning gap. The accepted price
# is a network call and an API key in the request path; D16 makes the
# degradation two-stage (voyage -> lexical only), so bge-m3 is NOT a runtime
# fallback and concept_emb holds voyage rows only.
SEMANTIC_MODEL = "voyage-3-large"
VOYAGE_EMBED_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_EMBED_TIMEOUT = 10
```

Replace `_embed_query_bge_m3` (lines 704-716) with:

```python
def _embed_query_voyage(text):
    """Best-effort Voyage embed call for the query string. NETWORK — reached
    only when the semantic arm actually runs (never at import time, never
    unconditionally). `input_type="query"` is the asymmetric query form the
    measurement used (eval/hybrid_eval.py:73-80); documents were embedded with
    input_type="document" by the producer. Any failure propagates so the
    caller degrades gracefully; this function never catches."""
    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key:
        raise RuntimeError("VOYAGE_API_KEY not set")
    req = urllib.request.Request(
        VOYAGE_EMBED_URL,
        data=json.dumps({
            "model": SEMANTIC_MODEL,
            "input": [text],
            "input_type": "query",
        }).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        },
    )
    with urllib.request.urlopen(req, timeout=VOYAGE_EMBED_TIMEOUT) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["data"][0]["embedding"]
```

- [ ] **Step 4: Rename and simplify the ranking function**

Replace `semantic_backstop` (lines 742-762) with:

```python
def semantic_ranking(root, query, limit):
    """[(cosine, path), ...] best first, or [] with one stderr note on any
    degradation (cache/table absent, no API key, backend unreachable).

    Renamed from semantic_backstop(): under conditional handover this arm is
    no longer a fallback that only fills gaps — on a paraphrase query it OWNS
    the ranking (D12). It also no longer takes exclude_paths, because
    deduplication happens in fusion, after the owner has been decided."""
    vectors = _load_concept_vectors(_tagvec_db_path(root), SEMANTIC_MODEL)
    if vectors is None:
        print("note: semantic arm skipped (.tagvec cache/concept embeddings "
              "absent) — lexical results only", file=sys.stderr)
        return []
    try:
        qvec = _embed_query_voyage(query)
    except Exception as exc:
        print("note: semantic arm skipped (embedding backend unavailable: {})"
              " — lexical results only".format(exc), file=sys.stderr)
        return []
    ranked = sorted(((_cosine(qvec, vec), path) for path, vec in vectors),
                    key=lambda x: -x[0])
    return ranked[:limit]
```

Replace `_semantic_hit_dicts` (lines 765-785) with:

```python
def _semantic_hit_dicts(root, query, limit):
    """semantic_ranking() results, hydrated into the same hit-dict shape the
    lexical arm produces so fusion and printing treat both uniformly.
    Semantic score is round(100 * cosine) — the same 0..100 scale the FTS arm
    reports, which makes the printed number comparable without implying the
    two are fused by score (they are not; see fuse_conditional)."""
    terms = tokenize(query)
    out = []
    for cosine, path in semantic_ranking(root, query, limit):
        hit = _hydrate_hit(root, path, terms, int(round(100 * cosine)),
                           "semantic", cosine=cosine)
        if hit is not None:
            out.append(hit)
    return out
```

- [ ] **Step 5: Update the existing semantic suite**

`cli/test_okf_cli.py:1487-1690` monkeypatches `okf._embed_query_bge_m3` and seeds `concept_emb` rows with `model='bge-m3'`. Rename both throughout that suite: patch `okf._embed_query_voyage`, and insert rows with `model='voyage-3-large'`. Tests that assert the old `note: semantic backstop skipped …` wording must assert the new `note: semantic arm skipped …` wording. Do not weaken any assertion — only rename the model, the function, and the note text.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m unittest cli.test_okf_cli -v 2>&1 | tail -5`
Expected: the new classes pass; the renamed suite passes; total still exactly 19 failures, 2 errors.

- [ ] **Step 7: Commit**

```bash
git add cli/okf-cli.py cli/test_okf_cli.py
git commit -m "feat(cli): semantic arm on voyage-3-large"
```

---

### Task 8: Conditional handover fusion (T12/D12)

**Files:**
- Modify: `cli/okf-cli.py` — replace the gate at `:853-861` and the fusion at `:863-879`
- Test: `cli/test_okf_cli.py`

**Interfaces:**
- Consumes: `_fts_ranking`/`_substring_ranking`/`_hydrate_hit` (Task 6), `_semantic_hit_dicts` (Task 7).
- Produces: `fuse_conditional(lexical_hits, semantic_hits, limit) -> tuple[list[dict], bool]` — the fused list and whether the lexical arm owned the ranking. `_keyword_top1_is_confident(hits)` keeps its name and its `SEMANTIC_MARGIN_RATIO` semantics but is now also the ownership decision, so it must handle the one-hit and the empty case itself.

**Removed:** `SEMANTIC_NOISE_RATIO` and its gate branch. It existed to force the backstop to fire against a noisy substring top-1 (`cli/okf-cli.py:665-672`). Under conditional handover a noisy lexical arm simply does not own the ranking, so the absolute ratio is redundant — and R43 measured the rule without it. Delete the constant; do not keep it unused.

- [ ] **Step 1: Write the failing tests**

Add to `cli/test_okf_cli.py`:

```python
def _h(path, score, provenance):
    return {"path": path, "score": score, "provenance": provenance,
            "title": path, "type": "", "desc": "", "snip": ""}


class FuseConditional(unittest.TestCase):
    """D12/R43 — decide WHICH arm owns the ranking; never blend two
    incomparable scales. Measured: worst case 0.437 MRR vs 0.201 for RRF and
    0.029 for the pin+blend rule shipped before this plan."""

    def test_confident_lexical_owns_the_ranking(self):
        lex = [_h("a", 100, "lexical"), _h("b", 40, "lexical")]
        sem = [_h("c", 90, "semantic")]
        out, lex_owned = okf.fuse_conditional(lex, sem, 10)
        self.assertTrue(lex_owned)
        self.assertEqual([h["path"] for h in out], ["a", "b", "c"])

    def test_ambiguous_lexical_hands_the_ranking_to_semantic(self):
        lex = [_h("a", 100, "lexical"), _h("b", 95, "lexical")]
        sem = [_h("c", 60, "semantic")]
        out, lex_owned = okf.fuse_conditional(lex, sem, 10)
        self.assertFalse(lex_owned)
        self.assertEqual([h["path"] for h in out], ["c", "a", "b"])

    def test_single_lexical_hit_is_treated_as_confident(self):
        lex = [_h("a", 100, "lexical")]
        sem = [_h("c", 90, "semantic")]
        out, lex_owned = okf.fuse_conditional(lex, sem, 10)
        self.assertTrue(lex_owned)
        self.assertEqual([h["path"] for h in out], ["a", "c"])

    def test_empty_lexical_hands_over(self):
        out, lex_owned = okf.fuse_conditional([], [_h("c", 60, "semantic")], 10)
        self.assertFalse(lex_owned)
        self.assertEqual([h["path"] for h in out], ["c"])

    def test_duplicate_paths_keep_the_owning_arms_entry(self):
        lex = [_h("a", 100, "lexical"), _h("b", 95, "lexical")]
        sem = [_h("b", 70, "semantic"), _h("c", 60, "semantic")]
        out, lex_owned = okf.fuse_conditional(lex, sem, 10)
        self.assertFalse(lex_owned)
        self.assertEqual([h["path"] for h in out], ["b", "c", "a"])
        self.assertEqual(out[0]["provenance"], "semantic")

    def test_limit_is_respected(self):
        lex = [_h("a", 100, "lexical")]
        sem = [_h("c", 90, "semantic"), _h("d", 80, "semantic")]
        out, _lex_owned = okf.fuse_conditional(lex, sem, 2)
        self.assertEqual([h["path"] for h in out], ["a", "c"])

    def test_semantic_never_precedes_a_confident_lexical_top1(self):
        lex = [_h("a", 30, "lexical"), _h("b", 5, "lexical")]
        sem = [_h("c", 99, "semantic")]
        out, lex_owned = okf.fuse_conditional(lex, sem, 10)
        self.assertTrue(lex_owned)
        self.assertEqual(out[0]["path"], "a")

    def test_margin_band_matches_the_measured_rule(self):
        """The measured rule is top1 >= 1.5*top2 (eval/hybrid_eval.py:151).
        The pre-plan arithmetic was top1 >= 2*top2. 100 vs 60 sits inside the
        band where the two disagree: the measured rule says the lexical arm
        is confident, the old one says it is not. Pin the measured one."""
        lex = [_h("a", 100, "lexical"), _h("b", 60, "lexical")]
        sem = [_h("c", 90, "semantic")]
        out, lex_owned = okf.fuse_conditional(lex, sem, 10)
        self.assertTrue(lex_owned)
        self.assertEqual([h["path"] for h in out], ["a", "b", "c"])

    def test_just_below_the_band_hands_over(self):
        lex = [_h("a", 100, "lexical"), _h("b", 68, "lexical")]
        sem = [_h("c", 90, "semantic")]
        _out, lex_owned = okf.fuse_conditional(lex, sem, 10)
        self.assertFalse(lex_owned)


class NoiseRatioIsGone(unittest.TestCase):
    """The absolute noise floor was a crutch for the blend rule; conditional
    handover subsumes it. Leaving it in place would mean two competing gates."""

    def test_constant_removed(self):
        self.assertFalse(hasattr(okf, "SEMANTIC_NOISE_RATIO"))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest cli.test_okf_cli.FuseConditional -v`
Expected: FAIL — `AttributeError: module 'okf_cli' has no attribute 'fuse_conditional'`.

- [ ] **Step 3: Implement the ownership decision and fusion**

Replace `_keyword_top1_is_confident` (lines 728-739) with:

```python
def _keyword_top1_is_confident(hits):
    """True when the lexical arm may OWN the ranking: it has hits and either a
    single one (nothing to be ambiguous against) or a top-1 leading the
    runner-up by the measured margin.

    The comparison is `top1 >= (1 + SEMANTIC_MARGIN_RATIO) * top2`, i.e.
    top1 >= 1.5x top2 — copied from the rule that actually produced R43's
    0.437 (eval/hybrid_eval.py:151). The pre-plan code computed
    `(top1-top2)/top1 >= SEMANTIC_MARGIN_RATIO`, which is top1 >= 2x top2: a
    stricter bar that hands over to the semantic arm LESS often than what was
    measured. Do not "simplify" it back."""
    if not hits:
        return False
    if len(hits) == 1:
        return True
    top1, top2 = hits[0]["score"], hits[1]["score"]
    if top1 <= 0:
        return False
    return top1 >= (1 + SEMANTIC_MARGIN_RATIO) * top2
```

The two formulas disagree for every score pair in the 1.5x–2x band, which is
why the test below pins exactly that band.

Delete `SEMANTIC_NOISE_RATIO` (lines 665-672) and add, next to the fusion code:

```python
def fuse_conditional(lexical_hits, semantic_hits, limit):
    """(fused_hits, lexical_owned) — conditional HANDOVER, not blending (D12).

    Measured on the unbiased query set: blending a lexical list that is pure
    noise on paraphrases (zero-hit 1.000) into a working semantic list costs
    more than it adds, whether by score interleaving (MRR 0.029) or by RRF
    (0.201). On literal queries the lexical arm is the better one. So decide
    per query WHICH arm owns the ranking instead of averaging them: worst case
    0.437 across both regimes (R43).

    The owning arm's list comes first in its own order; the other arm is
    appended behind it, never in front. Duplicates keep the owning arm's entry
    (and therefore its provenance), so a concept both arms found is not
    reported twice."""
    lexical_owned = _keyword_top1_is_confident(lexical_hits)
    primary = lexical_hits if lexical_owned else semantic_hits
    secondary = semantic_hits if lexical_owned else lexical_hits
    out, seen = [], set()
    for hit in list(primary) + list(secondary):
        if hit["path"] in seen:
            continue
        seen.add(hit["path"])
        out.append(hit)
    return out[:limit], lexical_owned
```

- [ ] **Step 4: Rewire `cmd_find`**

Replace the gate block (lines 853-861) and the fusion block (863-879) with:

```python
    # The semantic arm costs a network call, so run it only when it can
    # change the answer: whenever the lexical arm is not confident (it will
    # then OWN the ranking), or when a confident lexical list is too short to
    # fill --limit (it then fills the tail, exactly as measured).
    lexical_owned_provisionally = _keyword_top1_is_confident(hits)
    semantic_hits = []
    if not lexical_owned_provisionally or len(hits) < args.limit:
        semantic_hits = _semantic_hit_dicts(root, args.query, args.limit)

    all_hits, lexical_owned = fuse_conditional(hits, semantic_hits, args.limit)
    if not lexical_owned and semantic_hits:
        print("note: semantic arm owns this ranking (lexical top-1 lacked a "
              "clear margin)", file=sys.stderr)
```

The printing loop below stays as it is; it already special-cases `provenance == "semantic"` for the cosine line (lines 892-898).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m unittest cli.test_okf_cli -v 2>&1 | tail -5`
Expected: the new classes pass; total still exactly 19 failures, 2 errors.

The threshold moved from `top1 >= 2*top2` to `top1 >= 1.5*top2`, so any existing
test in the semantic suite (`cli/test_okf_cli.py:1487-1690`) whose score pair
sits in that band flips its expectation. If one fails, check whether it asserts
*firing behaviour* (then update it to the measured rule and say so in the commit
body) or *a different invariant that happens to use such a pair* (then change the
pair, not the assertion). Do not change `SEMANTIC_MARGIN_RATIO` itself.

- [ ] **Step 6: Verify the architecture end-to-end on the live catalogue**

Run:
```bash
python3 cli/okf-cli.py --root ~/Obsidian/Knowledge-Catalogue find "mockup tailscale" --limit 5
```
Expected: `dev-wiki/testsystem-vite-tailscale/serve-excalidraw-drafts` appears — this is R12, the query that started the whole investigation and that today returns nothing. Its line must carry `provenance: semantic (cosine=…)`.

If it does not appear, stop and report before continuing: either the fill (Task 3) is incomplete, or the fusion handed the ranking to the wrong arm. Do not "fix" it by tuning `SEMANTIC_MARGIN_RATIO` — that value is what R43 measured.

- [ ] **Step 7: Commit**

```bash
git add cli/okf-cli.py cli/test_okf_cli.py
git commit -m "feat(cli): fuse arms by conditional handover"
```

---

### Task 9: Re-measure and gate (proof)

**Files:**
- Create: `docs/okf-retrieval-architecture/eval/remeasure.py`
- Modify: `cli/eval/runner.py:190-217` (build the index before scoring)
- Modify: `docs/okf-retrieval-architecture/REFERENCES.md`

**Interfaces:**
- Consumes: the shipped CLI from Tasks 4-8, the filled cache from Task 3.
- Produces: `docs/okf-retrieval-architecture/eval/shipped_v2.json` — the same metric shape `eval_v2.json` uses, so the numbers are directly comparable to R42/R43.

**Why a new script rather than reusing `hybrid_eval.py`:** `hybrid_eval.py` contains its own re-implementation of the arms. Measuring it again would measure the eval script. This one shells out to `okf-cli find` exactly like `cli/eval/runner.py:48 _run_cli` does, so what gets measured is what ships.

- [ ] **Step 1: Write the re-measurement script**

Create `docs/okf-retrieval-architecture/eval/remeasure.py`:

```python
#!/usr/bin/env python3
"""Re-measure the SHIPPED okf-cli find against the unbiased query set.

Unlike hybrid_eval.py (which re-implements the arms to compare fusion rules),
this runs the real CLI as a subprocess, so the number it prints is the number
users get. Metric shape matches eval_v2.json so it can be read next to R42.

Usage:
    python3 docs/okf-retrieval-architecture/eval/remeasure.py \\
        --root ~/Obsidian/Knowledge-Catalogue \\
        --queries queries_v2.json queries_real.json \\
        --out shipped_v2.json
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
CLI = os.path.join(REPO, "cli", "okf-cli.py")


def ranked_paths(root, query, limit):
    """Ordered result paths of one `okf-cli find`, plus its wall time."""
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable, CLI, "--root", root, "find", query,
         "--limit", str(limit)],
        capture_output=True, text=True)
    elapsed = time.time() - t0
    paths = [line[len("path: "):] for line in proc.stdout.splitlines()
             if line.startswith("path: ")]
    return paths, elapsed


def measure(root, rows, limit):
    """The query files use the keys "query", "target", "source" — verified in
    queries_v2.json and queries_real.json. `target` is the concept path."""
    ranks, times = [], []
    for row in rows:
        paths, elapsed = ranked_paths(root, row["query"], limit)
        times.append(elapsed)
        target = row["target"]
        ranks.append(paths.index(target) + 1 if target in paths else None)
    n = len(ranks) or 1
    hit = [r for r in ranks if r is not None]
    return {
        "n": len(ranks),
        "recall@1": sum(1 for r in hit if r == 1) / n,
        "recall@5": sum(1 for r in hit if r <= 5) / n,
        "recall@10": sum(1 for r in hit if r <= 10) / n,
        "mrr": sum(1.0 / r for r in hit) / n,
        "zero_hit": (len(ranks) - len(hit)) / n,
        "latency_p50": sorted(times)[len(times) // 2] if times else 0.0,
        "latency_max": max(times) if times else 0.0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--queries", nargs="+", required=True)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    root = os.path.abspath(os.path.expanduser(args.root))
    result = {}
    combined = []
    for qf in args.queries:
        path = qf if os.path.isabs(qf) else os.path.join(HERE, qf)
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)
        result[os.path.basename(path)] = measure(root, rows, args.limit)
        combined.extend(rows)
    result["combined"] = measure(root, combined, args.limit)

    print(json.dumps(result, indent=2))
    if args.out:
        out = args.out if os.path.isabs(args.out) else os.path.join(HERE, args.out)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Both query files were checked while writing this plan: each row is `{"query": ..., "target": ..., "source": ...}`, 40 rows in `queries_v2.json` and 8 in `queries_real.json`. No key adjustment is needed; never adjust the query files themselves.

- [ ] **Step 2: Run the re-measurement**

```bash
python3 docs/okf-retrieval-architecture/eval/remeasure.py \
  --root ~/Obsidian/Knowledge-Catalogue \
  --queries queries_v2.json queries_real.json \
  --out shipped_v2.json
```

**Success criteria (compare against R42's `K` row, the shipped state before this plan):**
- `combined.zero_hit` ≤ 0.30 (was **0.979**)
- `combined.mrr` ≥ 0.35 (was **0.021**)
- `queries_real.json` zero-hit ≤ 0.25 (was 0.875, R29)
- `combined.latency_p50` ≤ 2.0 s

If latency fails and nothing else does, that is a known and bounded risk: `_load_concept_vectors` (`cli/okf-cli.py:682-701`) unpacks 2437 × 1024 floats per query in pure Python. The stdlib remedy, in this order — (a) keep the vectors as `array.array('f')` instead of `list`, (b) compute the dot product with `sum(map(operator.mul, a, b))`, (c) store L2-normalised vectors at produce time so the query-side norm loop disappears. Apply the cheapest one that meets the bar; do not add a dependency.

If a retrieval criterion fails, stop and report with the JSON — do not tune `SEMANTIC_MARGIN_RATIO` to make a number move.

- [ ] **Step 3: Make the fixture gate exercise the new path**

`cli/eval/runner.py:190 run()` scores against a fixture catalogue that has no `.fts` index, so without this step the gate silently measures the degradation path. Add right after `root = os.path.abspath(...)` (line 194):

```python
    # The lexical arm is index-backed since D14; without a build here the
    # runner would score the substring fallback and report it as the shipped
    # behaviour. Local, no network, ~ms on a fixture catalogue.
    subprocess.run(
        [sys.executable, os.path.join(_REPO, "cli", "okf-cli.py"),
         "--root", root, "build-index"],
        check=True, capture_output=True, text=True)
```

Use whatever constant the module already has for the CLI path (see `_run_cli`, line 48); add `_REPO` only if none exists.

- [ ] **Step 4: Run the fixture gate**

The golden fixtures S1–S4 are `_okfeval-*` files that `cli/eval/fixtures.py` seeds into **the live catalogue** (`fixtures.py:41 DEFAULT_ROOT = ~/Obsidian/Knowledge-Catalogue`); they are not present between runs. Without seeding, every literal row misses and `gate.py:69-79` reports a false "literal S1 recall regressed". The predecessor plan bracketed the run with seed/teardown (`docs/okf-revision/PLAN.md:269,275`) — do the same, plus two steps that plan did not need:

```bash
REV=$(git rev-parse --short HEAD)
ROOT=~/Obsidian/Knowledge-Catalogue

# 1. seed the hidden fixtures into the live catalogue
python3 cli/eval/fixtures.py --root $ROOT --seed

# 2. the fixtures are brand-new concepts, so they have no concept_emb rows.
#    S3 exists precisely to be rescued by the semantic arm, which cannot
#    happen without a vector. Everything else is already embedded from Task 3,
#    so this delta is exactly the four fixtures and costs cents.
python3 cli/embeddings/build_tagvec.py --root $ROOT \
  --target concepts --model voyage-3-large --produce

# 3. score + gate (runner.py builds the FTS index itself, see Step 3)
python3 cli/eval/runner.py --root $ROOT --golden cli/eval/golden.json \
  --out cli/eval/results/architecture-$REV.json
python3 cli/eval/gate.py --baseline cli/eval/results/baseline-f0714b2.json \
  --hybrid cli/eval/results/architecture-$REV.json

# 4. remove the fixtures again — the real catalogue must end clean
python3 cli/eval/fixtures.py --root $ROOT --teardown

# 5. drop the now-dangling fixture vectors and rebuild the index, so the
#    live catalogue is not left with rows and an index pointing at files
#    that no longer exist
sqlite3 $ROOT/.tagvec/tag_vectors.sqlite \
  "DELETE FROM concept_emb WHERE path LIKE '%/_okfeval-%';"
python3 cli/okf-cli.py --root $ROOT build-index
```

Expected: `GATE: PASS`. The gate checks that the paraphrase zero-hit rate decreased and that no literal S1 row regressed (`cli/eval/gate.py:56-81`). `mean_score_ratio` will move because of the 0..100 scale — that is expected and ungated; note it in the commit body.

Verify the catalogue is clean afterwards:

```bash
find $ROOT -name "_okfeval-*" | wc -l
sqlite3 $ROOT/.tagvec/tag_vectors.sqlite \
  "SELECT COUNT(*) FROM concept_emb WHERE path LIKE '%/_okfeval-%';"
```
Expected: `0` and `0`.

- [ ] **Step 5: Record the numbers as new references**

Append to `docs/okf-retrieval-architecture/REFERENCES.md`, continuing the R-numbering after R43:

```markdown
R44 — **Shipped architecture, measured through the real CLI** (`eval/remeasure.py`,
n=48 = queries_v2 + queries_real, live catalogue): fill in the table from
`shipped_v2.json` — R@1, R@10, MRR, zero-hit, latency p50/max — next to R42's
`K` row so the delta against the pre-plan state is readable in one place.

R45 — **Fixture gate after the architecture change**: baseline
`cli/eval/results/baseline-f0714b2.json` vs `architecture-<sha>.json`, verdict
and the two gated quantities (paraphrase zero-hit, literal S1 ranks).
```

Replace the instruction text with the actual numbers — a reference with a placeholder in it is worse than no reference.

- [ ] **Step 6: Commit**

```bash
git add docs/okf-retrieval-architecture/eval/remeasure.py \
        docs/okf-retrieval-architecture/eval/shipped_v2.json \
        docs/okf-retrieval-architecture/REFERENCES.md \
        cli/eval/runner.py cli/eval/results/
git commit -m "test(eval): re-measure shipped retrieval, gate pass"
```

---

### Task 10: Informative zero-hit (T07, closes Q13)

**Files:**
- Modify: `cli/okf-cli.py:881-883` (the `(no matches …)` branch)
- Test: `cli/test_okf_cli.py`

**Interfaces:**
- Consumes: `all_tags(root)` (`cli/okf-cli.py:196`), `difflib` (already imported, line 50).
- Produces: `_zero_hit_suggestions(root, query, limit=5) -> list[str]` — registered tag slugs closest to the query terms, best first, possibly empty.

**Rationale:** the consumer of `find` is usually an agent over MCP, and an agent can reformulate if it learns *why* nothing matched (Q13). This changes only the zero-hit branch — a query with hits prints exactly as before.

- [ ] **Step 1: Write the failing tests**

```python
class ZeroHitSuggestions(unittest.TestCase):
    """T07/Q13 — a zero hit should hand the caller something to reformulate
    with, not just '(no matches)'."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "b"))
        with open(os.path.join(self.root, "b", "one.md"), "w",
                  encoding="utf-8") as f:
            f.write("---\ntype: Runbook\ntitle: One\ndescription: d\n"
                    "tags: [excalidraw, tailscale]\n---\nbody\n")
        with open(os.path.join(self.root, "b", "index.md"), "w",
                  encoding="utf-8") as f:
            f.write("# B\n")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_near_miss_term_suggests_the_registered_tag(self):
        got = okf._zero_hit_suggestions(self.root, "tailscal")
        self.assertIn("tailscale", got)

    def test_unrelated_query_may_return_nothing(self):
        got = okf._zero_hit_suggestions(self.root, "zzzzqqqq")
        self.assertEqual(got, [])

    def test_output_names_the_suggestions(self):
        out = _run_find(self.root, "tailscal")
        self.assertIn("(no matches for: tailscal)", out)
        self.assertIn("tailscale", out)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest cli.test_okf_cli.ZeroHitSuggestions -v`
Expected: FAIL — `AttributeError: module 'okf_cli' has no attribute '_zero_hit_suggestions'`.

- [ ] **Step 3: Implement**

Add next to the other find helpers:

```python
def _zero_hit_suggestions(root, query, limit=5):
    """Registered tag slugs closest to the query's terms — the reformulation
    hint a zero hit hands back (Q13). difflib only: no network, no vectors, so
    this works on the fully degraded path too."""
    tags = sorted(all_tags(root))
    if not tags:
        return []
    out = []
    for term in tokenize(query):
        for cand in difflib.get_close_matches(term, tags, n=limit, cutoff=0.7):
            if cand not in out:
                out.append(cand)
    return out[:limit]
```

Replace lines 881-883 with:

```python
    if not all_hits:
        print("(no matches for: {})".format(args.query))
        near = _zero_hit_suggestions(root, args.query)
        if near:
            print("nearest registered tags: {}".format(", ".join(near)))
            print("try: okf-cli find \"{}\"".format(" ".join(near[:2])))
        return
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest cli.test_okf_cli -v 2>&1 | tail -5`
Expected: PASS for the new class; total still exactly 19 failures, 2 errors.

Note: `cli/eval/runner.py:64 _parse_find_blocks` only reads `score:`/`path:` lines between `------` markers, so the extra lines cannot confuse it. Confirm by re-running the gate command from Task 9 Step 4 — it must still say `GATE: PASS`.

- [ ] **Step 5: Commit**

```bash
git add cli/okf-cli.py cli/test_okf_cli.py
git commit -m "feat(cli): suggest nearest tags on zero hit"
```

---

### Task 11: Tag query expansion behind a flag (T05, Q05/Q06)

**Files:**
- Modify: `cli/okf-cli.py` (expansion helper + `--expand-tags` flag on `find`)
- Test: `cli/test_okf_cli.py`
- Modify: `docs/okf-retrieval-architecture/QUESTIONS.md`

**Interfaces:**
- Consumes: the `emb` table of `.tagvec` (752 bge-m3 + 650 voyage rows, R09), `_load_concept_vectors`'s sibling read pattern, `_embed_query_voyage` (Task 7), `_cosine`.
- Produces: `_expand_query_tags(root, query, top_k=3, floor=0.6) -> list[str]` — extra tag slugs to append to the lexical query terms; `[]` on any degradation.

**Flag-gated by decision (D17).** This is the only change in the plan that alters ranking without prior measurement. It ships behind `--expand-tags`, off by default, and becomes a default only after Step 6 shows it does not regress the numbers from Task 9.

**Where it fires.** Expansion is a *rescue* path, on the same terms as the semantic arm: it runs only when the unexpanded lexical arm is not confident. Running it on every query would spend a network call on exactly the queries that did not need one, which contradicts Task 8's cost rule. Concretely: run the lexical arm once unexpanded → if `_keyword_top1_is_confident()` says it owns the ranking, stop; otherwise expand and re-run the lexical arm with the widened term set.

**Q06 answered by construction.** A query term that is not a registered tag never needs its own embedding call — expansion embeds the *whole query* and compares it against the tag vectors. And because the semantic arm embeds the same string in the same invocation, Step 3 adds a one-entry cache so both share a single call.

- [ ] **Step 1: Write the failing tests**

```python
class ExpandQueryTags(unittest.TestCase):
    """T05/Q05 — the tag vectors are already populated and clean (R09); this
    asks whether they can pull a synonym into the lexical query."""

    def setUp(self):
        okf._QUERY_VEC_CACHE.clear()

    def _seed(self, root, rows):
        db = okf._tagvec_db_path(root)
        os.makedirs(os.path.dirname(db), exist_ok=True)
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE IF NOT EXISTS emb(key TEXT PRIMARY KEY, "
                     "tag TEXT, model TEXT, dim INT, vec BLOB)")
        conn.executemany("INSERT OR REPLACE INTO emb VALUES(?,?,?,?,?)", rows)
        conn.commit()
        conn.close()

    def test_returns_nearest_tag_above_the_floor(self):
        root = tempfile.mkdtemp()
        try:
            self._seed(root, [
                ("k1", "excalidraw", "voyage-3-large", 2,
                 struct.pack("<2f", 1.0, 0.0)),
                ("k2", "invoicing", "voyage-3-large", 2,
                 struct.pack("<2f", 0.0, 1.0)),
            ])
            orig = okf._embed_query_voyage
            okf._embed_query_voyage = lambda _t: [1.0, 0.0]
            try:
                got = okf._expand_query_tags(root, "mockup")
            finally:
                okf._embed_query_voyage = orig
            self.assertEqual(got, ["excalidraw"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_returns_empty_without_a_cache(self):
        root = tempfile.mkdtemp()
        try:
            self.assertEqual(okf._expand_query_tags(root, "mockup"), [])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_returns_empty_when_nothing_clears_the_floor(self):
        root = tempfile.mkdtemp()
        try:
            self._seed(root, [("k1", "invoicing", "voyage-3-large", 2,
                               struct.pack("<2f", 0.0, 1.0))])
            orig = okf._embed_query_voyage
            okf._embed_query_voyage = lambda _t: [1.0, 0.0]
            try:
                self.assertEqual(okf._expand_query_tags(root, "mockup"), [])
            finally:
                okf._embed_query_voyage = orig
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_find_without_the_flag_does_not_expand(self):
        root = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(root, "b"))
            with open(os.path.join(root, "b", "one.md"), "w",
                      encoding="utf-8") as f:
                f.write("---\ntype: Runbook\ntitle: One\ndescription: d\n"
                        "tags: [excalidraw]\n---\nbody\n")
            with open(os.path.join(root, "b", "index.md"), "w",
                      encoding="utf-8") as f:
                f.write("# B\n")
            out = _run_find(root, "mockup")
            self.assertIn("(no matches for: mockup)", out)
        finally:
            shutil.rmtree(root, ignore_errors=True)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest cli.test_okf_cli.ExpandQueryTags -v`
Expected: FAIL — `AttributeError: module 'okf_cli' has no attribute '_expand_query_tags'`.

- [ ] **Step 3: Implement**

```python
def _load_tag_vectors(db_path, model):
    """[(tag, [float, ...]), ...] from the `emb` table, or None when the cache
    or the model's rows are absent — mirrors _load_concept_vectors()."""
    if not os.path.isfile(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT tag, dim, vec FROM emb WHERE model = ?", (model,)
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return None
    if not rows:
        return None
    return [(tag, list(struct.unpack("<{}f".format(dim), blob)))
            for tag, dim, blob in rows]


def _expand_query_tags(root, query, top_k=3, floor=0.6):
    """Registered tag slugs semantically near the query (Q05). Reuses the
    query vector the semantic arm needs anyway, which is what makes Q06 moot:
    a query term that is not a registered tag never needs its own embedding
    call. Returns [] on any degradation — expansion is an enhancement, never a
    precondition. The floor exists because a nearest neighbour is always
    returned otherwise; unlike the concept case (R34, no separable floor),
    tag slugs are short, clean labels where a cutoff is defensible — that is
    exactly what Step 6 measures."""
    vectors = _load_tag_vectors(_tagvec_db_path(root), SEMANTIC_MODEL)
    if not vectors:
        return []
    try:
        qvec = _query_vector(query)
    except Exception:
        return []
    ranked = sorted(((_cosine(qvec, v), tag) for tag, v in vectors),
                    key=lambda x: -x[0])
    return [tag for score, tag in ranked[:top_k] if score >= floor]
```

Share the query vector between the two consumers. Add above `_embed_query_voyage`:

```python
# One CLI invocation answers one query, and both the semantic arm and (when
# enabled) tag expansion embed the SAME string. Cache it so --expand-tags
# costs zero extra network calls rather than doubling them.
_QUERY_VEC_CACHE = {}


def _query_vector(text):
    """Cached _embed_query_voyage(). Raises exactly what it raises, so every
    caller keeps its own degradation behaviour."""
    if text not in _QUERY_VEC_CACHE:
        _QUERY_VEC_CACHE[text] = _embed_query_voyage(text)
    return _QUERY_VEC_CACHE[text]
```

Change `semantic_ranking()` (Task 7) and `_expand_query_tags()` to call `_query_vector(query)` instead of `_embed_query_voyage(query)` directly. The tests monkeypatch `_embed_query_voyage`, which still works — but each test that patches it must clear the cache in `setUp` with `okf._QUERY_VEC_CACHE.clear()`, or a value from a previous test leaks in.

In `cmd_find`, wire expansion as a rescue path **after** the first lexical pass and **before** the semantic arm. Replace the gate block from Task 8, Step 4 with:

```python
    lexical_owned_provisionally = _keyword_top1_is_confident(hits)

    # T05/Q05 (experimental, off by default): when the unexpanded lexical arm
    # is not confident, widen the query with semantically near registered tags
    # and give the lexical arm a second chance. Deliberately NOT run when the
    # lexical arm is already confident — that query needs no rescue, and the
    # call would be pure cost (same rule the semantic arm follows below).
    if getattr(args, "expand_tags", False) and not lexical_owned_provisionally:
        extra = _expand_query_tags(root, args.query)
        if extra:
            print("note: query expanded with tag(s): {}".format(
                ", ".join(extra)), file=sys.stderr)
            terms = terms + [t for t in extra if t not in terms]
            hits, max_score = _rank_lexically(
                root, " ".join(terms), terms, args.limit,
                type_filter, tag_filter, target)
            lexical_owned_provisionally = _keyword_top1_is_confident(hits)

    semantic_hits = []
    if not lexical_owned_provisionally or len(hits) < args.limit:
        semantic_hits = _semantic_hit_dicts(root, args.query, args.limit)

    all_hits, lexical_owned = fuse_conditional(hits, semantic_hits, args.limit)
    if not lexical_owned and semantic_hits:
        print("note: semantic arm owns this ranking (lexical top-1 lacked a "
              "clear margin)", file=sys.stderr)
```

`_rank_lexically` is the helper Task 6, Step 5 already introduced — the second pass reuses it unchanged, including its `max_score`, which is why the rebind above assigns both names.

Note that the semantic arm still embeds `args.query`, never the expanded string: widening a query before embedding it dilutes the vector — the exact contamination `cli/embeddings/README.md:27-35` (R06) documents for tags.

Register the flag next to the other `find` options (line 2222-2231):

```python
    pf.add_argument("--expand-tags", action="store_true",
                    help="expand the query with semantically near registered "
                         "tags before lexical scoring (experimental, off by "
                         "default until measured)")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest cli.test_okf_cli -v 2>&1 | tail -5`
Expected: PASS for the new class; total still exactly 19 failures, 2 errors.

- [ ] **Step 5: Commit the implementation**

```bash
git add cli/okf-cli.py cli/test_okf_cli.py
git commit -m "feat(cli): experimental --expand-tags query expansion"
```

- [ ] **Step 6: Measure it, then decide**

`remeasure.py` runs `find` without the flag. Add a passthrough. In
`docs/okf-retrieval-architecture/eval/remeasure.py`, thread an `extra` argv
list through `ranked_paths` and `measure`:

```python
def ranked_paths(root, query, limit, extra=()):
    """Ordered result paths of one `okf-cli find`, plus its wall time."""
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable, CLI, "--root", root, "find", query,
         "--limit", str(limit), *extra],
        capture_output=True, text=True)
    elapsed = time.time() - t0
    paths = [line[len("path: "):] for line in proc.stdout.splitlines()
             if line.startswith("path: ")]
    return paths, elapsed
```

```python
def measure(root, rows, limit, extra=()):
    ...
        paths, elapsed = ranked_paths(root, row["query"], limit, extra)
```

```python
    ap.add_argument("--find-arg", action="append", default=[], dest="find_args",
                    help="extra argument passed through to `okf-cli find`; "
                         "repeatable")
```

and pass `args.find_args` into both `measure(...)` calls in `main()`. Then run both:

```bash
python3 docs/okf-retrieval-architecture/eval/remeasure.py \
  --root ~/Obsidian/Knowledge-Catalogue \
  --queries queries_v2.json queries_real.json --out shipped_expand.json \
  --find-arg --expand-tags
```

Compare `shipped_expand.json` against `shipped_v2.json` from Task 9.

- **MRR improves and zero-hit does not rise** → propose making it the default to the PO, with the two JSON files as evidence. Do not flip the default yourself.
- **otherwise** → the flag stays off. Record the result in `QUESTIONS.md` as the answer to Q05/Q06 and say plainly that expansion did not pay.

Either way, update the Q05 and Q06 rows in `docs/okf-retrieval-architecture/QUESTIONS.md` from 🟣 to 🟢 with the measured outcome, and commit:

```bash
git add docs/okf-retrieval-architecture/eval/shipped_expand.json \
        docs/okf-retrieval-architecture/eval/remeasure.py \
        docs/okf-retrieval-architecture/QUESTIONS.md
git commit -m "test(eval): measure tag expansion, answer Q05/Q06"
```

---

### Task 12: Failure taxonomy (T03, closes Q03/Q10)

**Files:**
- Create: `docs/okf-retrieval-architecture/eval/taxonomy.md`
- Modify: `docs/okf-retrieval-architecture/QUESTIONS.md` (Q03, Q10)

**Interfaces:**
- Consumes: `shipped_v2.json` from Task 9 and the query files.
- Produces: a per-query classification table for every query where the target did not reach rank 10.

Analysis, not code. The point is to separate what retrieval design can still fix from what it cannot.

- [ ] **Step 1: Collect the failures**

Extend `remeasure.py` to write the per-row detail it already computes (query, expected path, achieved rank, and the top-3 returned paths) into the output JSON under a `"rows"` key, then re-run it. Without the returned paths a failure cannot be classified.

- [ ] **Step 2: Classify every failure**

For each failing query, open the expected concept (`okf-cli read <path>`) and the top-3 returned concepts, and assign exactly one class:

| Class | Definition | Fixable by |
|-------|------------|------------|
| `catalogue-gap` | No concept in the catalogue actually answers the query (Q10) | Writing, not retrieval |
| `synonymy` | The concept answers it but shares no vocabulary, and the embedding still missed | Better model or aliases (Q14) |
| `ranking` | The target was retrieved but below rank 10 | Fusion / weighting |
| `wrong-target` | The query's recorded `expected_path` is itself questionable | Fix the query set |

- [ ] **Step 3: Write the taxonomy**

Create `docs/okf-retrieval-architecture/eval/taxonomy.md` with a header naming the measurement it is based on (file + git sha + date), one table row per failing query (`query | expected_path | rank | class | note`), and a short count summary per class. No prose beyond that.

- [ ] **Step 4: Answer the questions**

Update `docs/okf-retrieval-architecture/QUESTIONS.md`: Q03 from 🟡 to 🟢 with the class split, Q10 from 🟣 to 🟢 with the `catalogue-gap` count and share. If `catalogue-gap` dominates, say so explicitly — it means the next lever is authoring, not retrieval, and that belongs in the follow-up bean `okf-cli-iw0d`.

- [ ] **Step 5: Commit**

```bash
git add docs/okf-retrieval-architecture/eval/taxonomy.md \
        docs/okf-retrieval-architecture/eval/remeasure.py \
        docs/okf-retrieval-architecture/eval/shipped_v2.json \
        docs/okf-retrieval-architecture/QUESTIONS.md
git commit -m "docs(eval): failure taxonomy, answer Q03/Q10"
```

---

### Task 13: Documentation sync

**Files:**
- Modify: `cli/embeddings/README.md`
- Modify: `docs/CLAUDE.md:12` (I01)
- Modify: `docs/okf-retrieval-architecture/{DECISIONS,TASKS,QUESTIONS}.md`
- Modify: `docs/SSTD.md`

- [ ] **Step 1: Producer README**

In `cli/embeddings/README.md`, document what Tasks 1-3 changed: batching limits per model and why (`BATCH_LIMITS`, LL-09), the retry/halve/skip ladder and that a skipped batch simply reappears in the next delta plan (LL-08), that rows are written per batch so a run is resumable, and that `concept_emb` now holds `voyage-3-large` rows for the whole catalogue (2437) while `emb` keeps both models for tags.

- [ ] **Step 2: Fix I01**

In `docs/CLAUDE.md:12`, replace the `plans/<beans-id>-<slug>/` line with:

```markdown
- **`<topic-slug>/`** — one folder per topic: the whole think chain co-located
  (SPEC/DECISIONS/QUESTIONS/TASKS/REFERENCES) plus `PLAN.md`. Both brainstorming
  and writing-plans write here. No separate `plans/` folder — the governing
  `/tools/CLAUDE.md` Docs-Standard forbids it (one topic, one folder).
```

If `docs/plans/` still holds files, leave them where they are and note the discrepancy to the PO rather than moving history around.

- [ ] **Step 3: Bring the think collection up to date**

- `DECISIONS.md`: append D14, D15, D16, D17 with the wording from this plan's "Decisions this plan implements" table, each with its Warum.
- `TASKS.md`: T10, T11, T12, T13 → 🟢 with the commit shas; T03, T05, T07 → 🟢 or 🔴 per the measured outcome; T14/T15/T09 → 🟢 (already true before this plan).
- `QUESTIONS.md`: Q09 → 🟢 (D15). Q03/Q10 come from Task 12, Q05/Q06 from Task 11. Q08 (latency) → 🟢 with the p50/max from Task 9.

- [ ] **Step 4: SSTD entry point**

Update the Entry-Point section of `docs/SSTD.md`: the retrieval architecture shipped, which bean covers it, where the measurement lives (`eval/shipped_v2.json`, `eval/taxonomy.md`), and that the merge gate to `main` is the PO's next call. Remove the "parallel session owns Q03" warning — that session is this one, and it is done.

- [ ] **Step 5: Commit**

```bash
git add cli/embeddings/README.md docs/CLAUDE.md docs/SSTD.md \
        docs/okf-retrieval-architecture/DECISIONS.md \
        docs/okf-retrieval-architecture/TASKS.md \
        docs/okf-retrieval-architecture/QUESTIONS.md
git commit -m "docs: sync retrieval architecture end state"
```

- [ ] **Step 6: Final verification**

```bash
python3 -m unittest discover -s cli -p 'test_*.py' 2>&1 | tail -5
git status --short
```
Expected: exactly 19 failures, 2 errors; working tree clean except files owned by another session.

---

## Deferred — not in this plan

| Item | Why deferred |
|------|--------------|
| Q14 alias frontmatter field | Author-time synonym resolution. Task 12's taxonomy decides whether it is worth it; building it first would be another unmeasured intuition. |
| Q15 navigation instead of search | Questions the premise that search is the access path. Real, but a different product question. |
| MCP registration of `build-index` | The MCP surface exposes read verbs plus `reindex`; adding a second index-mutating verb needs its own decision. Note it for the PO. |
| Promoting `bge-m3` to a runtime fallback | Ruled out by D16 in this plan. Revisit only if voyage availability turns out to be a practical problem. |
