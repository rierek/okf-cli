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


if __name__ == "__main__":
    unittest.main()
