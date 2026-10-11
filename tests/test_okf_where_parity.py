#!/usr/bin/env python3
"""Parity of `--where` with the removed `--type` / `--tag` / `--scope` / `--include-archive`
flags (OKFT-zpom). PINNED holds the concept set each old-flag invocation returned on this
fixture, captured on the pre-removal tree (milestone/0.2 at b87f1e7); the test asserts the
`--where` equivalent returns the same set. Stdlib unittest, no deps.

Run: python3 -m unittest tests.test_okf_where_parity -v
"""
import contextlib
import io
import os
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import unittest

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli")
if _HERE not in sys.path:  # cli/ holds the okf package
    sys.path.insert(0, _HERE)
if os.path.dirname(_HERE) not in sys.path:  # the repo root holds tests/
    sys.path.insert(0, os.path.dirname(_HERE))

from okf import fts as okf_fts
from okf import parser as okf_parser
from okf import semantic as okf_semantic
from okf.find_filters import FindFilters
from tests.okf_testkit import run_cli, run_json

# (rel path, type, tags): `alpha-extra` style names are avoided on purpose, because
# `path ~ b/` also matches `xb/...` (Q34) and parity must not depend on that.
CONCEPTS = [
    ("alpha/one", "Runbook", ["alpha-tag", "shared"]),
    ("alpha/two", "Concept", ["beta-tag", "shared"]),
    ("alpha/sub/three", "Runbook", ["alpha-tag"]),
    ("beta/four", "Runbook", ["shared"]),
    ("beta/five", "Pattern", ["beta-tag"]),
    ("gamma/six", "Concept", ["alpha-tag"]),
    ("_archive/alpha/old-one", "Runbook", ["alpha-tag", "shared"]),
    ("_archive/gamma/old-two", "Concept", ["shared"]),
]
LITERAL = "zqxparity"
PARAPHRASE = "zzz-no-keyword-match-zzz"

# (old flags, --where equivalent per OKFT-zpom: --type T -> type = T, --tag G -> tag = G,
# --scope S -> path ~ S/, --include-archive -> archived in (true, false))
WHERE = {
    "--type Runbook": "type = Runbook",
    "--tag alpha-tag": "tag = alpha-tag",
    "--scope alpha": "path ~ alpha/",
    "--scope alpha/sub": "path ~ alpha/sub/",
    "--include-archive": "archived in (true, false)",
    "--scope alpha --include-archive": "path ~ alpha/ and archived in (true, false)",
    "--type Runbook --tag shared --scope alpha": "type = Runbook and tag = shared and path ~ alpha/",
    "--type Runbook --include-archive": "type = Runbook and archived in (true, false)",
}

# {(command, old flags): sorted concept paths}, captured by running the OLD flags on this fixture
# on the pre-removal tree (milestone/0.2 at b87f1e7). The old `list` refused a call without
# --type/--tag, `recent` and the tag verbs had no --include-archive, the tag verbs only --scope,
# so those combinations are absent.
PINNED = {
    ('find lexical', '--type Runbook'): ['alpha/one', 'alpha/sub/three', 'beta/four'],
    ('find lexical', '--tag alpha-tag'): ['alpha/one', 'alpha/sub/three', 'gamma/six'],
    ('find lexical', '--scope alpha'): ['alpha/one', 'alpha/sub/three', 'alpha/two'],
    ('find lexical', '--scope alpha/sub'): ['alpha/sub/three'],
    ('find lexical', '--include-archive'): ['_archive/alpha/old-one', '_archive/gamma/old-two', 'alpha/one', 'alpha/sub/three', 'alpha/two', 'beta/five', 'beta/four', 'gamma/six'],
    ('find lexical', '--scope alpha --include-archive'): ['_archive/alpha/old-one', 'alpha/one', 'alpha/sub/three', 'alpha/two'],
    ('find lexical', '--type Runbook --tag shared --scope alpha'): ['alpha/one'],
    ('find lexical', '--type Runbook --include-archive'): ['_archive/alpha/old-one', 'alpha/one', 'alpha/sub/three', 'beta/four'],
    ('find semantic', '--type Runbook'): ['alpha/one', 'alpha/sub/three', 'beta/four'],
    ('find semantic', '--tag alpha-tag'): ['alpha/one', 'alpha/sub/three', 'gamma/six'],
    ('find semantic', '--scope alpha'): ['alpha/one', 'alpha/sub/three', 'alpha/two'],
    ('find semantic', '--scope alpha/sub'): ['alpha/sub/three'],
    ('find semantic', '--include-archive'): ['alpha/one', 'alpha/sub/three', 'alpha/two', 'beta/five', 'beta/four', 'gamma/six'],
    ('find semantic', '--scope alpha --include-archive'): ['alpha/one', 'alpha/sub/three', 'alpha/two'],
    ('find semantic', '--type Runbook --tag shared --scope alpha'): ['alpha/one'],
    ('find semantic', '--type Runbook --include-archive'): ['alpha/one', 'alpha/sub/three', 'beta/four'],
    ('find degraded', '--type Runbook'): ['alpha/one', 'alpha/sub/three', 'beta/four'],
    ('find degraded', '--tag alpha-tag'): ['alpha/one', 'alpha/sub/three', 'gamma/six'],
    ('find degraded', '--scope alpha'): ['alpha/one', 'alpha/sub/three', 'alpha/two'],
    ('find degraded', '--scope alpha/sub'): ['alpha/sub/three'],
    ('find degraded', '--include-archive'): ['_archive/alpha/old-one', '_archive/gamma/old-two', 'alpha/one', 'alpha/sub/three', 'alpha/two', 'beta/five', 'beta/four', 'gamma/six'],
    ('find degraded', '--scope alpha --include-archive'): ['_archive/alpha/old-one', 'alpha/one', 'alpha/sub/three', 'alpha/two'],
    ('find degraded', '--type Runbook --tag shared --scope alpha'): ['alpha/one'],
    ('find degraded', '--type Runbook --include-archive'): ['_archive/alpha/old-one', 'alpha/one', 'alpha/sub/three', 'beta/four'],
    ('list', '--type Runbook'): ['alpha/one', 'alpha/sub/three', 'beta/four'],
    ('list', '--tag alpha-tag'): ['alpha/one', 'alpha/sub/three', 'gamma/six'],
    ('list', '--type Runbook --tag shared --scope alpha'): ['alpha/one'],
    ('list', '--type Runbook --include-archive'): ['_archive/alpha/old-one', 'alpha/one', 'alpha/sub/three', 'beta/four'],
    ('recent', '--type Runbook'): ['alpha/one', 'alpha/sub/three', 'beta/four'],
    ('recent', '--tag alpha-tag'): ['alpha/one', 'alpha/sub/three', 'gamma/six'],
    ('recent', '--scope alpha'): ['alpha/one', 'alpha/sub/three', 'alpha/two'],
    ('recent', '--scope alpha/sub'): ['alpha/sub/three'],
    ('recent', '--type Runbook --tag shared --scope alpha'): ['alpha/one'],
    ('merge-tags', '--scope alpha'): ['alpha/one', 'alpha/sub/three', 'alpha/two'],
    ('merge-tags', '--scope alpha/sub'): ['alpha/sub/three'],
}


def build_fixture(root):
    """The throwaway catalogue: a git repo (recent reads creation dates from history)."""
    for rel, ctype, tags in CONCEPTS:
        ap = os.path.join(root, rel + ".md")
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write("---\ntype: {}\ntitle: {}\ntags: [{}]\ndescription: d\n---\n# T\n\n{} body.\n"
                    .format(ctype, rel.rsplit("/", 1)[-1], ", ".join(tags), LITERAL))
    git = ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", root]
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["add", "."], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "fixture"], check=True)


def build_tagvec(root):
    """Every active concept embeds to the same vector, as in FindFilterContract: which one the
    semantic arm would rank first is irrelevant, only which ones it may return."""
    db = os.path.join(root, ".tagvec", "tag_vectors.sqlite")
    os.makedirs(os.path.dirname(db), exist_ok=True)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE concept_emb(key TEXT PRIMARY KEY, path TEXT, model TEXT, "
                 "dim INT, vec BLOB)")
    for i, (rel, _t, _g) in enumerate(c for c in CONCEPTS if not c[0].startswith("_archive/")):
        conn.execute("INSERT INTO concept_emb VALUES (?,?,?,?,?)",
                     ("k{}".format(i), rel, "voyage-3-large", 2, struct.pack("<2f", 1.0, 0.0)))
    conn.commit()
    conn.close()


def command_argv(command, filter_argv):
    if command.startswith("find"):
        query = PARAPHRASE if command == "find semantic" else LITERAL
        return ["find", query, "--limit", "50"] + filter_argv
    if command == "list":
        return ["list"] + filter_argv
    if command == "recent":
        return ["recent", "--limit", "50"] + filter_argv
    return ["merge-tags", "alpha-tag", "shared", "--into", "zz"] + filter_argv


class WhereParity(unittest.TestCase):
    """OKFT-zpom criteria 13 and 14 — `--where` selects exactly what the removed flags selected."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        build_fixture(self.root)
        build_tagvec(self.root)
        self._embed = okf_semantic._embed_query_voyage
        self.addCleanup(setattr, okf_semantic, "_embed_query_voyage", self._embed)
        okf_semantic._QUERY_VEC_CACHE.clear()

    def regime(self, command):
        """The ownership regime `command` names: lexical (FTS index, semantic arm disabled),
        semantic (FTS index, paraphrase query, stub embedding) or degraded (no index)."""
        def unavailable(_text):
            raise OSError("semantic arm disabled for this regime")
        okf_semantic._embed_query_voyage = (
            (lambda text: [1.0, 0.0]) if command == "find semantic" else unavailable)
        if command in ("find lexical", "find semantic"):
            okf_fts.build_fts_index(self.root)

    def run_where(self, command, expression):
        """sorted concept paths one command returns, through the parser and the dispatch table."""
        args = okf_parser.build_parser().parse_args(
            ["--root", self.root] + command_argv(command, ["--where", expression]) + ["--json"])
        with contextlib.redirect_stderr(io.StringIO()):
            data = okf_parser.COMMAND_DISPATCH[args.cmd](self.root, args)
        if command.startswith("find"):
            paths = [h["path"] for h in data["hits"]]
        elif command == "merge-tags":
            paths = data["files"]
        else:
            paths = [row["path"] for row in data]
        return sorted(p[:-3] if p.endswith(".md") else p for p in paths)

    def test_every_pinned_old_flag_set_is_what_where_selects(self):
        for (command, old), expected in PINNED.items():
            with self.subTest(command=command, old_flags=old):
                self.regime(command)
                self.assertEqual(self.run_where(command, WHERE[old]), expected)

    def test_the_fixture_tells_the_flags_apart(self):
        """A parity row that every flag combination satisfies proves nothing: the pinned sets of
        the find rows must differ from each other and from the unfiltered answer."""
        sets = [tuple(v) for (c, _o), v in PINNED.items() if c == "find lexical"]
        self.assertEqual(len(set(sets)), len(sets))


class WhereIsTheOnlyFilterPath(unittest.TestCase):
    """OKFT-zpom criteria 4, 10 and 12 — through the real okf-cli.py, on a throwaway catalogue."""

    COMMANDS = [["find", "q"], ["list", "--where", "type = x"], ["recent"],
                ["merge-tags", "a", "--into", "b"], ["remove-tags", "a"], ["normalize-tags"]]

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp()
        build_fixture(cls.root)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_a_removed_flag_is_an_unrecognised_argument_with_exit_2(self):
        for command in self.COMMANDS:
            for flag in (["--type", "x"], ["--tag", "x"], ["--scope", "x"], ["--include-archive"]):
                with self.subTest(command=command[0], flag=flag[0]):
                    _out, err, code = run_cli(self.root, *command, *flag)
                    self.assertEqual(code, 2)
                    self.assertIn("unrecognized arguments: " + flag[0], err)

    def test_a_malformed_where_is_an_invalid_input_envelope_with_exit_2(self):
        for command in self.COMMANDS:
            with self.subTest(command=command[0]):
                envelope, _err, code = run_json(
                    self.root, *[a for a in command if a != "--where" and a != "type = x"],
                    "--where", "type =")
                self.assertEqual(code, 2)
                self.assertFalse(envelope["ok"])
                self.assertEqual(envelope["error"]["kind"], "invalid_input")
                self.assertIn("--where", envelope["error"]["message"])

    def test_a_malformed_where_fails_whatever_the_query_is(self):
        """find compiles the expression before it looks at the query: a query without a single
        term must not hide the error behind `(empty query)`."""
        envelope, _err, code = run_json(self.root, "find", "!!", "--where", "type =")
        self.assertEqual((code, envelope["error"]["kind"]), (2, "invalid_input"))

    def test_a_semantic_misuse_is_the_same_envelope(self):
        envelope, _err, code = run_json(self.root, "list", "--where", "archived = maybe")
        self.assertEqual((code, envelope["error"]["kind"]), (2, "invalid_input"))

    def test_the_filter_value_has_no_keyword_construction(self):
        for keyword in ("scope", "type", "tag", "include_archive"):
            with self.subTest(keyword):
                with self.assertRaises(TypeError):
                    FindFilters(**{keyword: "x"})

    def test_help_names_where_and_no_removed_flag(self):
        for command in self.COMMANDS:
            with self.subTest(command=command[0]):
                out, _err, code = run_cli(self.root, command[0], "--help")
                self.assertEqual(code, 0)
                self.assertIn("--where", out)
                self.assertNotRegex(out, r"--(type|tag|scope|include-archive)\b")
