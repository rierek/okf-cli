#!/usr/bin/env python3
"""Tests for cli/eval/fixtures.py — stdlib unittest, no deps.

Runs against the REAL catalogue (D11: fixtures live in the real catalogue,
not a tmp fixture dir) — that is the point of this module. teardown() is
called in a finally-block so a failed assertion never leaves residue.

Run: python3 -m unittest test_eval_fixtures -v
"""
import importlib.util
import io
import os
import types
import unittest
from contextlib import redirect_stdout

_HERE = os.path.dirname(os.path.abspath(__file__))

_cli_spec = importlib.util.spec_from_file_location(
    "okf_cli", os.path.join(_HERE, "okf-cli.py")
)
okf = importlib.util.module_from_spec(_cli_spec)
_cli_spec.loader.exec_module(okf)

_fx_spec = importlib.util.spec_from_file_location(
    "eval_fixtures", os.path.join(_HERE, "eval", "fixtures.py")
)
fixtures = importlib.util.module_from_spec(_fx_spec)
_fx_spec.loader.exec_module(fixtures)

CATALOGUE_ROOT = fixtures.DEFAULT_ROOT


def _capture_stdout(fn):
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn()
    return buf.getvalue()


def _find_hits(root, query):
    args = types.SimpleNamespace(query=query, limit=50)
    out = _capture_stdout(lambda: okf.cmd_find(root, args))
    if out.startswith("(no matches"):
        return []
    return [line for line in out.splitlines() if line.startswith("path: ")]


class SeedThenTeardownIsClean(unittest.TestCase):
    """SC-001/SC-002 — token has 0 find hits before seed, 4 fixture files
    exist after seed, 0 exist after teardown (idempotent)."""

    def setUp(self):
        self.assertTrue(
            os.path.isdir(CATALOGUE_ROOT),
            "real catalogue not found at {} — fixtures.py targets the real "
            "catalogue by design (D11)".format(CATALOGUE_ROOT),
        )
        # Defensive pre-clean in case a prior run left residue.
        fixtures.teardown(CATALOGUE_ROOT)

    def tearDown(self):
        fixtures.teardown(CATALOGUE_ROOT)

    def test_token_absent_before_seed(self):
        self.assertEqual(
            _find_hits(CATALOGUE_ROOT, fixtures.SEED_TOKEN),
            [],
            "seed token must not appear in any real catalogue concept "
            "before seed",
        )

    def test_seed_writes_four_files_teardown_removes_them(self):
        written = fixtures.seed(CATALOGUE_ROOT)
        try:
            self.assertEqual(len(written), 4)
            for p in written:
                self.assertTrue(os.path.isfile(p), p)
                self.assertTrue(os.path.basename(p).startswith(fixtures.FIXTURE_PREFIX))
            # every fixture reachable by iter_concepts (okf-cli.py:89-98)
            reachable = set()
            for b in okf.list_bundles(CATALOGUE_ROOT):
                bp = os.path.join(CATALOGUE_ROOT, b)
                for _cid, ap in okf.iter_concepts(bp):
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
