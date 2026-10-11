#!/usr/bin/env python3
"""Tests for the entry file cli/okf-cli.py itself: main(), the root safety it enforces and the
BrokenPipe handling of its __main__ guard. The commands live in cli/okf/, one test module each.

Run: python3 -m unittest tests.test_okf_cli -v
"""
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli")
if _HERE not in sys.path:  # cli/ holds the okf package
    sys.path.insert(0, _HERE)
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from okf import catalogue as okf_catalogue
from okf import errors as okf_errors
from okf import fts as okf_fts
from okf import parser as okf_parser
from okf import parser_support as okf_parser_support
from tests.okf_testkit import SyncFixtureMixin

_spec = importlib.util.spec_from_file_location("okf_cli", os.path.join(_HERE, "okf-cli.py"))
okf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(okf)


class RootSafety(unittest.TestCase):
    """okf-cli-1617 (P11) — no --root + no auto-detectable catalogue must
    hard-fail instead of silently scanning the script's own directory."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.cwd = os.getcwd()

    def tearDown(self):
        import shutil
        os.chdir(self.cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_explicit_root_returns_abspath_unchanged(self):
        # SC-002: --root behavior unchanged regardless of cwd/markers
        got = okf_catalogue.catalogue_root(self.tmp)
        self.assertEqual(got, os.path.abspath(self.tmp))

    def test_no_root_no_catalogue_returns_none(self):
        os.chdir(self.tmp)
        self.assertIsNone(okf_catalogue.catalogue_root(None))

    def test_no_root_no_catalogue_hard_fails_via_main(self):
        # SC-001
        os.chdir(self.tmp)
        import sys as _sys
        old_argv, old_stderr = _sys.argv, _sys.stderr
        _sys.argv = ["okf-cli.py", "find", "test"]
        _sys.stderr = captured = io.StringIO()
        try:
            with self.assertRaises(SystemExit) as ctx:
                okf.main()
        finally:
            _sys.argv, _sys.stderr = old_argv, old_stderr
        self.assertEqual(ctx.exception.code, okf_errors.EXIT_CODES["not_found"])
        self.assertIn("--root", captured.getvalue())

    def test_auto_detect_okf_toml_marker(self):
        # SC-003
        with open(os.path.join(self.tmp, ".okf.toml"), "w", encoding="utf-8") as f:
            f.write("")
        os.chdir(self.tmp)
        self.assertEqual(okf_catalogue.catalogue_root(None), os.getcwd())

    def test_auto_detect_spec_types_marker(self):
        # SC-003
        open(os.path.join(self.tmp, "SPEC.md"), "w", encoding="utf-8").close()
        open(os.path.join(self.tmp, "TYPES.md"), "w", encoding="utf-8").close()
        os.chdir(self.tmp)
        self.assertEqual(okf_catalogue.catalogue_root(None), os.getcwd())

    def test_partial_marker_not_enough(self):
        open(os.path.join(self.tmp, "SPEC.md"), "w", encoding="utf-8").close()
        os.chdir(self.tmp)
        self.assertIsNone(okf_catalogue.catalogue_root(None))

    def test_auto_detect_walks_up_from_subdir(self):
        # SC-003: ancestor lookup
        open(os.path.join(self.tmp, ".okf.toml"), "w", encoding="utf-8").close()
        sub = os.path.join(self.tmp, "a", "b")
        os.makedirs(sub)
        os.chdir(sub)
        expected = os.path.dirname(os.path.dirname(os.getcwd()))
        self.assertEqual(okf_catalogue.catalogue_root(None), expected)

    def test_auto_detect_docs_nested_okf_toml_from_sibling_subdir(self):
        # okf-cli worktree bug: a hull-layout project keeps `docs/.okf.toml`
        # at the WORKSPACE level, sibling to `repo/` and `worktrees/<id>/` —
        # never inside either checkout. From a linked worktree two levels
        # below the hull, the walk must still find `<hull>/docs/.okf.toml`
        # and return `<hull>/docs` (not the hull itself, and not None).
        hull = self.tmp
        docs = os.path.join(hull, "docs")
        os.makedirs(docs)
        open(os.path.join(docs, ".okf.toml"), "w", encoding="utf-8").close()
        worktree = os.path.join(hull, "worktrees", "container-1")
        os.makedirs(worktree)
        os.chdir(worktree)
        # os.getcwd() resolves the macOS /var -> /private/var symlink that
        # tempfile.mkdtemp() returns unresolved, so derive the expectation
        # from the resolved cwd rather than from self.tmp directly.
        expected = os.path.join(os.path.dirname(os.path.dirname(os.getcwd())), "docs")
        self.assertEqual(okf_catalogue.catalogue_root(None), expected)


class GroupedOverview(unittest.TestCase):

    def test_overview_names_every_group_that_has_commands(self):
        text = okf_parser.build_parser().format_help()
        self.assertIn("commands by purpose:", text)
        for group in okf_parser_support._GROUP_ORDER:
            self.assertIn("  {}:".format(group), text)

    def test_overview_covers_every_command(self):
        text = okf_parser.build_parser().format_help()
        overview = text.split("commands by purpose:", 1)[1]
        for name in okf_parser_support.COMMAND_GROUPS:
            self.assertRegex(overview, r"\n\s+{}\s".format(re.escape(name)))

    def test_module_docstring_no_longer_lists_commands_by_hand(self):
        self.assertNotIn("okf-cli.py find", okf.__doc__)
        self.assertNotIn("okf-cli.py merge-tags", okf.__doc__)


class TopLevelHelpDescription(unittest.TestCase):
    """The parser is built in okf.parser, whose own docstring is another text; the
    entry hands its docstring over, so `okf-cli.py --help` still opens with it."""

    def test_help_prints_the_entry_docstring(self):
        done = subprocess.run([sys.executable, os.path.join(_HERE, "okf-cli.py"), "--help"],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(okf.__doc__.strip(), done.stdout)


class BrokenPipeOnFind(unittest.TestCase):
    """OKFT-0k55. `okf-cli find <query> | head` must not surface Python's
    plumbing. This needs a REAL subprocess piped into a REAL early-closing
    reader — an in-process contextlib.redirect_stdout(io.StringIO()) (as
    `okf_testkit.run_find` uses) never touches an actual file descriptor, so it
    can never observe SIGPIPE/EPIPE at all; that is the exact interplay of
    process, pipe and interpreter shutdown this bean is about.

    Two failure modes, asserted separately per the bean's acceptance
    criteria: (1) the raised BrokenPipeError itself must not print a
    traceback, and (2) flushing the still-open (now broken) stdout at
    interpreter shutdown must not print `Exception ignored in: ...` — that
    second message appears only AFTER any handler has already run, so
    catching the exception alone provably does not cover it (proven by the
    RED run captured in OKFT-0k55's `## Test-Output`, before stdout was
    redirected to os.devnull).

    D01 (bean, revisable — Q02 open with the PO): exit status on a clean
    early close is 0, not 141.

    The producer needs enough real output that it is still writing after
    the consumer has already closed its end, or the whole answer fits in
    the OS pipe buffer and no EPIPE is ever raised — hence 300 fixture
    concepts with a padded body (CLAUDE.md rule 1: this substrate lives
    under its own tmpdir, never under ~/Obsidian/Knowledge-Catalogue)."""

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(cls.root, "b"))
        pad = "x" * 400
        for i in range(300):
            with open(os.path.join(cls.root, "b", "c{}.md".format(i)), "w",
                      encoding="utf-8") as f:
                f.write(
                    "---\ntype: Concept\ntitle: Zqxbrokenpipe item {}\n"
                    "description: {}\ntags: [k]\n---\n# t{}\n\n{}\n".format(
                        i, pad, i, pad))
        with open(os.path.join(cls.root, "b", "index.md"), "w",
                  encoding="utf-8") as f:
            f.write("# B\n")
        okf_fts.build_fts_index(cls.root)
        for i in range(300):
            with open(os.path.join(cls.root, "b", "invalid{}.md".format(i)),
                      "wb") as f:
                f.write(b"\xff\n")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def _pipe_into_early_closing_reader(self):
        import subprocess
        import sys
        producer = subprocess.Popen(
            [sys.executable, os.path.join(_HERE, "okf-cli.py"), "--root",
             self.root, "find", "zqxbrokenpipe", "--limit", "300"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        consumer = subprocess.Popen(["head", "-n", "1"],
                                     stdin=producer.stdout,
                                     stdout=subprocess.DEVNULL)
        # Drop our own handle on the read end so the producer's writes hit
        # EPIPE once (and only once) the consumer's copy is gone too —
        # the standard recipe for provoking SIGPIPE across a Popen pipe.
        producer.stdout.close()
        consumer.wait(timeout=10)
        producer.wait(timeout=10)
        stderr = producer.stderr.read().decode("utf-8", "replace")
        producer.stderr.close()
        return producer.returncode, stderr
    def _pipe_merged_stderr_into_early_closing_reader(self):
        import subprocess
        import sys
        producer = subprocess.Popen(
            [sys.executable, os.path.join(_HERE, "okf-cli.py"), "--root",
             self.root, "fix-crosslinks", "b"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        consumer = subprocess.Popen(["head", "-n", "1"],
                                     stdin=producer.stdout,
                                     stdout=subprocess.PIPE)
        producer.stdout.close()
        consumer_output = consumer.communicate(timeout=10)[0]
        producer.wait(timeout=10)
        return producer.returncode, consumer_output.decode("utf-8", "replace")

    def test_merged_stderr_pipe_exits_cleanly(self):
        returncode, output = self._pipe_merged_stderr_into_early_closing_reader()
        self.assertEqual(returncode, 0)
        self.assertNotIn("Traceback (most recent call last)", output)
        self.assertNotIn("Exception ignored", output)


    def test_no_traceback_on_stderr(self):
        _, stderr = self._pipe_into_early_closing_reader()
        self.assertNotIn("Traceback (most recent call last)", stderr)
        self.assertNotIn("BrokenPipeError", stderr)

    def test_no_exception_ignored_noise_at_interpreter_shutdown(self):
        # ERRATA vs. the bean text: this interpreter (3.14) prints
        # "Exception ignored while flushing sys.stdout:", not the older
        # "Exception ignored in: <_io.TextIOWrapper ...>" the bean quotes —
        # same failure class (unraisable-exception noise from flushing a
        # closed stdout at shutdown), different exact wording across
        # CPython versions. Assert the version-stable substring so the
        # test does not accidentally pass vacuously on a newer runtime.
        _, stderr = self._pipe_into_early_closing_reader()
        self.assertNotIn("Exception ignored", stderr)

    def test_exit_status_is_zero_per_d01(self):
        returncode, _ = self._pipe_into_early_closing_reader()
        self.assertEqual(returncode, 0)


class BrokenPipeOnFindTinyAnswer(unittest.TestCase):
    """Companion to BrokenPipeOnFind, guarding a failure mode the large
    fixture there cannot reach. Confirmed against the real Knowledge-
    Catalogue (read-only smoke, no write — CLAUDE.md rule 1) during
    OKFT-0k55: a small `find` answer completes cmd_find's whole print loop
    without ANY write() syscall ever being attempted — stdout to a pipe is
    block-buffered (default ~8KB), so a small answer just accumulates in
    Python's own buffer and main() returns normally. The one and only
    write() then happens at the FINAL flush, whichever flush actually
    runs first: our entrypoint's explicit `sys.stdout.flush()` (inside its
    try/except), or — if that line is ever removed — Python's own implicit
    flush at interpreter shutdown, which runs OUTSIDE any try/except in
    user code and therefore can never be caught, however it's written
    around `main()`.

    A `head -n 1` consumer (as BrokenPipeOnFind uses) cannot isolate this:
    `head` has to actually read a line before it can exit, so with a
    small, fully-buffered answer it just blocks until that one write
    lands — and since the write happens while `head` is still connected,
    it always succeeds either way, discriminating nothing. The consumer
    here instead exits immediately without reading anything at all — a
    real subprocess that inherits and then simply drops its copy of the
    pipe's read end on exit — so the read end is already gone before the
    producer's single write is ever attempted, regardless of buffering."""

    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(cls.root, "b"))
        with open(os.path.join(cls.root, "b", "one.md"), "w",
                  encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: Zqxtinyanswer\n"
                    "description: d\ntags: [k]\n---\n# t\n\nzqxtinyanswer\n")
        with open(os.path.join(cls.root, "b", "index.md"), "w",
                  encoding="utf-8") as f:
            f.write("# B\n")
        okf_fts.build_fts_index(cls.root)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def _pipe_into_instantly_closing_reader(self):
        import subprocess
        import sys
        producer = subprocess.Popen(
            [sys.executable, os.path.join(_HERE, "okf-cli.py"), "--root",
             self.root, "find", "zqxtinyanswer"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        consumer = subprocess.Popen([sys.executable, "-c", "pass"],
                                     stdin=producer.stdout,
                                     stdout=subprocess.DEVNULL)
        producer.stdout.close()
        consumer.wait(timeout=10)
        producer.wait(timeout=10)
        stderr = producer.stderr.read().decode("utf-8", "replace")
        producer.stderr.close()
        return producer.returncode, stderr

    def test_no_exception_ignored_noise_when_answer_fits_the_buffer(self):
        _, stderr = self._pipe_into_instantly_closing_reader()
        self.assertNotIn("Exception ignored", stderr)

    def test_exit_status_is_zero_when_answer_fits_the_buffer(self):
        returncode, _ = self._pipe_into_instantly_closing_reader()
        self.assertEqual(returncode, 0)


class MainExplicitRootMarkerWarning(unittest.TestCase):
    """OKFT-czm9 root cause: resolve_crosslink_target and peers compute every
    emitted path as "/" + relpath(dest, root). An explicit --root pointed one
    level above the real catalogue silently prefixes every emitted path with
    the extra segment (the observed vault-relative alias) instead of failing.
    main() must warn on stderr, without blocking (SC-002 requires an explicit
    --root to keep working with no marker present)."""

    def test_warns_when_explicit_root_has_no_marker(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "bundle"))
            import sys as _sys, io as _io
            old_argv, old_stderr = _sys.argv, _sys.stderr
            _sys.argv = ["okf-cli.py", "--root", root, "index"]
            _sys.stderr = captured = _io.StringIO()
            try:
                okf.main()
            finally:
                _sys.argv, _sys.stderr = old_argv, old_stderr
            self.assertIn("no catalogue marker", captured.getvalue())

    def test_no_warning_when_marker_present(self):
        with tempfile.TemporaryDirectory() as root:
            okf_catalogue.write_file(os.path.join(root, ".okf.toml"), "")
            import sys as _sys, io as _io
            old_argv, old_stderr = _sys.argv, _sys.stderr
            _sys.argv = ["okf-cli.py", "--root", root, "index"]
            _sys.stderr = captured = _io.StringIO()
            try:
                okf.main()
            finally:
                _sys.argv, _sys.stderr = old_argv, old_stderr
            self.assertNotIn("no catalogue marker", captured.getvalue())

    def test_no_warning_when_root_auto_detected(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "bundle"))
            import sys as _sys, io as _io
            old_cwd, old_argv, old_stderr = os.getcwd(), _sys.argv, _sys.stderr
            os.chdir(root)
            okf_catalogue.write_file(os.path.join(root, ".okf.toml"), "")
            _sys.argv = ["okf-cli.py", "index"]
            _sys.stderr = captured = _io.StringIO()
            try:
                okf.main()
            finally:
                os.chdir(old_cwd)
                _sys.argv, _sys.stderr = old_argv, old_stderr
            self.assertNotIn("no catalogue marker", captured.getvalue())


class ExitErrorMapping(unittest.TestCase):
    def test_error_kinds_carry_their_table_code(self):
        self.assertEqual(set(okf_errors.EXIT_CODES),
                         {"internal", "invalid_input", "not_found", "non_conformant", "drift"})
        self.assertEqual(len(set(okf_errors.EXIT_CODES.values())), 5)
        for kind in okf_errors.EXIT_CODES:
            error = okf_errors.OkfError(kind, "problem")
            self.assertEqual((error.kind, error.message, error.code),
                             (kind, "problem", okf_errors.EXIT_CODES[kind]))
        with self.assertRaises(ValueError):
            okf_errors.OkfError("unknown", "problem")

    def test_main_maps_okf_error_without_losing_stdout(self):
        def fail(_, __):
            print("report")
            raise okf_errors.OkfError("drift", "stale")

        old_argv, old_stdout, old_stderr = sys.argv, sys.stdout, sys.stderr
        sys.argv = ["okf-cli.py", "prime"]
        stdout, stderr = io.StringIO(), io.StringIO()
        sys.stdout, sys.stderr = stdout, stderr
        try:
            with tempfile.TemporaryDirectory() as root:
                with (mock.patch.object(okf, "COMMAND_DISPATCH", {"prime": fail}),
                      mock.patch.object(okf, "catalogue_root", return_value=root)):
                    with self.assertRaises(SystemExit) as raised:
                        okf.main()
        finally:
            sys.argv, sys.stdout, sys.stderr = old_argv, old_stdout, old_stderr
        self.assertEqual(raised.exception.code, okf_errors.EXIT_CODES["drift"])
        self.assertEqual(stdout.getvalue(), "report\n")
        self.assertEqual(stderr.getvalue(), "stale\n")

    def test_unknown_flag_exits_two_with_or_without_json(self):
        with tempfile.TemporaryDirectory() as root:
            for argv in (["--root", root, "index", "--unknown"],
                         ["--root", root, "index", "--json", "--unknown"]):
                result = subprocess.run(
                    [sys.executable, os.path.join(_HERE, "okf-cli.py"), *argv],
                    capture_output=True, text=True)
                self.assertEqual(result.returncode, 2, result.stderr)

    def test_unhandled_exception_exits_one(self):
        program = """
import importlib.util
import sys
sys.path.insert(0, {cli!r})
spec = importlib.util.spec_from_file_location("entry", {entry!r})
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)
entry.COMMAND_DISPATCH = {{"prime": lambda _, __: (_ for _ in ()).throw(RuntimeError("broken"))}}
sys.argv = ["okf-cli.py", "--root", {root!r}, "prime"]
entry.main()
"""
        with tempfile.TemporaryDirectory() as root:
            result = subprocess.run(
                [sys.executable, "-c", program.format(
                    cli=_HERE, entry=os.path.join(_HERE, "okf-cli.py"), root=root)],
                cwd=root, capture_output=True, text=True)
        self.assertEqual(result.returncode, okf_errors.EXIT_CODES["internal"], result.stderr)
        self.assertIn("RuntimeError: broken", result.stderr)


class ExitCodePerClass(unittest.TestCase):
    """R-03 end to end: the real entry file against a throwaway catalogue. The
    literal numbers are the specified contract, not a copy of the table."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        open(os.path.join(self.root, ".okf.toml"), "w").close()
        os.makedirs(os.path.join(self.root, "b"))
        self._w("b/one.md", "---\ntype: Concept\ndescription: d\n---\n# One\n")

    def _w(self, rel, text):
        with open(os.path.join(self.root, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def _cli(self, *argv):
        return subprocess.run(
            [sys.executable, os.path.join(_HERE, "okf-cli.py"), "--root", self.root, *argv],
            capture_output=True, text=True)

    def test_read_missing_concept_is_3(self):
        r = self._cli("read", "b/missing")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (3, "", "not found: b/missing\n"))

    def test_empty_result_is_0(self):
        r = self._cli("find", "zzzznothingmatches")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self._cli("list", "--type", "NoSuchType")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_rejected_call_is_2(self):
        r = self._cli("list")
        self.assertEqual((r.returncode, r.stderr), (2, "(error: pass --type and/or --tag)\n"))

    def test_check_violation_is_4_with_full_report_in_both_modes(self):
        self._w("b/bad.md", "no frontmatter\n")
        text = self._cli("check")
        self.assertEqual(text.returncode, 4, text.stderr)
        self.assertIn("VIOLATIONS", text.stdout)
        js = self._cli("check", "--json")
        self.assertEqual(js.returncode, 4, js.stderr)
        self.assertIn(("okf/frontmatter/parseable", "error", "b/bad.md"),
                      [(f["rule"], f["severity"], f["path"])
                       for f in json.loads(js.stdout)["findings"]])

    def test_reindex_check_stale_is_5(self):
        self._w("b/index.md", "# B\n\n<!-- okf:index -->\nstale\n<!-- /okf:index -->\n")
        r = self._cli("reindex", "b", "--check")
        self.assertEqual(r.returncode, 5, r.stderr)
        self.assertIn("STALE", r.stdout)
        self.assertIn("reindex --check: 1 stale", r.stdout)

    def test_tags_validate_unknown_is_4_with_report_known_is_0(self):
        self._w("TAGS.md", "| Tag | Description |\n|---|---|\n| `known` | d |\n")
        r = self._cli("tags", "--validate", "known", "ghost")
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertIn("UNKNOWN  ghost", r.stdout)
        self.assertIn("1 UNKNOWN — register with", r.stdout)
        r = self._cli("tags", "--validate", "known")
        self.assertEqual((r.returncode, r.stdout), (0, "OK — all 1 known\n"))

    def test_unknown_flag_is_2_in_both_modes(self):
        for argv in (["check", "--nope"], ["check", "--json", "--nope"]):
            self.assertEqual(self._cli(*argv).returncode, 2, argv)


class SyncStatusDriftExit(SyncFixtureMixin, unittest.TestCase):
    def test_outdated_block_is_5_with_report_in_both_modes(self):
        self._insert()
        self._w("kc-gov/ownership.md",
                self._r("kc-gov/ownership.md").replace(self.OWNER_PAYLOAD, "Neuer Kanon.\n"))
        for extra in ((), ("--json",)):
            r = subprocess.run(
                [sys.executable, os.path.join(_HERE, "okf-cli.py"), "--root", self.tmp,
                 "sync-status", *extra], capture_output=True, text=True)
            self.assertEqual(r.returncode, 5, r.stderr)
            self.assertIn("source-changed", r.stdout)


if __name__ == "__main__":
    unittest.main()
