#!/usr/bin/env python3
"""Tests for cli/okf/diffs.py — the plan-to-unified-diff helper and the plan writer. unittest.

Run: just test tests.test_okf_diffs -v
"""
import os
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli")
if _HERE not in sys.path:  # cli/ holds the okf package
    sys.path.insert(0, _HERE)

from okf.diffs import unified_diffs, write_plan


class CreatedFile(unittest.TestCase):
    def test_a_created_file_is_headed_dev_null(self):
        (entry,) = unified_diffs([("d/new.md", None, "one\ntwo")])
        self.assertEqual(entry, {"path": "d/new.md", "old_path": None, "diff": (
            "--- /dev/null\n+++ b/d/new.md\n@@ -0,0 +1,2 @@\n+one\n+two\n\\ No newline at end of file\n")})

    def test_changed_and_created_files_are_ordered_by_path_and_equal_texts_are_omitted(self):
        plan = [("z.md", "a\n", "b\n"), ("a.md", None, "x\n"), ("m.md", "same\n", "same\n")]
        self.assertEqual([e["path"] for e in unified_diffs(plan)], ["a.md", "z.md"])
        self.assertTrue(unified_diffs(plan)[1]["diff"].startswith("--- a/z.md\n+++ b/z.md\n"))


class WritePlan(unittest.TestCase):
    def test_writes_new_texts_verbatim_and_creates_directories(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        os.makedirs(os.path.join(tmp, "d"))
        with open(os.path.join(tmp, "d/old.md"), "wb") as f:
            f.write(b"a\r\n")
        write_plan(tmp, [("d/old.md", "a\r\n", "b\r\n"), ("n/e/w.md", None, "x"), ("d/same.md", "s", "s")])
        with open(os.path.join(tmp, "d/old.md"), "rb") as f:
            self.assertEqual(f.read(), b"b\r\n")
        with open(os.path.join(tmp, "n/e/w.md"), "rb") as f:
            self.assertEqual(f.read(), b"x")
        self.assertFalse(os.path.exists(os.path.join(tmp, "d/same.md")))


class MovedAndDeletedFile(unittest.TestCase):
    def test_a_moved_file_has_the_rename_header_even_when_its_text_is_unchanged(self):
        changed, same = unified_diffs([("n/same.md", "x\n", "x\n"), ("n/chg.md", "x\n", "y\n")],
                                      {"n/same.md": "o/same.md", "n/chg.md": "o/chg.md"})
        self.assertEqual(changed, {"path": "n/chg.md", "old_path": "o/chg.md", "diff": (
            "rename from o/chg.md\nrename to n/chg.md\n--- a/o/chg.md\n+++ b/n/chg.md\n@@ -1 +1 @@\n-x\n+y\n")})
        self.assertEqual(same["diff"], "rename from o/same.md\nrename to n/same.md\n")

    def test_a_deleted_file_is_headed_dev_null_and_write_plan_skips_it(self):
        (entry,) = unified_diffs([("d/gone.md", "x\n", None)])
        self.assertEqual(entry["diff"], "--- a/d/gone.md\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n")
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        write_plan(tmp, [("d/gone.md", "x\n", None)])
        self.assertFalse(os.path.exists(os.path.join(tmp, "d")))


if __name__ == "__main__":
    unittest.main()
