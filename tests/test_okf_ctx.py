#!/usr/bin/env python3
"""Tests for the ctx command module cli/okf/ctx.py (OKFT-t0lj). The ctx storage layer
they sit on is tested in test_okf_catalogue.py.

Run: python3 -m unittest tests.test_okf_ctx -v
"""
import contextlib
import io
import os
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
from okf.errors import EXIT_CODES
from okf import ctx as okf_ctx
from okf import linkscan as okf_linkscan
from tests.okf_testkit import CtxFixtureMixin, E


class CtxRenameArchive(CtxFixtureMixin, unittest.TestCase):
    def _demo(self, text=None):
        if text is None:
            okf_catalogue.save_ctx(self.root, {"slug": "demo", "description": "d", "entries": [
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
            e = okf_catalogue.load_ctx(self.root, "demo")["entries"][0]
        self.assertTrue(os.path.exists(okf_catalogue.ctx_entry_abspath(self.root, e["path"])))
        self.assertIn("listed in 1 ctx bundle(s): demo (pos 1)\n", r.stdout)

    def test_archive_apply_points_entry_at_archive_path(self):
        self._demo()
        r = self._cli("archive", "b/two.md", "--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("(/_archive/b/two.md)", self._read("_ctx/demo.md"))
        self.assertIn("listed in 1 ctx bundle(s): demo (pos 1)\n", r.stdout)

    def test_reference_entry_reports_reference(self):
        okf_catalogue.save_ctx(self.root, {"slug": "demo", "description": "d", "entries": [
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


class CtxBundleGate(CtxFixtureMixin, unittest.TestCase):
    def test_ctx_dir_is_bundle_other_underscore_and_dot_are_not(self):
        self.assertTrue(okf_catalogue.is_bundle_dir("_ctx"))
        self.assertFalse(okf_catalogue.is_bundle_dir("_archive"))
        self.assertFalse(okf_catalogue.is_bundle_dir("_other"))
        self.assertFalse(okf_catalogue.is_bundle_dir(".fts"))
        self.assertTrue(okf_catalogue.is_bundle_dir("b"))

    def test_list_bundles_includes_ctx_once_it_exists(self):
        self.assertNotIn("_ctx", okf_catalogue.list_bundles(self.root))
        okf_catalogue.save_ctx(self.root, {"slug": "a", "description": "d", "entries": []})
        self.assertIn("_ctx", okf_catalogue.list_bundles(self.root))


class CtxShorthand(unittest.TestCase):
    def test_rewrites(self):
        S = okf_ctx._ctx_shorthand
        self.assertEqual(S(["ctx"]), ["ctx", "list"])
        self.assertEqual(S(["--root", "r", "ctx"]), ["--root", "r", "ctx", "list"])
        self.assertEqual(S(["--root=r", "ctx", "--list"]), ["--root=r", "ctx", "list"])
        self.assertEqual(S(["ctx", "demo"]), ["ctx", "show", "demo"])
        self.assertEqual(S(["ctx", "create", "x"]), ["ctx", "create", "x"])
        self.assertEqual(S(["ctx", "--help"]), ["ctx", "--help"])

    def test_other_commands_untouched(self):
        for argv in (["list", "ctx"], ["find", "ctx", "x"], ["--root", "ctx", "read", "a"],
                     ["read", "b/ctx"], []):
            self.assertEqual(okf_ctx._ctx_shorthand(argv), argv)


class CtxListCreate(CtxFixtureMixin, unittest.TestCase):
    def _create(self, *argv):
        return self._cli("ctx", "create", *argv)

    def test_create_orders_and_list_counts(self):
        r = self._create("demo", "b/two", "b/one")
        self.assertEqual((r.returncode, r.stdout), (0, "created _ctx/demo.md (2 entries)\n"))
        c = okf_catalogue.load_ctx(self.root, "demo")
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
        okf_catalogue.save_ctx(self.root, {"slug": "alpha", "description": "Alpha desc", "entries": [
            E(1, "pflicht", "b/one.md"), E(2, "pflicht", "b/two.md"),
            E(None, "nachschlag", "ext/three.md")]})
        okf_catalogue.save_ctx(self.root, {"slug": "be", "description": "Be desc", "entries": [
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
        es = okf_catalogue.load_ctx(self.root, "imp")["entries"]
        self.assertEqual([(e["path"], e["comment"]) for e in es],
                         [("b/one.md", ""), ("b/two.md", "second one")])

    def test_create_errors_write_nothing(self):
        self._create("old", "b/one")
        cases = [
            (("Bad", "b/one"), "invalid_input",
             'ctx: invalid slug "Bad": use lowercase letters, digits and hyphens'),
            (("show", "b/one"), "invalid_input",
             'ctx: invalid slug "show": "show" is a reserved name'),
            (("old", "b/two"), "invalid_input", "ctx: old already exists"),
            (("new",), "invalid_input", "ctx: create needs at least one path"),
            (("new", "b/one", "--import", "nofile.txt"), "not_found",
             "ctx: import file not found: nofile.txt"),
        ]
        for argv, kind, msg in cases:
            r = self._create(*argv)
            self.assertEqual((r.returncode, r.stdout), (EXIT_CODES[kind], ""), argv)
            self.assertEqual(r.stderr.strip(), msg, argv)
        self.assertEqual(okf_catalogue.ctx_slugs(self.root), ["old"])
        self.assertEqual(len(okf_catalogue.load_ctx(self.root, "old")["entries"]), 1)

    def test_create_missing_paths_each_reported(self):
        r = self._create("new", "b/one", "b/x", "b/y")
        self.assertEqual(r.returncode, EXIT_CODES["not_found"])
        self.assertEqual(r.stderr.splitlines(), ["ctx: not found: b/x", "ctx: not found: b/y"])
        self.assertEqual(okf_catalogue.ctx_slugs(self.root), [])


class CtxShowRead(CtxFixtureMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.one = os.path.join(self.root, "b/one.md")
        self.three = os.path.join(self.root, "ext", "three.md")
        self.out = os.path.join(self.home, "notes", "out.md")
        okf_catalogue.save_ctx(self.root, {"slug": "demo", "description": "Demo ctx", "entries": [
            {"mode": "pflicht", "path": "b/one.md", "comment": "start here"},
            {"mode": "pflicht", "path": "ext/three.md", "comment": ""},
            {"mode": "nachschlag", "path": "~/notes/out.md", "comment": "background"}]})

    def _kill_one(self):
        os.remove(self.one)

    def test_show_text_exact(self):
        r = self._cli("ctx", "show", "demo")
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        one_chars = len(okf_catalogue.read_file(self.one))
        three_chars = len(okf_catalogue.read_file(self.three))
        t1, t3 = (one_chars + 3) // 4, (three_chars + 3) // 4
        t_out = (len(okf_catalogue.read_file(self.out)) + 3) // 4
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
        self.assertEqual((r.returncode, r.stdout), (EXIT_CODES["not_found"], ""))
        self.assertEqual(r.stderr.strip(), "ctx: unknown slug: nope")

    def test_show_dead_entry(self):
        self._kill_one()
        r = self._cli("ctx", "show", "demo")
        self.assertEqual(r.returncode, EXIT_CODES["non_conformant"])
        self.assertIn("  1. [DEAD] {}\n     why: start here\n".format(self.one), r.stdout)
        self.assertTrue(r.stdout.endswith(
            "WARNING: 1 dead entry — this list is incomplete; fix with `ctx edit demo`\n"))

    def test_show_empty_reference_and_none(self):
        okf_catalogue.save_ctx(self.root, {"slug": "refonly", "description": "", "entries": [
            {"mode": "nachschlag", "path": "b/two.md", "comment": ""}]})
        out = self._cli("ctx", "show", "refonly").stdout
        self.assertTrue(out.startswith("ctx refonly\n\nrequired — read in this order:\n  (none)\n"
                                       "reference — query when needed:\n"))
        okf_catalogue.save_ctx(self.root, {"slug": "reqonly", "description": "", "entries": [
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
        self.assertEqual(e1["chars"], len(okf_catalogue.read_file(self.one)))

    def test_show_json_follows_title_change(self):
        import json
        self._w("b/one.md", "---\ntype: Concept\ntitle: Renamed\n---\n\nx\n")
        d = json.loads(self._cli("ctx", "show", "demo", "--json").stdout)
        self.assertEqual(d["entries"][0]["title"], "Renamed")

    def test_show_json_dead_stdout_only_object(self):
        import json
        self._kill_one()
        r = self._cli("ctx", "show", "demo", "--json")
        self.assertEqual(r.returncode, EXIT_CODES["non_conformant"])
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
                c1=okf_catalogue.read_file(self.one), c3=okf_catalogue.read_file(self.three)))
        self.assertNotIn("# Out", r.stdout)

    def test_read_adds_missing_newline_and_plural(self):
        self._w("b/two.md", "no newline")
        okf_catalogue.save_ctx(self.root, {"slug": "p", "description": "", "entries": [
            {"mode": "pflicht", "path": "b/two.md", "comment": ""},
            {"mode": "nachschlag", "path": "b/one.md", "comment": ""},
            {"mode": "nachschlag", "path": "ext/three.md", "comment": ""}]})
        out = self._cli("ctx", "read", "p").stdout
        self.assertIn("no newline\n===== 2 reference entries not printed", out)

    def test_read_dead_exit_1(self):
        self._kill_one()
        r = self._cli("ctx", "read", "demo")
        self.assertEqual(r.returncode, EXIT_CODES["non_conformant"])
        self.assertTrue(r.stdout.startswith(
            "===== 1/2 [DEAD] {} =====\n===== 2/2 ".format(self.one)))

    def test_prime_ctx_bundles_line(self):
        okf_catalogue.save_ctx(self.root, {"slug": "alpha", "description": "", "entries": [
            {"mode": "pflicht", "path": "b/two.md", "comment": ""}]})
        out = self._cli("prime").stdout
        self.assertIn("ctx bundles: 2 — alpha · demo — `ctx show <slug>` lists one", out)

    def test_prime_no_line_without_ctx(self):
        shutil.rmtree(os.path.join(self.root, "_ctx"))
        r = self._cli("prime")
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("ctx bundles", r.stdout)

    def test_show_dead_reference_counts(self):
        import json
        os.remove(self.out)
        r = self._cli("ctx", "show", "demo")
        self.assertEqual(r.returncode, EXIT_CODES["non_conformant"])
        self.assertIn("  - [DEAD] {}\n     why: background\n".format(self.out), r.stdout)
        self.assertIn("WARNING: 1 dead entry", r.stdout)
        j = self._cli("ctx", "show", "demo", "--json")
        self.assertEqual((j.returncode, json.loads(j.stdout)["dead"]),
                         (EXIT_CODES["non_conformant"], 1))

    def test_show_orders_required_by_pos_not_file_order(self):
        self._w("_ctx/hand.md", okf_catalogue.render_ctx("hand", "", [
            {"pos": 9, "mode": "pflicht", "path": "b/two.md", "comment": ""},
            {"pos": 2, "mode": "pflicht", "path": "b/one.md", "comment": ""}]))
        out = self._cli("ctx", "show", "hand").stdout
        self.assertLess(out.index("one.md"), out.index("two.md"))

    def test_show_reference_description_not_printed(self):
        okf_catalogue.save_ctx(self.root, {"slug": "r", "description": "", "entries": [
            {"mode": "nachschlag", "path": "b/one.md", "comment": ""}]})
        self.assertNotIn("first", self._cli("ctx", "show", "r").stdout)

    def test_non_md_member_metadata(self):
        import json
        with open(os.path.join(self.home, "notes", "a.txt"), "w", encoding="utf-8") as f:
            f.write("---\ntype: X\ntitle: T\n---\nabcde")
        okf_catalogue.save_ctx(self.root, {"slug": "t", "description": "", "entries": [
            {"mode": "pflicht", "path": "~/notes/a.txt", "comment": ""}]})
        e = json.loads(self._cli("ctx", "show", "t", "--json").stdout)["entries"][0]
        self.assertEqual((e["type"], e["title"], e["description"], e["chars"], e["tokens"]),
                         ("", "a.txt", "", 30, 8))


class CtxMaintain(CtxFixtureMixin, unittest.TestCase):
    """add / drop / move / rename / remove (OKFT-jetz)."""

    def setUp(self):
        super().setUp()
        okf_catalogue.save_ctx(self.root, {"slug": "demo", "description": "d", "entries": [
            E(1, "pflicht", "b/one.md", "c-one"), E(2, "pflicht", "b/two.md", "c|two"),
            E(None, "nachschlag", "ext/three.md", "c-three")]})

    def _rows(self, slug="demo"):
        return [(e["pos"], e["mode"], e["path"], e["comment"])
                for e in okf_catalogue.load_ctx(self.root, slug)["entries"]]

    def _bytes(self, slug="demo"):
        with open(okf_catalogue.ctx_file(self.root, slug), "rb") as f:
            return f.read()

    def _broken(self):
        """demo with one valid row and one 3-cell row (AC-11)."""
        ap = okf_catalogue.ctx_file(self.root, "demo")
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
        self.assertEqual((r.returncode, r.stderr),
                         (EXIT_CODES["not_found"], "ctx: not found: b/nope.md\n"))
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
        self.assertEqual((r.returncode, r.stderr),
                         (EXIT_CODES["not_found"], "ctx: b/gone.md is not in demo\n"))
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
        for argv, msg, kind in (
                (["b/one.md"], "ctx: move needs --pos or --mode\n", "invalid_input"),
                (["b/gone.md", "--pos", "1"], "ctx: b/gone.md is not in demo\n", "not_found"),
                (["b/one.md", "--pos", "1", "--mode", "nachschlag"],
                 "ctx: --pos applies only to mode pflicht\n", "invalid_input"),
                (["ext/three.md", "--pos", "1"], "ctx: --pos applies only to mode pflicht\n",
                 "invalid_input")):
            r = self._cli("ctx", "move", "demo", *argv)
            self.assertEqual((r.returncode, r.stderr), (EXIT_CODES[kind], msg), argv)
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
        self.assertFalse(os.path.exists(okf_catalogue.ctx_file(self.root, "demo")))
        with open(os.path.join(self.root, "b", "ref.md"), encoding="utf-8") as f:
            self.assertIn("(/_ctx/demo2.md)", f.read())
        _, body = okf_catalogue.split_frontmatter(self._bytes("demo2").decode())
        self.assertTrue(body.lstrip().startswith("# demo2\n"), body)
        self.assertEqual(self._rows("demo2")[1], (2, "pflicht", "b/two.md", "c|two"))
        with open(os.path.join(self.root, "_ctx", "index.md"), encoding="utf-8") as f:
            self.assertIn("demo2", f.read())

    def test_rename_refusals_move_nothing(self):
        okf_catalogue.save_ctx(self.root, {"slug": "other", "description": "", "entries": []})
        before = self._bytes()
        for argv, msg, kind in (
                (["demo", "Bad_Slug"], 'ctx: invalid slug "Bad_Slug": use lowercase letters, digits and hyphens\n',
                 "invalid_input"),
                (["demo", "list"], 'ctx: invalid slug "list": "list" is a reserved name\n',
                 "invalid_input"),
                (["demo", "other"], "ctx: other already exists\n", "invalid_input"),
                (["nope", "fresh"], "ctx: unknown slug: nope\n", "not_found")):
            r = self._cli("ctx", "rename", *argv)
            self.assertEqual((r.returncode, r.stderr), (EXIT_CODES[kind], msg), argv)
            self.assertEqual(self._bytes(), before, argv)
        self.assertEqual(okf_catalogue.ctx_slugs(self.root), ["demo", "other"])

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
        self.assertFalse(os.path.exists(okf_catalogue.ctx_file(self.root, "demo")))
        with open(os.path.join(self.root, "_ctx", "index.md"), encoding="utf-8") as f:
            self.assertNotIn("demo", f.read())

    def test_remove_without_inbound_links_is_silent_after_first_line(self):
        r = self._cli("ctx", "remove", "demo")
        self.assertEqual((r.returncode, r.stdout), (0, "removed _ctx/demo.md (3 entries)\n"), r.stderr)

    def test_remove_unknown_slug_refused(self):
        r = self._cli("ctx", "remove", "nope")
        self.assertEqual((r.returncode, r.stderr),
                         (EXIT_CODES["not_found"], "ctx: unknown slug: nope\n"))


class CtxNavigate(CtxFixtureMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self._w("b/three.md", "# Three\n\n[x](/b/two.md) [dead](nope.md)\n")
        okf_catalogue.save_ctx(self.root, {"slug": "demo", "description": "d", "entries": [
            {"mode": "pflicht", "path": "b/two.md", "comment": ""}]})

    def _set(self, *paths):
        okf_catalogue.save_ctx(self.root, {"slug": "demo", "description": "d", "entries": [
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
        with mock.patch.object(okf_linkscan, "outbound_links", side_effect=AssertionError):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                okf_ctx.cmd_ctx_outbound(self.root, mock.Mock(slug="demo", file=None,
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
                         (EXIT_CODES["not_found"], "", 'ctx: no entry in demo matches --file "zzz"\n'))
        self._w("c/two.md", "# T\n")
        self._set("b/two.md", "c/two.md")
        r = self._cli("ctx", "outbound", "demo", "--file", "two")
        self.assertEqual((r.returncode, r.stdout, r.stderr),
                         (EXIT_CODES["invalid_input"], "", 'ctx: --file "two" matches several entries: b/two.md, c/two.md\n'))


class CtxEdit(CtxFixtureMixin, unittest.TestCase):
    """`ctx edit`: editor chain, validation after exit. Editor = script in tmp dir."""

    def setUp(self):
        super().setUp()
        self.bin = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.bin, True)
        self.log = os.path.join(self.bin, "log")
        self._editor("vi", "")  # guard: a mutant that reaches the fallback never starts a real vi
        okf_catalogue.save_ctx(self.root, {"slug": "demo", "description": "Demo", "entries": [
            E(1, "pflicht", "b/one.md")]})
        self.good = okf_catalogue.render_ctx("demo", "Edited", [E(1, "pflicht", "b/two.md")])
        self.bad = okf_catalogue.render_ctx("demo", "Edited", [E(1, "pflicht", "b/gone.md")])

    def _editor(self, name, text, rc=0):
        p = os.path.join(self.bin, name)
        with open(p, "w") as f:
            f.write("#!/bin/sh\necho {} \"$@\" >> '{}'\nfor a; do t=\"$a\"; done\n"
                    "cat '{}' > \"$t\"\nexit {}\n".format(name, self.log, p + ".txt", rc))
        os.chmod(p, 0o755)
        with open(p + ".txt", "w") as f:
            f.write(text)
        return p

    def _edit(self, slug="demo", **env):
        e = {k: v for k, v in os.environ.items() if k not in ("VISUAL", "EDITOR")}
        e.update(HOME=self.home, PATH=self.bin + os.pathsep + os.environ["PATH"], **env)
        return subprocess.run([sys.executable, os.path.join(_HERE, "okf-cli.py"), "--root",
                               self.root, "ctx", "edit", slug], capture_output=True, text=True, env=e)

    def _calls(self):
        return open(self.log).read().splitlines() if os.path.exists(self.log) else []

    def test_visual_beats_editor(self):
        v = self._editor("vis", self.good)
        ed = self._editor("ed", self.bad)
        r = self._edit(VISUAL=v, EDITOR=ed)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "OK — 0 violations\n", ""))
        self.assertEqual([c.split()[0] for c in self._calls()], ["vis"])

    def test_editor_used_when_no_visual_and_args_are_split(self):
        ed = self._editor("ed", self.good)
        r = self._edit(EDITOR=ed + " --wait")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self._calls()[0].split()[:2], ["ed", "--wait"])
        self.assertTrue(self._calls()[0].endswith(os.path.join("_ctx", "demo.md")))

    def test_vi_fallback(self):
        self._editor("vi", self.good)
        r = self._edit()
        self.assertEqual((r.returncode, r.stdout), (0, "OK — 0 violations\n"))
        self.assertEqual([c.split()[0] for c in self._calls()], ["vi"])

    def test_errors_after_edit_exit_1(self):
        r = self._edit(EDITOR=self._editor("ed", self.bad))
        self.assertEqual((r.returncode, r.stdout, r.stderr), (EXIT_CODES["non_conformant"],
            "ERROR    kc/ctx/dead-entry    _ctx/demo.md  (dead entry: b/gone.md)\n1 VIOLATIONS\n", ""))

    def test_editor_nonzero_exit(self):
        r = self._edit(EDITOR=self._editor("ed", self.good, rc=3))
        self.assertEqual((r.returncode, r.stdout, r.stderr),
                         (EXIT_CODES["invalid_input"], "", "ctx: editor exited 3\n"))

    def test_unknown_slug_never_starts_editor(self):
        r = self._edit("nope", EDITOR=self._editor("ed", self.good))
        self.assertEqual((r.returncode, r.stdout, r.stderr),
                         (EXIT_CODES["not_found"], "", "ctx: unknown slug: nope\n"))
        self.assertEqual(self._calls(), [])

    def test_index_refreshed_after_edit(self):
        self._edit(EDITOR=self._editor("ed", self.good))
        self.assertIn("Edited", okf_catalogue.read_file(os.path.join(self.root, "_ctx", "index.md")))


if __name__ == "__main__":
    unittest.main()
