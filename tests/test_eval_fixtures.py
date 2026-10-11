#!/usr/bin/env python3
"""Tests for cli/eval/fixtures.py — stdlib unittest, no deps.

Runs against a throwaway catalogue in a tmpdir, never the live vault.
teardown() runs in setUp/tearDown so a failed assertion leaves no residue.

Run: python3 -m unittest tests.test_eval_fixtures -v
"""
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli")
if _HERE not in sys.path:  # cli/ holds the okf package
    sys.path.insert(0, _HERE)

from okf import catalogue as okf_catalogue
from okf import find as okf_find
from okf import semantic as okf_semantic

_fx_spec = importlib.util.spec_from_file_location(
    "eval_fixtures", os.path.join(_HERE, "eval", "fixtures.py")
)
fixtures = importlib.util.module_from_spec(_fx_spec)
_fx_spec.loader.exec_module(fixtures)

CATALOGUE_ROOT = None


def setUpModule():
    global CATALOGUE_ROOT
    CATALOGUE_ROOT = tempfile.mkdtemp(prefix="okfeval-fixtures-")
    for b in (fixtures.CORRECT_BUNDLE, fixtures.WRONG_BUNDLE):
        os.makedirs(os.path.join(CATALOGUE_ROOT, b))


def tearDownModule():
    shutil.rmtree(CATALOGUE_ROOT, ignore_errors=True)


def _capture_stdout(fn):
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn()
    return buf.getvalue()


def _find_hits(root, query):
    args = types.SimpleNamespace(query=query, limit=50)
    out = _capture_stdout(lambda: okf_find.cmd_find(root, args))
    if out.startswith("(no matches"):
        return []
    return [line for line in out.splitlines() if line.startswith("path: ")]


class SeedThenTeardownIsClean(unittest.TestCase):
    """SC-001/SC-002 — token has 0 find hits before seed, 4 fixture files
    exist after seed, 0 exist after teardown (idempotent)."""

    def setUp(self):
        # Defensive pre-clean in case a prior run left residue.
        fixtures.teardown(CATALOGUE_ROOT)

    def tearDown(self):
        fixtures.teardown(CATALOGUE_ROOT)

    def test_seed_precleans_stray_fixture_files(self):
        # I09 (P12 prelude, from P11 review): an aborted prior run can
        # leave stray _okfeval-* files; seed() must clean them first so
        # a fresh run never counts residue as live fixtures.
        stray = os.path.join(
            CATALOGUE_ROOT,
            os.path.dirname(fixtures._fixture_spec(CATALOGUE_ROOT)[0]
                            .rel_path.replace("/", os.sep)),
            fixtures.FIXTURE_PREFIX + "stray.md",
        )
        with open(stray, "w", encoding="utf-8") as f:
            f.write("---\ntitle: stray\ntype: Concept\n---\nstray body\n")
        try:
            written = fixtures.seed(CATALOGUE_ROOT)
            self.assertFalse(
                os.path.exists(stray),
                "seed() must remove stray fixture residue before seeding",
            )
            self.assertEqual(len(written), 4)
        finally:
            fixtures.teardown(CATALOGUE_ROOT)

    def test_token_absent_before_seed(self):
        # T07 (D13/D16): the semantic arm now speaks a real, populated
        # voyage-3-large index, so it legitimately returns nearest-neighbour
        # hits for ANY string, including a nonsense seed token — that does
        # not refute this test's LEXICAL claim ("the token appears in no
        # real concept"), it is the arm doing its job. Neutralise the arm
        # here instead of weakening the assertion: force its query-embed
        # call to raise, which triggers the documented degradation (semantic
        # arm -> [] + one stderr note, lexical path unaffected) so this test
        # stays network-free, per SC-NET.
        orig_embed = okf_semantic._embed_query_voyage

        def _raise(_text):
            raise RuntimeError("network disabled under test")

        okf_semantic._embed_query_voyage = _raise
        try:
            self.assertEqual(
                _find_hits(CATALOGUE_ROOT, fixtures.SEED_TOKEN),
                [],
                "seed token must not appear in any real catalogue concept "
                "before seed",
            )
        finally:
            okf_semantic._embed_query_voyage = orig_embed

    def test_seed_writes_four_files_teardown_removes_them(self):
        written = fixtures.seed(CATALOGUE_ROOT)
        try:
            self.assertEqual(len(written), 4)
            for p in written:
                self.assertTrue(os.path.isfile(p), p)
                self.assertTrue(os.path.basename(p).startswith(fixtures.FIXTURE_PREFIX))
            # every fixture reachable by iter_concepts (okf-cli.py:89-98)
            reachable = set()
            for b in okf_catalogue.list_bundles(CATALOGUE_ROOT):
                bp = os.path.join(CATALOGUE_ROOT, b)
                for _cid, ap in okf_catalogue.iter_concepts(bp):
                    reachable.add(os.path.abspath(ap))
            for p in written:
                self.assertIn(os.path.abspath(p), reachable)
        finally:
            removed = fixtures.teardown(CATALOGUE_ROOT)
        self.assertEqual(sorted(removed), sorted(written))
        for p in written:
            self.assertFalse(os.path.isfile(p), p)

    def test_teardown_after_partial_seed_is_idempotent(self):
        written = fixtures.seed(CATALOGUE_ROOT)
        os.remove(written[0])  # simulate a partial/interrupted seed
        first = fixtures.teardown(CATALOGUE_ROOT)
        second = fixtures.teardown(CATALOGUE_ROOT)
        self.assertEqual(len(first), 3)
        self.assertEqual(second, [])
        for p in written:
            self.assertFalse(os.path.isfile(p), p)


class MainCliDispatch(unittest.TestCase):
    """SC-003 — __main__ CLI dispatches --seed/--teardown and prints
    affected paths."""

    def setUp(self):
        fixtures.teardown(CATALOGUE_ROOT)

    def tearDown(self):
        fixtures.teardown(CATALOGUE_ROOT)

    def test_seed_flag_prints_written_paths(self):
        out = _capture_stdout(
            lambda: fixtures.main(["--root", CATALOGUE_ROOT, "--seed"])
        )
        lines = [l for l in out.splitlines() if l.strip()]
        self.assertEqual(len(lines), 4)
        for l in lines:
            self.assertTrue(os.path.isfile(l), l)

    def test_teardown_flag_removes_and_prints_paths(self):
        fixtures.seed(CATALOGUE_ROOT)
        out = _capture_stdout(
            lambda: fixtures.main(["--root", CATALOGUE_ROOT, "--teardown"])
        )
        lines = [l for l in out.splitlines() if l.strip()]
        self.assertEqual(len(lines), 4)
        for l in lines:
            self.assertFalse(os.path.isfile(l), l)

    def test_seed_and_teardown_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            fixtures.main(["--root", CATALOGUE_ROOT, "--seed", "--teardown"])


if __name__ == "__main__":
    unittest.main()
