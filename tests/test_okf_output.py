#!/usr/bin/env python3
"""Tests for cli/okf/output.py: the `--json` envelope around the entry point (`_add_output`,
the emitter in main()) and the call-note path (`_note`). The commands themselves are covered
in their own modules; here a test-local parser stands in for a converted command.

Run: just test tests.test_okf_output -v
"""
import argparse
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli")
if _HERE not in sys.path:  # cli/ holds the okf package
    sys.path.insert(0, _HERE)

from okf import output
from okf.errors import OkfError

_spec = importlib.util.spec_from_file_location("okf_cli", os.path.join(_HERE, "okf-cli.py"))
okf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(okf)

KEYS = {"command", "ok", "data", "warnings", "error"}


def _probe_parser(description=None):
    """`probe` is registered through _add_output; `ctx show` mirrors the real ctx subparser,
    whose verb lands in `ctx_verb`."""
    ap = argparse.ArgumentParser(prog="okf-cli.py")
    ap.add_argument("--root")
    sub = ap.add_subparsers(dest="cmd", required=True)
    output._add_output(sub.add_parser("probe"))
    verbs = sub.add_parser("ctx").add_subparsers(dest="ctx_verb", required=True)
    output._add_output(verbs.add_parser("show"))
    return ap


class _MainHarness(unittest.TestCase):
    """Drives the real main() with the probe parser, in-process."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        with open(os.path.join(self.root, ".okf.toml"), "w", encoding="utf-8"):
            pass
        self.addCleanup(__import__("shutil").rmtree, self.root, True)

    def run_main(self, argv, handler, root=None):
        """(stdout, stderr, exit code) of `okf --root <root> <argv>` with `handler`
        behind both probe commands."""
        argv = ["okf-cli.py", "--root", root or self.root] + argv
        out, err = io.StringIO(), io.StringIO()
        dispatch = {"probe": handler, "ctx": handler}
        with mock.patch.object(okf, "build_parser", _probe_parser), \
                mock.patch.object(okf, "COMMAND_DISPATCH", dispatch), \
                mock.patch.object(sys, "argv", argv), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                okf.main()
                code = 0
            except SystemExit as exit_:
                code = exit_.code
        return out.getvalue(), err.getvalue(), code


class EnvelopeForReturnedValue(_MainHarness):
    def test_returned_value_becomes_data_of_one_five_key_envelope(self):
        out, err, code = self.run_main(["probe", "--json"], lambda root, args: {"hits": [1, "ü"]})
        self.assertEqual(json.loads(out), {"command": "probe", "ok": True,
                                           "data": {"hits": [1, "ü"]}, "warnings": [],
                                           "error": None})
        self.assertEqual((err, code), ("", 0))

    def test_stdout_is_exactly_one_json_line(self):
        out, _err, _code = self.run_main(["probe", "--json"], lambda root, args: [1, 2])
        self.assertEqual(set(json.loads(out)), KEYS)
        self.assertEqual(out.count("\n"), 1)
        self.assertTrue(out.endswith("\n"))

    def test_ctx_verb_is_named_with_its_verb(self):
        out, _err, _code = self.run_main(["ctx", "show", "--json"], lambda root, args: [])
        self.assertEqual(json.loads(out)["command"], "ctx show")

    def test_text_mode_runs_the_handler_without_an_envelope(self):
        def handler(root, args):
            print("plain text")
            return {"ignored": True}
        out, err, code = self.run_main(["probe"], handler)
        self.assertEqual((out, err, code), ("plain text\n", "", 0))


class EnvelopeForErrors(_MainHarness):
    # The literal numbers are the specified contract (R-03), not a copy of the table.
    CODES = {"invalid_input": 2, "not_found": 3, "non_conformant": 4, "drift": 5, "internal": 1}

    def test_classified_error_without_result_has_null_data(self):
        for kind, code_ in self.CODES.items():
            with self.subTest(kind=kind):
                def handler(root, args, kind=kind):
                    raise OkfError(kind, "it broke")
                out, err, code = self.run_main(["probe", "--json"], handler)
                env = json.loads(out)
                self.assertEqual(env["error"], {"kind": kind, "code": code_, "message": "it broke"})
                self.assertEqual((env["ok"], env["data"], set(env)), (False, None, KEYS))
                self.assertEqual((code, err), (code_, ""))

    def test_error_result_lands_in_data(self):
        def handler(root, args):
            raise OkfError("non_conformant", "", result={"findings": [{"rule": "x"}]})
        out, _err, code = self.run_main(["probe", "--json"], handler)
        env = json.loads(out)
        self.assertEqual(env["data"], {"findings": [{"rule": "x"}]})
        self.assertEqual((env["ok"], env["error"]["kind"], env["error"]["code"], code),
                         (False, "non_conformant", 4, 4))

    def test_silent_error_still_carries_a_message(self):
        def handler(root, args):
            raise OkfError("drift", "")
        env = json.loads(self.run_main(["probe", "--json"], handler)[0])
        self.assertEqual(env["error"]["message"], "drift")

    def test_unclassified_exception_is_internal_with_code_1(self):
        def handler(root, args):
            raise ValueError("boom")
        out, _err, code = self.run_main(["probe", "--json"], handler)
        env = json.loads(out)
        self.assertEqual((env["ok"], env["data"], set(env)), (False, None, KEYS))
        self.assertEqual((env["error"]["kind"], env["error"]["code"], code), ("internal", 1, 1))
        self.assertIn("boom", env["error"]["message"])

    def test_unserialisable_data_is_internal_not_a_broken_document(self):
        out, _err, code = self.run_main(["probe", "--json"], lambda root, args: {1, 2})
        env = json.loads(out)
        self.assertEqual((env["error"]["kind"], code), ("internal", 1))

    def test_text_mode_error_is_unchanged(self):
        def handler(root, args):
            raise OkfError("not_found", "gone")
        self.assertEqual(self.run_main(["probe"], handler), ("", "gone\n", 3))


class EntryChecksInsideTheEnvelope(_MainHarness):
    def test_missing_root_is_a_not_found_envelope(self):
        out, err, code = self.run_main(["probe", "--json"], lambda root, args: None,
                                       root="/nonexistent/okf-root")
        env = json.loads(out)
        self.assertEqual((env["ok"], env["data"], env["error"]["kind"], env["error"]["code"]),
                         (False, None, "not_found", 3))
        self.assertIn("/nonexistent/okf-root", env["error"]["message"])
        self.assertEqual((err, code), ("", 3))

    def test_no_catalogue_found_is_a_not_found_envelope(self):
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        os.chdir(tempfile.mkdtemp())
        argv = ["okf-cli.py", "probe", "--json"]
        out = io.StringIO()
        with mock.patch.object(okf, "build_parser", _probe_parser), \
                mock.patch.object(okf, "COMMAND_DISPATCH", {"probe": lambda r, a: None}), \
                mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit) as raised:
                okf.main()
        env = json.loads(out.getvalue())
        self.assertEqual((env["error"]["kind"], raised.exception.code), ("not_found", 3))
        self.assertIn("--root", env["error"]["message"])


class CallNotes(_MainHarness):
    def test_note_in_envelope_mode_is_a_warning_and_not_on_stderr(self):
        def handler(root, args):
            output._note("index is stale")
            output._note("second one")
            return "data"
        out, err, _code = self.run_main(["probe", "--json"], handler)
        env = json.loads(out)
        self.assertEqual((env["warnings"], env["data"]), (["index is stale", "second one"], "data"))
        self.assertEqual(err, "")

    def test_note_in_text_mode_keeps_the_stderr_line(self):
        def handler(root, args):
            output._note("index is stale")
        self.assertEqual(self.run_main(["probe"], handler), ("", "note: index is stale\n", 0))

    def test_notes_survive_a_failure(self):
        def handler(root, args):
            output._note("before the failure")
            raise OkfError("not_found", "gone")
        env = json.loads(self.run_main(["probe", "--json"], handler)[0])
        self.assertEqual((env["warnings"], env["error"]["kind"]), (["before the failure"], "not_found"))

    def test_notes_do_not_leak_into_the_next_call(self):
        self.run_main(["probe", "--json"], lambda root, args: output._note("first call"))
        env = json.loads(self.run_main(["probe", "--json"], lambda root, args: None)[0])
        self.assertEqual(env["warnings"], [])

    def test_marker_note_of_the_entry_point_is_a_warning_in_envelope_mode(self):
        bare = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, bare, True)
        out, err, _code = self.run_main(["probe", "--json"], lambda root, args: None, root=bare)
        env = json.loads(out)
        self.assertEqual(len(env["warnings"]), 1)
        self.assertIn("carries no catalogue marker", env["warnings"][0])
        self.assertFalse(env["warnings"][0].startswith("note:"))
        self.assertEqual(err, "")

    def test_marker_note_in_text_mode_keeps_the_stderr_line(self):
        bare = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, bare, True)
        _out, err, _code = self.run_main(["probe"], lambda root, args: None, root=bare)
        self.assertTrue(err.startswith("note: --root {} carries no catalogue marker".format(bare)))


if __name__ == "__main__":
    unittest.main()
