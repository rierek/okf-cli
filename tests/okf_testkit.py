"""Helpers shared by several test modules. Not a test module: the name has no
test_ prefix, so unittest discovery never collects it."""
import argparse
import builtins
import collections
import contextlib
import io
import json
import os
import shlex
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
from okf.parser import COMMAND_DISPATCH, build_parser


def run_find(root, query, **kw):
    """Module-level twin of the per-class _run() helpers in
    tests/test_okf_find.py — same in-process convention (SimpleNamespace
    args, cmd_find, redirected streams), but parameterised by root so the new
    suites can each use their own temp catalogue. Returns stdout."""
    args = types.SimpleNamespace(
        query=query, limit=10, where=None,
        breakdown=False,
    )
    for k, v in kw.items():
        setattr(args, k, v)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        okf_find.cmd_find(root, args)
    return buf.getvalue()


def run_cli(root, *argv, home=None, env=None):
    """(stdout, stderr, exit code) of one real okf-cli.py call against the catalogue at
    `root`. VOYAGE_API_KEY is dropped, so no call reaches the embedding backend; `env`
    adds or overrides variables."""
    full_env = {k: v for k, v in os.environ.items() if k != "VOYAGE_API_KEY"}
    if home is not None:
        full_env["HOME"] = home
    full_env.update(env or {})
    proc = _cli(root, *argv, env=full_env, cwd=root)
    return proc.stdout, proc.stderr, proc.returncode


def run_json(root, *argv, **kw):
    """(envelope, stderr, exit code) of `okf --root <root> <argv> --json`. Fails
    unless stdout is exactly one JSON object on one line carrying the five envelope keys."""
    out, err, code = run_cli(root, *argv, "--json", **kw)
    assert out.count("\n") == 1 and out.endswith("\n"), "stdout is not one line: {!r}".format(out)
    envelope = json.loads(out)
    assert isinstance(envelope, dict), "stdout is not a JSON object: {!r}".format(out)
    assert set(envelope) == {"command", "ok", "data", "warnings", "error"}, sorted(envelope)
    return envelope, err, code


def uv_dirs():
    """UV_CACHE_DIR and UV_PYTHON_INSTALL_DIR of the real home, for a test that swaps HOME and must
    still find the uv cache and the managed Pythons."""
    return {var: subprocess.run(["uv", kind, "dir"], capture_output=True, text=True, check=True).stdout.strip()
            for var, kind in (("UV_CACHE_DIR", "cache"), ("UV_PYTHON_INSTALL_DIR", "python"))}


def uv_start_log(case):
    """Put a `uv` shim first on PATH for the test `case`. The shim appends its arguments, one call
    per line, to a log and then runs the real uv. Returns a function that gives the logged calls,
    so a test sees how a caller starts okf across the process boundary, not which Python runs."""
    real = shutil.which("uv")
    case.assertIsNotNone(real, "uv is not on PATH")
    tmp = tempfile.mkdtemp()
    case.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
    log = os.path.join(tmp, "uv.log")
    shim = os.path.join(tmp, "uv")
    with open(shim, "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\nprintf '%s\\n' \"$*\" >> {}\nexec {} \"$@\"\n".format(shlex.quote(log), shlex.quote(real)))
    os.chmod(shim, 0o755)
    patcher = mock.patch.dict(os.environ, {"PATH": tmp + os.pathsep + os.environ["PATH"]})
    patcher.start()
    case.addCleanup(patcher.stop)

    def calls():
        if not os.path.exists(log):
            return []
        with open(log, encoding="utf-8") as f:
            return f.read().splitlines()
    return calls


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
        """(data of `sync-status --json`, exit code): the handler's result, or what its drift
        failure carries."""
        kw = dict(target=None, source=None, block=None, json=True)
        kw.update(over)
        try:
            return okf_sync.cmd_sync_status(self.tmp, argparse.Namespace(**kw)), 0
        except OkfError as e:
            return e.result, e.code

    def _update(self, **over):
        kw = dict(target=None, source=None, block=None, apply=True, force=False)
        kw.update(over)
        return self._run(okf_sync.cmd_sync_update, **kw)

    def _payload_of(self, rel):
        body = okf_catalogue.read_frontmatter(self._r(rel)).body
        return okf_sync.parse_sync_blocks(body)[0]["payload"]


# --- helpers shared by the check, wikilinks and rename suites ---------------


def _fs_is_case_insensitive():
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "a"), "w").close()
        return os.path.exists(os.path.join(d, "A"))


needs_case_insensitive_fs = unittest.skipUnless(
    _fs_is_case_insensitive(), "braucht case-insensitives Dateisystem (APFS)")


_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli")
CLI = os.path.join(_HERE, "okf-cli.py")


def _cli(root, *argv, env=None, cwd=None):
    """Drive the REAL cli/okf-cli.py as a subprocess: the one subprocess path of the tests.
    The `command:` acceptance criteria of docs/wikilink-awareness/SPEC.md are written
    against the shell surface (exit code, stdout shape), which an in-process call cannot
    pin."""
    return subprocess.run([sys.executable, CLI, "--root", root] + list(argv),
                          capture_output=True, text=True, env=env, cwd=cwd)


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
        return _cli(self.root, *argv, env={**os.environ, "HOME": self.home})

    def _home(self):
        return mock.patch.dict(os.environ, {"HOME": self.home})


def E(pos, mode, path, comment=""):
    return {"pos": pos, "mode": mode, "path": path, "comment": comment}


DECLARE = 'okf_version: "0.2"'


class SpecCase(unittest.TestCase):
    """A throwaway catalogue with one bundle `b`. `_bundle` writes its root index.md. A base with
    no tests of its own: the OKF v0.2 test modules inherit it."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _w(self, rel, text):
        ap = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(text)

    def _bundle(self, front: "str | None" = DECLARE, bundle="b"):
        """The bundle-root index.md; `front` is its frontmatter text, None for no block."""
        head = "" if front is None else "---\n{}\n---\n".format(front)
        self._w(bundle + "/index.md", head + "# B\n\nA bundle for the v0.2 rule tests.\n")

    def _concept(self, extra="", rel="b/x.md", type_="Note"):
        self._w(rel, "---\ntype: {}\n{}\n---\n# X\n\nbody\n".format(type_, extra))

    def _findings(self, target: "str | None" = "b"):
        return okf_check.run_checks(self.tmp, target)

    def _group(self, prefix, target: "str | None" = "b"):
        return [f for f in self._findings(target) if f.rule.startswith(prefix)]


needs_git = unittest.skipUnless(subprocess.run(["git", "--version"], capture_output=True).returncode == 0,
                                "git not available")


@needs_git
class GitCatalogue(SpecCase):
    """The catalogue root `self.tmp` is a git repository; every commit pins author, committer and dates."""

    def setUp(self):
        super().setUp()
        patch = mock.patch.dict(os.environ)
        patch.start()
        self.addCleanup(patch.stop)
        for key in [k for k in os.environ if k.startswith("GIT_")]:
            del os.environ[key]  # a hook that runs the tests must not steer the fixture's git
        os.environ.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
                          GIT_TERMINAL_PROMPT="0")
        self._git("init", "-q")

    def _git(self, *argv, env=None, cwd=None):
        res = subprocess.run(["git", "-C", cwd or self.tmp, "-c", "init.defaultBranch=main",
                              "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *argv],
                             capture_output=True, text=True, env={**os.environ, **(env or {})})
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout

    def _commit(self, message, when, author="a@x.org", author_when=None):
        self._git("add", "-A")
        self._git("commit", "-q", "-m", message, env={
            "GIT_AUTHOR_NAME": "A", "GIT_AUTHOR_EMAIL": author, "GIT_COMMITTER_NAME": "C",
            "GIT_COMMITTER_EMAIL": "c@x.org", "GIT_AUTHOR_DATE": author_when or when,
            "GIT_COMMITTER_DATE": when})

    def _doc(self, rel="b/x.md", body="body\n", front="type: Note"):
        self._w(rel, "---\n{}\n---\n{}".format(front, body))

    def _reset(self):
        """An empty catalogue in a fresh repository."""
        for name in os.listdir(self.tmp):
            path = os.path.join(self.tmp, name)
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        self._git("init", "-q")

    def _count_git(self):
        """The list that collects argv[0] of every process started from here on (run goes through Popen)."""
        started = []
        real_popen = subprocess.Popen

        def popen(argv, *a, **k):
            started.append(argv[0])
            return real_popen(argv, *a, **k)

        patch = mock.patch.object(subprocess, "Popen", popen)
        patch.start()
        self.addCleanup(patch.stop)
        return started



def call_command(root, *argv):
    """The data a command returns in-process, as its `--json` envelope would carry it; the notes
    of the call go to a discarded stderr."""
    args = build_parser().parse_args(["--root", root, *argv, "--json"])
    with contextlib.redirect_stderr(io.StringIO()):
        return COMMAND_DISPATCH[args.cmd](root, args)


def count_md_reads(root, *argv):
    """Counter of how often each .md file under `root` is opened during one in-process call."""
    real, seen = builtins.open, collections.Counter()

    def spy(file, *a, **k):
        if isinstance(file, str) and file.startswith(root) and file.endswith(".md"):
            seen[file] += 1
        return real(file, *a, **k)

    with mock.patch("builtins.open", spy):
        call_command(root, *argv)
    return seen
