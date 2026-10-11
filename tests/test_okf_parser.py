#!/usr/bin/env python3
"""Tests for cli/okf/parser.py — the parser builder, the command directory, help
conformance and shell completion. unittest.

Run: just test tests.test_okf_parser -v
"""
import argparse
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli")
if _HERE not in sys.path:  # cli/ holds the okf package
    sys.path.insert(0, _HERE)

from okf import parser as okf_parser
from okf import parser_support as okf_parser_support


class ParserExtraction(unittest.TestCase):
    """build_parser() renders the surface without executing a command."""

    def test_every_registered_command_is_dispatchable(self):
        parsers = okf_parser_support.subcommand_parsers(okf_parser.build_parser())
        self.assertEqual(set(parsers), set(okf_parser.COMMAND_DISPATCH))

    def test_parser_actions_skips_the_auto_help_action(self):
        parsers = okf_parser_support.subcommand_parsers(okf_parser.build_parser())
        dests = [a.dest for a in okf_parser_support.parser_actions(parsers["read"])]
        self.assertNotIn("help", dests)
        self.assertIn("path", dests)


class CommandDirectory(unittest.TestCase):
    """Every command carries a summary, at exactly one authored place."""

    def test_find_index_read_are_no_longer_invisible(self):
        parsers = okf_parser_support.subcommand_parsers(okf_parser.build_parser())
        for name in ("find", "index", "read"):
            self.assertTrue((parsers[name].description or "").strip(),
                            "{} has no summary".format(name))

    def test_the_summary_reaches_both_help_levels(self):
        ap = okf_parser.build_parser()
        parsers = okf_parser_support.subcommand_parsers(ap)
        summary = parsers["read"].description
        self.assertIn(summary, parsers["read"].format_help())
        self.assertIn("find", ap.format_help())

    def test_every_command_declares_a_group(self):
        parsers = okf_parser_support.subcommand_parsers(okf_parser.build_parser())
        self.assertEqual(set(okf_parser_support.COMMAND_GROUPS), set(parsers))

    def test_find_help_explains_both_score_scales(self):
        parsers = okf_parser_support.subcommand_parsers(okf_parser.build_parser())
        text = parsers["find"].format_help()
        self.assertIn("100", text)
        self.assertIn("6 * number of terms", text)
        self.assertIn("provenance", text)


class FindOptionHelp(unittest.TestCase):
    """find's options describe themselves, and truthfully."""

    def _find_action(self, dest):
        parsers = okf_parser_support.subcommand_parsers(okf_parser.build_parser())
        for act in okf_parser_support.parser_actions(parsers["find"]):
            if act.dest == dest:
                return act
        self.fail("find has no action with dest {!r}".format(dest))

    def test_limit_carries_help_text(self):
        self.assertIn("default 10", self._find_action("limit").help or "")

    def test_expand_tags_no_longer_promises_a_pending_measurement(self):
        help_text = self._find_action("expand_tags").help or ""
        self.assertNotIn("until measured", help_text)
        self.assertIn("measured", help_text)


class CommandDirectoryOrder(unittest.TestCase):

    def test_commands_are_listed_alphabetically(self):
        names = list(okf_parser_support.subcommand_parsers(okf_parser.build_parser()))
        self.assertEqual(names, sorted(names))

    def test_top_level_help_points_at_per_command_help(self):
        self.assertIn("<command> --help", okf_parser.build_parser().format_help())


class CommandHelpConformance(unittest.TestCase):
    """An undocumented command or option is unmergeable, not merely
    noticeable (D02). This is the gate the 2026-07-26 PO review asked for."""

    def setUp(self):
        self.ap = okf_parser.build_parser()
        self.parsers = okf_parser_support.subcommand_parsers(self.ap)

    def test_every_subcommand_has_a_summary(self):
        missing = sorted(n for n, p in self.parsers.items()
                         if not (p.description or "").strip())
        self.assertEqual(missing, [])

    def test_every_option_and_positional_has_help(self):
        missing = []
        for name, parser in sorted(self.parsers.items()):
            for act in okf_parser_support.parser_actions(parser):
                if not (act.help or "").strip():
                    missing.append("{} {}".format(name, act.dest))
        self.assertEqual(missing, [])

    def test_every_command_is_grouped_and_dispatchable(self):
        self.assertEqual(set(okf_parser_support.COMMAND_GROUPS), set(self.parsers))
        self.assertEqual(set(okf_parser.COMMAND_DISPATCH), set(self.parsers))

    def test_top_level_option_has_help(self):
        """R-02 (okf-cli-x60r): the subcommand-only gate above missed the
        top-level parser's own options (e.g. --root). parser_actions()
        drops the auto-added -h/--help (AC-2), but on the top-level parser
        object it also yields the add_subparsers() dispatch action itself
        (dest="cmd") — that is not a user-facing option; the summary each
        subcommand carries is already asserted by
        test_every_subcommand_has_a_summary above, so it is filtered here
        too. A separate method, rather than folding this into
        test_every_option_and_positional_has_help, gives a failure message
        scoped to the top-level surface and keeps that existing method's
        assertion untouched (AC-4)."""
        missing = [act.dest for act in okf_parser_support.parser_actions(self.ap)
                   if not isinstance(act, argparse._SubParsersAction)
                   and not (act.help or "").strip()]
        self.assertEqual(missing, [])


@unittest.skipUnless(importlib.util.find_spec("argcomplete"),
                     "argcomplete not installed (pip install argcomplete)")
class ShellCompletion(unittest.TestCase):
    """TAB completion, driven through the real cli/okf-cli.py with the env
    protocol the zsh glue cli/_okf-cli speaks. --root is the raw shell word
    `~/cat`, as the glue delivers it from an alias."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        for rel, text in {
            "stray.txt": "x",
            "cat/TYPES.md": "| Type | Note |\n|---|---|\n| `Concept` | a |\n| `Decision` | b |\n",
            "cat/b1/alpha.md": "---\ntitle: Alpha\ntype: Concept\ntags: [x, y]\n---\nbody\n",
            "cat/b1/sub/beta.md": ("---\ntitle: Beta\ntype: Decision\ntags: [x]\n---\n"
                                   "<!-- okf:canon id=blk-1 -->\npayload\n<!-- /okf:canon -->\n"),
            "cat/_archive/b1/old.md": "---\ntitle: Old\n---\n",
        }.items():
            path = os.path.join(self.tmp, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)

    def _complete(self, words, start=None):
        import subprocess
        import sys
        line = "okf-cli --root ~/cat " + words
        out = os.path.join(self.tmp, "out")
        env = dict(os.environ, HOME=self.tmp, COMP_LINE=line, COMP_POINT=str(len(line)),
                   _ARGCOMPLETE="1", _ARGCOMPLETE_SHELL="zsh",
                   _ARGCOMPLETE_SUPPRESS_SPACE="1", _ARGCOMPLETE_STDOUT_FILENAME=out)
        subprocess.run((start or [sys.executable]) + [os.path.join(_HERE, "okf-cli.py")],
                       env=env, cwd=self.tmp, capture_output=True)
        if not os.path.exists(out):
            return []
        with open(out, encoding="utf-8") as f:
            raw = f.read()
        if not raw:
            return []
        return [tuple(e.split(":", 1)) if ":" in e else (e, "") for e in raw.split("\x0b")]

    def test_completion_through_uv_run_script_returns_the_same_candidates(self):
        """R-11 — the zsh glue calls the `okf-cli` wrapper, which starts `uv run --script`. The
        script environment holds argcomplete only when the PEP 723 header declares it; without it
        the call returns no candidates and no error."""
        import subprocess
        uv_dirs = {k: subprocess.run(["uv", d, "dir"], capture_output=True, text=True, check=True).stdout.strip()
                   for k, d in (("UV_CACHE_DIR", "cache"), ("UV_PYTHON_INSTALL_DIR", "python"))}
        with mock.patch.dict(os.environ, uv_dirs):  # kept when _complete swaps HOME for the fixture
            self.assertEqual(self._complete("merge-tags q --into ", start=["uv", "run", "--script"]),
                             [("x", "concepts: 2"), ("y", "concepts: 1")])

    def _values(self, words):
        """Candidates minus option strings: argcomplete offers `-h/--help`
        next to positional values."""
        return [v for v, _ in self._complete(words) if not v.startswith("-")]

    def test_tag_values_most_used_first_with_counts(self):
        self.assertEqual(self._complete("merge-tags q --into "),
                         [("x", "concepts: 2"), ("y", "concepts: 1")])

    def test_scope_values_are_bundles_and_concept_dirs(self):
        self.assertEqual(self._values("check "), ["b1", "b1/sub"])

    def test_concept_refs_and_archive_on_restore(self):
        self.assertEqual(self._values("read "), ["b1/alpha", "b1/sub/beta"])
        self.assertEqual(self._values("archive --restore "), ["_archive/b1/old"])

    def test_block_ids_come_from_the_concept_on_the_line(self):
        self.assertEqual(self._values("sync-export b1/sub/beta "), ["blk-1"])

    def test_free_text_offers_options_not_cwd_files(self):
        values = [v for v, _ in self._complete("find ")]
        self.assertIn("--where", values)
        self.assertNotIn("stray.txt", values)


if __name__ == "__main__":
    unittest.main()
