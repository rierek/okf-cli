#!/usr/bin/env python3
"""Tests for cli/okf/registry.py — `registry convert`. unittest.

Run: just test tests.test_okf_registry -v
"""
import os
import shutil
import sys
import tempfile
import types
import unittest

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli")
if _HERE not in sys.path:  # cli/ holds the okf package
    sys.path.insert(0, _HERE)
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from okf import catalogue as okf_catalogue
from okf.errors import OkfError
from okf.registry import cmd_registry

TAGS = ("# Mine\n\nProsa.\n\n| Tag | Description |\n|-----|-------------|\n| `a` | A |\n| `b` | B |\n\n"
        "## Checks\n\nText.\n")
TYPES = ("# Types\n\n## One\n\n| type | rank | Meaning |\n|------|:----:|---------|\n"
         "| `X` | 1 | x |\n| `Y` | — | y |\n\n## Two\n\n| type | Meaning |\n|------|---------|\n| `Z` | z |\n")


class RegistryConvert(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _w(self, rel, text):
        with open(os.path.join(self.tmp, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def _r(self, rel):
        with open(os.path.join(self.tmp, rel), encoding="utf-8") as f:
            return f.read()

    def _convert(self, file, to, apply=True):
        return cmd_registry(self.tmp, types.SimpleNamespace(file=file, to=to, apply=apply, json=True))

    def test_tags_preview_writes_nothing_and_round_trip_is_byte_equal(self):
        self._w("TAGS.md", TAGS)
        result = self._convert("TAGS.md", "block", apply=False)
        self.assertEqual(self._r("TAGS.md"), TAGS)
        self.assertEqual((result["converted"], len(result["files"])), (2, 1))
        self._convert("TAGS.md", "block")
        self.assertEqual(self._r("TAGS.md"), "# Mine\n\nProsa.\n\n### `a`\nA\n\n### `b`\nB\n\n## Checks\n\nText.\n")
        self.assertEqual(okf_catalogue.load_tags(self.tmp), {"a", "b"})
        self._convert("TAGS.md", "table")
        self.assertEqual(self._r("TAGS.md"), TAGS)

    def test_types_rank_survives_both_ways(self):
        self._w("TYPES.md", TYPES)
        self._convert("TYPES.md", "block")
        self.assertEqual(self._r("TYPES.md"),
                         "# Types\n\n## One\n\n### `X`\nrank: 1\nx\n\n### `Y`\nrank: —\ny\n\n## Two\n\n### `Z`\nz\n")
        self.assertEqual(okf_catalogue.load_types(self.tmp), {"X", "Y", "Z"})
        self._convert("TYPES.md", "table")
        self.assertEqual(self._r("TYPES.md"), TYPES)

    def _refused(self, file, text, to):
        self._w(file, text)
        with self.assertRaises(OkfError) as cm:
            self._convert(file, to)
        self.assertEqual(cm.exception.code, 2)
        self.assertEqual(self._r(file), text)

    def test_refuses_what_would_change_meaning(self):
        self._refused("TAGS.md", "| Tag | Description |\n|---|---|\n| `a` | A |\nProse\n", "block")
        self._refused("TAGS.md", "### `a`\nline one\nline two\n", "table")
        self._refused("TAGS.md", "| Tag | Description |\n|---|---|\n| `a` | A |\n| plain | row |\n", "block")
        self._refused("TAGS.md", "| Tag | Meaning | Example |\n|---|---|---|\n| `a` | x | |\n", "block")


if __name__ == "__main__":
    unittest.main()
