#!/usr/bin/env python3
"""Boundary test of `okf tui` dispatch — unittest.

`tui` resolves the catalogue root exactly as `find` does: with no root at all it ends before the
TUI starts, with the same message and exit code 3. Runs the REAL okf binary (go/bin/okf from
`just go-build`, or $OKF_BIN) in an empty directory with an empty HOME and XDG_CONFIG_HOME.

Run: just test tests.test_okf_tui -v
"""
import os
import subprocess
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_BIN = os.path.realpath(os.environ.get("OKF_BIN") or os.path.join(_HERE, os.pardir, "go", "bin", "okf"))


class TuiDispatch(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = os.path.join(tmp.name, "home")
        self.work = os.path.join(tmp.name, "work")
        os.makedirs(os.path.join(self.home, ".config"))
        os.makedirs(self.work)

    def _run(self, *args):
        self.assertTrue(os.path.isfile(_BIN), "no okf binary at {}: run `just go-build`".format(_BIN))
        env = {"PATH": os.environ.get("PATH", ""), "HOME": self.home, "XDG_CONFIG_HOME": os.path.join(self.home, ".config")}
        return subprocess.run([_BIN, *args], cwd=self.work, env=env, capture_output=True, text=True, timeout=30)

    def test_tui_without_a_root_fails_like_find(self):
        tui, find = self._run("tui"), self._run("find", "x")
        self.assertEqual(find.returncode, 3)
        self.assertEqual(tui.returncode, 3)
        self.assertEqual(tui.stderr, find.stderr)
        self.assertIn("no catalogue found", tui.stderr)
        self.assertEqual(tui.stdout, "")

    def test_tui_is_listed_in_the_overview(self):
        self.assertRegex(self._run("--help").stdout, r"(?m)^\s+tui\s+\S")


if __name__ == "__main__":
    unittest.main()
