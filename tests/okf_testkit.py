"""Helpers shared by several test modules. Not a test module: the name has no
test_ prefix, so unittest discovery never collects it."""
import argparse
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

from okf import catalogue as okf_catalogue
from okf import check as okf_check
from okf import find as okf_find
from okf.errors import OkfError
from okf import sync as okf_sync


def run_find(root, query, **kw):
    """Module-level twin of the per-class _run() helpers in
    tests/test_okf_find.py — same in-process convention (SimpleNamespace
    args, cmd_find, redirected streams), but parameterised by root so the new
    suites can each use their own temp catalogue. Returns stdout."""
    args = types.SimpleNamespace(
        query=query, limit=10, type=None, tag=None, scope=None,
        breakdown=False,
    )
    for k, v in kw.items():
        setattr(args, k, v)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        okf_find.cmd_find(root, args)
    return buf.getvalue()


CLI = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli", "okf-cli.py")


def run_cli(root, *argv, home=None):
    """(stdout, stderr, exit code) of one real okf-cli.py call against the catalogue at
    `root`. VOYAGE_API_KEY is dropped, so no call reaches the embedding backend."""
    env = {k: v for k, v in os.environ.items() if k != "VOYAGE_API_KEY"}
    if home is not None:
        env["HOME"] = home
    proc = subprocess.run([sys.executable, CLI, "--root", root, *argv],
                          capture_output=True, text=True, env=env, cwd=root)
    return proc.stdout, proc.stderr, proc.returncode


def run_json(root, *argv):
    """(envelope, stderr, exit code) of `okf-cli.py --root <root> <argv> --json`. Fails
    unless stdout is exactly one JSON line carrying the five envelope keys."""
    out, err, code = run_cli(root, *argv, "--json")
    assert out.count("\n") == 1 and out.endswith("\n"), "stdout is not one line: {!r}".format(out)
    envelope = json.loads(out)
    assert set(envelope) == {"command", "ok", "data", "warnings", "error"}, sorted(envelope)
    return envelope, err, code


def _scan(root, target, **kw):
    """okf_check.run_checks, split by each finding's own severity into
    (errors, warnings), each a list of (rule, path, message)."""
    findings = okf_check.run_checks(root, target, **kw)
    return ([(f.rule, f.path, f.message) for f in findings if f.severity == "error"],
            [(f.rule, f.path, f.message) for f in findings if f.severity == "warning"])


# --- canon block synchronisation -------------------------------------------


class SyncFixtureMixin:
    """A two-bundle throwaway catalogue: one canon owner, one consumer."""

    OWNER_PAYLOAD = "Jede normative Aussage hat genau einen Owner.\n"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._w(".okf.toml", "")
        self._w("kc-gov/ownership.md",
                "---\ntype: Rule\ndescription: d\n---\n\n# Ownership\n\n"
                "<!-- okf:canon id=ownership-rule -->\n"
                + self.OWNER_PAYLOAD
                + "<!-- /okf:canon -->\n")
        self._w("kc-proj/setup.md",
                "---\ntype: Runbook\ndescription: d\n---\n\n# Setup\n\nLokal.\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _w(self, rel, text):
        ap = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(text)

    def _r(self, rel):
        with open(os.path.join(self.tmp, rel), encoding="utf-8") as f:
            return f.read()

    def _run(self, fn, **kw):
        """Call a handler with a namespace, capturing stdout and exit code."""
        buf = io.StringIO()
        code = 0
        try:
            with contextlib.redirect_stdout(buf):
                fn(self.tmp, argparse.Namespace(**kw))
        except OkfError as e:
            code = e.code
        return buf.getvalue(), code

    def _insert(self, **over):
        kw = dict(consumer="kc-proj/setup", concept="kc-gov/ownership",
                  block_id="ownership-rule", apply=True)
        kw.update(over)
        return self._run(okf_sync.cmd_sync_insert, **kw)

    def _status(self, **over):
        kw = dict(target=None, source=None, block=None, json=True)
        kw.update(over)
        return self._run(okf_sync.cmd_sync_status, **kw)

    def _update(self, **over):
        kw = dict(target=None, source=None, block=None, apply=True, force=False)
        kw.update(over)
        return self._run(okf_sync.cmd_sync_update, **kw)

    def _payload_of(self, rel):
        _, body = okf_catalogue.split_frontmatter(self._r(rel))
        return okf_sync.parse_sync_blocks(body)[0]["payload"]


# --- helpers shared by the check, wikilinks and rename suites ---------------


def _fs_is_case_insensitive():
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "a"), "w").close()
        return os.path.exists(os.path.join(d, "A"))


needs_case_insensitive_fs = unittest.skipUnless(
    _fs_is_case_insensitive(), "braucht case-insensitives Dateisystem (APFS)")


_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli")


def _cli(root, *argv):
    """Drive the REAL cli/okf-cli.py as a subprocess. The `command:` acceptance
    criteria of docs/wikilink-awareness/SPEC.md are written against the shell
    surface (exit code, stdout shape), which an in-process call cannot pin."""
    return subprocess.run(
        [sys.executable, os.path.join(_HERE, "okf-cli.py"), "--root", root] + list(argv),
        capture_output=True, text=True)


# --- the ctx fixture shared by the ctx command and catalogue (ctx storage) suites ---


class CtxFixtureMixin:
    """Shared fixture for every ctx test: tmp catalogue + external bundle + fake HOME."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.ext = tempfile.mkdtemp()
        self.home = os.path.realpath(tempfile.mkdtemp())  # cwd-derived paths are realpaths on macOS
        self.addCleanup(shutil.rmtree, self.root, True)
        self.addCleanup(shutil.rmtree, self.ext, True)
        self.addCleanup(shutil.rmtree, self.home, True)
        self._w(".okf.toml", "")
        self._w("TYPES.md", "| Type | Meaning | Example |\n|---|---|---|\n"
                            "| `Concept` | x | |\n| `Context` | x | |\n")
        self._w("b/index.md", "# B\n\nIntro.\n\n## Contents\n\n"
                              + okf_catalogue.MARK_START + "\n" + okf_catalogue.MARK_END + "\n")
        self._w("b/one.md", "---\ntype: Concept\ntitle: One\ndescription: first\n---\n\n"
                            "# One\n\nSee [Two](/b/two.md).\n")
        self._w("b/two.md", "---\ntype: Concept\ntitle: Two\ndescription: second\n---\n\n"
                            "# Two\n\n## Part\n")
        with open(os.path.join(self.ext, "three.md"), "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: Three\n---\n\n# Three\n")
        os.symlink(self.ext, os.path.join(self.root, "ext"))
        os.makedirs(os.path.join(self.home, "notes"))
        with open(os.path.join(self.home, "notes", "out.md"), "w", encoding="utf-8") as f:
            f.write("# Out\n")

    def _w(self, rel, text):
        ap = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(text)

    def _cli(self, *argv):
        return subprocess.run(
            [sys.executable, os.path.join(_HERE, "okf-cli.py"), "--root", self.root, *argv],
            capture_output=True, text=True, env={**os.environ, "HOME": self.home})

    def _home(self):
        return mock.patch.dict(os.environ, {"HOME": self.home})


def E(pos, mode, path, comment=""):
    return {"pos": pos, "mode": mode, "path": path, "comment": comment}
