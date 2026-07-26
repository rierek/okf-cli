#!/usr/bin/env python3
"""Tests for cli/embeddings/build_tagvec.py (P7 / okf-cli-3geg).

Network-free by construction: every test here exercises parsing, the
sha1 cache-key scheme, and the delta-plan against a real (tmp) sqlite —
none of it calls Ollama or Voyage. The --produce network path is exercised
manually only (see cli/embeddings/README.md); it must never run under test
or at import time.

Run: python3 -m unittest cli.test_embeddings_tagvec -v
"""
import hashlib
import importlib.util
import json
import os
import shutil
import sqlite3
import struct
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "build_tagvec", os.path.join(_HERE, "embeddings", "build_tagvec.py"))
bt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bt)


def _w(root, rel, text):
    ap = os.path.join(root, rel)
    os.makedirs(os.path.dirname(ap), exist_ok=True)
    with open(ap, "w", encoding="utf-8") as f:
        f.write(text)


def _make_tmp_catalogue():
    root = tempfile.mkdtemp()
    _w(root, "b/one.md",
       "---\ntype: Runbook\ntitle: One\ndescription: first\ntags: [task-brief, git]\n"
       "---\n# One\n")
    _w(root, "b/two.md",
       "---\ntype: Runbook\ntitle: Two\ndescription: second\ntags: [git]\n"
       "---\n# Two\n")
    _w(root, "b/index.md", "# B\n\nSee [One](one.md).\n")
    return root


class SlugText(unittest.TestCase):
    """SC-003 grounding: slug-only, NOT context-enriched (SOP critical decision)."""

    def test_hyphens_become_spaces(self):
        self.assertEqual(bt.slug_text("task-brief"), "task brief")

    def test_no_hyphen_passthrough(self):
        self.assertEqual(bt.slug_text("git"), "git")


class CacheKey(unittest.TestCase):
    """Must match the live cache's key scheme (RET10):
    key = sha1(model + '\\x00slug\\x00' + text)."""

    def test_matches_documented_scheme(self):
        model, text = "bge-m3", "task brief"
        expected = hashlib.sha1(
            (model + "\x00slug\x00" + text).encode("utf-8")).hexdigest()
        self.assertEqual(bt.cache_key(model, text), expected)

    def test_differs_by_model(self):
        self.assertNotEqual(
            bt.cache_key("bge-m3", "git"), bt.cache_key("voyage-3-large", "git"))


class PlanDelta(unittest.TestCase):
    """Delta-reuse gate (SOP): only tags without a cache key get (re-)planned."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "tag_vectors.sqlite")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_db_yet_plans_everything(self):
        delta = bt.plan_delta({"git", "task-brief"}, "bge-m3", self.db)
        planned_tags = {tag for tag, _text, _key in delta}
        self.assertEqual(planned_tags, {"git", "task-brief"})

    def test_existing_key_is_skipped(self):
        key = bt.cache_key("bge-m3", "git")
        conn = sqlite3.connect(self.db)
        conn.execute(bt.SCHEMA)
        conn.execute(
            "INSERT INTO emb(key, tag, model, dim, vec) VALUES (?, ?, ?, ?, ?)",
            (key, "git", "bge-m3", 4, struct.pack("<4f", 0.1, 0.2, 0.3, 0.4)),
        )
        conn.commit()
        conn.close()

        delta = bt.plan_delta({"git", "task-brief"}, "bge-m3", self.db)
        planned_tags = {tag for tag, _text, _key in delta}
        self.assertEqual(planned_tags, {"task-brief"})

    def test_different_model_is_independent(self):
        """bge-m3 and voyage-3-large rows coexist — a cached bge-m3 key must
        not suppress the voyage-3-large plan for the same tag."""
        key = bt.cache_key("bge-m3", "git")
        conn = sqlite3.connect(self.db)
        conn.execute(bt.SCHEMA)
        conn.execute(
            "INSERT INTO emb(key, tag, model, dim, vec) VALUES (?, ?, ?, ?, ?)",
            (key, "git", "bge-m3", 4, struct.pack("<4f", 0.1, 0.2, 0.3, 0.4)),
        )
        conn.commit()
        conn.close()

        delta = bt.plan_delta({"git"}, "voyage-3-large", self.db)
        self.assertEqual({tag for tag, _t, _k in delta}, {"git"})


class MainNoNetworkWithoutProduce(unittest.TestCase):
    """--produce is the ONLY gate for network calls (hard constraint)."""

    def setUp(self):
        self.root = _make_tmp_catalogue()
        self.tmp_out = tempfile.mkdtemp()
        self.output = os.path.join(self.tmp_out, "tag_vectors.sqlite")
        self._orig_bge = bt.embed_bge_m3
        self._orig_voyage = bt.embed_voyage
        self.calls = []
        bt.embed_bge_m3 = lambda texts: self.calls.append(("bge-m3", texts)) or []
        bt.embed_voyage = lambda texts: self.calls.append(("voyage", texts)) or []

    def tearDown(self):
        bt.embed_bge_m3 = self._orig_bge
        bt.embed_voyage = self._orig_voyage
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.tmp_out, ignore_errors=True)

    def test_dry_run_never_calls_network_functions(self):
        rc = bt.main(["--root", self.root, "--output", self.output])
        self.assertEqual(rc, 0)
        self.assertEqual(self.calls, [])
        self.assertFalse(os.path.exists(self.output))

    def test_produce_flag_invokes_embed_functions(self):
        rc = bt.main(["--root", self.root, "--output", self.output,
                       "--model", "bge-m3", "--produce"])
        self.assertEqual(rc, 0)
        self.assertTrue(any(name == "bge-m3" for name, _texts in self.calls))


class ParserHelp(unittest.TestCase):
    def test_help_exits_zero(self):
        with self.assertRaises(SystemExit) as cm:
            bt.build_parser().parse_args(["--help"])
        self.assertEqual(cm.exception.code, 0)


class ConceptText(unittest.TestCase):
    """P8/8c (okf-cli-8uaf) — the corrected Task-7 finding requires the
    producer to ALSO embed titles/bodies (not tags only), so S3-class
    body-only-token concepts are reachable by the semantic backstop."""

    def test_combines_title_and_body(self):
        text = bt.concept_text("One", "prose body here")
        self.assertIn("One", text)
        self.assertIn("prose body here", text)


class ConceptCacheKey(unittest.TestCase):
    def test_matches_documented_scheme(self):
        model, path, text = "bge-m3", "b/one", "One\n\nprose"
        expected = hashlib.sha1(
            (model + "\x00concept\x00" + path + "\x00" + text).encode("utf-8")
        ).hexdigest()
        self.assertEqual(bt.concept_cache_key(model, path, text), expected)

    def test_differs_by_path_not_just_text(self):
        # same text, different path -> different key (path-scoped, unlike
        # tag keys, so re-embedding responds to a concept's identity too)
        k1 = bt.concept_cache_key("bge-m3", "b/one", "same text")
        k2 = bt.concept_cache_key("bge-m3", "b/two", "same text")
        self.assertNotEqual(k1, k2)


class PlanConceptDelta(unittest.TestCase):
    def setUp(self):
        self.root = _make_tmp_catalogue()
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "tag_vectors.sqlite")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_db_yet_plans_every_concept(self):
        delta = bt.plan_concept_delta(self.root, "bge-m3", self.db)
        paths = {path for path, _text, _key in delta}
        self.assertEqual(paths, {"b/one", "b/two"})

    def test_existing_key_is_skipped(self):
        first = bt.plan_concept_delta(self.root, "bge-m3", self.db)
        rows = [(key, path, "bge-m3", 2, struct.pack("<2f", 0.1, 0.2))
                for path, _text, key in first if path == "b/one"]
        bt.write_concept_rows(self.db, rows)
        second = bt.plan_concept_delta(self.root, "bge-m3", self.db)
        paths = {path for path, _text, _key in second}
        self.assertEqual(paths, {"b/two"})

    def test_path_prefix_filters_candidates(self):
        delta = bt.plan_concept_delta(
            self.root, "bge-m3", self.db, path_prefix="b/one")
        paths = {path for path, _text, _key in delta}
        self.assertEqual(paths, {"b/one"})


class MainConceptsTarget(unittest.TestCase):
    """--target default stays "tags" (regression-safe); --target concepts/
    both additionally plans/produces title+body embeddings, still gated by
    --produce alone (hard constraint: no network without --produce)."""

    def setUp(self):
        self.root = _make_tmp_catalogue()
        self.tmp_out = tempfile.mkdtemp()
        self.output = os.path.join(self.tmp_out, "tag_vectors.sqlite")
        self._orig_bge = bt.embed_bge_m3
        self._orig_voyage = bt.embed_voyage
        self.calls = []
        bt.embed_bge_m3 = lambda texts: self.calls.append(("bge-m3", texts)) or [
            [0.1, 0.2] for _ in texts]
        bt.embed_voyage = lambda texts: self.calls.append(("voyage", texts)) or [
            [0.1, 0.2] for _ in texts]

    def tearDown(self):
        bt.embed_bge_m3 = self._orig_bge
        bt.embed_voyage = self._orig_voyage
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.tmp_out, ignore_errors=True)

    def test_default_target_never_touches_concept_emb(self):
        rc = bt.main(["--root", self.root, "--output", self.output,
                      "--model", "bge-m3", "--produce"])
        self.assertEqual(rc, 0)
        self.assertTrue(all(name == "bge-m3" for name, _texts in self.calls))
        # concept_emb table must not exist / stay empty — default is tags-only
        if os.path.exists(self.output):
            conn = sqlite3.connect(self.output)
            try:
                cur = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name='concept_emb'")
                row = cur.fetchone()
                if row:
                    count = conn.execute("SELECT COUNT(*) FROM concept_emb").fetchone()[0]
                    self.assertEqual(count, 0)
            finally:
                conn.close()

    def test_target_concepts_produce_writes_concept_rows(self):
        rc = bt.main(["--root", self.root, "--output", self.output,
                      "--model", "bge-m3", "--target", "concepts", "--produce"])
        self.assertEqual(rc, 0)
        conn = sqlite3.connect(self.output)
        try:
            rows = conn.execute("SELECT path FROM concept_emb").fetchall()
        finally:
            conn.close()
        self.assertEqual({r[0] for r in rows}, {"b/one", "b/two"})

    def test_target_concepts_dry_run_never_calls_network(self):
        rc = bt.main(["--root", self.root, "--output", self.output,
                      "--model", "bge-m3", "--target", "concepts"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.calls, [])


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


if __name__ == "__main__":
    unittest.main()
