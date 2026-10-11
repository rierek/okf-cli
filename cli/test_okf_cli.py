#!/usr/bin/env python3
"""Tests for okf-cli.py — stdlib unittest, no deps.

Run: python3 -m unittest test_okf_cli -v
"""
import argparse
import contextlib
import io
import importlib.util
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:  # cli/ holds the okf package; a repo-root run lacks it
    sys.path.insert(0, _HERE)

from okf import catalogue as okf_catalogue
from okf import check as okf_check
from okf import find as okf_find
from okf import find_filters as okf_find_filters
from okf import fts as okf_fts
from okf import index as okf_index
from okf import linkscan as okf_linkscan
from okf import parser_support as okf_parser_support
from okf import semantic as okf_semantic
from okf import sync as okf_sync
from okf import wikilinks as okf_wikilinks
from okf_testkit import SyncFixtureMixin, _cli, needs_case_insensitive_fs, run_find
from test_okf_wikilinks import WikilinkFixtureMixin


_spec = importlib.util.spec_from_file_location("okf_cli", os.path.join(_HERE, "okf-cli.py"))
okf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(okf)

M0, M1 = okf_catalogue.MARK_START, okf_catalogue.MARK_END


class VisualizeDefaultOutputPath(unittest.TestCase):
    """viz.html is a generated artifact, not knowledge content — it must land
    under <bundle>/assets/ by default so it doesn't trip asset-placement."""

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
        okf.cmd_visualize(self.tmp, args)
        expected = os.path.join(self.tmp, "b", "assets", "viz.html")
        self.assertTrue(os.path.isfile(expected))


class IndexableArchiveScopedToDeclaredBundle(unittest.TestCase):
    """OKFT-n8xz test 6 / Gate B B01 — with a `bundle` key declared, an
    archived directory that is NOT the declared bundle must not surface in
    the FTS index (740/745) nor in find's --include-archive scope
    (resolve_scopes, 3312/3317/3326)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "declared-bundle"))
        self._w("declared-bundle/one.md", "One", "active body.\n")
        self._w("_archive/declared-bundle/two.md", "Two", "archived, same bundle.\n")
        self._w("_archive/other-scaffolding/three.md", "Three", "archived, other dir.\n")
        with open(os.path.join(self.tmp, ".okf.toml"), "w", encoding="utf-8") as f:
            f.write('bundle = "declared-bundle"\n')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _w(self, rel, title, body):
        ap = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: {}\n---\n{}".format(title, body))

    def test_fts_index_excludes_the_undeclared_archived_bundle(self):
        okf_fts.build_fts_index(self.tmp)
        conn = sqlite3.connect(okf_fts._fts_db_path(self.tmp))
        rows = [r[0] for r in conn.execute("SELECT path FROM docs")]
        conn.close()
        self.assertIn("declared-bundle/one", rows)
        self.assertIn("_archive/declared-bundle/two", rows)
        self.assertNotIn("_archive/other-scaffolding/three", rows)

    def test_find_include_archive_scope_excludes_the_undeclared_bundle(self):
        """Review 2026-08-13 D02: `indexable_only` is find's explicit opt-in,
        not resolve_scopes()'s default — the call below mirrors what
        `_substring_ranking` actually passes, not a bare unscoped call."""
        scopes = okf_catalogue.resolve_scopes(self.tmp, None, include_archive=True,
                                    indexable_only=True)
        names = [b for b, _ in scopes]
        self.assertIn("_archive/declared-bundle", names)
        self.assertNotIn("_archive/other-scaffolding", names)

    def test_resolve_scopes_default_stays_wide_even_with_a_bundle_key(self):
        """Review 2026-08-13 B01 — the regression itself, pinned at the
        primitive level: without indexable_only=True, resolve_scopes() must
        NOT narrow just because `.okf.toml` declares a `bundle` key. Every
        caller except find (merge-tags, remove-tags, normalize-tags, list,
        _recent_scopes, fix-xml-like-tags, fix-crosslinks, wikilinks, check)
        relies on this default."""
        scopes = okf_catalogue.resolve_scopes(self.tmp, None, include_archive=True)
        names = [b for b, _ in scopes]
        self.assertIn("_archive/other-scaffolding", names)


class RewritePath(unittest.TestCase):
    """rewrite_path: literal old->new path replace across text files, dry-run
    writes nothing, binary/vendored dirs pruned."""

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

    def _r(self, rel):
        with open(os.path.join(self.tmp, rel), encoding="utf-8") as f:
            return f.read()

    def test_rewrites_across_md_and_code(self):
        self._w("README.md", "docs live at docs/notes.md today\n")
        self._w("app.py", "# see docs/notes.md for details\n")
        touched = okf.rewrite_path(self.tmp, "docs/notes.md", "docs/demo-okf/notes.md")
        self.assertEqual(sorted(t[0] for t in touched), ["README.md", "app.py"])
        self.assertIn("docs/demo-okf/notes.md", self._r("README.md"))
        self.assertIn("docs/demo-okf/notes.md", self._r("app.py"))

    def test_dry_run_writes_nothing_but_reports(self):
        self._w("README.md", "docs/notes.md\n")
        before = self._r("README.md")
        touched = okf.rewrite_path(self.tmp, "docs/notes.md", "docs/x.md", dry_run=True)
        self.assertEqual(touched, [("README.md", 1)])
        self.assertEqual(self._r("README.md"), before)

    def test_prunes_git_and_node_modules(self):
        self._w(".git/config", "docs/notes.md\n")
        self._w("node_modules/x.js", "docs/notes.md\n")
        touched = okf.rewrite_path(self.tmp, "docs/notes.md", "docs/x.md")
        self.assertEqual(touched, [])

    def test_counts_multiple_occurrences(self):
        self._w("a.txt", "docs/notes.md and docs/notes.md again\n")
        touched = okf.rewrite_path(self.tmp, "docs/notes.md", "docs/x.md")
        self.assertEqual(touched, [("a.txt", 2)])

    def test_does_not_touch_substring_collision(self):
        self._w("a.txt", "my-docs/notes.md and docs/notes.md-old and docs/notes.md\n")
        touched = okf.rewrite_path(self.tmp, "docs/notes.md", "docs/x.md")
        self.assertEqual(touched, [("a.txt", 1)])            # only the standalone path
        self.assertIn("my-docs/notes.md", self._r("a.txt"))  # prefix-collision untouched
        self.assertIn("docs/notes.md-old", self._r("a.txt")) # suffix-collision untouched
        self.assertIn("docs/x.md\n", self._r("a.txt"))       # the real one rewritten


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
            okf.cmd_refs(os.path.join(self.tmp, "docs"), args)
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
            okf.cmd_refs(self.tmp, args)
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
        with self.assertRaises(SystemExit) as cm:
            okf.cmd_refs(os.path.join(self.tmp, "docs"), args)
        self.assertNotEqual(cm.exception.code, 0)


class RenameConcept(unittest.TestCase):
    """rename: link_expr / plan_rename reference-integrity core (no git needed)."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self._w("aaa/index.md", "# AAA\n\nIntro.\n\n" + M0 + "\n" + M1 + "\n")
        self._w("aaa/sub/index.md", "# Sub\n\nIntro.\n\n" + M0 + "\n" + M1 + "\n")
        self._w("bbb/index.md", "# BBB\n\nIntro.\n\n" + M0 + "\n" + M1 + "\n")
        self._w("aaa/a.md", "---\ntype: Concept\n---\n"
                            "Links [B](/aaa/b.md) and [C](/aaa/sub/c.md#h).")
        self._w("aaa/b.md", "---\ntype: Concept\n---\nBack to [A](/aaa/a.md).")
        self._w("aaa/sub/c.md", "---\ntype: Concept\n---\nSee [A](/aaa/a.md).")
        self._w("bbb/x.md", "---\ntype: Concept\n---\nCross to [A](/aaa/a.md).")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _w(self, rel, text):
        ap = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(text)

    def _ap(self, rel):
        return os.path.join(self.tmp, rel)

    def test_link_expr_same_bundle_is_catalogue_absolute(self):
        self.assertEqual(
            okf.link_expr(self.tmp, self._ap("aaa/b.md"), self._ap("aaa/a.md")),
            "/aaa/a.md")

    def test_link_expr_cross_bundle_is_catalogue_absolute(self):
        self.assertEqual(
            okf.link_expr(self.tmp, self._ap("aaa/b.md"), self._ap("bbb/a.md")),
            "/bbb/a.md")

    def test_link_expr_from_subdir_does_not_climb(self):
        """Renamed from ..._climbs_correctly: under the catalogue-absolute
        form nothing climbs. The expression no longer depends on where the
        SOURCE sits, which is the whole point — the same link text names the
        same file from anywhere in the catalogue."""
        self.assertEqual(
            okf.link_expr(self.tmp, self._ap("aaa/sub/c.md"), self._ap("bbb/a.md")),
            "/bbb/a.md")

    def test_split_link_suffix_keeps_anchor(self):
        self.assertEqual(okf._split_link_suffix("/sub/c.md#h"), ("/sub/c.md", "#h"))

    def test_plan_same_bundle_rewrites_inbound_only(self):
        plan = okf.plan_rename(self.tmp, self._ap("aaa/a.md"), self._ap("aaa/a2.md"))
        srcs = {s: (o, n) for s, o, n in plan["inbound"]}
        self.assertEqual(srcs["aaa/b.md"], ("/aaa/a.md", "/aaa/a2.md"))
        self.assertEqual(srcs["aaa/sub/c.md"], ("/aaa/a.md", "/aaa/a2.md"))
        self.assertEqual(srcs["bbb/x.md"], ("/aaa/a.md", "/aaa/a2.md"))
        self.assertEqual(plan["outbound"], [])          # bundle unchanged
        self.assertEqual(plan["bundles"], ["aaa"])

    def test_plan_cross_bundle_rewrites_inbound_and_outbound(self):
        plan = okf.plan_rename(self.tmp, self._ap("aaa/a.md"), self._ap("bbb/a.md"))
        srcs = {s: (o, n) for s, o, n in plan["inbound"]}
        self.assertEqual(srcs["aaa/b.md"], ("/aaa/a.md", "/bbb/a.md"))
        self.assertEqual(srcs["aaa/sub/c.md"], ("/aaa/a.md", "/bbb/a.md"))
        self.assertEqual(srcs["bbb/x.md"], ("/aaa/a.md", "/bbb/a.md"))
        # The moved file's OWN links need no reforging any more: a
        # catalogue-absolute link names the same file regardless of where the
        # source sits, so moving a.md from aaa/ to bbb/ leaves its outbound
        # links valid as written. Under the old bundle-relative form every one
        # of them had to be rewritten — that whole class of churn is gone.
        self.assertEqual(plan["outbound"], [])
        self.assertEqual(plan["bundles"], ["aaa", "bbb"])

    def test_apply_link_rewrites_targets_link_not_label(self):
        p = self._ap("aaa/b.md")
        self._w("aaa/b.md", "[/a.md](/a.md) and text /a.md bare")
        okf._apply_link_rewrites(p, [("/a.md", "/a2.md")])
        with open(p) as f:
            out = f.read()
        # only the ](...) target rewritten; label text + bare mention untouched
        self.assertEqual(out, "[/a.md](/a2.md) and text /a.md bare")


class CmdPrimeBundleListing(unittest.TestCase):
    """T-okf-cli-dwcq, revised by okf-cli-3hjr — the three listing depths.

    dwcq made the compact name+count line the DEFAULT, because prime was then
    carrying a 69-line CLAUDE.md on top of it and the total was unreadable. With
    the guide rewritten and sized, the catalogue TOC an agent actually navigates
    by (`index`: description + concepts + directories) is the default again, and
    dwcq's listing survives as `--compact`. --full is unchanged."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        ap = os.path.join(self.tmp, "b", "one.md")
        os.makedirs(os.path.join(self.tmp, "b", "sub"))
        with open(ap, "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: One\ntags:\n  - t\n---\n# One\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _prime(self, full=False, compact=False):
        import io, contextlib, types
        args = types.SimpleNamespace(full=full, compact=compact)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf.cmd_prime(self.tmp, args)
        return buf.getvalue()

    def test_default_runs_the_index_listing(self):
        out = self._prime()
        self.assertIn("description:", out)
        self.assertIn("concepts: 1", out)
        self.assertIn("directories:", out)
        self.assertNotIn("types:", out)      # that depth is --full

    def test_compact_keeps_the_dwcq_one_liner(self):
        out = self._prime(compact=True)
        self.assertIn("b (1 concepts)", out)
        self.assertNotIn("description:", out)
        self.assertNotIn("directories:", out)

    def test_full_adds_types_and_tags(self):
        out = self._prime(full=True)
        self.assertIn("description:", out)
        self.assertIn("types: Concept", out)
        self.assertIn("tags: t", out)


class CmdPrimeOnboardingGuide(unittest.TestCase):
    """okf-cli-3hjr — prime carries its own onboarding guide. Until now it
    printed <root>/CLAUDE.md; that file was removed from the catalogue on
    2026-07-28 (claude-ablation-1, D14/D15), which left prime emitting
    `(missing: CLAUDE.md)` plus a bundle list. The guide now lives in the CLI,
    and its command overview is generated from the same _sub() registry that
    builds the parser, so it cannot drift from the commands it describes."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        ap = os.path.join(self.tmp, "b", "one.md")
        os.makedirs(os.path.dirname(ap))
        with open(ap, "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: One\n---\n# One\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _prime(self, full=False, compact=False, check_semantic=False):
        import io, contextlib, types
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf.cmd_prime(self.tmp, types.SimpleNamespace(
                full=full, compact=compact, check_semantic=check_semantic))
        return buf.getvalue()

    def test_guide_renders_without_claude_md(self):
        """The regression the ablation exposed: no CLAUDE.md, no guide."""
        out = self._prime()
        self.assertNotIn("missing: CLAUDE.md", out)
        self.assertIn("OKF Knowledge Catalogue", out)

    def test_claude_md_is_not_read_at_all(self):
        """Not merely tolerated when absent — no longer a source. A catalogue
        that still carries one must not have it injected into every prime."""
        with open(os.path.join(self.tmp, "CLAUDE.md"), "w", encoding="utf-8") as f:
            f.write("# Guide\nSENTINEL-FROM-CLAUDE-MD\n")
        self.assertNotIn("SENTINEL-FROM-CLAUDE-MD", self._prime())

    def test_overview_covers_every_registered_command(self):
        """The anti-drift guard. A hand-written command list would pass today
        and rot on the next `_sub()` registration; this fails the moment a
        command exists that prime does not name."""
        out = self._prime()
        registered = set(okf_parser_support.subcommand_parsers(okf.build_parser()))
        missing = sorted(n for n in registered if n not in out)
        self.assertEqual(missing, [])

    def test_overview_is_generated_not_transcribed(self):
        """Counter-mutation to the test above: assert the rendering comes from
        the registry, by pinning a summary that only the registry holds."""
        out = self._prime()
        summary = okf.build_parser()
        parsers = okf_parser_support.subcommand_parsers(summary)
        self.assertIn(parsers["find"].description.split(":")[0], out)

    def test_retrieval_path_is_ordered_and_named(self):
        out = self._prime()
        for step in ("find", "index", "toc", "read"):
            self.assertIn(step, out)
        self.assertIn("progressive disclosure", out.lower())

    def test_write_path_names_the_skill_and_the_gate(self):
        out = self._prime()
        self.assertIn("ce-okf", out)
        self.assertIn("check", out)

    def test_state_reports_absent_index_and_open_tag_vocabulary(self):
        out = self._prime()
        self.assertIn("build-index", out)
        self.assertRegex(out, r"(?i)fts index:\s*absent")
        self.assertRegex(out, r"(?i)tag vocabulary:\s*open")

    def test_state_reports_present_index_and_closed_tag_vocabulary(self):
        okf_fts.build_fts_index(self.tmp)
        with open(os.path.join(self.tmp, "TAGS.md"), "w", encoding="utf-8") as f:
            f.write("| tag | description |\n| --- | --- |\n| `x` | y |\n")
        out = self._prime()
        self.assertRegex(out, r"(?i)fts index:\s*present")
        self.assertRegex(out, r"(?i)tag vocabulary:\s*closed")

    def _make_tagvec(self, paths):
        """A .tagvec carrying one CURRENT-content vector per given path.
        The key is computed with the production concept_cache_key() (via
        split_frontmatter/read_file/concept_text(), the same functions
        plan_concept_delta() uses per concept) so 'covered' here means
        exactly what it means to the real detector, not a stand-in key."""
        bt = okf_catalogue._load_build_tagvec()
        db = okf_semantic._tagvec_db_path(self.tmp)
        rows = []
        for p in paths:
            b, cid = p.split("/", 1)
            ap = os.path.join(self.tmp, b, cid + ".md")
            fm, body = okf_catalogue.split_frontmatter(okf_catalogue.read_file(ap))
            title = okf_catalogue._dequote(fm.get("title", "")) or cid
            text = bt.concept_text(title, body)
            key = bt.concept_cache_key(okf_semantic.SEMANTIC_MODEL, p, text)
            rows.append((key, p, okf_semantic.SEMANTIC_MODEL, 2, bt.pack_vec([1.0, 0.0])))
        bt.write_concept_rows(db, rows)

    def test_state_reports_absent_semantic_index(self):
        """Modus-B: the semantic arm degraded silently for 4.4 % of the live
        catalogue because nothing ever said how much of it was embedded. An
        onboarding agent has to learn that the same way it learns about .fts."""
        out = self._prime()
        self.assertRegex(out, r"(?i)semantic index:\s*absent")

    def test_state_reports_an_incomplete_semantic_index(self):
        """The failure mode that actually occurred: an index that is PRESENT
        and silently partial. Two concepts, one vector. --check-semantic runs
        the exact (content-hash) count; see the two gating tests below for the
        cheap default."""
        ap = os.path.join(self.tmp, "b", "two.md")
        with open(ap, "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: Two\n---\n# Two\n")
        self._make_tagvec(["b/one"])
        out = self._prime(check_semantic=True)
        self.assertRegex(out, r"(?i)semantic index:.*1 of 2")
        self.assertIn("build_tagvec", out)

    def test_state_reports_a_complete_semantic_index(self):
        """Counter-mutation: a covered catalogue must NOT be reported as
        partial, or the notice degenerates into noise nobody reads."""
        self._make_tagvec(["b/one"])
        out = self._prime(check_semantic=True)
        self.assertRegex(out, r"(?i)semantic index:\s*complete")
        self.assertNotIn("build_tagvec", out)

    def test_default_prime_skips_the_expensive_content_check(self):
        """B: the content-hash pass reads and hashes every concept body
        (~2.2s over 2590 concepts on the live catalogue) -- too slow for a
        call that runs on every session start. Bare `prime` must not run it;
        it reports presence only, honestly, rather than an unchecked count."""
        self._make_tagvec(["b/one"])
        out = self._prime()
        self.assertRegex(out, r"(?i)semantic index:\s*present")
        self.assertNotRegex(out, r"(?i)semantic index:\s*(complete|partial)")

    def test_check_semantic_flag_runs_the_exact_content_check(self):
        self._make_tagvec(["b/one"])
        out = self._prime(check_semantic=True)
        self.assertRegex(out, r"(?i)semantic index:\s*complete")

    def test_check_semantic_flag_is_documented(self):
        ap = okf.build_parser()
        parsers = okf_parser_support.subcommand_parsers(ap)
        actions = okf_parser_support.parser_actions(parsers["prime"])
        flag = next((a for a in actions if a.dest == "check_semantic"), None)
        self.assertIsNotNone(flag, "prime has no --check-semantic option")
        self.assertTrue((flag.help or "").strip())

    def test_guide_is_catalogue_agnostic(self):
        """The old CLAUDE.md hardcoded one operator's catalogue path into every
        example. The CLI ships to any catalogue; it speaks of --root."""
        out = self._prime()
        self.assertNotIn("Obsidian/Knowledge-Catalogue", out)
        self.assertIn("--root", out)

    def test_root_docs_are_pointed_at_only_when_present(self):
        self.assertNotIn("SPEC.md", self._prime())
        with open(os.path.join(self.tmp, "SPEC.md"), "w", encoding="utf-8") as f:
            f.write("# spec\n")
        self.assertIn("SPEC.md", self._prime())

    def test_bundle_toc_survives_the_guide(self):
        out = self._prime()
        self.assertIn("bundle: b", out)

    def test_find_help_is_inlined(self):
        """`find` is the entry point an agent reaches for first, and its filters
        and score scales are not guessable. prime carries its --help verbatim so
        the first search does not cost a second round trip."""
        out = self._prime()
        find_help = okf_parser_support.subcommand_parsers(okf.build_parser())["find"].format_help()
        self.assertIn(find_help.strip(), out)

    def test_find_help_is_rendered_not_paraphrased(self):
        """Counter-mutation: pin option strings that only argparse emits, so a
        hand-written summary of `find` cannot pass this pair of tests."""
        out = self._prime()
        for flag in ("--breakdown", "--expand-tags", "--scope"):
            self.assertIn(flag, out)
        self.assertIn("score lines:", out)

    def test_bundle_names_are_the_next_call_verbatim(self):
        """Point 4 of the 2026-08-05 brief: every name prime lists must be the
        exact argument of the next call, not a label the agent has to assemble.
        Asserted by resolving each listed name through the production resolver
        rather than by re-deriving the path here."""
        with open(os.path.join(self.tmp, "b", "index.md"), "w", encoding="utf-8") as f:
            f.write("# B\n")
        out = self._prime()
        self.assertIn("toc <bundle>", out)
        for b in okf_catalogue.list_bundles(self.tmp):
            self.assertIn("bundle: {}".format(b), out)
            self.assertTrue(os.path.isfile(okf_catalogue.resolve_concept(self.tmp, b)))


class CmdPrimeCompactGuide(unittest.TestCase):
    """`prime --compact` is what a session-start recipe pulls, and there the
    guide competes for context with the SSTD, the roadmap and the git log. The
    measurement that opened this (2026-08-05): prime was 13199 of 27391
    characters of `just -g start`. --compact drops what is one call away
    (`find --help`) or irrelevant before the first read (the tag-editing
    ceremony), and keeps what is not guessable: every command name, every find
    flag, the two score scales, the live catalogue state, the bundle list.

    The default and --full renderings are untouched; the guards for those live
    in CmdPrimeOnboardingGuide and must stay green alongside these."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        ap = os.path.join(self.tmp, "b", "one.md")
        os.makedirs(os.path.dirname(ap))
        with open(ap, "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: One\n---\n# One\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _prime(self, full=False, compact=False):
        import io, contextlib, types
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf.cmd_prime(self.tmp, types.SimpleNamespace(full=full, compact=compact))
        return buf.getvalue()

    def test_compact_is_shorter_than_the_default_guide(self):
        """Both renderings list one bundle here, so the difference is guide
        prose alone — the thing this change is about."""
        self.assertLess(len(self._prime(compact=True)), len(self._prime()))

    def test_compact_drops_the_verbatim_find_help(self):
        find_help = okf_parser_support.subcommand_parsers(okf.build_parser())["find"].format_help()
        self.assertNotIn(find_help.strip(), self._prime(compact=True))

    def test_compact_still_names_every_find_flag(self):
        """The anti-drift guard for the shortened find block: the flag list is
        rendered from the parser, not transcribed, so a flag registered
        tomorrow cannot go missing here. Derived from the production parser
        rather than a literal list, or this test would rot with the text."""
        out = self._prime(compact=True)
        parser = okf_parser_support.subcommand_parsers(okf.build_parser())["find"]
        flags = [o for a in parser._actions for o in a.option_strings
                 if o.startswith("--") and o != "--help"]
        self.assertTrue(flags)
        self.assertEqual(sorted(f for f in flags if f not in out), [])

    def test_compact_keeps_the_two_score_scales_apart(self):
        """`score: a/b` names a scale, not a confidence. An agent that reads
        a/100 and a/(6 * n) as one scale misreads every degraded run — this is
        the one fact from find's help that is not recoverable by trying."""
        out = self._prime(compact=True)
        self.assertIn("a/100", out)
        self.assertIn("6 * n", out)

    def test_compact_points_at_the_full_help(self):
        self.assertIn("find --help", self._prime(compact=True))

    def test_compact_names_every_registered_command(self):
        out = self._prime(compact=True)
        registered = set(okf_parser_support.subcommand_parsers(okf.build_parser()))
        self.assertEqual(sorted(n for n in registered if n not in out), [])

    def test_compact_command_directory_is_one_line_per_command(self):
        """Where the directory's characters went: wrapping at 96 columns put a
        21-space continuation indent under most descriptions. Nothing is
        dropped, the wrapping is — asserted by matching each command's whole
        registered description against its single line."""
        lines = self._prime(compact=True).splitlines()
        parsers = okf_parser_support.subcommand_parsers(okf.build_parser())
        for name, parser in parsers.items():
            head = "    {:<16} ".format(name)
            own = [l for l in lines if l.startswith(head)]
            self.assertEqual(len(own), 1, name)
            self.assertEqual(own[0][len(head):], parser.description)

    def test_compact_keeps_the_write_gate(self):
        out = self._prime(compact=True)
        self.assertIn("ce-okf", out)
        self.assertIn("check", out)

    def test_compact_keeps_the_live_state_and_the_bundles(self):
        out = self._prime(compact=True)
        self.assertRegex(out, r"(?i)fts index:")
        self.assertRegex(out, r"(?i)tag vocabulary:")
        for b in okf_catalogue.list_bundles(self.tmp):
            self.assertIn("{} (1 concepts)".format(b), out)

    def test_compact_keeps_the_retrieval_ladder(self):
        out = self._prime(compact=True)
        for step in ("find", "index", "toc", "read", "refs"):
            self.assertIn(step, out)
        self.assertIn("progressive disclosure", out.lower())

    def test_default_keeps_the_root_contract(self):
        """Counter-mutation to the intro trim: --compact may assume its caller
        passes --root (a recipe or the MCP server always does), the default
        rendering may not — it is what a human reads first."""
        self.assertIn("--root", self._prime())


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
            okf.cmd_list(self.tmp, args)
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
        old_argv = _sys.argv
        _sys.argv = ["okf-cli.py", "find", "test"]
        try:
            with self.assertRaises(SystemExit) as ctx:
                okf.main()
        finally:
            _sys.argv = old_argv
        self.assertIn("--root", str(ctx.exception))

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
            okf.cmd_list(self.tmp, args)
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
        parsers = okf_parser_support.subcommand_parsers(okf.build_parser())
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
        args = types.SimpleNamespace(path=path)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf.cmd_read(self.tmp, args)
        return buf.getvalue()

    def test_list_archive_hit_path_resolves_via_read(self):
        import io, contextlib, types
        args = types.SimpleNamespace(type="Concept", tag=None, scope=None,
                                     json=False, include_archive=True)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf.cmd_list(self.tmp, args)
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


class CmdBuildIndexIfStale(unittest.TestCase):
    """okf-cli-iaxj — `build-index --if-stale` skips the rebuild when the
    existing index is current, so the Stop/SessionStart hook can call it on
    every trigger without re-reading every concept body each time (D02)."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "b"))
        with open(os.path.join(self.root, "b", "one.md"), "w",
                  encoding="utf-8") as f:
            f.write("---\ntype: Runbook\ntitle: One\ndescription: d\n"
                    "tags: []\n---\nbody one.\n")
        with open(os.path.join(self.root, "b", "index.md"), "w",
                  encoding="utf-8") as f:
            f.write("# B\n")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _run(self, if_stale):
        import io
        import contextlib
        import types
        args = types.SimpleNamespace(if_stale=if_stale)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf_fts.cmd_build_index(self.root, args)
        return buf.getvalue()

    def test_without_flag_always_rebuilds_even_when_current(self):
        """Regression guard for the D02 promise: omitting --if-stale must
        stay byte-identical to today — an unconditional full rebuild, never
        a skip, no matter how fresh the index already is."""
        okf_fts.build_fts_index(self.root)
        db_path = okf_fts._fts_db_path(self.root)
        before = os.path.getmtime(db_path)
        out = self._run(if_stale=False)
        after = os.path.getmtime(db_path)
        self.assertIn("indexed 1 concept(s)", out)
        self.assertGreaterEqual(after, before)

    def test_if_stale_skips_rebuild_when_index_is_current(self):
        okf_fts.build_fts_index(self.root)
        db_path = okf_fts._fts_db_path(self.root)
        # os.replace() on rebuild always produces a fresh inode/mtime, so an
        # unchanged mtime is proof the rebuild branch never ran.
        before = os.path.getmtime(db_path)
        out = self._run(if_stale=True)
        after = os.path.getmtime(db_path)
        self.assertEqual(before, after)
        self.assertIn("index is current", out)
        self.assertIn(db_path, out)

    def test_if_stale_rebuilds_when_a_concept_changed(self):
        okf_fts.build_fts_index(self.root)
        with open(os.path.join(self.root, "b", "two.md"), "w",
                  encoding="utf-8") as f:
            f.write("---\ntype: Konzept\ntitle: Two\ndescription: d\n"
                    "tags: []\n---\nbody two.\n")
        out = self._run(if_stale=True)
        self.assertIn("indexed 2 concept(s)", out)
        conn = sqlite3.connect(okf_fts._fts_db_path(self.root))
        try:
            total = conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(total, 2)

    def test_if_stale_rebuilds_when_index_is_absent(self):
        # No build_fts_index() call at all — the .fts dir does not exist yet.
        out = self._run(if_stale=True)
        self.assertIn("indexed 1 concept(s)", out)
        self.assertTrue(os.path.isfile(okf_fts._fts_db_path(self.root)))

    def test_help_documents_the_flag(self):
        ap = okf.build_parser()
        parsers = okf_parser_support.subcommand_parsers(ap)
        actions = okf_parser_support.parser_actions(parsers["build-index"])
        flag = next((a for a in actions if a.dest == "if_stale"), None)
        self.assertIsNotNone(flag, "build-index has no --if-stale option")
        self.assertTrue((flag.help or "").strip())


class CmdBuildSemanticIndex(unittest.TestCase):
    """OKFT-wsne — `build-semantic-index [--if-stale]`: the trigger the
    concept_emb producer lacked (SC-001/EARS "brought up to date without a
    human remembering to do it"). Shape mirrors CmdBuildIndexIfStale (D02:
    skip only when the artefact both exists and is current), but the probe
    is semantic_coverage()'s PATH-SET comparison, not _fts_index_stale()'s
    stat check -- concept_emb carries orphan rows for deleted concepts
    (OKFT-3520) that a row-count check would let mask a real gap. No test
    here makes a network call: embed_voyage is replaced on the cached
    build_tagvec module (same pattern AutoEmbedOnRegister uses for
    embed_bge_m3), and VOYAGE_API_KEY is popped from the environment in
    setUp so a missing/real key on the host machine can never leak in."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self._w("b/one.md", "One", "one body")
        self._w("b/two.md", "Two", "two body")
        self.bt = okf_catalogue._load_build_tagvec()
        self._orig_voyage = self.bt.embed_voyage
        self._orig_resilient = self.bt.embed_resilient
        self._orig_key = os.environ.pop("VOYAGE_API_KEY", None)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        self.bt.embed_voyage = self._orig_voyage
        self.bt.embed_resilient = self._orig_resilient
        os.environ.pop("VOYAGE_API_KEY", None)
        if self._orig_key is not None:
            os.environ["VOYAGE_API_KEY"] = self._orig_key

    def _w(self, rel, title, body):
        ap = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write("---\ntype: Runbook\ntitle: {}\ndescription: d\n"
                     "tags: []\n---\n{}\n".format(title, body))

    def _fake_embed(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def _run(self, if_stale=False, with_key=True):
        import io
        import contextlib
        import types
        if with_key:
            os.environ["VOYAGE_API_KEY"] = "test-key"
        else:
            os.environ.pop("VOYAGE_API_KEY", None)
        args = types.SimpleNamespace(if_stale=if_stale)
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            okf_semantic.cmd_build_semantic_index(self.root, args)
        return out_buf.getvalue(), err_buf.getvalue()

    def test_without_flag_embeds_the_full_delta(self):
        self.bt.embed_voyage = self._fake_embed
        out, err = self._run(if_stale=False)
        self.assertIn("embedded 2 concept(s)", out)
        self.assertIn(okf_semantic._tagvec_db_path(self.root), out)
        self.assertEqual(err, "")

    def test_sc002_disk_paths_match_concept_emb_rows_after_run(self):
        """SC-002 verbatim: compare on-disk concept paths against
        concept_emb rows after the trigger runs, with the embedding backend
        replaced -- no network."""
        self.bt.embed_voyage = self._fake_embed
        self._run(if_stale=False)
        conn = sqlite3.connect(okf_semantic._tagvec_db_path(self.root))
        try:
            embedded = {r[0] for r in conn.execute(
                "SELECT path FROM concept_emb WHERE model = ?",
                (okf_semantic.SEMANTIC_MODEL,))}
        finally:
            conn.close()
        disk_paths = {p for b in okf_catalogue.list_bundles(self.root)
                      for p, _ap in
                      (("{}/{}".format(b, cid), ap)
                       for cid, ap in okf_catalogue.iter_concepts(os.path.join(self.root, b)))}
        self.assertEqual(embedded, disk_paths)

    def test_if_stale_skips_when_coverage_is_complete(self):
        self.bt.embed_voyage = self._fake_embed
        self._run(if_stale=False)
        calls = []
        self.bt.embed_voyage = lambda texts: calls.append(texts) or self._fake_embed(texts)
        out, err = self._run(if_stale=True)
        self.assertIn("skipping", out)
        self.assertEqual(calls, [])

    def test_if_stale_embeds_when_partial(self):
        self.bt.embed_voyage = self._fake_embed
        self._run(if_stale=False)
        self._w("b/three.md", "Three", "three body")
        out, err = self._run(if_stale=True)
        self.assertIn("embedded 1 concept(s)", out)

    def test_if_stale_embeds_when_a_body_changed_without_reembedding(self):
        """The regression this fix closes (OKFT-9wk6): semantic_coverage()
        used to compare PATH sets only, so a changed concept body left the
        OLD key's row sitting in concept_emb and --if-stale reported the
        index complete -- skipping the rebuild that the changed content
        actually needed. The probe now shares plan_concept_delta()'s
        content-hash detection, so an edited body -- same path, same row
        count, different key -- must trigger exactly one re-embed."""
        self.bt.embed_voyage = self._fake_embed
        self._run(if_stale=False)
        self._w("b/one.md", "One", "one body CHANGED")
        calls = []
        self.bt.embed_voyage = lambda texts: calls.append(texts) or self._fake_embed(texts)
        out, err = self._run(if_stale=True)
        self.assertIn("embedded 1 concept(s)", out)
        self.assertTrue(calls, "changed body must reach embed_voyage, not be skipped")

    def test_if_stale_embeds_when_index_is_absent(self):
        self.bt.embed_voyage = self._fake_embed
        out, err = self._run(if_stale=True)
        self.assertIn("embedded 2 concept(s)", out)

    def test_missing_api_key_degrades_without_raising(self):
        out, err = self._run(if_stale=False, with_key=False)
        self.assertIn("note:", err)
        self.assertIn("VOYAGE_API_KEY", err)
        db = okf_semantic._tagvec_db_path(self.root)
        self.assertFalse(os.path.isfile(db))

    def test_network_failure_degrades_without_raising(self):
        def _boom(texts):
            raise RuntimeError("connection refused")
        self.bt.embed_voyage = _boom
        real_resilient = self.bt.embed_resilient
        self.bt.embed_resilient = (
            lambda fn, texts, label, sleep=None:
            real_resilient(fn, texts, label, sleep=lambda _s: None))
        out, err = self._run(if_stale=False)
        self.assertIn("note:", err)

    def test_help_documents_the_flag(self):
        ap = okf.build_parser()
        parsers = okf_parser_support.subcommand_parsers(ap)
        actions = okf_parser_support.parser_actions(parsers["build-semantic-index"])
        flag = next((a for a in actions if a.dest == "if_stale"), None)
        self.assertIsNotNone(flag, "build-semantic-index has no --if-stale option")
        self.assertTrue((flag.help or "").strip())

    def test_dispatch_table_carries_the_command(self):
        self.assertIn("build-semantic-index", okf.COMMAND_DISPATCH)
        self.assertIs(okf.COMMAND_DISPATCH["build-semantic-index"],
                       okf_semantic.cmd_build_semantic_index)


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
            okf.cmd_list(self.tmp, args)
        out = buf.getvalue()
        self.assertNotIn("_intake", out)
        self.assertIn("sub/regular", out)

    def test_find_degraded_excludes_staging(self):
        out = run_find(self.tmp, "zqxstagingmarker")
        self.assertNotIn("_intake", out)


class ParserExtraction(unittest.TestCase):
    """build_parser() renders the surface without executing a command."""

    def test_every_registered_command_is_dispatchable(self):
        parsers = okf_parser_support.subcommand_parsers(okf.build_parser())
        self.assertEqual(set(parsers), set(okf.COMMAND_DISPATCH))

    def test_parser_actions_skips_the_auto_help_action(self):
        parsers = okf_parser_support.subcommand_parsers(okf.build_parser())
        dests = [a.dest for a in okf_parser_support.parser_actions(parsers["read"])]
        self.assertNotIn("help", dests)
        self.assertIn("path", dests)


class CommandDirectory(unittest.TestCase):
    """Every command carries a summary, at exactly one authored place."""

    def test_find_index_read_are_no_longer_invisible(self):
        parsers = okf_parser_support.subcommand_parsers(okf.build_parser())
        for name in ("find", "index", "read"):
            self.assertTrue((parsers[name].description or "").strip(),
                            "{} has no summary".format(name))

    def test_the_summary_reaches_both_help_levels(self):
        ap = okf.build_parser()
        parsers = okf_parser_support.subcommand_parsers(ap)
        summary = parsers["read"].description
        self.assertIn(summary, parsers["read"].format_help())
        self.assertIn("find", ap.format_help())

    def test_every_command_declares_a_group(self):
        parsers = okf_parser_support.subcommand_parsers(okf.build_parser())
        self.assertEqual(set(okf_parser_support.COMMAND_GROUPS), set(parsers))

    def test_find_help_explains_both_score_scales(self):
        parsers = okf_parser_support.subcommand_parsers(okf.build_parser())
        text = parsers["find"].format_help()
        self.assertIn("100", text)
        self.assertIn("6 * number of terms", text)
        self.assertIn("provenance", text)


class FindOptionHelp(unittest.TestCase):
    """find's options describe themselves, and truthfully."""

    def _find_action(self, dest):
        parsers = okf_parser_support.subcommand_parsers(okf.build_parser())
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
        names = list(okf_parser_support.subcommand_parsers(okf.build_parser()))
        self.assertEqual(names, sorted(names))

    def test_top_level_help_points_at_per_command_help(self):
        self.assertIn("<command> --help", okf.build_parser().format_help())


class GroupedOverview(unittest.TestCase):

    def test_overview_names_every_group_that_has_commands(self):
        text = okf.build_parser().format_help()
        self.assertIn("commands by purpose:", text)
        for group in okf_parser_support._GROUP_ORDER:
            self.assertIn("  {}:".format(group), text)

    def test_overview_covers_every_command(self):
        text = okf.build_parser().format_help()
        overview = text.split("commands by purpose:", 1)[1]
        for name in okf_parser_support.COMMAND_GROUPS:
            self.assertRegex(overview, r"\n\s+{}\s".format(re.escape(name)))

    def test_module_docstring_no_longer_lists_commands_by_hand(self):
        self.assertNotIn("okf-cli.py find", okf.__doc__)
        self.assertNotIn("okf-cli.py merge-tags", okf.__doc__)


class CommandHelpConformance(unittest.TestCase):
    """An undocumented command or option is unmergeable, not merely
    noticeable (D02). This is the gate the 2026-07-26 PO review asked for."""

    def setUp(self):
        self.ap = okf.build_parser()
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
        self.assertEqual(set(okf.COMMAND_DISPATCH), set(self.parsers))

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

    def _complete(self, words):
        import subprocess
        import sys
        line = "okf-cli --root ~/cat " + words
        out = os.path.join(self.tmp, "out")
        env = dict(os.environ, HOME=self.tmp, COMP_LINE=line, COMP_POINT=str(len(line)),
                   _ARGCOMPLETE="1", _ARGCOMPLETE_SHELL="zsh",
                   _ARGCOMPLETE_SUPPRESS_SPACE="1", _ARGCOMPLETE_STDOUT_FILENAME=out)
        subprocess.run([sys.executable, os.path.join(_HERE, "okf-cli.py")],
                       env=env, cwd=self.tmp, capture_output=True)
        if not os.path.exists(out):
            return []
        with open(out, encoding="utf-8") as f:
            raw = f.read()
        if not raw:
            return []
        return [tuple(e.split(":", 1)) if ":" in e else (e, "") for e in raw.split("\x0b")]

    def _values(self, words):
        """Candidates minus option strings: argcomplete offers `-h/--help`
        next to positional values."""
        return [v for v, _ in self._complete(words) if not v.startswith("-")]

    def test_type_values_come_from_the_root_on_the_line(self):
        self.assertEqual([c for c in self._complete("find q --type ") if not c[0].startswith("-")],
                         [("Concept", "a"), ("Decision", "b")])

    def test_tag_values_most_used_first_with_counts(self):
        self.assertEqual(self._complete("find q --tag "),
                         [("x", "concepts: 2"), ("y", "concepts: 1")])

    def test_scope_values_are_bundles_and_concept_dirs(self):
        self.assertEqual(self._values("list --scope "), ["b1", "b1/sub"])

    def test_concept_refs_and_archive_on_restore(self):
        self.assertEqual(self._values("read "), ["b1/alpha", "b1/sub/beta"])
        self.assertEqual(self._values("archive --restore "), ["_archive/b1/old"])

    def test_block_ids_come_from_the_concept_on_the_line(self):
        self.assertEqual(self._values("sync-export b1/sub/beta "), ["blk-1"])

    def test_free_text_offers_options_not_cwd_files(self):
        values = [v for v, _ in self._complete("find ")]
        self.assertIn("--type", values)
        self.assertNotIn("stray.txt", values)


class MoveSimulationArchivePrecedence(WikilinkFixtureMixin, unittest.TestCase):
    """R-07 (docs/okf-archive-lifecycle/SPEC.md) — _index_after_move applies
    the same active-before-archived rule build_concept_basename_index applies
    (R-06), for the basename slot the move lands in. Without it, a dry run
    can report an ambiguity that never materialises (AC1/AC2/SC-01)."""

    def test_precedence_applied_to_the_slot_the_move_lands_in(self):
        """Archiving a/old.md while d/old.md stays active must leave "old"
        resolving to the sole surviving active candidate, not to both the
        freshly archived path and the active one."""
        self._w("a/old.md", "---\ntype: Concept\n---\n# Old\n")
        self._w("d/old.md", "---\ntype: Concept\n---\n# D Old\n")
        index = self._index()
        after = okf._index_after_move(index, "/a/old.md", "/_archive/a/old.md")
        self.assertEqual(after["old"], ["/d/old.md"])


class RenameWikilinks(WikilinkFixtureMixin, unittest.TestCase):
    """REQ-10..REQ-12 — rename keeps inbound wikilinks intact in both regions,
    discloses them in the dry-run, and refuses to guess on ambiguity."""

    def setUp(self):
        super().setUp()
        self._w("a/index.md", "# A\n\nIntro.\n\n" + M0 + "\n" + M1 + "\n")
        self._w("a/old.md", "---\ntype: Concept\n---\n# Old\n")

    def _rename(self, old, new, apply=False):
        import contextlib
        import io
        import types
        args = types.SimpleNamespace(old=old, new=new, apply=apply, force=False)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf.cmd_rename(self.tmp, args)
        return buf.getvalue()

    def _rename_fails(self, old, new, message, apply=False):
        """Assert a refusal AND which one. `assertRaises(SystemExit)` alone is
        not an assertion about the guard under test: cmd_rename has ten of them
        plus the turns-ambiguous refusal, so dropping the guard a test names
        still produced an exit and the test still passed. The message is the
        only thing that distinguishes them."""
        import contextlib
        import io
        import types
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                okf.cmd_rename(self.tmp, types.SimpleNamespace(
                    old=old, new=new, apply=apply, force=False))
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn(message, err.getvalue())
        return err.getvalue()

    def test_inbound_plain_is_rewritten(self):
        self._w("a/src.md", "---\ntype: Concept\n---\nSee [[old]].\n")
        self._rename("a/old.md", "a/new.md", apply=True)
        self.assertIn("[[new]]", self._r("a/src.md"))
        self.assertNotIn("[[old]]", self._r("a/src.md"))

    def test_alias_and_suffix_survive(self):
        self._w("a/src.md", "---\ntype: Concept\n---\n"
                            "[[old|Label]] [[old#Heading]] [[old#^blk]] ![[old]]\n")
        self._rename("a/old.md", "a/new.md", apply=True)
        body = self._r("a/src.md")
        for expected in ("[[new|Label]]", "[[new#Heading]]", "[[new#^blk]]", "![[new]]"):
            self.assertIn(expected, body)

    def test_frontmatter_property_is_rewritten_and_stays_parseable(self):
        self._w("a/src.md", '---\ntype: Concept\nrelated:\n  - "[[old]]"\n---\n# Src\n')
        before = set(okf_catalogue.split_frontmatter(self._r("a/src.md"))[0])
        self._rename("a/old.md", "a/new.md", apply=True)
        after_text = self._r("a/src.md")
        self.assertIn('- "[[new]]"', after_text)
        self.assertEqual(set(okf_catalogue.split_frontmatter(after_text)[0]), before)

    def test_directory_only_move_rewrites_nothing(self):
        """A wikilink carries no path, so only a basename change can break one."""
        self._w("a/x.md", "---\ntype: Concept\n---\n# X\n")
        self._w("a/src.md", "---\ntype: Concept\n---\nSee [[x]].\n")
        before = self._r("a/src.md")
        self._rename("a/x.md", "a/sub/x.md", apply=True)
        self.assertEqual(self._r("a/src.md"), before)

    def test_code_spans_are_not_rewritten(self):
        self._w("a/src.md", "---\ntype: Concept\n---\n"
                            "```\n[[old]]\n```\n\nand `[[old]]` inline.\n")
        before = self._r("a/src.md")
        self._rename("a/old.md", "a/new.md", apply=True)
        self.assertEqual(self._r("a/src.md"), before)

    def test_dry_run_lists_and_writes_nothing(self):
        self._w("a/src.md", '---\ntype: Concept\nrelated:\n  - "[[old]]"\n---\n'
                            "Body [[old]] too.\n")
        before = self._r("a/src.md")
        out = self._rename("a/old.md", "a/new.md")
        wl_lines = [l for l in out.splitlines() if l.strip().startswith("wikilink ")]
        self.assertEqual(len(wl_lines), 2)
        self.assertTrue(any("[frontmatter]" in l for l in wl_lines), wl_lines)
        self.assertTrue(any("[body]" in l for l in wl_lines), wl_lines)
        self.assertEqual(self._r("a/src.md"), before)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "a/old.md")))

    def test_summary_counts_wikilinks_separately(self):
        self._w("a/src.md", "---\ntype: Concept\n---\nSee [[old]] and [Old](/a/old.md).\n")
        out = self._rename("a/old.md", "a/new.md")
        self.assertRegex(out, r"rename \(dry-run\): 1 inbound, 0 outbound link\(s\), "
                              r"1 wikilink\(s\) \(0 skipped-ambiguous\), ")

    def test_ambiguous_inbound_is_reported_not_rewritten(self):
        self._w("a/g.md", "---\ntype: Concept\n---\n# G\n")
        self._w("b/g.md", "---\ntype: Concept\n---\n# G\n")
        self._w("c/x.md", "---\ntype: Concept\n---\nSee [[g]].\n")
        before = self._r("c/x.md")
        dry = self._rename("a/g.md", "a/g2.md")
        self.assertIn("skipped-ambiguous", dry)
        self.assertIn("/a/g.md", dry)
        self.assertIn("/b/g.md", dry)
        applied = self._rename("a/g.md", "a/g2.md", apply=True)
        self.assertIn("skipped-ambiguous", applied)
        self.assertEqual(self._r("c/x.md"), before)

    def test_inbound_wikilink_in_staging_dir_is_rewritten(self):
        """C02 — the rename scan must not leave a stale reference behind in a
        `_`-prefixed staging directory, which the reporting surfaces skip.
        Root-level staging counts too: build_ref_matrix walks the root, so a
        per-bundle-only walk would honour the constraint for `a/_intake` and
        quietly break it for `_inbox`."""
        self._w("a/_intake/draft.md", "See [[old]].\n")
        self._w("_inbox/draft.md", "See [[old]].\n")
        self._rename("a/old.md", "a/new.md", apply=True)
        self.assertIn("[[new]]", self._r("a/_intake/draft.md"))
        self.assertIn("[[new]]", self._r("_inbox/draft.md"))

    def test_rename_reaches_every_file_its_markdown_half_reaches(self):
        """The wikilink pass must cover exactly what build_ref_matrix covers.
        Pruning `assets/` from it left this file with its markdown link updated
        and its wikilink dangling in the same line — a worse outcome than
        touching a file the reporting surfaces do not list."""
        self._w("a/assets/note.md", "Md [Old](/a/old.md) and wiki [[old]].\n")
        self._w("ROOTNOTE.md", "Root-level: [Old](/a/old.md) and [[old]].\n")
        self._rename("a/old.md", "a/new.md", apply=True)
        for rel in ("a/assets/note.md", "ROOTNOTE.md"):
            self.assertIn("[[new]]", self._r(rel), rel)
            self.assertIn("(/a/new.md)", self._r(rel), rel)

    def test_renaming_into_an_occupied_basename_is_refused(self):
        """S1 — the rename manufactured the exact ambiguity the design refuses
        to commit: `[[old]]` became `[[new]]` while a different `/b/new.md`
        already owned that name, leaving both addresses ambiguous and a
        bystander link collateral damage."""
        self._w("b/new.md", "---\ntype: Concept\n---\n# Other New\n")
        self._w("c/src.md", "---\ntype: Concept\n---\nDistinct: [[old]] and [[new]].\n")
        before = self._r("c/src.md")
        with self.assertRaises(SystemExit) as ctx:
            self._rename("a/old.md", "a/new.md", apply=True)
        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(self._r("c/src.md"), before)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "a/old.md")))

    def test_occupied_basename_is_disclosed_in_the_dry_run(self):
        self._w("b/new.md", "---\ntype: Concept\n---\n# Other New\n")
        self._w("c/src.md", "---\ntype: Concept\n---\nSee [[old]].\n")
        out = self._rename("a/old.md", "a/new.md")
        self.assertIn("wikilink-collision", out)
        self.assertIn("/b/new.md", out)

    def test_occupied_basename_proceeds_under_force(self):
        self._w("b/new.md", "---\ntype: Concept\n---\n# Other New\n")
        self._w("c/src.md", "---\ntype: Concept\n---\nSee [[old]].\n")
        import contextlib
        import io
        import types
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf.cmd_rename(self.tmp, types.SimpleNamespace(
                old="a/old.md", new="a/new.md", apply=True, force=True))
        self.assertIn("[[new]]", self._r("c/src.md"))
        self.assertIn("wikilink-collision", buf.getvalue())

    def test_path_form_inbound_keeps_its_prefix(self):
        self._w("c/x.md", "---\ntype: Concept\n---\nSee [[a/old]].\n")
        self._rename("a/old.md", "a/new.md", apply=True)
        self.assertIn("[[a/new]]", self._r("c/x.md"))

    def test_foreign_same_named_concept_is_not_rewritten(self):
        """`b/src.md`'s `[[old]]` resolves to `/b/old.md` via the bundle
        tie-break, so renaming `/a/old.md` must leave it alone."""
        self._w("b/old.md", "---\ntype: Concept\n---\n# B Old\n")
        self._w("b/src.md", "---\ntype: Concept\n---\nSee [[old]].\n")
        before = self._r("b/src.md")
        self._rename("a/old.md", "a/renamed.md", apply=True)
        self.assertEqual(self._r("b/src.md"), before)

    def test_self_reference_is_rewritten_at_the_new_location(self):
        """The file holding the link is the file being moved; writing to the
        path it just vacated raises FileNotFoundError."""
        self._w("a/old.md", "---\ntype: Concept\n---\nI am [[old]].\n")
        self._rename("a/old.md", "a/new.md", apply=True)
        self.assertIn("[[new]]", self._r("a/new.md"))

    def test_applier_masking_is_exercised_on_a_mixed_file(self):
        """A file with a real link AND a fenced one reaches
        _apply_wikilink_rewrites (the planner alone cannot protect it, because
        the rewrite list is not empty)."""
        self._w("a/src.md", "---\ntype: Concept\n---\n"
                            "real [[old]]\n\n```\nfenced [[old]]\n```\n\n"
                            "    indented [[old]]\n\n%% commented [[old]] %%\n")
        self._rename("a/old.md", "a/new.md", apply=True)
        after = self._r("a/src.md")
        self.assertIn("real [[new]]", after)
        self.assertIn("fenced [[old]]", after)
        self.assertIn("indented [[old]]", after)
        self.assertIn("commented [[old]] %%", after)

    def test_same_basename_move_plans_no_wikilink_work(self):
        """The short-circuit is the reason a directory-only move is free; an
        identity rewrite would pass the byte-comparison test either way."""
        self._w("a/src.md", "---\ntype: Concept\n---\nSee [[old]].\n")
        plan = okf.plan_rename(self.tmp,
                               os.path.join(self.tmp, "a/old.md"),
                               os.path.join(self.tmp, "a/sub/old.md"))
        self.assertEqual(plan["wikilinks"], [])
        self.assertEqual(plan["wikilink_collisions"], [])

    def test_case_variant_inbound_is_rewritten(self):
        """The planner filtered candidates case-sensitively while the resolver
        matched case-insensitively, so every case-variant inbound link was
        dropped from the plan and orphaned by the move that reported success."""
        self._w("a/src.md", "---\ntype: Concept\n---\nSee [[OLD]] and [[old]].\n")
        out = self._rename("a/old.md", "a/new.md", apply=True)
        # Both are rewritten, and both land on the file's actual spelling —
        # the author's casing was never the filename's to begin with.
        self.assertEqual(self._r("a/src.md"),
                         "---\ntype: Concept\n---\nSee [[new]] and [[new]].\n")
        self.assertIn("rewrote 2 wikilink(s)", out)

    def test_case_variant_ambiguity_is_disclosed(self):
        self._w("a/g.md", "---\ntype: Concept\n---\n# G\n")
        self._w("b/g.md", "---\ntype: Concept\n---\n# G\n")
        self._w("c/x.md", "---\ntype: Concept\n---\nSee [[G]].\n")
        self.assertIn("skipped-ambiguous", self._rename("a/g.md", "a/g2.md"))

    def test_collision_counts_links_already_pointing_at_the_other_concept(self):
        """A bystander `[[new]]` loses its unique target without this rename
        touching a byte of it, so an empty rewrite list must not wave the move
        through."""
        self._w("b/new.md", "---\ntype: Concept\n---\n# Other New\n")
        self._w("c/ref.md", "---\ntype: Concept\n---\nOnly [[new]] here.\n")
        with self.assertRaises(SystemExit) as ctx:
            self._rename("a/old.md", "a/new.md", apply=True)
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("turns-ambiguous", self._rename("a/old.md", "a/new.md"))

    def test_nested_masked_spans_survive_byte_identical(self):
        """A stash-and-restore mask lost content whenever one masked span held
        another's placeholder: `re.sub` does not rescan its replacement, so the
        inner token reached disk verbatim and its text was gone."""
        cases = {
            "a/c1.md": "Live [[old]].\n\n<!-- note: use `foo --bar` here -->\n",
            "a/c2.md": "Live [[old]].\n\n%% todo: rename `old` soon %%\n",
            "a/c3.md": "Live [[old]].\n\n<!--\n```\ncode [[old]]\n```\n-->\n",
            "a/c4.md": "Live [[old]].\n\nintro\n\n    run `make build` then go\n",
            "a/c5.md": "Live [[old]].\n\nintro\n\n\tdef f(): return `x`",
        }
        for rel, body in cases.items():
            self._w(rel, "---\ntype: Concept\n---\n" + body)
        self._rename("a/old.md", "a/new.md", apply=True)
        for rel, body in cases.items():
            after = self._r(rel)
            self.assertNotIn("\x00", after, rel)
            self.assertEqual(after, ("---\ntype: Concept\n---\n" + body)
                             .replace("Live [[old]]", "Live [[new]]"), rel)

    def test_pre_existing_nul_is_preserved(self):
        """The mask blanks to NUL, so a file already containing one used to have
        it expanded into a stashed token's content on rewrite. Splicing by
        offset against the original text removes that class entirely."""
        self._w("a/src.md", "---\ntype: Concept\n---\nLive [[old]] and \x00 raw.\n")
        before = self._r("a/src.md")
        self._rename("a/old.md", "a/new.md", apply=True)
        self.assertEqual(self._r("a/src.md"), before.replace("[[old]]", "[[new]]"))

    def test_symlinked_bundle_inbound_is_rewritten(self):
        """os.walk does not descend into a symlinked subdirectory, so the root
        walk alone cannot see a mounted bundle's files (C07, ASM-05)."""
        import tempfile
        ext = tempfile.mkdtemp()
        try:
            with open(os.path.join(ext, "src.md"), "w", encoding="utf-8") as f:
                f.write("---\ntype: Concept\n---\nSee [[old]].\n")
            os.symlink(ext, os.path.join(self.tmp, "mounted"))
            self._rename("a/old.md", "a/new.md", apply=True)
            with open(os.path.join(ext, "src.md"), encoding="utf-8") as f:
                self.assertIn("[[new]]", f.read())
        finally:
            import shutil
            shutil.rmtree(ext, ignore_errors=True)

    def test_cross_bundle_move_repoints_a_path_form_link(self):
        """Carrying the old prefix over unchanged turned `[[a/old]]` into
        `[[a/new]]` after a move to bundle `b` — an address resolving to
        nothing, reported as a successful rewrite."""
        self._w("b/index.md", "# B\n\nIntro.\n")
        self._w("c/x.md", "---\ntype: Concept\n---\nSee [[a/old]].\n")
        self._rename("a/old.md", "b/new.md", apply=True)
        self.assertIn("[[b/new]]", self._r("c/x.md"))

    def test_directory_move_repoints_a_path_form_link(self):
        """C03 as written — "only a basename change can invalidate a wikilink" —
        is false for the path form: a pure directory move breaks it."""
        self._w("a/x.md", "---\ntype: Concept\n---\n# X\n")
        self._w("c/plain.md", "---\ntype: Concept\n---\nSee [[x]].\n")
        self._w("c/path.md", "---\ntype: Concept\n---\nSee [[a/x]].\n")
        self._rename("a/x.md", "a/sub/x.md", apply=True)
        self.assertIn("[[x]]", self._r("c/plain.md"))       # plain form unaffected
        self.assertIn("[[sub/x]]", self._r("c/path.md"))

    def test_md_suffix_is_preserved_by_the_rewrite(self):
        self._w("a/src.md", "---\ntype: Concept\n---\n[[old.md]] and [[old.md|A]]\n")
        self._rename("a/old.md", "a/new.md", apply=True)
        after = self._r("a/src.md")
        self.assertIn("[[new.md]]", after)
        self.assertIn("[[new.md|A]]", after)

    def test_case_only_rename_still_rewrites(self):
        """old_key == new_key on a case-only rename. Testing the bystander
        branch first classified every genuine inbound link as a bystander and
        dropped the whole wikilink pass."""
        self._w("a/Foo.md", "---\ntype: Concept\n---\n# Foo\n")
        self._w("a/src.md", "---\ntype: Concept\n---\nSee [[Foo]] and [F](/a/Foo.md).\n")
        self._rename("a/Foo.md", "a/foo.md", apply=True)
        after = self._r("a/src.md")
        self.assertIn("[[foo]]", after)
        self.assertIn("(/a/foo.md)", after)

    def test_uppercase_source_basename_is_matched(self):
        self._w("a/Old2.md", "---\ntype: Concept\n---\n# O\n")
        self._w("a/src.md", "---\ntype: Concept\n---\nSee [[old2]].\n")
        self._rename("a/Old2.md", "a/fresh.md", apply=True)
        self.assertIn("[[fresh]]", self._r("a/src.md"))

    @needs_case_insensitive_fs
    def test_differently_cased_source_path_still_matches(self):
        """On a case-insensitive filesystem `A/old.md` reaches `a/old.md`, so
        the path the caller typed and the path in the index differ in case. A
        case-sensitive comparison of the two rewrote nothing and reported
        success — the silent-orphan path again, one layer down."""
        self._w("a/src.md", "---\ntype: Concept\n---\nSee [[old]].\n")
        self._rename("A/old.md", "A/new.md", apply=True)
        self.assertIn("[[new]]", self._r("a/src.md"))

    @needs_case_insensitive_fs
    def test_differently_cased_source_path_still_places_a_self_reference(self):
        """D14 — the source has to be respelled the way the filesystem stores it
        before `old_rel` is derived, because cmd_rename compares that string
        against the scan's own spelling to decide WHERE to write a
        self-reference. Without the normalisation the two never match and the
        rewrite is aimed at the path the file has just vacated."""
        self._w("a/old.md", "---\ntype: Concept\n---\nSelf [[old]].\n")
        self._w("a/src.md", "---\ntype: Concept\n---\nSee [[old]].\n")
        self._rename("A/old.md", "A/new.md", apply=True)
        self.assertIn("[[new]]", self._r("a/new.md"))
        self.assertIn("[[new]]", self._r("a/src.md"))

    def test_ambiguity_is_seen_through_a_case_variant_candidate(self):
        """D06 — the resolver is case-insensitive, so the candidate list holds
        the filesystem's spelling while the caller's path may differ. Comparing
        the two exactly dropped a case-variant candidate out of the
        skipped-ambiguous branch, and the occurrence fell through unreported.

        Driven at plan level on purpose: cmd_rename canonicalises the source
        first, so the two spellings can only diverge below that."""
        self._w("a/G.md", "---\ntype: Concept\n---\n# G\n")
        self._w("b/g.md", "---\ntype: Concept\n---\n# G\n")
        self._w("c/x.md", "---\ntype: Concept\n---\nSee [[g]].\n")
        recs, _ = okf.plan_wikilink_rewrites(
            self.tmp, os.path.join(self.tmp, "a/g.md"),
            os.path.join(self.tmp, "a/g2.md"))
        self.assertEqual([(r["source"], r["status"]) for r in recs],
                         [("c/x.md", "skipped-ambiguous")])

    def test_basename_preserving_move_that_turns_a_link_ambiguous_is_refused(self):
        """The token does not change, so nothing is rewritten — but its meaning
        does. 81 basenames in the live catalogue exist in more than one bundle,
        so this is the shape a real move takes."""
        self._w("b/old.md", "---\ntype: Concept\n---\n# B Old\n")
        self._w("d/old.md", "---\ntype: Concept\n---\n# D Old\n")
        self._w("b/src.md", "---\ntype: Concept\n---\nsee [[old]].\n")
        self.assertEqual(self._status("b/src.md", "old"), ("resolved", ["/b/old.md"]))
        with self.assertRaises(SystemExit) as ctx:
            self._rename("b/old.md", "c/old.md", apply=True)
        self.assertEqual(ctx.exception.code, 2)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "b/old.md")))
        self.assertIn("turns-ambiguous", self._rename("b/old.md", "c/old.md"))

    # -- AC3/SC-03 (okf-cli-yixf): a rename-scan collision that is itself
    # archived must not defeat the active-before-archived precedence. -----
    def test_rename_into_a_basename_held_by_an_archived_namesake_stays_resolved(self):
        """iter_rename_scan_md walks _archive/ too — _prune_walk_dirs
        (cli/okf-cli.py:1872-1874) excludes only node_modules and dot-dirs,
        not `_`-prefixed staging/archive dirs — so an archived concept
        sharing the move's destination basename lands in
        plan_wikilink_rewrites' `collisions` set (cli/okf-cli.py:3826-3830)
        next to the move's own fresh active candidate.
        _index_after_move (cli/okf-cli.py:3892-3899) merges `collisions`
        with the new active link and re-applies precedence to that slot: a
        bystander already resolving to the archived concept must re-resolve
        to the moved-in active one, not degrade into ambiguous merely
        because both now share a basename."""
        self._w("_archive/z/target.md", "---\ntype: Concept\n---\n# Archived Target\n")
        self._w("b/x.md", "---\ntype: Concept\n---\nsee [[target]].\n")
        self.assertEqual(self._status("b/x.md", "target"),
                         ("resolved", ["/_archive/z/target.md"]))
        out = self._rename("a/old.md", "a/target.md")  # dry-run
        self.assertNotIn("turns-ambiguous", out)
        self._rename("a/old.md", "a/target.md", apply=True)
        self.assertEqual(self._status("b/x.md", "target"),
                         ("resolved", ["/a/target.md"]))

    def test_whitespace_destination_basename_is_refused(self):
        """The scanner strips the page part, the index does not strip filenames,
        so the rewritten link could never meet its target."""
        self._w("a/src.md", "---\ntype: Concept\n---\nSee [[old]].\n")
        self._rename_fails("a/old.md", "a/ sp .md",
                           "leading or trailing whitespace", apply=True)
        self.assertIn("[[old]]", self._r("a/src.md"))

    def test_control_character_destination_basename_is_refused(self):
        self._w("a/src.md", "---\ntype: Concept\n---\nSee [[old]].\n")
        self._rename_fails("a/old.md", "a/ne\nw.md",
                           "control character", apply=True)
        self.assertIn("[[old]]", self._r("a/src.md"))

    def test_non_md_destination_is_refused(self):
        """A non-markdown destination has no concept identity — nothing resolves
        to it, so every rewritten link would be dead on arrival."""
        self._w("a/x.md", "---\ntype: Concept\n---\n# X\n")
        self._rename_fails("a/x.md", "a/y.txt", "both paths must be .md")
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "a/x.md")))

    def test_destination_outside_the_catalogue_root_is_refused(self):
        """A destination outside the root escapes every scan, so the rewrite
        would point out of the catalogue. Dry-run deliberately: without the
        guard an --apply run moves the file out of the tree under test."""
        self._w("a/x.md", "---\ntype: Concept\n---\n# X\n")
        self._rename_fails("a/x.md", "../out.md", "under the catalogue root")

    def test_root_level_destination_is_refused(self):
        """A root-level file is not a concept and is not in the resolution
        index, so no wikilink can address it."""
        self._w("a/x.md", "---\ntype: Concept\n---\n# X\n")
        self._rename_fails("a/x.md", "top.md", "inside a bundle")

    def test_forbidden_char_destination_is_refused(self):
        """ASM-03 — a wikilink metacharacter in the filename makes the rewritten
        link unparseable."""
        self._w("a/x.md", "---\ntype: Concept\n---\n# X\n")
        self._rename_fails("a/x.md", "a/y#z.md", "forbidden char")

    @needs_case_insensitive_fs
    def test_differently_cased_markdown_link_is_rewritten_too(self):
        """A link may spell its target in a different case than the disk does;
        on this filesystem that link is live. The wikilink half followed it and
        the markdown half did not, leaving one dead beside the other."""
        self._w("a/src.md", "---\ntype: Concept\n---\n[x](/a/OLD.md) and [[OLD]].\n")
        self._rename("a/old.md", "a/renamed.md", apply=True)
        after = self._r("a/src.md")
        self.assertIn("(/a/renamed.md)", after)
        self.assertIn("[[renamed]]", after)

    def test_outbound_pass_masks_like_the_applier(self):
        """Planner and applier must agree, or the run reports rewrites it then
        declines to make.

        The masked-out link must be a DIFFERENT link than the live one and the
        live one must actually change: two occurrences of an already
        catalogue-absolute link produce no rewrite at all, and two occurrences of
        the same relative link collapse in _dedupe — either way the count is
        identical with and without the mask and the test asserts nothing."""
        self._w("b/index.md", "# B\n\nIntro.\n")
        self._w("a/target.md", "---\ntype: Concept\n---\n# T\n")
        self._w("a/other.md", "---\ntype: Concept\n---\n# O\n")
        self._w("a/mover.md", "---\ntype: Concept\n---\n"
                              "Real [T](target.md)\n\nand `[U](other.md)` inline.\n")
        out = self._rename("a/mover.md", "b/mover.md")
        self.assertIn("1 outbound link(s)", out)
        self.assertNotIn("other.md", out)
        self._rename("a/mover.md", "b/mover.md", apply=True)
        self.assertIn("`[U](other.md)`", self._r("b/mover.md"))

    def test_force_overwrite_discloses_what_it_clobbers(self):
        self._w("b/keep.md", "---\ntype: Concept\n---\n# Keep\n")
        self._w("b/ref.md", "---\ntype: Concept\n---\n[k](/b/keep.md) and [[keep]].\n")
        self._w("a/x.md", "---\ntype: Concept\n---\n# X\n")
        import contextlib
        import io
        import types
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf.cmd_rename(self.tmp, types.SimpleNamespace(
                old="a/x.md", new="b/keep.md", apply=True, force=True))
        self.assertIn("overwrote", buf.getvalue())
        self.assertIn("b/keep.md", buf.getvalue())
        # The destination is what this move REPLACES, not a third concept
        # competing for the name. Reporting it as a collision makes --force
        # accuse itself and buries the one line that says what was lost.
        self.assertNotIn("wikilink-collision", buf.getvalue())

    def test_reserved_destination_is_refused(self):
        """A reserved name is not a concept, so nothing resolves to it: every
        inbound link would be rewritten to an address dead on arrival, and the
        run would still report success."""
        self._w("a/src.md", "---\ntype: Concept\n---\nSee [[old]].\n")
        before = self._r("a/src.md")
        for dest in ("a/sub/index.md", "a/log.md", "a/README.md"):
            with self.assertRaises(SystemExit) as ctx:
                self._rename("a/old.md", dest, apply=True)
            self.assertEqual(ctx.exception.code, 2, dest)
        self.assertEqual(self._r("a/src.md"), before)

    def test_reserved_source_is_refused(self):
        """The mirror of the reserved-destination rule, and unasserted until
        round 5: a reserved file is a bundle's managed index, log or readme, not
        a concept. Moving one out from under `reindex_tree` breaks the structure
        every other surface reads, and no wikilink pointed at it to begin with."""
        for src in ("a/index.md", "a/log.md", "a/README.md"):
            self._w(src, "# Reserved\n")
            self._rename_fails(src, "a/moved.md", "refusing to move a reserved file")
            self.assertTrue(os.path.isfile(os.path.join(self.tmp, src)), src)

    def test_empty_destination_basename_is_refused(self):
        self._w("a/src.md", "---\ntype: Concept\n---\nSee [[old]].\n")
        with self.assertRaises(SystemExit):
            self._rename("a/old.md", "a/.md", apply=True)
        self.assertIn("[[old]]", self._r("a/src.md"))

    def test_crlf_line_endings_survive(self):
        """read_file translates CRLF to LF and write_file persists it, so a
        rewrite used to rewrite every line ending in the file, not the link."""
        self._w("a/src.md", "---\r\ntype: Concept\r\n---\r\n\r\nSee [[old]].\r\n")
        self._rename("a/old.md", "a/new.md", apply=True)
        with open(os.path.join(self.tmp, "a/src.md"), newline="", encoding="utf-8") as f:
            after = f.read()
        self.assertIn("[[new]]", after)
        self.assertEqual(after.count("\r\n"), 5)

    def test_undecodable_file_is_skipped_not_mangled(self):
        """errors='replace' would write U+FFFD over the original bytes."""
        ap = os.path.join(self.tmp, "a/bin.md")
        with open(ap, "wb") as f:
            f.write(b"---\ntype: Concept\n---\nCaf\xe9 sees [[old]].\n")
        before = open(ap, "rb").read()
        self._rename("a/old.md", "a/new.md", apply=True)
        self.assertEqual(open(ap, "rb").read(), before)

    def test_markdown_pass_does_not_rewrite_inside_a_fence(self):
        """The two halves of one rename must apply one policy. A whole-file
        str.replace edited a fenced sample the planner never reported."""
        self._w("a/src.md", "---\ntype: Concept\n---\n"
                            "real [O](/a/old.md)\n\n```\nexample [O](/a/old.md)\n```\n")
        self._rename("a/old.md", "a/new.md", apply=True)
        after = self._r("a/src.md")
        self.assertIn("real [O](/a/new.md)", after)
        self.assertIn("example [O](/a/old.md)", after)

    def test_symlinked_bundle_markdown_link_is_rewritten_too(self):
        """build_ref_matrix walked only the root, so a mounted file got its
        wikilink updated and its markdown link left dangling in the same line."""
        import tempfile
        ext = tempfile.mkdtemp()
        try:
            with open(os.path.join(ext, "src.md"), "w", encoding="utf-8") as f:
                f.write("---\ntype: Concept\n---\nMd [O](/a/old.md) and wiki [[old]].\n")
            os.symlink(ext, os.path.join(self.tmp, "mounted"))
            self._rename("a/old.md", "a/new.md", apply=True)
            with open(os.path.join(ext, "src.md"), encoding="utf-8") as f:
                after = f.read()
            self.assertIn("[[new]]", after)
            self.assertIn("(/a/new.md)", after)
        finally:
            import shutil
            shutil.rmtree(ext, ignore_errors=True)

    def test_collision_sees_a_staging_file_the_index_skips(self):
        """The resolution index skips staging; the rewrite pass does not. A
        collision looked for in the index alone missed a draft that Obsidian
        itself indexes."""
        self._w("a/_draft/new.md", "---\ntype: Concept\n---\n# Draft New\n")
        self._w("c/src.md", "---\ntype: Concept\n---\nSee [[old]].\n")
        with self.assertRaises(SystemExit) as ctx:
            self._rename("a/old.md", "a/new.md", apply=True)
        self.assertEqual(ctx.exception.code, 2)

    def test_collision_lookup_is_case_insensitive(self):
        """The link lives in a third bundle, so the tie-break cannot rescue it
        and the differently-cased collision must still be seen."""
        self._w("b/Foo.md", "---\ntype: Concept\n---\n# Foo\n")
        self._w("c/src.md", "---\ntype: Concept\n---\nSee [[old]].\n")
        with self.assertRaises(SystemExit):
            self._rename("a/old.md", "a/foo.md", apply=True)

    def test_collision_the_tie_break_absorbs_is_not_refused(self):
        """A bystander in its own bundle stays resolved through the tie-break,
        so claiming it turns ambiguous refuses a harmless rename."""
        self._w("z/foo.md", "---\ntype: Concept\n---\n# Foo\n")
        self._w("z/ref.md", "---\ntype: Concept\n---\nSee [[foo]].\n")
        self._w("a/old.md", "---\ntype: Concept\n---\n# Old\n")
        self._rename("a/old.md", "a/foo.md", apply=True)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "a/foo.md")))
        self.assertIn("[[foo]]", self._r("z/ref.md"))

    def test_summary_separates_rewritten_from_skipped(self):
        self._w("a/g.md", "---\ntype: Concept\n---\n# G\n")
        self._w("b/g.md", "---\ntype: Concept\n---\n# G\n")
        self._w("c/x.md", "---\ntype: Concept\n---\nSee [[g]].\n")
        self._w("a/y.md", "---\ntype: Concept\n---\nSee [[g]].\n")
        out = self._rename("a/g.md", "a/g2.md")
        self.assertIn("1 wikilink(s) (1 skipped-ambiguous)", out)


class PerformRenameDirectCall(WikilinkFixtureMixin, unittest.TestCase):
    """R-04 — perform_rename is the callable core cmd_rename delegates to.
    okf-cli-16rg's cmd_archive calls it directly with already-resolved
    paths and its own verb, so the function must work without an argparse
    namespace and must prefix error messages with the given verb."""

    def setUp(self):
        super().setUp()
        self._w("a/index.md", "# A\n\nIntro.\n\n" + M0 + "\n" + M1 + "\n")
        self._w("a/old.md", "---\ntype: Concept\n---\n# Old\n")

    def _ap(self, rel):
        return os.path.join(self.tmp, rel)

    def test_apply_moves_the_file_and_rewrites_inbound_links(self):
        self._w("a/src.md", "---\ntype: Concept\n---\nSee [[old]].\n")
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf.perform_rename(self.tmp, self._ap("a/old.md"), self._ap("a/new.md"),
                                apply=True, force=False)
        self.assertTrue(os.path.isfile(self._ap("a/new.md")))
        self.assertIn("[[new]]", self._r("a/src.md"))

    def test_dry_run_makes_no_change_and_reports_it_would_move(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf.perform_rename(self.tmp, self._ap("a/old.md"), self._ap("a/new.md"),
                                apply=False, force=False)
        self.assertTrue(os.path.isfile(self._ap("a/old.md")))
        self.assertFalse(os.path.isfile(self._ap("a/new.md")))
        self.assertIn("would move", buf.getvalue())

    def test_explicit_verb_prefixes_the_error_message(self):
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                okf.perform_rename(self.tmp, self._ap("a/old.md"), self._ap("a/y.txt"),
                                    apply=False, force=False, verb="archive")
        self.assertEqual(ctx.exception.code, 2)
        self.assertTrue(err.getvalue().startswith("archive:"))

    def test_default_verb_is_rename(self):
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit):
                okf.perform_rename(self.tmp, self._ap("a/old.md"), self._ap("a/y.txt"),
                                    apply=False, force=False)
        self.assertTrue(err.getvalue().startswith("rename:"))

    # -- AC4 (okf-cli-5436): the missing-source/existing-counterpart signal
    # is cmd_archive's, not perform_rename's. `rename` has no archive
    # semantics, so a missing source with a file already sitting at the
    # destination — an everyday rename collision, not an archive move —
    # must keep the plain "source not found" message unchanged.
    def test_ac4_missing_source_with_file_at_destination_stays_plain(self):
        import contextlib
        import io
        self._w("a/new.md", "---\ntype: Concept\n---\n# New\n")
        os.remove(self._ap("a/old.md"))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                okf.perform_rename(self.tmp, self._ap("a/old.md"), self._ap("a/new.md"),
                                    apply=False, force=False)
        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(
            "rename: source not found: {}\n".format(self._ap("a/old.md")),
            err.getvalue())

    # -- AC4 (okf-cli-tk33): the "source under _archive/" refusal is
    # cmd_rename's guard, not perform_rename's — that shared function is
    # also `archive --restore`'s own path back OUT of _archive/ (AC5), so a
    # guard placed here would refuse the very move the refusal's own message
    # points users at. Every other test in this bean reaches perform_rename
    # through cmd_rename, where the guard already ran by the time control
    # gets here — only a DIRECT call proves the check has not migrated into
    # the shared core (the okf-cli-5436 review's exact trap, same shape).
    def test_ac4_direct_call_with_source_under_archive_is_not_refused(self):
        self._w("_archive/a/deep.md", "---\ntype: Concept\n---\n# Deep\n")
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf.perform_rename(self.tmp, self._ap("_archive/a/deep.md"),
                                self._ap("a/deep.md"), apply=True, force=False)
        self.assertFalse(os.path.isfile(self._ap("_archive/a/deep.md")))
        self.assertTrue(os.path.isfile(self._ap("a/deep.md")))


class ArchiveConcept(WikilinkFixtureMixin, unittest.TestCase):
    """R-01..R-03 (okf-cli-16rg) — `archive`/`archive --restore` as a thin
    wrapper over perform_rename. The destination is derived, never typed."""

    def setUp(self):
        super().setUp()
        self._w("a/index.md", "# A\n\nIntro.\n\n" + M0 + "\n" + M1 + "\n")
        self._w("a/old.md", "---\ntype: Concept\n---\n# Old\n\nBody text.\n")

    def _ap(self, rel):
        return os.path.join(self.tmp, rel)

    def _archive(self, path, restore=False, apply=False, force=False):
        import contextlib
        import io
        import types
        args = types.SimpleNamespace(path=path, restore=restore, apply=apply, force=force)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf.cmd_archive(self.tmp, args)
        return buf.getvalue()

    def _archive_fails(self, path, message, restore=False, apply=False, force=False):
        import contextlib
        import io
        import types
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                okf.cmd_archive(self.tmp, types.SimpleNamespace(
                    path=path, restore=restore, apply=apply, force=force))
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn(message, err.getvalue())
        return err.getvalue()

    # -- A01/SC-01: dry run --------------------------------------------
    def test_dry_run_prints_the_plan_and_touches_nothing(self):
        out = self._archive("a/old.md")
        self.assertIn("would move", out)
        self.assertIn("_archive/a/old.md", out)
        self.assertTrue(os.path.isfile(self._ap("a/old.md")))
        self.assertFalse(os.path.exists(self._ap("_archive")))

    def test_dry_run_accepts_bare_concept_id_without_md_suffix(self):
        out = self._archive("a/old")
        self.assertIn("_archive/a/old.md", out)

    # -- A02/SC-02: apply -------------------------------------------------
    def test_apply_moves_file_under_archive_bundle_dir_fs_fallback(self):
        out = self._archive("a/old.md", apply=True)
        self.assertFalse(os.path.isfile(self._ap("a/old.md")))
        self.assertTrue(os.path.isfile(self._ap("_archive/a/old.md")))
        self.assertIn("moved (fs)", out)

    def test_apply_moves_file_via_real_git_when_tracked(self):
        import subprocess
        subprocess.run(["git", "init", "-q"], cwd=self.tmp, check=True)
        subprocess.run(["git", "add", "-A"], cwd=self.tmp, check=True)
        subprocess.run(["git", "-c", "user.email=t@t.de", "-c", "user.name=t",
                         "commit", "-qm", "seed"], cwd=self.tmp, check=True)
        out = self._archive("a/old.md", apply=True)
        self.assertTrue(os.path.isfile(self._ap("_archive/a/old.md")))
        self.assertIn("moved (git mv)", out)

    # -- A03: restore -------------------------------------------------
    def test_restore_derives_destination_without_a_second_path(self):
        self._archive("a/old.md", apply=True)
        out = self._archive("_archive/a/old.md", restore=True, apply=True)
        self.assertIn("_archive/a/old.md", out)
        self.assertTrue(os.path.isfile(self._ap("a/old.md")))
        self.assertFalse(os.path.exists(self._ap("_archive/a/old.md")))

    def test_restore_preserves_multi_level_concept_id_substructure(self):
        self._w("a/sub/deep.md", "---\ntype: Concept\n---\n# Deep\n")
        self._archive("a/sub/deep.md", apply=True)
        self.assertTrue(os.path.isfile(self._ap("_archive/a/sub/deep.md")))
        self._archive("_archive/a/sub/deep.md", restore=True, apply=True)
        self.assertTrue(os.path.isfile(self._ap("a/sub/deep.md")))

    # -- SC-03: round trip, including the links that point at the concept -
    def test_round_trip_archive_then_restore_is_byte_identical_including_links(self):
        self._w("b/src.md", "---\ntype: Concept\n---\nSee [Old](/a/old.md) and [[old]].\n")
        concept_before = self._r("a/old.md")
        linker_before = self._r("b/src.md")

        self._archive("a/old.md", apply=True)
        self.assertIn("/_archive/a/old.md", self._r("b/src.md"))
        self.assertIn("[[old]]", self._r("b/src.md"))

        self._archive("_archive/a/old.md", restore=True, apply=True)

        self.assertEqual(self._r("a/old.md"), concept_before)
        self.assertEqual(self._r("b/src.md"), linker_before)

    # -- A04/R-03: direction guards ------------------------------------
    def test_archive_refuses_a_source_already_under_archive(self):
        self._w("_archive/a/x.md", "---\ntype: Concept\n---\n# X\n")
        self._archive_fails("_archive/a/x.md", "already lies under _archive/")

    def test_restore_refuses_a_source_outside_archive(self):
        self._archive_fails("a/old.md", "must lie under _archive/", restore=True)

    def test_restore_refuses_an_archive_path_without_a_bundle_segment(self):
        self._w("_archive/x.md", "---\ntype: Concept\n---\n# X\n")
        self._archive_fails("_archive/x.md", "no bundle segment", restore=True)

    def test_each_direction_guard_is_distinguishable_by_message(self):
        """SC-04 — three refusals, three distinct messages, not one shared
        'refused' string that any of the three could satisfy."""
        self._w("_archive/a/x.md", "---\ntype: Concept\n---\n# X\n")
        self._w("_archive/y.md", "---\ntype: Concept\n---\n# Y\n")
        m1 = self._archive_fails("_archive/a/x.md", "already lies under _archive/")
        m2 = self._archive_fails("a/old.md", "must lie under _archive/", restore=True)
        m3 = self._archive_fails("_archive/y.md", "no bundle segment", restore=True)
        self.assertEqual(len({m1, m2, m3}), 3)

    # -- A07: report of active inbound references -----------------------
    def test_report_counts_active_concepts_still_linking_to_it(self):
        self._w("b/src.md", "---\ntype: Concept\n---\nSee [Old](/a/old.md).\n")
        self._w("c/other.md", "---\ntype: Concept\n---\nAlso [Old](/a/old.md).\n")
        out = self._archive("a/old.md")
        self.assertIn("2 active concept(s)", out)

    def test_report_is_zero_when_nothing_links_to_it(self):
        out = self._archive("a/old.md")
        self.assertIn("0 active concept(s)", out)

    # -- R-07/AC2/SC-01: move simulation honours the precedence rule -----
    def test_archive_does_not_falsely_flag_a_bystander_as_turning_ambiguous(self):
        """archiving a/old.md, whose basename is also held by the active
        d/old.md, must not report a/other.md's bystander [[old]] as turning
        ambiguous: once a/old.md leaves the active tier, [[old]] simply
        re-resolves to the sole remaining active concept, d/old.md — a
        retarget, not an ambiguity — so the move must complete without
        --force."""
        self._w("d/old.md", "---\ntype: Concept\n---\n# D Old\n")
        self._w("a/other.md", "---\ntype: Concept\n---\nSee [[old]].\n")
        out = self._archive("a/old.md", apply=True)
        self.assertNotIn("turns-ambiguous", out)
        self.assertTrue(os.path.isfile(self._ap("_archive/a/old.md")))
        # AC1/SC-01 (okf-cli-yixf) — the absence of "turns-ambiguous" is a
        # necessary, not a sufficient, condition: under an inverted
        # precedence direction the result also stays a single candidate, just
        # the wrong one (the freshly archived path). Assert the RESOLVED
        # TARGET the bystander actually re-addresses.
        after_index = okf_wikilinks.build_concept_basename_index(self.tmp)
        self.assertEqual(
            okf_wikilinks.resolve_wikilink(after_index, "a/other.md", "old"),
            ("resolved", ["/d/old.md"]))

    # -- SC-01 (okf-cli-gqss): restore of the last concept in a bundle
    # removes both _archive/<bundle>/ and, once that empties it, _archive/
    # itself — a filesystem check, not a git-status check, because git does
    # not track empty directories and the whole point of this bean is that
    # `git status` staying clean hides the residue.
    def test_sc01_restore_of_last_concept_removes_empty_archive_dirs(self):
        self._archive("a/old.md", apply=True)
        self._archive("_archive/a/old.md", restore=True, apply=True)
        self.assertFalse(os.path.isdir(self._ap("_archive/a")))
        self.assertFalse(os.path.isdir(self._ap("_archive")))

    # -- AC3/SC-02: a sibling concept left in the bundle keeps the dir --
    def test_sc02_restore_with_sibling_concept_keeps_the_directory(self):
        self._w("a/other.md", "---\ntype: Concept\n---\n# Other\n")
        self._archive("a/old.md", apply=True)
        self._archive("a/other.md", apply=True)
        self._archive("_archive/a/old.md", restore=True, apply=True)
        self.assertTrue(os.path.isdir(self._ap("_archive/a")))
        self.assertTrue(os.path.isfile(self._ap("_archive/a/other.md")))
        self.assertTrue(os.path.isdir(self._ap("_archive")))


class ArchiveComputesPlanOnce(WikilinkFixtureMixin, unittest.TestCase):
    """okf-cli-h12o — SC-01: a single `archive` invocation performs exactly
    one build_ref_matrix scan. cmd_archive built a plan for its AC7 report
    line and perform_rename used to recompute the same plan internally,
    doubling the scan cost with catalogue size. Counted, not timed: a
    timing assertion would be flaky and would not prove the count."""

    def setUp(self):
        super().setUp()
        self._w("a/index.md", "# A\n\nIntro.\n\n" + M0 + "\n" + M1 + "\n")
        self._w("a/old.md", "---\ntype: Concept\n---\n# Old\n\nBody text.\n")

    def _archive(self, path, restore=False, apply=False, force=False):
        import contextlib
        import io
        import types
        args = types.SimpleNamespace(path=path, restore=restore, apply=apply, force=force)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf.cmd_archive(self.tmp, args)
        return buf.getvalue()

    def test_sc01_single_archive_run_scans_the_ref_matrix_once(self):
        """Exercised through cmd_archive, not a direct perform_rename call —
        a direct call would not pin the wiring between the two plans."""
        from unittest import mock
        with mock.patch.object(okf_linkscan, "build_ref_matrix",
                                wraps=okf_linkscan.build_ref_matrix) as spy:
            self._archive("a/old.md", apply=True)
        self.assertEqual(spy.call_count, 1)

    def test_ac2_inbound_report_line_is_byte_identical(self):
        """AC2 — the report line built from cmd_archive's own plan, ahead of
        perform_rename, must not change at all. Pinned as a literal string,
        not the "N active concept(s)" substring the pre-existing tests use,
        which would not catch a change to the trailing wording."""
        self._w("b/src.md", "---\ntype: Concept\n---\nSee [Old](/a/old.md).\n")
        out = self._archive("a/old.md")
        self.assertIn("1 active concept(s) still link to this concept\n", out)


class ArchiveMissingSourcePointsAtCounterpart(WikilinkFixtureMixin, unittest.TestCase):
    """okf-cli-5436 — a missing source whose derived counterpart exists is a
    navigation signal, not a bare miss: name the counterpart and the verb
    that reaches it. AC1-AC4. The check lives in cmd_archive, not
    perform_rename (AC4) — SPEC.md §2 reasoning, same as the three existing
    direction guards."""

    def setUp(self):
        super().setUp()
        self._w("a/index.md", "# A\n")

    def _ap(self, rel):
        return os.path.join(self.tmp, rel)

    def _archive_fails(self, path, restore=False, apply=False, force=False):
        import contextlib
        import io
        import types
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                okf.cmd_archive(self.tmp, types.SimpleNamespace(
                    path=path, restore=restore, apply=apply, force=force))
        self.assertEqual(ctx.exception.code, 2)
        return err.getvalue()

    # -- SC-02: regression guard on the untouched path, written first ----
    # A missing source with no counterpart anywhere must keep the CURRENT
    # "source not found" message, asserted against the literal string —
    # this has to exist and pass BEFORE the new branch is written, or there
    # is no way to tell whether the untouched path stayed untouched.
    def test_sc02_missing_source_with_no_counterpart_keeps_current_message(self):
        err = self._archive_fails("a/ghost.md")
        self.assertEqual(
            "archive: source not found: {}\n".format(self._ap("a/ghost.md")),
            err)

    # -- AC1/SC-01: missing source, an archived counterpart exists -------
    # A substring check alone is not enough here: the source path itself
    # already contains "old.md", so both required tokens are asserted, and
    # the full message is pinned so a future edit cannot silently drop the
    # active-path/--restore wording while still matching a loose assertion.
    def test_sc01_missing_source_with_archived_counterpart_names_restore(self):
        self._w("_archive/a/old.md", "---\ntype: Concept\n---\n# Old\n")
        err = self._archive_fails("a/old.md")
        self.assertIn("_archive/a/old.md", err)
        self.assertIn("--restore", err)
        self.assertEqual(
            "archive: source not found: {} — already archived at "
            "_archive/a/old.md (use --restore to bring it back)\n"
            .format(self._ap("a/old.md")),
            err)

    # -- AC2: mirrored case on the --restore path -------------------------
    # "a/old.md" is trivially a substring of the unmodified message (it is
    # the tail of ".../_archive/a/old.md"), so a bare assertIn would pass
    # against the OLD, unchanged code — pin the full message instead, which
    # only the new branch produces.
    def test_ac2_missing_restore_source_with_active_counterpart_names_it(self):
        self._w("a/old.md", "---\ntype: Concept\n---\n# Old\n")
        err = self._archive_fails("_archive/a/old.md", restore=True)
        self.assertEqual(
            "archive: source not found: {} — the active copy already "
            "exists at a/old.md\n".format(self._ap("_archive/a/old.md")),
            err)


class RenameSourceUnderArchiveRefuses(WikilinkFixtureMixin, unittest.TestCase):
    """okf-cli-tk33 — D02 (PO decision on Q02): a `rename` whose RESOLVED
    source lies under _archive/ reproduces, through a different command, the
    invisible empty-directory residue okf-cli-gqss closed for
    `archive --restore`. The guard lives in cmd_rename (AC4/AC5), not
    perform_rename — that function is `archive --restore`'s own path back
    OUT of _archive/, so a shared guard would refuse the very move this
    refusal's message points users at. See
    PerformRenameDirectCall.test_ac4_direct_call_with_source_under_archive_is_not_refused
    for the placement proof."""

    def setUp(self):
        super().setUp()
        self._w("a/index.md", "# A\n")
        self._w("b/index.md", "# B\n")

    def _ap(self, rel):
        return os.path.join(self.tmp, rel)

    def _rename(self, old, new, apply=False):
        import contextlib
        import io
        import types
        args = types.SimpleNamespace(old=old, new=new, apply=apply, force=False)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf.cmd_rename(self.tmp, args)
        return buf.getvalue()

    def _rename_fails(self, old, new, apply=False):
        import contextlib
        import io
        import types
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                okf.cmd_rename(self.tmp, types.SimpleNamespace(
                    old=old, new=new, apply=apply, force=False))
        self.assertEqual(ctx.exception.code, 2)
        return out.getvalue(), err.getvalue()

    # -- SC-03 regression, written first: both untouched paths must keep
    # behaving exactly as before the refusal exists. ----------------------
    def test_sc03_ordinary_rename_between_active_paths_is_unchanged(self):
        self._w("a/old.md", "---\ntype: Concept\n---\n# Old\n")
        out = self._rename("a/old.md", "a/new.md", apply=True)
        self.assertIn("moved (fs)", out)
        self.assertTrue(os.path.isfile(self._ap("a/new.md")))
        self.assertFalse(os.path.isfile(self._ap("a/old.md")))

    def test_sc03_rename_with_destination_under_archive_is_unchanged(self):
        self._w("a/old.md", "---\ntype: Concept\n---\n# Old\n")
        out = self._rename("a/old.md", "_archive/a/old.md", apply=True)
        self.assertIn("moved (fs)", out)
        self.assertTrue(os.path.isfile(self._ap("_archive/a/old.md")))
        self.assertFalse(os.path.isfile(self._ap("a/old.md")))

    # -- SC-04/AC5: archive --restore, the operation this refusal points
    # users at, keeps working through the same shared perform_rename. -----
    def test_sc04_archive_restore_of_a_deep_path_still_works(self):
        import types
        import contextlib
        import io
        self._w("a/old.md", "---\ntype: Concept\n---\n# Old\n")
        okf.cmd_archive(self.tmp, types.SimpleNamespace(
            path="a/old.md", restore=False, apply=True, force=False))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf.cmd_archive(self.tmp, types.SimpleNamespace(
                path="_archive/a/old.md", restore=True, apply=True, force=False))
        self.assertTrue(os.path.isfile(self._ap("a/old.md")))
        self.assertFalse(os.path.isfile(self._ap("_archive/a/old.md")))

    # -- AC1/AC2/SC-01/SC-02: the refusal itself ---------------------------
    def test_sc01_apply_refuses_and_names_archive_restore(self):
        self._w("_archive/a/old.md", "---\ntype: Concept\n---\n# Old\n")
        out, err = self._rename_fails("_archive/a/old.md", "a/old.md", apply=True)
        self.assertIn("archive --restore", err)
        self.assertTrue(os.path.isfile(self._ap("_archive/a/old.md")))
        self.assertFalse(os.path.isfile(self._ap("a/old.md")))

    def test_sc02_dry_run_refuses_identically_not_a_would_move_line(self):
        self._w("_archive/a/old.md", "---\ntype: Concept\n---\n# Old\n")
        out, err = self._rename_fails("_archive/a/old.md", "a/old.md", apply=False)
        self.assertIn("archive --restore", err)
        self.assertNotIn("would move", out)

    def test_ac2_dry_run_and_apply_refuse_with_the_identical_message(self):
        """AC2: the refusal is not a preview --apply would later decline to
        honour — dry-run and --apply must produce the SAME message, not
        merely both exit non-zero."""
        self._w("_archive/a/old.md", "---\ntype: Concept\n---\n# Old\n")
        _, err_dry = self._rename_fails("_archive/a/old.md", "a/old.md", apply=False)
        self._w("_archive/a/old.md", "---\ntype: Concept\n---\n# Old\n")
        _, err_apply = self._rename_fails("_archive/a/old.md", "a/old.md", apply=True)
        self.assertEqual(err_dry, err_apply)

    # -- AC1: the RESOLVED source, not the raw argument string -------------
    def test_ac1_traversal_argument_that_resolves_into_archive_is_refused(self):
        """A raw prefix check on args.old would miss this: the argument
        string itself never starts with "_archive/"."""
        self._w("_archive/a/old.md", "---\ntype: Concept\n---\n# Old\n")
        _, err = self._rename_fails("b/../_archive/a/old.md", "a/old.md", apply=True)
        self.assertIn("archive --restore", err)
        self.assertTrue(os.path.isfile(self._ap("_archive/a/old.md")))

    def test_ac1_symlink_resolving_into_archive_is_refused(self):
        """A symlink living OUTSIDE _archive/ whose target resolves inside
        it — the raw path the user typed never mentions _archive/ at all,
        so only resolving the source catches this."""
        self._w("_archive/a/old.md", "---\ntype: Concept\n---\n# Old\n")
        os.symlink(self._ap("_archive/a/old.md"), self._ap("b/alias.md"))
        _, err = self._rename_fails("b/alias.md", "a/moved.md", apply=True)
        self.assertIn("archive --restore", err)
        self.assertTrue(os.path.isfile(self._ap("_archive/a/old.md")))


@unittest.skipUnless(shutil.which("git"), "git not installed")
class GitMvBeyondSymlink(unittest.TestCase):
    """okf-cli-mk7m, SC-02. Two real git repos: `foreign` tracks a project
    bundle's real content, `catalogue` tracks only the symlink (mode 120000)
    that reaches it — the layout of every project bundle in the real
    catalogue. `git -C <catalogue> mv` on a path beyond that symlink refuses
    with `fatal: not under version control, source=…, destination=…` (exit
    128) — NOT the `git add`-only "beyond a symbolic link" pathspec message
    an earlier draft of the bean mis-attributed (point 2 of the gate)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _env(self, when):
        env = dict(os.environ)
        env.update({
            "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
            "HOME": self.tmp, "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e",
            "GIT_AUTHOR_DATE": "@{} +0000".format(when),
            "GIT_COMMITTER_DATE": "@{} +0000".format(when),
        })
        return env

    def _git(self, repo, *argv, when=1785000000):
        import subprocess
        base = ["git", "-C", repo, "-c", "init.defaultBranch=main",
                "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
                "-c", "user.name=t", "-c", "user.email=t@e"]
        return subprocess.run(base + list(argv), capture_output=True, text=True,
                              env=self._env(when))

    def _repo(self, name):
        repo = os.path.join(self.tmp, name)
        os.makedirs(repo)
        r = self._git(repo, "init", "-q")
        self.assertEqual(r.returncode, 0, r.stderr)
        return repo

    def _write(self, repo, rel, text="---\ntype: Concept\n---\n# x\n"):
        ap = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(text)
        return ap

    def _catalogue_with_symlinked_bundle(self, bundle="proj-okf", concept="concept.md"):
        """Bean's SC-02 layout: `catalogue` and `foreign` are separate git
        repos; `foreign` tracks the bundle's real content, `catalogue` tracks
        only the symlink (mode 120000) that reaches it."""
        catalogue = self._repo("catalogue")
        foreign = self._repo("foreign")
        self._write(foreign, "docs/{}/{}".format(bundle, concept))
        r = self._git(foreign, "add", "-A", when=1785900000)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self._git(foreign, "commit", "-qm", "add", when=1785900000)
        self.assertEqual(r.returncode, 0, r.stderr)
        bundle_target = os.path.join(foreign, "docs", bundle)
        os.symlink(bundle_target, os.path.join(catalogue, bundle))
        r = self._git(catalogue, "add", "-A", when=1785000000)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self._git(catalogue, "commit", "-qm", "link", when=1785000000)
        self.assertEqual(r.returncode, 0, r.stderr)
        return catalogue, foreign, bundle_target

    def test_fixture_reproduces_the_cited_git_message(self):
        """Ground truth for point 2 of the gate: `git mv` beyond the symlink
        says `not under version control`, never `beyond a symbolic link` —
        that phrase is `git add`'s, not `git mv`'s."""
        import subprocess
        catalogue, _foreign, _bt = self._catalogue_with_symlinked_bundle()
        old = os.path.join(catalogue, "proj-okf", "concept.md")
        new = os.path.join(catalogue, "proj-okf", "concept2.md")
        proc = subprocess.run(["git", "-C", catalogue, "mv", "-f", old, new],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 128)
        self.assertIn("not under version control", proc.stderr)
        self.assertNotIn("beyond a symbolic link", proc.stderr)

    # -- AC1, first branch: destination stays inside the SAME foreign repo --
    def test_rename_fully_inside_a_symlinked_bundle_is_tracked_in_the_foreign_repo(self):
        import subprocess
        catalogue, foreign, _bt = self._catalogue_with_symlinked_bundle()
        old = os.path.join(catalogue, "proj-okf", "concept.md")
        new = os.path.join(catalogue, "proj-okf", "renamed.md")
        moved, repo, reason = okf._git_mv(catalogue, old, new)
        self.assertTrue(moved, reason)
        self.assertEqual(repo, os.path.realpath(foreign))
        self.assertIsNone(reason)
        self.assertTrue(os.path.isfile(new))
        status = subprocess.run(["git", "-C", foreign, "status", "--porcelain"],
                                capture_output=True, text=True).stdout
        self.assertIn("R  docs/proj-okf/concept.md -> docs/proj-okf/renamed.md",
                       status)

    # -- AC1 second branch + AC2 + AC3: archive's cross-repo case (SC-01) --
    def test_archive_across_repos_states_the_fallback_and_names_the_repo(self):
        import contextlib
        import io
        import types
        catalogue, foreign, _bt = self._catalogue_with_symlinked_bundle()
        args = types.SimpleNamespace(path="proj-okf/concept.md", restore=False,
                                     apply=True, force=False)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf.cmd_archive(catalogue, args)
        out = buf.getvalue()

        self.assertIn("moved (fs)", out)
        self.assertNotIn("moved (git mv)", out)
        self.assertIn("not under version control", out)  # point 4: stderr surfaced
        self.assertIn(os.path.realpath(foreign), out)  # AC2: names the repo
        self.assertIn("repository differs from --root", out)
        self.assertTrue(os.path.isfile(
            os.path.join(catalogue, "_archive", "proj-okf", "concept.md")))

    # -- widened AC3: the untracked-but-not-symlinked cause, PO 2026-08-10 --
    def test_untracked_file_in_an_ordinary_bundle_also_states_git_declined(self):
        import contextlib
        import io
        import types
        catalogue = self._repo("catalogue")
        self._write(catalogue, "a/seed.md")
        r = self._git(catalogue, "add", "-A")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self._git(catalogue, "commit", "-qm", "seed")
        self.assertEqual(r.returncode, 0, r.stderr)
        self._write(catalogue, "a/untracked.md")  # never git-added

        args = types.SimpleNamespace(path="a/untracked.md", restore=False,
                                     apply=True, force=False)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf.cmd_archive(catalogue, args)
        out = buf.getvalue()

        self.assertIn("moved (fs)", out)
        self.assertIn("not under version control", out)
        # Same repository as --root: unlike the symlinked-bundle cause above,
        # there is no second repository to name — the report must not claim
        # one (point 3: the two causes share a surface but not a report).
        self.assertNotIn("repository differs from --root", out)


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
        """Run a command, returning (exit_code_or_None, stdout, stderr)."""
        import io, contextlib
        out, err = io.StringIO(), io.StringIO()
        code = None
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                fn(self.tmp, args)
            except SystemExit as e:
                code = e.code
        return code, out.getvalue(), err.getvalue()

    def _index_args(self, bundle, json_flag=False):
        import types
        return types.SimpleNamespace(bundle=bundle, full=False, json=json_flag)

    def test_index_refuses_a_bundle_that_does_not_exist(self):
        code, out, err = self._call(okf_index.cmd_index, self._index_args("nope"))
        self.assertEqual(code, 1)
        self.assertIn("nope", err)
        self.assertNotIn("# nope", out)

    def test_index_json_refuses_too(self):
        """The --json branch returns before the text branch, so it needs the
        same gate — otherwise a consumer gets `{"bundle": "nope", ...}` and a
        zero exit for a bundle that is not there."""
        code, out, _err = self._call(okf_index.cmd_index,
                                     self._index_args("nope", json_flag=True))
        self.assertEqual(code, 1)
        self.assertEqual(out, "")

    def test_index_still_prints_an_existing_bundle(self):
        code, out, _err = self._call(okf_index.cmd_index, self._index_args("real"))
        self.assertIsNone(code)
        self.assertIn("One", out)

    def test_visualize_refuses_a_bundle_that_does_not_exist(self):
        import types
        code, _out, err = self._call(
            okf.cmd_visualize, types.SimpleNamespace(bundle="nope", out=None))
        self.assertEqual(code, 1)
        self.assertIn("nope", err)

    def test_visualize_creates_nothing_for_a_bundle_that_does_not_exist(self):
        """The actual damage: os.makedirs() on a path derived from an
        unvalidated argument. A typo left a directory behind in the
        catalogue."""
        import types
        self._call(okf.cmd_visualize,
                   types.SimpleNamespace(bundle="nope", out=None))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "nope")))

    def test_visualize_still_writes_for_an_existing_bundle(self):
        import types
        code, out, _err = self._call(
            okf.cmd_visualize, types.SimpleNamespace(bundle="real", out=None))
        self.assertIsNone(code)
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
        code, out, _err = self._call(okf_index.cmd_index, self._index_args("_archive"))
        self.assertIsNone(code)
        self.assertIn("Old", out)


class StagingContentRepair(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._w("b/published.md",
                "---\ntype: Concept\ntitle: Published\n---\n"
                "See [Old](old.md).\n<PLACEHOLDER>\nold/path\n")
        self._w("b/_intake/staged.md",
                "See [Old](../old.md).\n<PLACEHOLDER>\nold/path\n")
        self._w("b/old.md", "---\ntype: Concept\ntitle: Old\n---\n")

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

    def test_fix_crosslinks_reaches_staging(self):
        touched, _ = okf_check.fix_crosslinks(self.tmp, "b")
        self.assertEqual({p for p, _ in touched},
                         {"b/published.md", "b/_intake/staged.md"})
        self.assertIn("(/b/old.md)", self._r("b/_intake/staged.md"))

    def test_fix_xml_tags_reaches_staging(self):
        touched = okf_check.fix_xml_like_tags(self.tmp, "b")
        self.assertEqual({p for p, _ in touched},
                         {"b/published.md", "b/_intake/staged.md"})
        self.assertIn("`<PLACEHOLDER>`", self._r("b/_intake/staged.md"))

    def test_rewrite_path_reaches_staging(self):
        touched = okf.rewrite_path(self.tmp, "old/path", "new/path")
        self.assertEqual({p for p, _ in touched},
                         {"b/published.md", "b/_intake/staged.md"})
        self.assertIn("new/path", self._r("b/_intake/staged.md"))

    def test_reindex_and_check_prune_staging(self):
        reindexed = _cli(self.tmp, "reindex", "b")
        checked = _cli(self.tmp, "check", "b")
        self.assertEqual(reindexed.returncode, 0, reindexed.stderr)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertNotIn("_intake/staged.md", reindexed.stdout)
        self.assertNotIn("_intake/staged.md", checked.stdout)



class CorpusScopingTask1(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "canonical"))
        os.makedirs(os.path.join(self.root, "topic"))
        with open(os.path.join(self.root, ".okf.toml"), "w") as f:
            f.write("bundle = \"canonical\"\n")
        for bundle, cid, title in [("canonical", "main", "Canonical"), ("topic", "topic-only", "UniqueTopicNeedle")]:
            with open(os.path.join(self.root, bundle, cid + ".md"), "w") as f:
                f.write("---\ntype: Concept\ntitle: " + title + "\ndescription: d\ntags: []\n---\n" + title + "\n")
            with open(os.path.join(self.root, bundle, "index.md"), "w") as f:
                f.write("# " + bundle + "\n")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_default_filter_excludes_topic_from_broad_fts(self):
        okf_fts.build_fts_index(self.root, include_topics=True)
        filters = okf_find_filters.FindFilters(corpus_bundles=okf_catalogue.list_search_bundles(self.root))
        ranked = okf_fts._fts_ranking(self.root, "UniqueTopicNeedle", 10, filters)
        self.assertEqual(ranked, [])

    def test_explicit_inclusion_returns_topic_from_broad_fts(self):
        okf_fts.build_fts_index(self.root, include_topics=True)
        filters = okf_find_filters.FindFilters(include_topics=True, corpus_bundles=okf_catalogue.list_search_bundles(self.root, True))
        ranked = okf_fts._fts_ranking(self.root, "UniqueTopicNeedle", 10, filters)
        self.assertEqual(ranked[0][0], "topic/topic-only")

    def test_narrow_metadata_is_stale_for_topic_request(self):
        okf_fts.build_fts_index(self.root, include_topics=False)
        conn = sqlite3.connect(okf_fts._fts_db_path(self.root))
        try:
            self.assertTrue(okf_fts._fts_index_stale(self.root, conn, include_topics=True))
        finally:
            conn.close()

    def test_topic_request_against_narrow_index_emits_only_rebuild_note(self):
        okf_fts.build_fts_index(self.root, include_topics=False)
        args = argparse.Namespace(
            query="UniqueTopicNeedle", limit=10, scope=None, type=None,
            tag=None, include_archive=False, include_topics=True,
            breakdown=False)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            okf_find.cmd_find(self.root, args)
        lexical_notes = [line for line in stderr.getvalue().splitlines()
                         if line.startswith("note: lexical index")]
        self.assertEqual(
            lexical_notes,
            ["note: lexical index excludes topic folders — run "
             "`okf-cli build-index --include-topics`"])

    def test_topic_request_without_fts_uses_wide_substring_scan(self):
        filters = okf_find_filters.FindFilters(include_topics=True)
        ranked = okf_find._substring_ranking(
            self.root, "UniqueTopicNeedle", ["uniquetopicneedle"], 10, filters)
        self.assertEqual(ranked[0]["path"], "topic/topic-only")

    def test_parser_exposes_include_topics(self):
        parser = okf.build_parser()
        self.assertTrue(parser.parse_args(["build-index", "--include-topics"]).include_topics)
        self.assertTrue(parser.parse_args(["find", "needle", "--include-topics"]).include_topics)


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


class SyncProtectedFromRewriters(SyncFixtureMixin, unittest.TestCase):
    """A materialised payload is owned by its canon concept: no scanner
    reports inside it and no rewriter touches it."""

    OWNER_PAYLOAD = ("Siehe [details](../kc-proj/setup.md), [[setup]] und "
                     "<info>.<other>.\n")

    def setUp(self):
        super().setUp()
        self._w(".okf.toml", '[wikilinks]\nchecked_bundles = ["kc-proj"]\n')
        self._insert()
        self.consumer_before = self._r("kc-proj/setup.md")

    def test_fix_crosslinks_leaves_the_block_byte_identical(self):
        okf_check.fix_crosslinks(self.tmp, None)
        self.assertEqual(self._r("kc-proj/setup.md"), self.consumer_before)

    def test_fix_xml_tags_leaves_the_block_byte_identical(self):
        okf_check.fix_xml_like_tags(self.tmp, None)
        self.assertEqual(self._r("kc-proj/setup.md"), self.consumer_before)

    def test_crosslink_and_xml_checks_report_nothing_for_the_consumer(self):
        ctx = okf_check.gather_file_context(
            self.tmp, "kc-proj", os.path.join(self.tmp, "kc-proj/setup.md"))
        self.assertEqual(okf_check.check_crosslink_format(ctx), [])
        self.assertEqual(okf_check.check_xml_like_tags(ctx), [])

    def test_wikilink_in_a_synced_payload_is_not_scanned(self):
        _, body = okf_catalogue.split_frontmatter(self._r("kc-proj/setup.md"))
        self.assertEqual(okf_wikilinks.parse_wikilinks(body), [])

    def test_rename_leaves_the_payload_intact_and_rewrites_the_source(self):
        expected = okf_sync.parse_sync_blocks(
            okf_catalogue.split_frontmatter(self.consumer_before)[1])[0]["payload"]
        okf.perform_rename(self.tmp,
                           os.path.join(self.tmp, "kc-proj/setup.md"),
                           os.path.join(self.tmp, "kc-proj/setup2.md"),
                           apply=True, force=True)
        # The payload wikilinks to the renamed concept and must NOT be
        # rewritten: the owner's copy is the one that carries that link.
        self.assertEqual(self._payload_of("kc-proj/setup2.md"), expected)
        okf.perform_rename(self.tmp,
                           os.path.join(self.tmp, "kc-gov/ownership.md"),
                           os.path.join(self.tmp, "kc-gov/canon/ownership.md"),
                           apply=True, force=True)
        _, body = okf_catalogue.split_frontmatter(self._r("kc-proj/setup2.md"))
        self.assertEqual(okf_sync.parse_sync_blocks(body)[0]["source"],
                         "/kc-gov/canon/ownership.md")


class IndexMapRecursiveBlock(unittest.TestCase):
    """index-map.md is a managed, recursive full-tree index (OKFT-on05).

    index.md lists one level; index-map.md lists the whole subtree below its
    own directory. Both are marker-bounded and generated by reindex, so a
    moved or deleted concept can no longer leave a dead entry behind."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        b = os.path.join(self.tmp, "b")
        os.makedirs(os.path.join(b, "sub"))
        okf_catalogue.write_file(os.path.join(b, "top.md"), "---\ntitle: Top\n---\n# Top\n")
        okf_catalogue.write_file(os.path.join(b, "sub", "deep.md"), "---\ntitle: Deep\n---\n# Deep\n")
        okf_catalogue.write_file(os.path.join(b, "sub", "index.md"),
                       "# Sub\n\n" + M0 + "\n" + M1 + "\n")
        okf_catalogue.write_file(os.path.join(b, "index.md"), "# B\n\n" + M0 + "\n" + M1 + "\n")
        okf_catalogue.write_file(os.path.join(b, "INDEX-MAP.md"),
                       "# B — Index Map\n\nEntry point.\n\n" + M0 + "\n" + M1 + "\n")

    def _reindex(self):
        okf_index.cmd_reindex(self.tmp, okf.build_parser().parse_args(["reindex", "b"]))

    def _map(self):
        return okf_catalogue.read_file(os.path.join(self.tmp, "b", "INDEX-MAP.md"))

    def test_index_map_lists_the_whole_subtree_indented(self):
        self._reindex()
        text = self._map()
        self.assertIn("* [Top](/b/top.md)", text)
        self.assertIn("* [Sub](/b/sub/index.md)", text)
        self.assertIn("  * [Deep](/b/sub/deep.md)", text)
        self.assertIn("Entry point.", text)     # prose outside the block survives
        # index.md stays one level deep: no nested entry leaks into it.
        self.assertNotIn("deep.md", okf_catalogue.read_file(os.path.join(self.tmp, "b", "index.md")))

    def test_a_removed_concept_disappears_from_the_index_map(self):
        self._reindex()
        self.assertIn("deep.md", self._map())
        os.remove(os.path.join(self.tmp, "b", "sub", "deep.md"))
        self._reindex()
        self.assertNotIn("deep.md", self._map())

    def test_rename_refreshes_the_index_map(self):
        self._reindex()
        okf.perform_rename(self.tmp,
                           os.path.join(self.tmp, "b", "sub", "deep.md"),
                           os.path.join(self.tmp, "b", "sub", "deeper.md"),
                           apply=True, force=True)
        text = self._map()
        self.assertIn("/b/sub/deeper.md", text)
        self.assertNotIn("/b/sub/deep.md", text)



if __name__ == "__main__":
    unittest.main()
