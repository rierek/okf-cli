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


class CtxRenameArchive(CtxCatalogue):
    def _demo(self, text=None):
        if text is None:
            okf.save_ctx(self.root, {"slug": "demo", "description": "d", "entries": [
                E(1, "pflicht", "b/two.md", "c")]})
        else:
            self._w("_ctx/demo.md", text)

    def _read(self, rel):
        with open(os.path.join(self.root, rel), encoding="utf-8") as f:
            return f.read()

    def test_preview_prints_ctx_line_with_position_and_changes_nothing(self):
        self._demo()
        before = self._read("_ctx/demo.md")
        r = self._cli("rename", "b/two.md", "b/zwei.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("  ctx        demo (pos 1)\n", r.stdout)
        self.assertEqual(self._read("_ctx/demo.md"), before)

    def test_rename_apply_refreshes_entry_and_lists_membership(self):
        self._demo()
        r = self._cli("rename", "b/two.md", "b/zwei.md", "--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[zwei](/b/zwei.md)", self._read("_ctx/demo.md"))
        self.assertNotIn("[two]", self._read("_ctx/demo.md"))
        with self._home():
            e = okf.load_ctx(self.root, "demo")["entries"][0]
        self.assertTrue(os.path.exists(okf.ctx_entry_abspath(self.root, e["path"])))
        self.assertIn("listed in 1 ctx bundle(s): demo (pos 1)\n", r.stdout)

    def test_archive_apply_points_entry_at_archive_path(self):
        self._demo()
        r = self._cli("archive", "b/two.md", "--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("(/_archive/b/two.md)", self._read("_ctx/demo.md"))
        self.assertIn("listed in 1 ctx bundle(s): demo (pos 1)\n", r.stdout)

    def test_reference_entry_reports_reference(self):
        okf.save_ctx(self.root, {"slug": "demo", "description": "d", "entries": [
            E(None, "nachschlag", "b/two.md", "c")]})
        r = self._cli("rename", "b/two.md", "b/zwei.md")
        self.assertIn("  ctx        demo (reference)\n", r.stdout)

    def test_no_membership_prints_no_ctx_line(self):
        r = self._cli("rename", "b/two.md", "b/zwei.md", "--apply")
        self.assertNotIn("  ctx        ", r.stdout)
        self.assertNotIn("listed in", r.stdout)

    def test_parse_problems_skip_save_and_warn(self):
        text = ("---\ntype: Context\ndescription: \"d\"\n---\n\n# demo\n\n"
                "| pos | mode | path | comment |\n|---|---|---|---|\n"
                "| 1 | pflicht | [two](/b/two.md) | c |\n"
                "| 2 | pflicht | broken row |\n")
        self._demo(text)
        r = self._cli("rename", "b/two.md", "b/zwei.md", "--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._read("_ctx/demo.md"), text.replace(
            "(/b/two.md)", "(/b/zwei.md)"))
        lines = r.stdout.splitlines()
        i = lines.index("listed in 1 ctx bundle(s): demo (pos 1)")
        self.assertEqual(lines[i + 1], "  ctx        demo: not refreshed, 1 parse "
                         "problem(s) — run okf ctx check")


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


class CtxShorthand(unittest.TestCase):
    def test_rewrites(self):
        S = okf._ctx_shorthand
        self.assertEqual(S(["ctx"]), ["ctx", "list"])
        self.assertEqual(S(["--root", "r", "ctx"]), ["--root", "r", "ctx", "list"])
        self.assertEqual(S(["--root=r", "ctx", "--list"]), ["--root=r", "ctx", "list"])
        self.assertEqual(S(["ctx", "demo"]), ["ctx", "show", "demo"])
        self.assertEqual(S(["ctx", "create", "x"]), ["ctx", "create", "x"])
        self.assertEqual(S(["ctx", "--help"]), ["ctx", "--help"])

    def test_other_commands_untouched(self):
        for argv in (["list", "ctx"], ["find", "ctx", "x"], ["--root", "ctx", "read", "a"],
                     ["read", "b/ctx"], []):
            self.assertEqual(okf._ctx_shorthand(argv), argv)


class CtxListCreate(CtxCatalogue):
    def _create(self, *argv):
        return self._cli("ctx", "create", *argv)

    def test_create_orders_and_list_counts(self):
        r = self._create("demo", "b/two", "b/one")
        self.assertEqual((r.returncode, r.stdout), (0, "created _ctx/demo.md (2 entries)\n"))
        c = okf.load_ctx(self.root, "demo")
        self.assertEqual([(e["pos"], e["mode"], e["path"]) for e in c["entries"]],
                         [(1, "pflicht", "b/one.md"), (2, "pflicht", "b/two.md")])
        r = self._cli("ctx", "list")
        self.assertEqual(r.returncode, 0)
        self.assertIn("demo", r.stdout)
        self.assertIn("(2 entries, 2 required)", r.stdout)

    def test_bare_ctx_and_flag_equal_list(self):
        self._create("demo", "b/one", "--description", "Demo ctx")
        want = self._cli("ctx", "list")
        self.assertIn("Demo ctx", want.stdout)
        for argv in (("ctx",), ("ctx", "--list")):
            got = self._cli(*argv)
            self.assertEqual((got.returncode, got.stdout), (want.returncode, want.stdout))

    def test_list_empty_text_and_json(self):
        r = self._cli("ctx", "list")
        self.assertEqual((r.returncode, r.stdout),
                         (0, "no ctx bundles under %s\n" % os.path.join(self.root, "_ctx")))
        r = self._cli("ctx", "list", "--json")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "[]"))

    def test_list_slug_order_alignment_and_json_keys(self):
        self._create("zz", "b/one")
        self._create("a", "b/one", "b/two")
        lines = self._cli("ctx", "list").stdout.splitlines()
        self.assertEqual([l.split()[0] for l in lines], ["a", "zz"])
        self.assertEqual(lines[0].index("("), lines[1].index("("))  # w = longest slug... padded
        import json
        data = json.loads(self._cli("ctx", "list", "--json").stdout)
        self.assertEqual(data[0], {"slug": "a", "description": "", "entries": 2,
                                   "required": 2, "path": "_ctx/a.md"})

    def test_list_for_filters_even_for_missing_file(self):
        self._create("one", "b/one")
        self._create("both", "b/one", "b/two")
        r = self._cli("ctx", "list", "--for", "b/two.md", "--json")
        self.assertEqual([d["slug"] for d in __import__("json").loads(r.stdout)], ["both"])
        os.remove(os.path.join(self.root, "b", "two.md"))
        r = self._cli("ctx", "list", "--for", "b/two.md", "--json")
        self.assertEqual([d["slug"] for d in __import__("json").loads(r.stdout)], ["both"])
        r = self._cli("ctx", "list", "--for", "b/nope.md")
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        r = self._cli("ctx", "list", "--for", "b/nope.md", "--json")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "[]"))

    def test_list_fields_each_observed_text_and_json(self):
        okf.save_ctx(self.root, {"slug": "alpha", "description": "Alpha desc", "entries": [
            E(1, "pflicht", "b/one.md"), E(2, "pflicht", "b/two.md"),
            E(None, "nachschlag", "ext/three.md")]})
        okf.save_ctx(self.root, {"slug": "be", "description": "Be desc", "entries": [
            E(1, "pflicht", "b/one.md")]})
        data = __import__("json").loads(self._cli("ctx", "list", "--json").stdout)
        self.assertEqual(data, [
            {"slug": "alpha", "description": "Alpha desc", "entries": 3, "required": 2,
             "path": "_ctx/alpha.md"},
            {"slug": "be", "description": "Be desc", "entries": 1, "required": 1,
             "path": "_ctx/be.md"}])
        self.assertEqual(self._cli("ctx", "list").stdout,
                         "  alpha  Alpha desc  (3 entries, 2 required)\n"
                         "  be     Be desc  (1 entries, 1 required)\n")

    def test_create_import_comments_skips_and_dedup(self):
        imp = os.path.join(self.home, "in.txt")
        with open(imp, "w", encoding="utf-8") as f:
            f.write("# head\n\nb/two\tsecond one\nb/one.md\tdup\n  \nb/one\n")
        r = subprocess.run(
            [sys.executable, os.path.join(_HERE, "okf-cli.py"), "--root", self.root,
             "ctx", "create", "imp", "b/one", "--import", "in.txt"],
            capture_output=True, text=True, cwd=self.home, env={**os.environ, "HOME": self.home})
        self.assertEqual((r.returncode, r.stdout), (0, "created _ctx/imp.md (2 entries)\n"))
        es = okf.load_ctx(self.root, "imp")["entries"]
        self.assertEqual([(e["path"], e["comment"]) for e in es],
                         [("b/one.md", ""), ("b/two.md", "second one")])

    def test_create_errors_write_nothing(self):
        self._create("old", "b/one")
        cases = [
            (("Bad", "b/one"), 'ctx: invalid slug "Bad": use lowercase letters, digits and hyphens'),
            (("show", "b/one"), 'ctx: invalid slug "show": "show" is a reserved name'),
            (("old", "b/two"), "ctx: old already exists"),
            (("new",), "ctx: create needs at least one path"),
            (("new", "b/one", "--import", "nofile.txt"), "ctx: import file not found: nofile.txt"),
        ]
        for argv, msg in cases:
            r = self._create(*argv)
            self.assertEqual((r.returncode, r.stdout), (2, ""), argv)
            self.assertEqual(r.stderr.strip(), msg, argv)
        self.assertEqual(okf.ctx_slugs(self.root), ["old"])
        self.assertEqual(len(okf.load_ctx(self.root, "old")["entries"]), 1)

    def test_create_missing_paths_each_reported(self):
        r = self._create("new", "b/one", "b/x", "b/y")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(r.stderr.splitlines(), ["ctx: not found: b/x", "ctx: not found: b/y"])
        self.assertEqual(okf.ctx_slugs(self.root), [])


class CtxShowRead(CtxCatalogue):
    def setUp(self):
        super().setUp()
        self.one = os.path.join(self.root, "b/one.md")
        self.three = os.path.join(self.root, "ext", "three.md")
        self.out = os.path.join(self.home, "notes", "out.md")
        okf.save_ctx(self.root, {"slug": "demo", "description": "Demo ctx", "entries": [
            {"mode": "pflicht", "path": "b/one.md", "comment": "start here"},
            {"mode": "pflicht", "path": "ext/three.md", "comment": ""},
            {"mode": "nachschlag", "path": "~/notes/out.md", "comment": "background"}]})

    def _kill_one(self):
        os.remove(self.one)

    def test_show_text_exact(self):
        r = self._cli("ctx", "show", "demo")
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        one_chars = len(okf.read_file(self.one))
        three_chars = len(okf.read_file(self.three))
        t1, t3 = (one_chars + 3) // 4, (three_chars + 3) // 4
        t_out = (len(okf.read_file(self.out)) + 3) // 4
        self.assertEqual(r.stdout, (
            "ctx demo — Demo ctx\n\n"
            "required — read in this order:\n"
            "  1. {one}  [Concept] One  ~{t1} tok\n"
            "     first\n"
            "     why: start here\n"
            "  2. {three}  [Concept] Three  ~{t3} tok\n"
            "reference — query when needed:\n"
            "  - {out}  out  ~{to} tok\n"
            "     why: background\n\n"
            "3 entries (2 required, 1 reference), ~{tt} tokens for the required set\n").format(one=self.one, three=self.three, out=self.out,
                                  t1=t1, t3=t3, to=t_out, tt=t1 + t3))

    def test_shorthand_equals_show(self):
        a, b = self._cli("ctx", "demo"), self._cli("ctx", "show", "demo")
        self.assertEqual((a.returncode, a.stdout, a.stderr), (b.returncode, b.stdout, b.stderr))
        self.assertIn("1. " + self.one, a.stdout)

    def test_show_unknown_slug(self):
        r = self._cli("ctx", "show", "nope")
        self.assertEqual((r.returncode, r.stdout), (2, ""))
        self.assertEqual(r.stderr.strip(), "ctx: unknown slug: nope")

    def test_show_dead_entry(self):
        self._kill_one()
        r = self._cli("ctx", "show", "demo")
        self.assertEqual(r.returncode, 1)
        self.assertIn("  1. [DEAD] {}\n     why: start here\n".format(self.one), r.stdout)
        self.assertTrue(r.stdout.endswith(
            "WARNING: 1 dead entry — this list is incomplete; fix with `ctx edit demo`\n"))

    def test_show_empty_reference_and_none(self):
        okf.save_ctx(self.root, {"slug": "refonly", "description": "", "entries": [
            {"mode": "nachschlag", "path": "b/two.md", "comment": ""}]})
        out = self._cli("ctx", "show", "refonly").stdout
        self.assertTrue(out.startswith("ctx refonly\n\nrequired — read in this order:\n  (none)\n"
                                       "reference — query when needed:\n"))
        okf.save_ctx(self.root, {"slug": "reqonly", "description": "", "entries": [
            {"mode": "pflicht", "path": "b/two.md", "comment": ""}]})
        self.assertNotIn("query when needed", self._cli("ctx", "show", "reqonly").stdout)

    def test_show_json_shape_and_values(self):
        import json
        r = self._cli("ctx", "show", "demo", "--json")
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        d = json.loads(r.stdout)
        self.assertEqual(list(d), ["slug", "description", "path", "entries", "dead", "tokens_required"])
        self.assertEqual((d["slug"], d["path"], d["dead"]), ("demo", "_ctx/demo.md", 0))
        e1, e2, e3 = d["entries"]
        self.assertEqual(list(e1), ["pos", "mode", "path", "abspath", "title", "type",
                                    "description", "comment", "alive", "chars", "tokens"])
        self.assertEqual((e1["pos"], e1["mode"], e1["title"], e1["type"], e1["alive"]),
                         (1, "pflicht", "One", "Concept", True))
        self.assertEqual((e3["pos"], e3["mode"], e3["type"], e3["title"]),
                         (None, "nachschlag", "", "out"))
        self.assertEqual(d["tokens_required"], e1["tokens"] + e2["tokens"])
        self.assertEqual(e1["chars"], len(okf.read_file(self.one)))

    def test_show_json_follows_title_change(self):
        import json
        self._w("b/one.md", "---\ntype: Concept\ntitle: Renamed\n---\n\nx\n")
        d = json.loads(self._cli("ctx", "show", "demo", "--json").stdout)
        self.assertEqual(d["entries"][0]["title"], "Renamed")

    def test_show_json_dead_stdout_only_object(self):
        import json
        self._kill_one()
        r = self._cli("ctx", "show", "demo", "--json")
        self.assertEqual(r.returncode, 1)
        d = json.loads(r.stdout)
        self.assertEqual(d["dead"], 1)
        e = d["entries"][0]
        self.assertEqual((e["alive"], e["chars"], e["tokens"], e["type"], e["title"]),
                         (False, 0, 0, "", "one.md"))
        self.assertIn("WARNING: 1 dead entry", r.stderr)

    def test_read_prints_required_only(self):
        r = self._cli("ctx", "read", "demo")
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertEqual(r.stdout, (
            "===== 1/2 {one} =====\n{c1}"
            "===== 2/2 {three} =====\n{c3}"
            "===== 1 reference entry not printed — ctx show demo =====\n").format(
                one=self.one, three=self.three,
                c1=okf.read_file(self.one), c3=okf.read_file(self.three)))
        self.assertNotIn("# Out", r.stdout)

    def test_read_adds_missing_newline_and_plural(self):
        self._w("b/two.md", "no newline")
        okf.save_ctx(self.root, {"slug": "p", "description": "", "entries": [
            {"mode": "pflicht", "path": "b/two.md", "comment": ""},
            {"mode": "nachschlag", "path": "b/one.md", "comment": ""},
            {"mode": "nachschlag", "path": "ext/three.md", "comment": ""}]})
        out = self._cli("ctx", "read", "p").stdout
        self.assertIn("no newline\n===== 2 reference entries not printed", out)

    def test_read_dead_exit_1(self):
        self._kill_one()
        r = self._cli("ctx", "read", "demo")
        self.assertEqual(r.returncode, 1)
        self.assertTrue(r.stdout.startswith(
            "===== 1/2 [DEAD] {} =====\n===== 2/2 ".format(self.one)))

    def test_prime_ctx_bundles_line(self):
        okf.save_ctx(self.root, {"slug": "alpha", "description": "", "entries": [
            {"mode": "pflicht", "path": "b/two.md", "comment": ""}]})
        out = okf.render_catalogue_state(self.root)
        self.assertIn("ctx bundles: 2 — alpha · demo — `ctx show <slug>` lists one", out)

    def test_prime_no_line_without_ctx(self):
        shutil.rmtree(os.path.join(self.root, "_ctx"))
        self.assertNotIn("ctx bundles", okf.render_catalogue_state(self.root))

    def test_show_dead_reference_counts(self):
        import json
        os.remove(self.out)
        r = self._cli("ctx", "show", "demo")
        self.assertEqual(r.returncode, 1)
        self.assertIn("  - [DEAD] {}\n     why: background\n".format(self.out), r.stdout)
        self.assertIn("WARNING: 1 dead entry", r.stdout)
        j = self._cli("ctx", "show", "demo", "--json")
        self.assertEqual((j.returncode, json.loads(j.stdout)["dead"]), (1, 1))

    def test_show_orders_required_by_pos_not_file_order(self):
        self._w("_ctx/hand.md", okf.render_ctx("hand", "", [
            {"pos": 9, "mode": "pflicht", "path": "b/two.md", "comment": ""},
            {"pos": 2, "mode": "pflicht", "path": "b/one.md", "comment": ""}]))
        out = self._cli("ctx", "show", "hand").stdout
        self.assertLess(out.index("one.md"), out.index("two.md"))

    def test_show_reference_description_not_printed(self):
        okf.save_ctx(self.root, {"slug": "r", "description": "", "entries": [
            {"mode": "nachschlag", "path": "b/one.md", "comment": ""}]})
        self.assertNotIn("first", self._cli("ctx", "show", "r").stdout)

    def test_non_md_member_metadata(self):
        import json
        with open(os.path.join(self.home, "notes", "a.txt"), "w", encoding="utf-8") as f:
            f.write("---\ntype: X\ntitle: T\n---\nabcde")
        okf.save_ctx(self.root, {"slug": "t", "description": "", "entries": [
            {"mode": "pflicht", "path": "~/notes/a.txt", "comment": ""}]})
        e = json.loads(self._cli("ctx", "show", "t", "--json").stdout)["entries"][0]
        self.assertEqual((e["type"], e["title"], e["description"], e["chars"], e["tokens"]),
                         ("", "a.txt", "", 30, 8))


class CtxMaintain(CtxCatalogue):
    """add / drop / move / rename / remove (OKFT-jetz)."""

    def setUp(self):
        super().setUp()
        okf.save_ctx(self.root, {"slug": "demo", "description": "d", "entries": [
            E(1, "pflicht", "b/one.md", "c-one"), E(2, "pflicht", "b/two.md", "c|two"),
            E(None, "nachschlag", "ext/three.md", "c-three")]})

    def _rows(self, slug="demo"):
        return [(e["pos"], e["mode"], e["path"], e["comment"])
                for e in okf.load_ctx(self.root, slug)["entries"]]

    def _bytes(self, slug="demo"):
        with open(okf.ctx_file(self.root, slug), "rb") as f:
            return f.read()

    def _broken(self):
        """demo with one valid row and one 3-cell row (AC-11)."""
        ap = okf.ctx_file(self.root, "demo")
        with open(ap, "a", encoding="utf-8") as f:
            f.write("| 3 | pflicht | [x](/b/x.md) |\n")
        return self._bytes()

    # --- add
    def test_add_appends_as_last_required(self):
        self._w("b/four.md", "# Four\n")
        r = self._cli("ctx", "add", "demo", "b/four.md")
        self.assertEqual((r.returncode, r.stdout), (0, "added b/four.md to demo (pos 3)\n"), r.stderr)
        self.assertEqual(self._rows(), [
            (1, "pflicht", "b/one.md", "c-one"), (2, "pflicht", "b/two.md", "c|two"),
            (3, "pflicht", "b/four.md", ""), (None, "nachschlag", "ext/three.md", "c-three")])

    def test_add_pos_inserts_and_renumbers(self):
        self._w("b/four.md", "# Four\n")
        r = self._cli("ctx", "add", "demo", "b/four.md", "--pos", "1", "--comment", "new")
        self.assertEqual((r.returncode, r.stdout), (0, "added b/four.md to demo (pos 1)\n"), r.stderr)
        self.assertEqual([x[:3] for x in self._rows()][:3], [
            (1, "pflicht", "b/four.md"), (2, "pflicht", "b/one.md"), (3, "pflicht", "b/two.md")])
        self.assertEqual(self._rows()[0][3], "new")

    def test_add_pos_is_clamped(self):
        self._w("b/four.md", "# Four\n")
        r = self._cli("ctx", "add", "demo", "b/four.md", "--pos", "99")
        self.assertEqual(r.stdout, "added b/four.md to demo (pos 3)\n")
        self._w("b/five.md", "# Five\n")
        r = self._cli("ctx", "add", "demo", "b/five.md", "--pos", "0")
        self.assertEqual(r.stdout, "added b/five.md to demo (pos 1)\n")

    def test_add_nachschlag_appends_reference(self):
        self._w("b/four.md", "# Four\n")
        r = self._cli("ctx", "add", "demo", "b/four.md", "--mode", "nachschlag")
        self.assertEqual((r.returncode, r.stdout), (0, "added b/four.md to demo (reference)\n"), r.stderr)
        self.assertEqual(self._rows()[-1], (None, "nachschlag", "b/four.md", ""))
        self.assertEqual(self._rows()[1][0], 2)

    def test_add_pos_with_nachschlag_refused(self):
        before = self._bytes()
        r = self._cli("ctx", "add", "demo", "b/one.md", "--mode", "nachschlag", "--pos", "1")
        self.assertEqual((r.returncode, r.stderr), (2, "ctx: --pos applies only to mode pflicht\n"))
        self.assertEqual(self._bytes(), before)

    def test_add_duplicate_refused_unchanged(self):
        before = self._bytes()
        r = self._cli("ctx", "add", "demo", "b/two.md")
        self.assertEqual((r.returncode, r.stderr), (2, "ctx: b/two.md is already in demo (pos 2)\n"))
        r = self._cli("ctx", "add", "demo", "ext/three.md")
        self.assertEqual(r.stderr, "ctx: ext/three.md is already in demo (reference)\n")
        self.assertEqual(self._bytes(), before)

    def test_add_missing_file_refused(self):
        before = self._bytes()
        r = self._cli("ctx", "add", "demo", "b/nope.md")
        self.assertEqual((r.returncode, r.stderr), (2, "ctx: not found: b/nope.md\n"))
        self.assertEqual(self._bytes(), before)

    # --- drop
    def test_drop_renumbers(self):
        r = self._cli("ctx", "drop", "demo", "b/one.md")
        self.assertEqual((r.returncode, r.stdout), (0, "dropped b/one.md from demo\n"), r.stderr)
        self.assertEqual(self._rows(), [
            (1, "pflicht", "b/two.md", "c|two"), (None, "nachschlag", "ext/three.md", "c-three")])

    def test_drop_works_when_file_is_gone(self):
        os.remove(os.path.join(self.root, "b", "one.md"))
        r = self._cli("ctx", "drop", "demo", "b/one.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([x[2] for x in self._rows()], ["b/two.md", "ext/three.md"])
        self.assertEqual(self._rows()[0][0], 1)

    def test_drop_absent_refused(self):
        before = self._bytes()
        r = self._cli("ctx", "drop", "demo", "b/gone.md")
        self.assertEqual((r.returncode, r.stderr), (2, "ctx: b/gone.md is not in demo\n"))
        self.assertEqual(self._bytes(), before)

    # --- move
    def test_move_pos_reorders(self):
        r = self._cli("ctx", "move", "demo", "b/two.md", "--pos", "1")
        self.assertEqual((r.returncode, r.stdout), (0, "moved b/two.md in demo to pos 1\n"), r.stderr)
        self.assertEqual(self._rows()[:2], [(1, "pflicht", "b/two.md", "c|two"),
                                            (2, "pflicht", "b/one.md", "c-one")])

    def test_move_pos_is_clamped(self):
        r = self._cli("ctx", "move", "demo", "b/one.md", "--pos", "99")
        self.assertEqual(r.stdout, "moved b/one.md in demo to pos 2\n")
        self.assertEqual([x[2] for x in self._rows()][:2], ["b/two.md", "b/one.md"])

    def test_move_to_nachschlag_goes_behind_required(self):
        r = self._cli("ctx", "move", "demo", "b/one.md", "--mode", "nachschlag")
        self.assertEqual((r.returncode, r.stdout), (0, "moved b/one.md in demo to reference\n"), r.stderr)
        self.assertEqual(self._rows(), [
            (1, "pflicht", "b/two.md", "c|two"),
            (None, "nachschlag", "ext/three.md", "c-three"),
            (None, "nachschlag", "b/one.md", "c-one")])

    def test_move_to_pflicht_without_pos_is_last_required(self):
        r = self._cli("ctx", "move", "demo", "ext/three.md", "--mode", "pflicht")
        self.assertEqual((r.returncode, r.stdout), (0, "moved ext/three.md in demo to pos 3\n"), r.stderr)
        self.assertEqual(self._rows()[2], (3, "pflicht", "ext/three.md", "c-three"))

    def test_move_to_pflicht_with_pos(self):
        r = self._cli("ctx", "move", "demo", "ext/three.md", "--mode", "pflicht", "--pos", "1")
        self.assertEqual(r.stdout, "moved ext/three.md in demo to pos 1\n")
        self.assertEqual([x[:3] for x in self._rows()], [
            (1, "pflicht", "ext/three.md"), (2, "pflicht", "b/one.md"), (3, "pflicht", "b/two.md")])

    def test_move_refusals_leave_file_unchanged(self):
        before = self._bytes()
        for argv, msg in (
                (["b/one.md"], "ctx: move needs --pos or --mode\n"),
                (["b/gone.md", "--pos", "1"], "ctx: b/gone.md is not in demo\n"),
                (["b/one.md", "--pos", "1", "--mode", "nachschlag"],
                 "ctx: --pos applies only to mode pflicht\n"),
                (["ext/three.md", "--pos", "1"], "ctx: --pos applies only to mode pflicht\n")):
            r = self._cli("ctx", "move", "demo", *argv)
            self.assertEqual((r.returncode, r.stderr), (2, msg), argv)
            self.assertEqual(self._bytes(), before, argv)

    def test_sequences_keep_positions_gapless(self):
        for p in ("b/four.md", "b/five.md"):
            self._w(p, "# X\n")
        for argv in (["add", "demo", "b/four.md", "--pos", "2"],
                     ["move", "demo", "b/one.md", "--pos", "3"],
                     ["drop", "demo", "b/two.md"],
                     ["add", "demo", "b/five.md"],
                     ["move", "demo", "b/four.md", "--mode", "nachschlag"],
                     ["move", "demo", "ext/three.md", "--mode", "pflicht", "--pos", "1"]):
            self.assertEqual(self._cli("ctx", *argv).returncode, 0, argv)
            req = [r[0] for r in self._rows() if r[1] == "pflicht"]
            self.assertEqual(req, list(range(1, len(req) + 1)), argv)

    # --- AC-11
    def test_parse_problems_block_add_drop_move(self):
        before = self._broken()
        for argv in (["add", "demo", "b/one.md", "--mode", "nachschlag"],
                     ["add", "demo", "ext/three.md"],
                     ["drop", "demo", "b/one.md"],
                     ["move", "demo", "b/one.md", "--pos", "2"]):
            r = self._cli("ctx", *argv)
            self.assertEqual((r.returncode, r.stderr),
                             (2, "ctx: demo has 1 parse problem(s) — fix with okf ctx edit, "
                                 "see okf ctx check\n"), argv)
            self.assertEqual(self._bytes(), before, argv)

    # --- rename
    def test_rename_moves_rewrites_links_refreshes_h1(self):
        self._w("b/ref.md", "---\ntype: Concept\ntitle: R\n---\n\nSee [d](/_ctx/demo.md).\n")
        r = self._cli("ctx", "rename", "demo", "demo2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(okf.ctx_file(self.root, "demo")))
        with open(os.path.join(self.root, "b", "ref.md"), encoding="utf-8") as f:
            self.assertIn("(/_ctx/demo2.md)", f.read())
        _, body = okf.split_frontmatter(self._bytes("demo2").decode())
        self.assertTrue(body.lstrip().startswith("# demo2\n"), body)
        self.assertEqual(self._rows("demo2")[1], (2, "pflicht", "b/two.md", "c|two"))
        with open(os.path.join(self.root, "_ctx", "index.md"), encoding="utf-8") as f:
            self.assertIn("demo2", f.read())

    def test_rename_refusals_move_nothing(self):
        okf.save_ctx(self.root, {"slug": "other", "description": "", "entries": []})
        before = self._bytes()
        for argv, msg in (
                (["demo", "Bad_Slug"], 'ctx: invalid slug "Bad_Slug": use lowercase letters, digits and hyphens\n'),
                (["demo", "list"], 'ctx: invalid slug "list": "list" is a reserved name\n'),
                (["demo", "other"], "ctx: other already exists\n"),
                (["nope", "fresh"], "ctx: unknown slug: nope\n")):
            r = self._cli("ctx", "rename", *argv)
            self.assertEqual((r.returncode, r.stderr), (2, msg), argv)
            self.assertEqual(self._bytes(), before, argv)
        self.assertEqual(okf.ctx_slugs(self.root), ["demo", "other"])

    def test_rename_with_parse_problems_moves_but_keeps_content(self):
        before = self._broken()
        r = self._cli("ctx", "rename", "demo", "demo2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self._bytes("demo2"), before)

    # --- remove
    def test_remove_deletes_and_lists_remaining_links(self):
        self._w("b/ref.md", "[a](/_ctx/demo.md) and [b](/_ctx/demo.md#x)\n")
        self._w("b/ref2.md", "[a](/_ctx/demo.md)\n")
        r = self._cli("ctx", "remove", "demo")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines()[0], "removed _ctx/demo.md (3 entries)")
        self.assertEqual(r.stdout.splitlines()[1:],
                         ["warning: 2 file(s) still link to _ctx/demo.md:",
                          "  b/ref.md", "  b/ref2.md"])
        self.assertFalse(os.path.exists(okf.ctx_file(self.root, "demo")))
        with open(os.path.join(self.root, "_ctx", "index.md"), encoding="utf-8") as f:
            self.assertNotIn("demo", f.read())

    def test_remove_without_inbound_links_is_silent_after_first_line(self):
        r = self._cli("ctx", "remove", "demo")
        self.assertEqual((r.returncode, r.stdout), (0, "removed _ctx/demo.md (3 entries)\n"), r.stderr)

    def test_remove_unknown_slug_refused(self):
        r = self._cli("ctx", "remove", "nope")
        self.assertEqual((r.returncode, r.stderr), (2, "ctx: unknown slug: nope\n"))


class CtxNavigate(CtxCatalogue):
    def setUp(self):
        super().setUp()
        self._w("b/three.md", "# Three\n\n[x](/b/two.md) [dead](nope.md)\n")
        okf.save_ctx(self.root, {"slug": "demo", "description": "d", "entries": [
            {"mode": "pflicht", "path": "b/two.md", "comment": ""}]})

    def _set(self, *paths):
        okf.save_ctx(self.root, {"slug": "demo", "description": "d", "entries": [
            {"mode": "pflicht", "path": p, "comment": ""} for p in paths]})

    def test_toc_exact(self):
        self._w("b/one.md", "---\ntype: Concept\n---\n# One\n```\n# no\n```\n## A\n### B\n")
        self._set("b/two.md", "b/one.md", "b/three.md")
        os.remove(os.path.join(self.root, "b/three.md"))
        self._w("b/four.md", "x\n")
        r = self._cli("ctx", "toc", "demo")
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertEqual(r.stdout, "# b/two.md\n## Two\n### Part\n\n# b/one.md\n## One\n### A\n#### B\n\n"
                                   "# b/three.md [DEAD]\n")

    def test_toc_depth_and_no_headings(self):
        self._w("b/four.md", "x\n")
        self._set("b/two.md", "b/four.md")
        r = self._cli("ctx", "toc", "demo", "--depth", "1")
        self.assertEqual(r.stdout, "# b/two.md\n## Two\n\n# b/four.md\n(no headings)\n")

    def test_toc_non_md_member_has_no_headings(self):
        self._w("b/a.txt", "# Not a heading\n")
        self._set("b/a.txt")
        self.assertEqual(self._cli("ctx", "toc", "demo").stdout, "# b/a.txt\n(no headings)\n")

    def test_inbound_external_only(self):
        r = self._cli("ctx", "inbound", "demo")
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        # scan order is directory order: compare the two source lines unordered
        head, *rest = r.stdout.splitlines()
        self.assertEqual(head, "inbound \u2014 ctx demo, 1 member(s), external sources only:")
        self.assertEqual((rest[0], sorted(rest[1:])), ("b/two.md", [
            "  <- b/one.md  (/b/two.md)", "  <- b/three.md  (/b/two.md)"]))

    def test_inbound_internal(self):
        self._set("b/one.md", "b/two.md")
        r = self._cli("ctx", "inbound", "demo")
        self.assertEqual(r.stdout, "inbound \u2014 ctx demo, 2 member(s), external sources only:\n"
                                   "b/one.md\n  (none)\nb/two.md\n  <- b/three.md  (/b/two.md)\n")
        r = self._cli("ctx", "inbound", "demo", "--include-internal")
        self.assertIn("including internal links:\n", r.stdout)
        self.assertIn("  <- b/one.md  (/b/two.md)\n", r.stdout)
        self.assertIn("  <- b/three.md  (/b/two.md)\n", r.stdout)
        self.assertIn("b/one.md\n  (none)\n", r.stdout)

    def test_inbound_excludes_ctx_files(self):
        r = self._cli("ctx", "inbound", "demo")
        self.assertNotIn("_ctx/", r.stdout)

    def test_inbound_case_insensitive_link(self):
        self._w("b/three.md", "[u](TWO.md)\n")
        if not os.path.exists(os.path.join(self.root, "b/TWO.md")):
            self.skipTest("case-sensitive filesystem")
        r = self._cli("ctx", "inbound", "demo")
        self.assertIn("  <- b/three.md  (TWO.md)\n", r.stdout)

    def test_outbound(self):
        self._set("b/one.md", "b/three.md")
        r = self._cli("ctx", "outbound", "demo")
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertEqual(r.stdout, "outbound \u2014 ctx demo, 2 member(s), external targets only:\n"
                                   "b/one.md\n  -> b/two.md  (/b/two.md)\n"
                                   "b/three.md\n  -> b/two.md  (/b/two.md)\n  -> b/nope.md  (nope.md)  [missing]\n")

    def test_outbound_excludes_member_targets(self):
        self._set("b/one.md", "b/two.md")
        r = self._cli("ctx", "outbound", "demo")
        self.assertEqual(r.stdout, "outbound \u2014 ctx demo, 2 member(s), external targets only:\n"
                                   "b/one.md\n  (none)\nb/two.md\n  (none)\n")
        r = self._cli("ctx", "outbound", "demo", "--include-internal")
        self.assertIn("b/one.md\n  -> b/two.md  (/b/two.md)\n", r.stdout)

    def test_outbound_dead_and_nonmd(self):
        self._w("b/a.txt", "[l](two.md)\n")
        self._set("b/gone.md", "b/a.txt")
        with mock.patch.object(okf, "outbound_links", side_effect=AssertionError):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                okf.cmd_ctx_outbound(self.root, mock.Mock(slug="demo", file=None,
                                                          include_internal=False, json=False))
        self.assertEqual(out.getvalue().split("\n", 1)[1], "b/gone.md [DEAD]\nb/a.txt\n  (none)\n")
        r = self._cli("ctx", "outbound", "demo")
        self.assertEqual(r.returncode, 0)

    def test_outbound_json(self):
        import json
        self._set("b/gone.md", "b/three.md")
        d = json.loads(self._cli("ctx", "outbound", "demo", "--json").stdout)
        self.assertEqual(d, {"slug": "demo", "direction": "outbound", "include_internal": False,
                             "members": [
            {"path": "b/gone.md", "dead": True, "links": []},
            {"path": "b/three.md", "dead": False, "links": [
                {"target": "b/two.md", "link": "/b/two.md", "exists": True},
                {"target": "b/nope.md", "link": "nope.md", "exists": False}]}]})

    def test_inbound_json(self):
        import json
        d = json.loads(self._cli("ctx", "inbound", "demo", "--json").stdout)
        self.assertEqual(d["direction"], "inbound")
        (m,) = d["members"]
        self.assertEqual((m["path"], sorted(l["source"] for l in m["links"]),
                          {l["link"] for l in m["links"]}),
                         ("b/two.md", ["b/one.md", "b/three.md"], {"/b/two.md"}))
        self.assertEqual(set(m), {"path", "links"})

    def test_file_filter(self):
        self._set("b/one.md", "b/two.md")
        for sel in ("TWO", "two", "b/TWO.md"):
            r = self._cli("ctx", "inbound", "demo", "--file", sel)
            self.assertEqual(r.stdout.splitlines()[0],
                             "inbound \u2014 ctx demo, 1 member(s), external sources only:", sel)
            self.assertIn("b/two.md\n", r.stdout)
            self.assertNotIn("b/one.md\n", r.stdout)

    def test_toc_skips_frontmatter(self):
        self._w("b/fm.md", "---\ntype: Concept\n# yaml comment\n---\n# Real\n")
        self._set("b/fm.md")
        self.assertEqual(self._cli("ctx", "toc", "demo").stdout, "# b/fm.md\n## Real\n")

    def test_file_matches_each_alternative(self):
        self._w("b/five.md", "---\ntype: Concept\ntitle: Fancy Name\n---\n# F\n")
        self._set("b/two.md", "b/five.md")
        for sel in ("fancy NAME", "B/Five.md", "FIVE"):  # live title / stored path / stem
            r = self._cli("ctx", "outbound", "demo", "--file", sel)
            self.assertEqual((r.returncode, r.stdout), (0, "outbound \u2014 ctx demo, 1 member(s), "
                             "external targets only:\nb/five.md\n  (none)\n"), sel)

    def test_outbound_case_insensitive_member(self):
        self._w("b/three.md", "[u](TWO.md)\n")
        if not os.path.exists(os.path.join(self.root, "b/TWO.md")):
            self.skipTest("case-sensitive filesystem")
        self._set("b/three.md", "b/two.md")
        r = self._cli("ctx", "outbound", "demo")
        self.assertEqual(r.stdout, "outbound \u2014 ctx demo, 2 member(s), external targets only:\n"
                                   "b/three.md\n  (none)\nb/two.md\n  (none)\n")
        r = self._cli("ctx", "outbound", "demo", "--include-internal")
        self.assertIn("b/three.md\n  -> b/TWO.md  (TWO.md)\n", r.stdout)

    def test_file_no_match_and_ambiguous(self):
        self._set("b/one.md", "b/two.md")
        r = self._cli("ctx", "inbound", "demo", "--file", "zzz")
        self.assertEqual((r.returncode, r.stdout, r.stderr),
                         (2, "", 'ctx: no entry in demo matches --file "zzz"\n'))
        self._w("c/two.md", "# T\n")
        self._set("b/two.md", "c/two.md")
        r = self._cli("ctx", "outbound", "demo", "--file", "two")
        self.assertEqual((r.returncode, r.stdout, r.stderr),
                         (2, "", 'ctx: --file "two" matches several entries: b/two.md, c/two.md\n'))


if __name__ == "__main__":
    unittest.main()
