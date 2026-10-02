#!/usr/bin/env python3
"""Tests for the ctx storage model in okf-cli.py (OKFT-t0lj).

Run: python3 -m unittest test_okf_ctx -v
"""
import contextlib
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("okf_cli", os.path.join(_HERE, "okf-cli.py"))
okf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(okf)


class CtxCatalogue(unittest.TestCase):
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
                              + okf.MARK_START + "\n" + okf.MARK_END + "\n")
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


class CtxBundleGate(CtxCatalogue):
    def test_ctx_dir_is_bundle_other_underscore_and_dot_are_not(self):
        self.assertTrue(okf.is_bundle_dir("_ctx"))
        self.assertFalse(okf.is_bundle_dir("_archive"))
        self.assertFalse(okf.is_bundle_dir("_other"))
        self.assertFalse(okf.is_bundle_dir(".fts"))
        self.assertTrue(okf.is_bundle_dir("b"))

    def test_list_bundles_includes_ctx_once_it_exists(self):
        self.assertNotIn("_ctx", okf.list_bundles(self.root))
        okf.save_ctx(self.root, {"slug": "a", "description": "d", "entries": []})
        self.assertIn("_ctx", okf.list_bundles(self.root))


class CtxSlugs(CtxCatalogue):
    def test_paths(self):
        self.assertEqual(okf.ctx_dir(self.root), os.path.join(self.root, "_ctx"))
        self.assertEqual(okf.ctx_file(self.root, "x"), os.path.join(self.root, "_ctx", "x.md"))

    def test_slugs_missing_dir_is_empty(self):
        self.assertEqual(okf.ctx_slugs(self.root), [])

    def test_slugs_sorted_and_reserved_filenames_excluded(self):
        for n in ("zeta.md", "alpha.md", "index.md", "README.md", "log.md", "notes.txt"):
            self._w("_ctx/" + n, "x")
        self.assertEqual(okf.ctx_slugs(self.root), ["alpha", "zeta"])

    def test_slug_problem(self):
        self.assertIsNone(okf.ctx_slug_problem("a-b1"))
        self.assertIsNone(okf.ctx_slug_problem("1a"))
        msg = "use lowercase letters, digits and hyphens"
        for bad in ("A", "-a", "a_b", "a b", ""):
            self.assertEqual(okf.ctx_slug_problem(bad), msg, bad)
        for res in ("add", "index", "index-map", "readme", "log", "toc"):
            self.assertEqual(okf.ctx_slug_problem(res), '"%s" is a reserved name' % res)


class CtxParseRender(CtxCatalogue):
    def test_render_exact(self):
        out = okf.render_ctx("my-ctx", 'say "hi"', [
            E(1, "pflicht", "b/one.md", "a|b\nc"),
            E(None, "nachschlag", "~/notes/out.md", "x"),
            E(None, "nachschlag", "/abs/p.md", ""),
        ])
        self.assertEqual(out, (
            '---\ntype: Context\ndescription: "say \\"hi\\""\n---\n\n# my-ctx\n\n'
            "| pos | mode | path | comment |\n|---|---|---|---|\n"
            "| 1 | pflicht | [one](/b/one.md) | a\\|b c |\n"
            "| - | nachschlag | `~/notes/out.md` | x |\n"
            "| - | nachschlag | `/abs/p.md` |  |\n"))

    def test_roundtrip(self):
        entries = [E(1, "pflicht", "b/one.md", "a|b c"),
                   E(None, "nachschlag", "~/notes/out.md", "x")]
        desc, got, problems = okf.parse_ctx(okf.render_ctx("s", 'q"q', entries))
        self.assertEqual((desc, got, problems), ('q"q', entries, []))

    def test_parse_problems(self):
        base = "---\ntype: Context\ndescription: d\n---\n\n# s\n\n"
        _, e, p = okf.parse_ctx(base + "no table\n")
        self.assertEqual((e, p), ([], ['no table with header "pos | mode | path | comment"']))
        hdr = "| Pos | Mode | Path | Comment |\n|---|---|---|---|\n"
        _, e, p = okf.parse_ctx(base + hdr + "| 1 | pflicht | [a](/a.md) |\n")
        self.assertEqual((e, p), ([], ["row 1: expected 4 cells, found 3"]))
        _, e, p = okf.parse_ctx(base + hdr + "| 1 | pflicht | [a](/a.md) | c |\n| x | pflicht | [a](/a.md) | c |\n")
        self.assertEqual(p, ['row 2: pos "x" is neither an integer nor -'])
        self.assertEqual(len(e), 1)
        _, e, p = okf.parse_ctx(base + hdr + "| 1 | pflicht | plain | c |\n")
        self.assertEqual(p, ["row 1: path cell is neither a catalogue link nor a code span"])

    def test_parse_rows_end_at_first_non_table_line_and_mode_lowercased(self):
        text = ("---\ntype: Context\ndescription: d\n---\n\n# s\n\n"
                "| pos | mode | path | comment |\n|---|---|---|---|\n"
                "| 1 | PFLICHT | [a](/b/one.md) | c |\n\ntrailing | not | a | row |\n")
        _, e, p = okf.parse_ctx(text)
        self.assertEqual(e, [E(1, "pflicht", "b/one.md", "c")])
        self.assertEqual(p, [])

    def test_parse_ignores_link_text(self):
        text = ("---\ntype: Context\ndescription: d\n---\n\n"
                "| pos | mode | path | comment |\n|---|---|---|---|\n"
                "| 1 | pflicht | [whatever](/b/one.md) |  |\n")
        self.assertEqual(okf.parse_ctx(text)[1][0]["path"], "b/one.md")


class CtxLoadSave(CtxCatalogue):
    def test_save_renumbers_stable_partition_and_roundtrips(self):
        ctx = {"slug": "s", "description": "d", "entries": [
            E(None, "nachschlag", "b/two.md", "n1"),
            E(7, "pflicht", "b/one.md", "p1"),
            E(None, "bogus", "ext/three.md", "n2"),
            E(3, "pflicht", "~/notes/out.md", "p2")]}
        okf.save_ctx(self.root, ctx)
        got = okf.load_ctx(self.root, "s")
        self.assertEqual(got["slug"], "s")
        self.assertEqual(got["description"], "d")
        self.assertEqual(got["problems"], [])
        self.assertEqual(got["entries"], [
            E(1, "pflicht", "b/one.md", "p1"), E(2, "pflicht", "~/notes/out.md", "p2"),
            E(None, "nachschlag", "b/two.md", "n1"), E(None, "bogus", "ext/three.md", "n2")])

    def test_save_ignores_problems_key(self):
        ctx = {"slug": "s", "description": "d", "entries": [E(1, "pflicht", "b/one.md")],
               "problems": ["row 9: junk"]}
        okf.save_ctx(self.root, ctx)
        self.assertNotIn("junk", okf.read_file(okf.ctx_file(self.root, "s")))

    def test_save_creates_index_skeleton_and_refreshes_index(self):
        okf.save_ctx(self.root, {"slug": "s", "description": "my desc", "entries": []})
        idx = okf.read_file(os.path.join(self.root, "_ctx", "index.md"))
        self.assertTrue(idx.startswith(
            "# Context bundles\n\nCurated, ordered reading lists per topic — one file per ctx slug, "
            "managed by `okf ctx`.\n\n## Contents\n\n" + okf.MARK_START + "\n"))
        self.assertIn("my desc", idx)
        self.assertIn("(/_ctx/s.md)", idx)

    def test_save_keeps_existing_index_text(self):
        self._w("_ctx/index.md", "# Mine\n\nHand written.\n\n" + okf.MARK_START + "\n" + okf.MARK_END + "\n")
        okf.save_ctx(self.root, {"slug": "s", "description": "d", "entries": []})
        idx = okf.read_file(os.path.join(self.root, "_ctx", "index.md"))
        self.assertTrue(idx.startswith("# Mine\n\nHand written.\n"))
        self.assertIn("(/_ctx/s.md)", idx)

    def test_load_missing_slug_exits_2_with_message(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            okf.load_ctx(self.root, "nope")
        self.assertEqual(cm.exception.code, 2)
        self.assertEqual(err.getvalue(), "ctx: unknown slug: nope\n")

    def test_load_reports_parse_problems(self):
        self._w("_ctx/s.md", "---\ntype: Context\ndescription: d\n---\n\n# s\n")
        self.assertEqual(okf.load_ctx(self.root, "s")["problems"],
                         ['no table with header "pos | mode | path | comment"'])

    def test_sc02_list_type_context_shows_saved_ctx(self):
        okf.save_ctx(self.root, {"slug": "s", "description": "d", "entries": []})
        r = self._cli("list", "--type", "Context")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("_ctx/s", r.stdout)


class CtxNormalize(CtxCatalogue):
    def n(self, raw, must_exist=True):
        with self._home():
            return okf.ctx_normalize_path(self.root, raw, must_exist)

    def test_catalogue_forms(self):
        for raw in ("b/one.md", "b/one", "/b/one.md", "/b/one", "  b/../b/one  ", "./b/one"):
            self.assertEqual(self.n(raw), "b/one.md", raw)

    def test_leading_slash_falls_back_to_filesystem(self):
        p = os.path.join(self.home, "notes", "out.md")
        self.assertEqual(self.n(p), "~/notes/out.md")

    def test_absolute_inside_root_becomes_relative(self):
        self.assertEqual(self.n(os.path.join(self.root, "b", "one.md")), "b/one.md")

    def test_symlinked_bundle_realpath_maps_back(self):
        self.assertEqual(self.n(os.path.join(self.ext, "three.md")), "ext/three.md")
        self.assertEqual(self.n("ext/three.md"), "ext/three.md")

    def test_home_forms(self):
        self.assertEqual(self.n("~/notes/out.md"), "~/notes/out.md")

    def test_outside_home_stays_absolute(self):
        other = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, other, True)
        p = os.path.join(other, "x.md")
        open(p, "w").close()
        self.assertEqual(self.n(p), os.path.abspath(p))

    def test_relative_existing_cwd_file_is_filesystem_path(self):
        cwd = os.getcwd()
        os.chdir(os.path.join(self.home, "notes"))
        self.addCleanup(os.chdir, cwd)
        self.assertEqual(self.n("out.md"), "~/notes/out.md")

    def test_dotdot_escape_is_filesystem(self):
        rel = os.path.relpath(os.path.join(self.ext, "three.md"), self.root)
        self.assertTrue(rel.startswith(".."))
        self.assertEqual(self.n(rel), "ext/three.md")

    def test_missing_file_none_unless_must_exist_false(self):
        self.assertIsNone(self.n("b/nope.md"))
        self.assertIsNone(self.n("~/nope.md"))
        self.assertEqual(self.n("b/nope.md", must_exist=False), "b/nope.md")
        self.assertEqual(self.n("~/nope.md", must_exist=False), "~/nope.md")


class CtxEntryAbspathMemberships(CtxCatalogue):
    def test_entry_abspath(self):
        with self._home():
            self.assertEqual(okf.ctx_entry_abspath(self.root, "~/notes/out.md"),
                             os.path.join(self.home, "notes", "out.md"))
        self.assertEqual(okf.ctx_entry_abspath(self.root, "/abs/p.md"), "/abs/p.md")
        self.assertEqual(okf.ctx_entry_abspath(self.root, "b/one.md"),
                         os.path.join(self.root, "b", "one.md"))

    def test_memberships(self):
        okf.save_ctx(self.root, {"slug": "a", "description": "d", "entries": [E(1, "pflicht", "b/one.md", "ca")]})
        okf.save_ctx(self.root, {"slug": "b-ctx", "description": "d", "entries": [
            E(None, "nachschlag", "b/one.md", "cb"), E(None, "nachschlag", "b/two.md", "x")]})
        with self._home():
            got = okf.ctx_memberships(self.root, "/b/one")
            self.assertEqual(got, [("a", E(1, "pflicht", "b/one.md", "ca")),
                                   ("b-ctx", E(None, "nachschlag", "b/one.md", "cb"))])
            self.assertEqual(okf.ctx_memberships(self.root, "b/gone.md"), [])


class CtxSaveEffects(CtxCatalogue):
    def _save_full(self):
        okf.save_ctx(self.root, {"slug": "s", "description": "d", "entries": [
            E(1, "pflicht", "b/one.md", "c1"), E(2, "pflicht", "ext/three.md", "c2"),
            E(None, "nachschlag", "~/notes/out.md", "c3")]})

    def test_saved_file_has_link_and_code_span_forms(self):
        self._save_full()
        text = okf.read_file(okf.ctx_file(self.root, "s"))
        self.assertIn("| 1 | pflicht | [one](/b/one.md) | c1 |", text)
        self.assertIn("| 2 | pflicht | [three](/ext/three.md) | c2 |", text)
        self.assertIn("| - | nachschlag | `~/notes/out.md` | c3 |", text)

    def test_check_reports_nothing_for_ctx(self):
        self._save_full()
        errors, warnings = okf.run_checks(self.root, None)
        names = ("entry-file-description", "asset-placement", "type-registered")
        bad = [x for x in errors + warnings if x[0] in names and "_ctx" in repr(x)]
        self.assertEqual(bad, [])

    def test_save_leaves_members_byte_identical(self):
        paths = [os.path.join(self.root, "b", "one.md"), os.path.join(self.ext, "three.md"),
                 os.path.join(self.home, "notes", "out.md")]
        before = [okf.read_file(p) for p in paths]
        self._save_full()
        self.assertEqual([okf.read_file(p) for p in paths], before)


if __name__ == "__main__":
    unittest.main()
