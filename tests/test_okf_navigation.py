#!/usr/bin/env python3
"""Tests for cli/okf/navigation.py — the list, read, info, toc, visualize and refs
commands. Stdlib unittest, no deps.

Run: python3 -m unittest tests.test_okf_navigation -v
"""
import os
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli")
if _HERE not in sys.path:  # cli/ holds the okf package
    sys.path.insert(0, _HERE)
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from okf import index as okf_index
from okf import linkscan as okf_linkscan
from okf import navigation as okf_navigation
from okf import parser as okf_parser
from okf import parser_support as okf_parser_support
from okf.errors import OkfError
from tests.okf_testkit import _cli, run_find


class VisualizeDefaultOutputPath(unittest.TestCase):
    """viz.html is a generated artifact, not knowledge content — it must land
    under <bundle>/assets/ by default so it doesn't trip kc/asset/placement."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_default_out_is_under_bundle_assets(self):
        import types
        os.makedirs(os.path.join(self.tmp, "b"))
        with open(os.path.join(self.tmp, "b", "x.md"), "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: X\n---\n# X\n")
        args = types.SimpleNamespace(bundle="b", out=None)
        okf_navigation.cmd_visualize(self.tmp, args)
        expected = os.path.join(self.tmp, "b", "assets", "viz.html")
        self.assertTrue(os.path.isfile(expected))


class CmdRefs(unittest.TestCase):
    """cmd_refs (B03): path resolves against --scan-root when given (the tree it
    lives in); a missing target exits non-zero instead of silently returning []."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _w(self, rel, text):
        ap = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(text)

    def test_scan_root_relative_path_resolves(self):
        import io, json, contextlib, types
        self._w("docs/arch.md", "# A\n")
        self._w("README.md", "[a](docs/arch.md)\n")
        # skill-style call: --root <repo>/docs, --scan-root <repo>, repo-relative path
        args = types.SimpleNamespace(path="docs/arch.md", scan_root=self.tmp, json=True)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf_navigation.cmd_refs(os.path.join(self.tmp, "docs"), args)
        out = json.loads(buf.getvalue())
        self.assertEqual([h["source"] for h in out["inbound"]], ["README.md"])

    def _refs(self, path, **flags):
        import io, json, contextlib, types
        args = types.SimpleNamespace(path=path, scan_root=self.tmp, json=False,
                                     only_in=False, only_out=False)
        for k, v in flags.items():
            setattr(args, k, v)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf_navigation.cmd_refs(self.tmp, args)
        return json.loads(buf.getvalue()) if args.json else buf.getvalue()

    def _link_fixture(self):
        self._w("b/one.md", "---\ntype: Concept\n---\n[T](/b/two.md) [G](gone.md#x) "
                            "[W](http://x.org/a.md)\n```\n[F](/b/fenced.md)\n```\n")
        self._w("b/two.md", "# two\n")

    def test_text_has_inbound_and_outbound_sections(self):
        self._link_fixture()
        self.assertEqual(self._refs("b/two.md"),
                         "inbound (1):\n  b/one.md  ->  /b/two.md\noutbound (0):\n  (none)\n")
        self.assertEqual(self._refs("b/one.md"),
                         "inbound (0):\n  (none)\noutbound (2):\n"
                         "  /b/two.md  ->  b/two.md\n"
                         "  gone.md#x  ->  b/gone.md  [missing]\n")

    def test_in_and_out_flags_select_one_section(self):
        self._link_fixture()
        self.assertEqual(self._refs("b/one.md", only_in=True), "inbound (0):\n  (none)\n")
        self.assertEqual(self._refs("b/one.md", only_out=True).splitlines()[0], "outbound (2):")
        self.assertNotIn("inbound", self._refs("b/one.md", only_out=True))

    def test_json_outbound_and_flag_omissions(self):
        self._link_fixture()
        full = self._refs("b/one.md", json=True)
        self.assertEqual(full["inbound"], [])
        self.assertEqual(full["outbound"], [
            {"link": "/b/two.md", "target": "b/two.md", "exists": True},
            {"link": "gone.md#x", "target": "b/gone.md", "exists": False}])
        self.assertNotIn("outbound", self._refs("b/two.md", json=True, only_in=True))
        self.assertNotIn("inbound", self._refs("b/two.md", json=True, only_out=True))

    def test_non_markdown_target_has_no_outbound(self):
        self._w("notes.txt", "[T](/b/two.md)\n")
        self._w("b/two.md", "# two\n")
        self.assertEqual(self._refs("notes.txt", only_out=True), "outbound (0):\n  (none)\n")

    def test_target_outside_scan_root_is_absolute(self):
        self._w("a.md", "[O](../../outside.md)\n")
        out = self._refs("a.md", json=True)["outbound"][0]
        self.assertEqual(out["target"], os.path.abspath(os.path.join(self.tmp, "../../outside.md")))

    def test_outbound_links_and_matrix_share_resolution(self):
        self._w("d/a.md", "[x]( ../e/t.md?q ) [m](mailto:a@b)\n")
        self._w("e/t.md", "t\n")
        ap = os.path.join(self.tmp, "d/a.md")
        tgt = os.path.join(self.tmp, "e/t.md")
        self.assertEqual(okf_linkscan.outbound_links(self.tmp, ap), [(" ../e/t.md?q ", tgt, True)])
        self.assertEqual(list(okf_linkscan.iter_md_links(self.tmp)), [("d/a.md", " ../e/t.md?q ", tgt)])
        self.assertEqual(okf_linkscan.build_ref_matrix(self.tmp, tgt), [("d/a.md", " ../e/t.md?q ")])
        self.assertEqual(okf_linkscan.resolve_md_link(self.tmp, ap, "mailto:a@b"), None)

    def test_missing_target_exits_nonzero(self):
        import types
        args = types.SimpleNamespace(path="ghost.md", scan_root=self.tmp, json=True)
        with self.assertRaises(OkfError) as cm:
            okf_navigation.cmd_refs(os.path.join(self.tmp, "docs"), args)
        self.assertNotEqual(cm.exception.code, 0)


class CmdListJson(unittest.TestCase):
    """okf-cli-83vq (B01) — `list --json` emits a json.loads-parseable array;
    non-json output stays byte-identical to today's human-readable form."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        ap = os.path.join(self.tmp, "b", "one.md")
        os.makedirs(os.path.dirname(ap))
        with open(ap, "w", encoding="utf-8") as f:
            f.write(
                "---\ntype: Runbook\ntitle: One\ndescription: first\n"
                "tags: [alpha]\n---\n# One\n"
            )
        ap2 = os.path.join(self.tmp, "b", "two.md")
        with open(ap2, "w", encoding="utf-8") as f:
            f.write(
                "---\ntype: Runbook\ntitle: Two\ndescription: second\n"
                "tags: [beta]\n---\n# Two\n"
            )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, **kw):
        import io, contextlib, types
        args = types.SimpleNamespace(type=None, tag=None, scope=None, json=False)
        for k, v in kw.items():
            setattr(args, k, v)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf_navigation.cmd_list(self.tmp, args)
        return buf.getvalue()

    def test_json_output_is_parseable_array(self):
        import json
        out = self._run(type="Runbook", json=True)
        data = json.loads(out)
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)
        self.assertTrue(all("path" in r and "type" in r and "title" in r
                            and "description" in r for r in data))

    def test_json_empty_result_is_parseable_empty_array(self):
        import json
        out = self._run(type="Nope", json=True)
        data = json.loads(out)
        self.assertEqual(data, [])

    def test_non_json_output_unchanged(self):
        out_json_false = self._run(type="Runbook", json=False)
        out_no_flag = self._run(type="Runbook")
        self.assertEqual(out_json_false, out_no_flag)
        self.assertIn("list: 2 concept(s)", out_json_false)
        self.assertNotIn("{", out_json_false)


class ListIncludeArchive(unittest.TestCase):
    """R-12/AC1-AC3 (okf-cli-iwx4) — `list` reaches the archive through the
    SAME resolve_scopes() `_substring_ranking` uses (SubstringRankingArchive
    in test_okf_find.py), not a second implementation of the same rule."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._w("bundle-a/active.md", "Runbook", "Active")
        self._w("_archive/bundle-a/hidden.md", "Runbook", "Hidden")
        self._w("_archive/bundle-b/other.md", "Concept", "Other")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _w(self, rel, typ, title):
        ap = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write("---\ntype: {}\ntitle: {}\ndescription: d\ntags: []\n"
                    "---\n# {}\n".format(typ, title, title))

    def _run(self, **kw):
        import io, contextlib, types
        args = types.SimpleNamespace(type=None, tag=None, scope=None,
                                     json=False, include_archive=False)
        for k, v in kw.items():
            setattr(args, k, v)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf_navigation.cmd_list(self.tmp, args)
        return buf.getvalue()

    def test_sc01_default_excludes_archived_concept(self):
        out = self._run(type="Runbook")
        self.assertIn("path: bundle-a/active", out)
        self.assertNotIn("path: _archive/bundle-a/hidden", out)

    def test_sc01_flag_includes_archived_concept_of_matching_type(self):
        out = self._run(type="Runbook", include_archive=True)
        self.assertIn("path: bundle-a/active", out)
        self.assertIn("path: _archive/bundle-a/hidden", out)
        self.assertNotIn("path: _archive/bundle-b/other", out)  # type Concept

    def test_list_parser_has_include_archive_flag(self):
        parsers = okf_parser_support.subcommand_parsers(okf_parser.build_parser())
        dests = {a.dest for a in okf_parser_support.parser_actions(parsers["list"])}
        self.assertIn("include_archive", dests)


class ArchiveHitPathResolvesViaRead(unittest.TestCase):
    """SC-02 (R-12, okf-cli-iwx4) — end to end: the path an archive hit
    prints under --include-archive is not just A path, it is the path
    `okf-cli read` resolves to the same file. Exercised through both
    surfaces this bean touches, not a unit test on path arithmetic."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.body_marker = "zqxread body marker for SC-02."
        self._w("bundle-a/active.md", "Concept", "Active", "filler")
        self._w("_archive/bundle-a/hidden.md", "Concept", "Hidden",
                self.body_marker)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _w(self, rel, typ, title, body):
        ap = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write("---\ntype: {}\ntitle: {}\ndescription: d\ntags: []\n"
                    "---\n# {}\n\n{}\n".format(typ, title, title, body))

    def _read_path(self, path):
        import io, contextlib, types
        args = types.SimpleNamespace(path=path, section=None, frontmatter_only=False,
                                     body_only=False)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf_navigation.cmd_read(self.tmp, args)
        return buf.getvalue()

    def test_list_archive_hit_path_resolves_via_read(self):
        import io, contextlib, types
        args = types.SimpleNamespace(type="Concept", tag=None, scope=None,
                                     json=False, include_archive=True)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf_navigation.cmd_list(self.tmp, args)
        lines = buf.getvalue().splitlines()
        path_line = next(l for l in lines if l == "path: _archive/bundle-a/hidden")
        path = path_line[len("path: "):]
        self.assertIn(self.body_marker, self._read_path(path))

    def test_substring_find_archive_hit_path_resolves_via_read(self):
        marker = "zqxfindread"
        self._w("_archive/bundle-a/needle.md", "Concept", "Needle",
                "{} {}".format(marker, self.body_marker))
        out = run_find(self.tmp, marker, include_archive=True)
        lines = out.splitlines()
        path_line = next(l for l in lines if l.startswith("path: "))
        path = path_line[len("path: "):]
        self.assertEqual(path, "_archive/bundle-a/needle")
        self.assertIn(self.body_marker, self._read_path(path))


class StagingExcludedFromIndexListFind(unittest.TestCase):
    """OKFT-oe8t AC 1+2: a bundle's `_intake` staging content was reachable
    via index/list/find before this fix (iter_concepts did not prune "_"),
    and is not after — while a bundle with only ordinary subdirs stays
    fully enumerated (AC 4)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._w("b/_intake/konzept.md",
                "---\ntype: Concept\ntitle: Konzept\ndescription: d\n"
                "tags: [staged]\n---\nzqxstagingmarker body.\n")
        self._w("b/sub/regular.md",
                "---\ntype: Concept\ntitle: Regular\ndescription: d\n"
                "tags: [kept]\n---\nzqxregularmarker body.\n")
        self._w("b/index.md", "# B\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _w(self, rel, text):
        ap = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(text)

    def test_index_json_excludes_staging_keeps_regular(self):
        import io
        import contextlib
        import json
        import types
        args = types.SimpleNamespace(bundle="b", json=True, full=True)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf_index.cmd_index(self.tmp, args)
        ids = [c["id"] for c in json.loads(buf.getvalue())["concepts"]]
        self.assertNotIn("_intake/konzept", ids)
        self.assertIn("sub/regular", ids)

    def test_list_excludes_staging_keeps_regular(self):
        import io
        import contextlib
        import types
        args = types.SimpleNamespace(type="Concept", tag=None, scope=None, json=False)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf_navigation.cmd_list(self.tmp, args)
        out = buf.getvalue()
        self.assertNotIn("_intake", out)
        self.assertIn("sub/regular", out)

    def test_find_degraded_excludes_staging(self):
        out = run_find(self.tmp, "zqxstagingmarker")
        self.assertNotIn("_intake", out)


class BundleArgumentIsValidated(unittest.TestCase):
    """A bundle argument naming a directory that does not exist must refuse,
    the same way `check` already does (cmd_check's own comment: "without this
    a typo'd or renamed bundle scanned nothing and exited 0 — a clean bill of
    health for a directory that does not exist").

    `index` and `visualize` were the two commands that took a bundle without
    checking it. `index` printed an empty listing under a `# <typo>` heading
    and exited 0; `visualize` went further and CREATED <root>/<typo>/assets/
    to write a 0-node graph into — a typo mutating the catalogue."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        ap = os.path.join(self.tmp, "real", "one.md")
        os.makedirs(os.path.dirname(ap))
        with open(ap, "w", encoding="utf-8") as f:
            f.write("---\ntype: Runbook\ntitle: One\n---\n# One\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _call(self, fn, args):
        """Run a command, returning (error_or_None, stdout)."""
        import io, contextlib
        out = io.StringIO()
        error = None
        with contextlib.redirect_stdout(out):
            try:
                fn(self.tmp, args)
            except OkfError as caught:
                error = caught
        return error, out.getvalue()

    def _index_args(self, bundle, json_flag=False):
        import types
        return types.SimpleNamespace(bundle=bundle, full=False, json=json_flag)

    def test_index_refuses_a_bundle_that_does_not_exist(self):
        error, out = self._call(okf_index.cmd_index, self._index_args("nope"))
        self.assertEqual(error.kind, "not_found")
        self.assertIn("nope", error.message)
        self.assertNotIn("# nope", out)

    def test_index_json_refuses_too(self):
        """The --json branch returns before the text branch, so it needs the
        same gate — otherwise a consumer gets `{"bundle": "nope", ...}` and a
        zero exit for a bundle that is not there."""
        error, out = self._call(okf_index.cmd_index,
                                self._index_args("nope", json_flag=True))
        self.assertEqual(error.kind, "not_found")
        self.assertEqual(out, "")

    def test_index_still_prints_an_existing_bundle(self):
        error, out = self._call(okf_index.cmd_index, self._index_args("real"))
        self.assertIsNone(error)
        self.assertIn("One", out)

    def test_visualize_refuses_a_bundle_that_does_not_exist(self):
        import types
        error, _out = self._call(
            okf_navigation.cmd_visualize, types.SimpleNamespace(bundle="nope", out=None))
        self.assertEqual(error.kind, "not_found")
        self.assertIn("nope", error.message)

    def test_visualize_creates_nothing_for_a_bundle_that_does_not_exist(self):
        """The actual damage: os.makedirs() on a path derived from an
        unvalidated argument. A typo left a directory behind in the
        catalogue."""
        import types
        self._call(okf_navigation.cmd_visualize,
                   types.SimpleNamespace(bundle="nope", out=None))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "nope")))

    def test_visualize_still_writes_for_an_existing_bundle(self):
        import types
        error, out = self._call(
            okf_navigation.cmd_visualize, types.SimpleNamespace(bundle="real", out=None))
        self.assertIsNone(error)
        self.assertTrue(os.path.isfile(
            os.path.join(self.tmp, "real", "assets", "viz.html")))
        self.assertIn("1 nodes", out)

    def test_the_gate_is_existence_not_bundle_eligibility(self):
        """The guard must ask "is this a directory", NOT "is this a bundle".
        `is_bundle_dir()` rejects a `_` prefix, so gating on it would refuse
        `index _archive` — a directory that is on disk and printable. Tightening
        the guard to list_bundles()/is_bundle_dir() turns this test red."""
        ap = os.path.join(self.tmp, "_archive", "old.md")
        os.makedirs(os.path.dirname(ap))
        with open(ap, "w", encoding="utf-8") as f:
            f.write("---\ntype: Runbook\ntitle: Old\n---\n# Old\n")
        error, out = self._call(okf_index.cmd_index, self._index_args("_archive"))
        self.assertIsNone(error)
        self.assertIn("Old", out)


class TocUsesTheSharedHeadingFunction(unittest.TestCase):
    """OKFT-ir4m — `toc` lists the headings the one heading function yields:
    plain three-backtick fences behave as before, tilde fences and longer
    fences now hide their headings too."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        os.makedirs(os.path.join(self.root, "b"))
        with open(os.path.join(self.root, ".okf.toml"), "w"):
            pass

    def _toc(self, body, *flags):
        with open(os.path.join(self.root, "b", "c.md"), "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: C\n---\n" + body)
        r = _cli(self.root, "toc", "b/c", *flags)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        return r.stdout

    def test_plain_backtick_fence_output_unchanged(self):
        self.assertEqual(self._toc("# One\n```\n## no\n```\n## Two\n", "--level", "0"),
                         "# C  [Concept]\n- One\n  - Two\n")

    def test_tilde_fence_headings_not_listed(self):
        self.assertEqual(self._toc("# One\n~~~\n## no\n~~~\n## Two\n"),
                         "# C  [Concept]\n- Two\n")

    def test_four_backtick_fence_with_inner_three_backticks_not_listed(self):
        self.assertEqual(self._toc("````\n```\n## no\n```\n````\n## Two\n"),
                         "# C  [Concept]\n- Two\n")


class ReadTargeted(unittest.TestCase):
    """OKFT-5pyb — `read --section / --frontmatter-only / --body-only`, over the
    real CLI process on a throwaway catalogue."""

    CONCEPT = "\n".join([
        "---",                    # 1
        "type: Concept",          # 2
        "title: C",               # 3
        "# yaml heading",         # 4
        "---",                    # 5
        "# Top",                  # 6
        "intro",                  # 7
        "## Alpha",               # 8
        "alpha text",             # 9
        "### Deep",               # 10
        "deep text",              # 11
        "## Beta",                # 12
        "beta text",              # 13
        "### Dup",                # 14
        "first dup text",         # 15
        "## Gamma",               # 16
        "### Dup",                # 17
        "second dup text",        # 18
        "## Fenced",              # 19
        "```",                    # 20
        "## Hidden",              # 21
        "```",                    # 22
        "after fence",            # 23
        "## Delta",               # 24
        "~~~",                    # 25
        "## Tilde",               # 26
        "~~~",                    # 27
        "end",                    # 28
    ]) + "\n"
    BARE = "# Bare\ntext\n## Sub\nmore\n"

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        os.makedirs(os.path.join(self.root, "b"))
        self._w(".okf.toml", "")
        self._w("b/c.md", self.CONCEPT)
        self._w("b/bare.md", self.BARE)
        self._w("b/index.md", "---\ntype: Index\n---\n# B\n## Contents\nlist\n## Other\nx\n")

    def _w(self, rel, text):
        with open(os.path.join(self.root, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def _read(self, path, *flags):
        return _cli(self.root, "read", path, *flags)

    def test_unique_section_runs_to_next_heading_of_equal_or_higher_level(self):
        r = self._read("b/c", "--section", "Alpha")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, '## Alpha\nalpha text\n### Deep\ndeep text\n', ""))

    def test_section_of_the_last_top_heading_runs_to_end_of_body(self):
        r = self._read("b/c", "--section", "Top")
        self.assertEqual((r.returncode, r.stdout), (0, '# Top\nintro\n## Alpha\nalpha text\n### Deep\ndeep text\n## Beta\nbeta text\n### Dup\nfirst dup text\n## Gamma\n### Dup\nsecond dup text\n## Fenced\n```\n## Hidden\n```\nafter fence\n## Delta\n~~~\n## Tilde\n~~~\nend\n'))

    def test_section_includes_subsections_and_stops_at_a_higher_level_heading(self):
        r = self._read("b/c", "--section", "Beta")
        self.assertEqual((r.returncode, r.stdout), (0, '## Beta\nbeta text\n### Dup\nfirst dup text\n'))

    def test_match_is_case_insensitive_exact(self):
        r = self._read("b/c", "--section", "dEEp")
        self.assertEqual((r.returncode, r.stdout), (0, '### Deep\ndeep text\n'))
        r = self._read("b/c", "--section", "Dee")
        self.assertEqual((r.returncode, r.stdout), (3, ""))

    def test_path_resolves_a_duplicate_heading(self):
        r = self._read("b/c", "--section", "Beta > Dup")
        self.assertEqual((r.returncode, r.stdout), (0, '### Dup\nfirst dup text\n'))
        r = self._read("b/c", "--section", "Gamma>Dup")
        self.assertEqual((r.returncode, r.stdout), (0, '### Dup\nsecond dup text\n'))

    def test_path_with_three_segments_follows_the_nesting(self):
        r = self._read("b/c", "--section", "top > alpha > deep")
        self.assertEqual((r.returncode, r.stdout), (0, '### Deep\ndeep text\n'))

    def test_later_segment_matches_only_inside_the_previous_section(self):
        r = self._read("b/c", "--section", "Alpha > Dup")
        self.assertEqual((r.returncode, r.stdout), (3, ""))

    def test_ambiguous_section_exits_2_and_lists_candidates_with_file_lines(self):
        r = self._read("b/c", "--section", "Dup")
        self.assertEqual((r.returncode, r.stdout), (2, ""))
        self.assertIn("line 14: Top > Beta > Dup", r.stderr)
        self.assertIn("line 17: Top > Gamma > Dup", r.stderr)

    def test_unknown_section_exits_3_with_empty_stdout(self):
        r = self._read("b/c", "--section", "Nope")
        self.assertEqual((r.returncode, r.stdout), (3, ""))
        self.assertNotEqual(r.stderr, "")

    def test_fenced_heading_is_not_selectable(self):
        for text in ("Hidden", "Tilde"):
            r = self._read("b/c", "--section", text)
            self.assertEqual((r.returncode, r.stdout), (3, ""), text)

    def test_fenced_heading_does_not_end_the_enclosing_section(self):
        r = self._read("b/c", "--section", "Fenced")
        self.assertEqual((r.returncode, r.stdout), (0, '## Fenced\n```\n## Hidden\n```\nafter fence\n'))

    def test_frontmatter_comment_is_not_selectable(self):
        r = self._read("b/c", "--section", "yaml heading")
        self.assertEqual((r.returncode, r.stdout), (3, ""))

    def test_every_unique_toc_heading_is_selectable(self):
        toc = _cli(self.root, "toc", "b/c", "--level", "0").stdout.splitlines()[1:]
        texts = [l.lstrip(" ")[2:] for l in toc]
        unique = [t for t in texts if texts.count(t) == 1]
        self.assertEqual(len(unique), len(texts) - 2)    # "Dup" twice is the only repeat
        for text in unique:
            r = self._read("b/c", "--section", text)
            self.assertEqual(r.returncode, 0, (text, r.stderr))
            first = r.stdout.splitlines()[0]
            self.assertTrue(first.startswith("#") and first.endswith(" " + text), (text, first))

    def test_directory_reference_resolves_to_index_in_every_mode(self):
        r = self._read("b", "--section", "Contents")
        self.assertEqual((r.returncode, r.stdout), (0, "## Contents\nlist\n"))
        r = self._read("b", "--frontmatter-only")
        self.assertEqual((r.returncode, r.stdout), (0, "---\ntype: Index\n---\n"))
        r = self._read("b", "--body-only")
        self.assertEqual((r.returncode, r.stdout), (0, "# B\n## Contents\nlist\n## Other\nx\n\n"))

    def test_frontmatter_only_prints_the_block_with_delimiters(self):
        r = self._read("b/c", "--frontmatter-only")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, '---\ntype: Concept\ntitle: C\n# yaml heading\n---\n', ""))

    def test_frontmatter_only_prints_nothing_without_frontmatter(self):
        r = self._read("b/bare", "--frontmatter-only")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_body_only_prints_everything_after_the_frontmatter(self):
        r = self._read("b/c", "--body-only")
        self.assertEqual((r.returncode, r.stdout), (0, '# Top\nintro\n## Alpha\nalpha text\n### Deep\ndeep text\n## Beta\nbeta text\n### Dup\nfirst dup text\n## Gamma\n### Dup\nsecond dup text\n## Fenced\n```\n## Hidden\n```\nafter fence\n## Delta\n~~~\n## Tilde\n~~~\nend\n\n'))

    def test_body_only_prints_the_whole_file_without_frontmatter(self):
        r = self._read("b/bare", "--body-only")
        self.assertEqual((r.returncode, r.stdout), (0, self.BARE + "\n"))

    def test_unterminated_frontmatter_counts_as_none(self):
        self._w("b/open.md", "---\ntype: X\n# not closed\n")
        self.assertEqual(self._read("b/open", "--frontmatter-only").stdout, "")
        self.assertEqual(self._read("b/open", "--body-only").stdout,
                         "---\ntype: X\n# not closed\n\n")

    def test_frontmatter_only_then_body_only_reproduces_plain_read(self):
        for path in ("b/c", "b/bare"):
            plain = self._read(path).stdout
            joined = self._read(path, "--frontmatter-only").stdout + self._read(path, "--body-only").stdout
            self.assertEqual(joined, plain, path)

    def test_plain_read_is_the_file_plus_one_newline(self):
        for path, text in (("b/c", self.CONCEPT), ("b/bare", self.BARE)):
            r = self._read(path)
            self.assertEqual((r.returncode, r.stdout), (0, text + "\n"), path)

    def test_any_two_selection_options_are_a_usage_error(self):
        for flags in (("--section", "Alpha", "--frontmatter-only"),
                      ("--section", "Alpha", "--body-only"),
                      ("--frontmatter-only", "--body-only")):
            with self.subTest(flags=flags):
                r = self._read("b/c", *flags)
                self.assertEqual((r.returncode, r.stdout), (2, ""))
                self.assertIn("not allowed with", r.stderr)


if __name__ == "__main__":
    unittest.main()
