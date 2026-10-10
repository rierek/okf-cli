#!/usr/bin/env python3
"""Tests for cli/okf/semantic.py — the semantic arm: query embedding, cosine ranking, tag expansion and coverage. Stdlib unittest, no deps.

Run: python3 -m unittest test_okf_semantic -v
"""
import json
import os
import shutil
import sqlite3
import struct
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:  # cli/ holds the okf package; a repo-root run lacks it
    sys.path.insert(0, _HERE)

from okf import catalogue as okf_catalogue
from okf import find as okf_find
from okf import find_filters as okf_find_filters
from okf import semantic as okf_semantic
from okf_testkit import run_find


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

        orig = okf_semantic.urllib.request.urlopen
        okf_semantic.urllib.request.urlopen = _fake_urlopen
        try:
            vec = okf_semantic._embed_query_voyage("mockup tailscale")
        finally:
            okf_semantic.urllib.request.urlopen = orig

        self.assertEqual(vec, [0.5, 0.5])
        self.assertEqual(seen["payload"]["model"], "voyage-3-large")
        self.assertEqual(seen["payload"]["input_type"], "query")
        self.assertEqual(seen["payload"]["input"], ["mockup tailscale"])
        self.assertEqual(seen["auth"], "Bearer test-key")

    def test_missing_api_key_raises_so_the_caller_can_degrade(self):
        os.environ.pop("VOYAGE_API_KEY", None)
        with self.assertRaises(RuntimeError):
            okf_semantic._embed_query_voyage("x")


class SemanticRankingDegradation(unittest.TestCase):
    """R05/D16 — every failure mode returns [] plus one stderr note, and none
    of them raises."""

    def test_absent_cache_returns_empty(self):
        root = tempfile.mkdtemp()
        try:
            self.assertEqual(okf_semantic.semantic_ranking(root, "x", 10, okf_find_filters.FindFilters()), [])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_unreachable_backend_returns_empty(self):
        root = tempfile.mkdtemp()
        try:
            db = okf_semantic._tagvec_db_path(root)
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

            orig = okf_semantic._embed_query_voyage
            okf_semantic._embed_query_voyage = _raise
            try:
                self.assertEqual(okf_semantic.semantic_ranking(root, "x", 10, okf_find_filters.FindFilters()), [])
            finally:
                okf_semantic._embed_query_voyage = orig
        finally:
            shutil.rmtree(root, ignore_errors=True)


class SemanticCoverageSharesTheProducersDetector(unittest.TestCase):
    """OKFT-9wk6 — semantic_coverage() used to compare PATH sets against
    concept_emb only, so a concept whose body changed after embedding still
    counted as covered: its old row's path still matched. The producer,
    plan_concept_delta(), already carries the correct detector -- a
    content-hash comparison via concept_cache_key(model, path, text). This
    is the OKF concept detector-and-autofixer-must-share-the-same-scan: the
    checker and the producer must run the same scan, not two.

    Each test builds its embedded row through split_frontmatter/read_file/
    concept_text()/concept_cache_key() -- the exact sequence
    plan_concept_delta() runs per concept -- never a hand-rolled sha1, so a
    passing test proves the shared detector, not a re-implementation of it."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.ap = os.path.join(self.root, "b", "one.md")
        os.makedirs(os.path.dirname(self.ap))
        self._write("original body")
        self.bt = okf_catalogue._load_build_tagvec()
        self.db = okf_semantic._tagvec_db_path(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _write(self, body):
        with open(self.ap, "w", encoding="utf-8") as f:
            f.write("---\ntype: Runbook\ntitle: One\n---\n{}\n".format(body))

    def _embed_current_content(self):
        fm, body = okf_catalogue.split_frontmatter(okf_catalogue.read_file(self.ap))
        title = okf_catalogue._dequote(fm.get("title", "")) or "one"
        text = self.bt.concept_text(title, body)
        key = self.bt.concept_cache_key(okf_semantic.SEMANTIC_MODEL, "b/one", text)
        self.bt.write_concept_rows(
            self.db,
            [(key, "b/one", okf_semantic.SEMANTIC_MODEL, 2, self.bt.pack_vec([1.0, 0.0]))])

    def test_covered_when_the_embedded_key_matches_current_content(self):
        self._embed_current_content()
        self.assertEqual(okf_semantic.semantic_coverage(self.root, ["b/one"]), (1, 1))

    def test_stale_after_a_body_edit_though_the_path_is_still_present(self):
        """The regression this closes: the OLD implementation returned (1, 1)
        here, because b/one's PATH was still in concept_emb -- the row just
        carried a key for content that no longer exists on disk."""
        self._embed_current_content()
        self._write("changed body")
        self.assertEqual(okf_semantic.semantic_coverage(self.root, ["b/one"]), (0, 1))


class ExpandQueryTags(unittest.TestCase):
    """T05/Q05 — the tag vectors are already populated and clean (R09); this
    asks whether they can pull a synonym into the lexical query."""

    def setUp(self):
        okf_semantic._QUERY_VEC_CACHE.clear()

    def _seed(self, root, rows):
        db = okf_semantic._tagvec_db_path(root)
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
            orig = okf_semantic._embed_query_voyage
            okf_semantic._embed_query_voyage = lambda _t: [1.0, 0.0]
            try:
                got = okf_semantic._expand_query_tags(root, "mockup")
            finally:
                okf_semantic._embed_query_voyage = orig
            self.assertEqual(got, ["excalidraw"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_returns_empty_without_a_cache(self):
        root = tempfile.mkdtemp()
        try:
            self.assertEqual(okf_semantic._expand_query_tags(root, "mockup"), [])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_returns_empty_when_nothing_clears_the_floor(self):
        root = tempfile.mkdtemp()
        try:
            self._seed(root, [("k1", "invoicing", "voyage-3-large", 2,
                               struct.pack("<2f", 0.0, 1.0))])
            orig = okf_semantic._embed_query_voyage
            okf_semantic._embed_query_voyage = lambda _t: [1.0, 0.0]
            try:
                self.assertEqual(okf_semantic._expand_query_tags(root, "mockup"), [])
            finally:
                okf_semantic._embed_query_voyage = orig
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
            out = run_find(root, "mockup")
            self.assertIn("(no matches for: mockup)", out)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_confident_lexical_arm_skips_expansion_entirely(self):
        """AC-2 (F06-forced): expansion is a rescue path, not a blanket
        cost. A single hit makes _keyword_top1_is_confident() True by
        construction (nothing to be ambiguous against), so the flag being on
        must never even call _expand_query_tags — spied with a raiser, not
        just checked for a stderr note, so a future refactor that widens the
        gate condition fails loudly instead of silently billing a network
        call per query."""
        root = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(root, "b"))
            with open(os.path.join(root, "b", "one.md"), "w",
                      encoding="utf-8") as f:
                f.write("---\ntype: Runbook\ntitle: Zzzznique concept\n"
                        "description: d\ntags: [excalidraw]\n---\nbody\n")
            with open(os.path.join(root, "b", "index.md"), "w",
                      encoding="utf-8") as f:
                f.write("# B\n")

            def _spy(*_a, **_kw):
                raise AssertionError(
                    "_expand_query_tags must not be called when the "
                    "lexical arm is already confident")

            orig = okf_semantic._expand_query_tags
            okf_semantic._expand_query_tags = _spy
            try:
                out = run_find(root, "zzzznique", expand_tags=True)
            finally:
                okf_semantic._expand_query_tags = orig
            self.assertIn("path: b/one", out)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_rescue_rerun_does_not_double_the_degradation_note(self):
        """B02/PF-4 — --expand-tags reruns the lexical arm a second time
        within one `find`, over the SAME (missing) .fts index. Without
        notify=False on the rescue rerun, `_fts_ranking`'s "index absent"
        note would print twice, with the expansion note sandwiched between
        them — a degradation note describes the invocation, not the
        individual arm pass."""
        root = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(root, "b"))
            with open(os.path.join(root, "b", "one.md"), "w",
                      encoding="utf-8") as f:
                f.write("---\ntype: Runbook\ntitle: One\ndescription: d\n"
                        "tags: [widget]\n---\nbody\n")
            with open(os.path.join(root, "b", "index.md"), "w",
                      encoding="utf-8") as f:
                f.write("# B\n")

            db = okf_semantic._tagvec_db_path(root)
            os.makedirs(os.path.dirname(db), exist_ok=True)
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE IF NOT EXISTS emb(key TEXT PRIMARY "
                         "KEY, tag TEXT, model TEXT, dim INT, vec BLOB)")
            conn.executemany(
                "INSERT OR REPLACE INTO emb VALUES(?,?,?,?,?)",
                [("k1", "widget", "voyage-3-large", 2,
                  struct.pack("<2f", 1.0, 0.0))])
            conn.commit()
            conn.close()

            import io
            import contextlib
            import types
            orig = okf_semantic._embed_query_voyage
            okf_semantic._embed_query_voyage = lambda _t: [1.0, 0.0]
            try:
                args = types.SimpleNamespace(
                    query="gizmo", limit=10, type=None, tag=None,
                    scope=None, breakdown=False, expand_tags=True)
                out_buf, err_buf = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out_buf), \
                     contextlib.redirect_stderr(err_buf):
                    okf_find.cmd_find(root, args)
            finally:
                okf_semantic._embed_query_voyage = orig

            err_lines = [l for l in err_buf.getvalue().splitlines() if l]
            absent_notes = [l for l in err_lines
                            if "lexical index absent" in l]
            self.assertEqual(len(absent_notes), 1, err_lines)
            self.assertIn("note: query expanded with tag(s): widget",
                          err_buf.getvalue())
        finally:
            shutil.rmtree(root, ignore_errors=True)
