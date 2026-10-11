#!/usr/bin/env python3
"""Tests for cli/okf/rename.py — the rename, archive and rewrite-path commands:
the reference rewrite plan and its writers, the git move, the archive guards and
the literal path-string rewrite. unittest.

Run: just test tests.test_okf_rename -v
"""
import contextlib
import io
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

from okf import catalogue as okf_catalogue
from okf import linkscan as okf_linkscan
from okf import rename as okf_rename
from okf import wikilinks as okf_wikilinks
from okf.diffs import write_plan
from okf.errors import OkfError
from tests.git_preview import HAS_GIT, GitPreviewMixin
from tests.okf_testkit import needs_case_insensitive_fs
from tests.test_okf_wikilinks import WikilinkFixtureMixin

M0, M1 = okf_catalogue.MARK_START, okf_catalogue.MARK_END


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
        touched, plan, _ = okf_rename.rewrite_path(self.tmp, "docs/notes.md", "docs/demo-okf/notes.md")
        write_plan(self.tmp, plan)
        self.assertEqual(sorted(t[0] for t in touched), ["README.md", "app.py"])
        self.assertIn("docs/demo-okf/notes.md", self._r("README.md"))
        self.assertIn("docs/demo-okf/notes.md", self._r("app.py"))

    def test_dry_run_writes_nothing_but_reports(self):
        self._w("README.md", "docs/notes.md\n")
        before = self._r("README.md")
        touched, _plan, _ = okf_rename.rewrite_path(self.tmp, "docs/notes.md", "docs/x.md")
        self.assertEqual(touched, [("README.md", 1)])
        self.assertEqual(self._r("README.md"), before)

    def test_prunes_git_and_node_modules(self):
        self._w(".git/config", "docs/notes.md\n")
        self._w("node_modules/x.js", "docs/notes.md\n")
        touched, _plan, _ = okf_rename.rewrite_path(self.tmp, "docs/notes.md", "docs/x.md")
        self.assertEqual(touched, [])

    def test_counts_multiple_occurrences(self):
        self._w("a.txt", "docs/notes.md and docs/notes.md again\n")
        touched, _plan, _ = okf_rename.rewrite_path(self.tmp, "docs/notes.md", "docs/x.md")
        self.assertEqual(touched, [("a.txt", 2)])

    def test_does_not_touch_substring_collision(self):
        self._w("a.txt", "my-docs/notes.md and docs/notes.md-old and docs/notes.md\n")
        touched, plan, _ = okf_rename.rewrite_path(self.tmp, "docs/notes.md", "docs/x.md")
        write_plan(self.tmp, plan)
        self.assertEqual(touched, [("a.txt", 1)])            # only the standalone path
        self.assertIn("my-docs/notes.md", self._r("a.txt"))  # prefix-collision untouched
        self.assertIn("docs/notes.md-old", self._r("a.txt")) # suffix-collision untouched
        self.assertIn("docs/x.md\n", self._r("a.txt"))       # the real one rewritten


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
            okf_rename.link_expr(self.tmp, self._ap("aaa/b.md"), self._ap("aaa/a.md")),
            "/aaa/a.md")

    def test_link_expr_cross_bundle_is_catalogue_absolute(self):
        self.assertEqual(
            okf_rename.link_expr(self.tmp, self._ap("aaa/b.md"), self._ap("bbb/a.md")),
            "/bbb/a.md")

    def test_link_expr_from_subdir_does_not_climb(self):
        """Renamed from ..._climbs_correctly: under the catalogue-absolute
        form nothing climbs. The expression no longer depends on where the
        SOURCE sits, which is the whole point — the same link text names the
        same file from anywhere in the catalogue."""
        self.assertEqual(
            okf_rename.link_expr(self.tmp, self._ap("aaa/sub/c.md"), self._ap("bbb/a.md")),
            "/bbb/a.md")

    def test_split_link_suffix_keeps_anchor(self):
        self.assertEqual(okf_rename._split_link_suffix("/sub/c.md#h"), ("/sub/c.md", "#h"))

    def test_plan_same_bundle_rewrites_inbound_only(self):
        plan = okf_rename.plan_rename(self.tmp, self._ap("aaa/a.md"), self._ap("aaa/a2.md"))
        srcs = {s: (o, n) for s, o, n in plan["inbound"]}
        self.assertEqual(srcs["aaa/b.md"], ("/aaa/a.md", "/aaa/a2.md"))
        self.assertEqual(srcs["aaa/sub/c.md"], ("/aaa/a.md", "/aaa/a2.md"))
        self.assertEqual(srcs["bbb/x.md"], ("/aaa/a.md", "/aaa/a2.md"))
        self.assertEqual(plan["outbound"], [])          # bundle unchanged
        self.assertEqual(plan["bundles"], ["aaa"])

    def test_plan_cross_bundle_rewrites_inbound_and_outbound(self):
        plan = okf_rename.plan_rename(self.tmp, self._ap("aaa/a.md"), self._ap("bbb/a.md"))
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
        okf_rename._apply_link_rewrites(p, [("/a.md", "/a2.md")])
        with open(p) as f:
            out = f.read()
        # only the ](...) target rewritten; label text + bare mention untouched
        self.assertEqual(out, "[/a.md](/a2.md) and text /a.md bare")


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
        after = okf_rename._index_after_move(index, "/a/old.md", "/_archive/a/old.md")
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
            okf_rename.cmd_rename(self.tmp, args)
        return buf.getvalue()

    def _rename_fails(self, old, new, message, apply=False):
        """Assert the precise error kind and message of one refusal guard."""
        import contextlib
        import io
        import types
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(OkfError) as ctx:
                okf_rename.cmd_rename(self.tmp, types.SimpleNamespace(
                    old=old, new=new, apply=apply, force=False))
        self.assertEqual(ctx.exception.kind, "invalid_input")
        self.assertIn(message, ctx.exception.message)
        return ctx.exception.message

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
        before = set(okf_catalogue.read_frontmatter(self._r("a/src.md")).data)
        self._rename("a/old.md", "a/new.md", apply=True)
        after_text = self._r("a/src.md")
        self.assertIn('- "[[new]]"', after_text)
        self.assertEqual(set(okf_catalogue.read_frontmatter(after_text).data), before)

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
        with self.assertRaises(OkfError) as ctx:
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
            okf_rename.cmd_rename(self.tmp, types.SimpleNamespace(
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
        plan = okf_rename.plan_rename(self.tmp,
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
        with self.assertRaises(OkfError) as ctx:
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
        recs, _ = okf_rename.plan_wikilink_rewrites(
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
        with self.assertRaises(OkfError) as ctx:
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
            okf_rename.cmd_rename(self.tmp, types.SimpleNamespace(
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
            with self.assertRaises(OkfError) as ctx:
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
        with self.assertRaises(OkfError):
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
        with self.assertRaises(OkfError) as ctx:
            self._rename("a/old.md", "a/new.md", apply=True)
        self.assertEqual(ctx.exception.code, 2)

    def test_collision_lookup_is_case_insensitive(self):
        """The link lives in a third bundle, so the tie-break cannot rescue it
        and the differently-cased collision must still be seen."""
        self._w("b/Foo.md", "---\ntype: Concept\n---\n# Foo\n")
        self._w("c/src.md", "---\ntype: Concept\n---\nSee [[old]].\n")
        with self.assertRaises(OkfError):
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
            okf_rename.perform_rename(self.tmp, self._ap("a/old.md"), self._ap("a/new.md"),
                                      apply=True, force=False)
        self.assertTrue(os.path.isfile(self._ap("a/new.md")))
        self.assertIn("[[new]]", self._r("a/src.md"))

    def test_dry_run_makes_no_change_and_reports_it_would_move(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf_rename.perform_rename(self.tmp, self._ap("a/old.md"), self._ap("a/new.md"),
                                      apply=False, force=False)
        self.assertTrue(os.path.isfile(self._ap("a/old.md")))
        self.assertFalse(os.path.isfile(self._ap("a/new.md")))
        self.assertIn("would move", buf.getvalue())

    def test_explicit_verb_prefixes_the_error_message(self):
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            with self.assertRaises(OkfError) as ctx:
                okf_rename.perform_rename(self.tmp, self._ap("a/old.md"), self._ap("a/y.txt"),
                                          apply=False, force=False, verb="archive")
        self.assertEqual(ctx.exception.kind, "invalid_input")
        self.assertTrue(ctx.exception.message.startswith("archive:"))

    def test_default_verb_is_rename(self):
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            with self.assertRaises(OkfError) as ctx:
                okf_rename.perform_rename(self.tmp, self._ap("a/old.md"), self._ap("a/y.txt"),
                                          apply=False, force=False)
        self.assertTrue(ctx.exception.message.startswith("rename:"))

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
            with self.assertRaises(OkfError) as ctx:
                okf_rename.perform_rename(self.tmp, self._ap("a/old.md"), self._ap("a/new.md"),
                                          apply=False, force=False)
        self.assertEqual(ctx.exception.kind, "not_found")
        self.assertEqual(
            "rename: source not found: {}".format(self._ap("a/old.md")),
            ctx.exception.message)

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
            okf_rename.perform_rename(self.tmp, self._ap("_archive/a/deep.md"),
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
            okf_rename.cmd_archive(self.tmp, args)
        return buf.getvalue()

    def _archive_fails(self, path, message, restore=False, apply=False, force=False):
        import contextlib
        import io
        import types
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(OkfError) as ctx:
                okf_rename.cmd_archive(self.tmp, types.SimpleNamespace(
                    path=path, restore=restore, apply=apply, force=force))
        self.assertEqual(ctx.exception.kind, "invalid_input")
        self.assertIn(message, ctx.exception.message)
        return ctx.exception.message

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
            okf_rename.cmd_archive(self.tmp, args)
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
            with self.assertRaises(OkfError) as ctx:
                okf_rename.cmd_archive(self.tmp, types.SimpleNamespace(
                    path=path, restore=restore, apply=apply, force=force))
        self.assertEqual(ctx.exception.kind, "not_found")
        return ctx.exception.message

    # -- SC-02: regression guard on the untouched path, written first ----
    # A missing source with no counterpart anywhere must keep the CURRENT
    # "source not found" message, asserted against the literal string —
    # this has to exist and pass BEFORE the new branch is written, or there
    # is no way to tell whether the untouched path stayed untouched.
    def test_sc02_missing_source_with_no_counterpart_keeps_current_message(self):
        err = self._archive_fails("a/ghost.md")
        self.assertEqual(
            "archive: source not found: {}".format(self._ap("a/ghost.md")),
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
            "_archive/a/old.md (use --restore to bring it back)"
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
            "exists at a/old.md".format(self._ap("_archive/a/old.md")),
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
            okf_rename.cmd_rename(self.tmp, args)
        return buf.getvalue()

    def _rename_fails(self, old, new, apply=False):
        import contextlib
        import io
        import types
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with self.assertRaises(OkfError) as ctx:
                okf_rename.cmd_rename(self.tmp, types.SimpleNamespace(
                    old=old, new=new, apply=apply, force=False))
        self.assertEqual(ctx.exception.kind, "invalid_input")
        return out.getvalue(), ctx.exception.message

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
        okf_rename.cmd_archive(self.tmp, types.SimpleNamespace(
            path="a/old.md", restore=False, apply=True, force=False))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf_rename.cmd_archive(self.tmp, types.SimpleNamespace(
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
        moved, repo, reason = okf_rename._git_mv(catalogue, old, new)
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
            okf_rename.cmd_archive(catalogue, args)
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
            okf_rename.cmd_archive(catalogue, args)
        out = buf.getvalue()

        self.assertIn("moved (fs)", out)
        self.assertIn("not under version control", out)
        # Same repository as --root: unlike the symlinked-bundle cause above,
        # there is no second repository to name — the report must not claim
        # one (point 3: the two causes share a surface but not a report).
        self.assertNotIn("repository differs from --root", out)


@unittest.skipUnless(HAS_GIT, "git not installed")
class RewritePathPreviewEqualsGitDiff(GitPreviewMixin, unittest.TestCase):
    """OKFT-d6an SC-01 — the `--check` preview of rewrite-path, paths relative to its --scan-root
    (a git repository outside the catalogue root), equals the `git diff` after the write run."""

    FILES = {
        "README.md": b"docs live at docs/notes.md today\n" + b"x\n" * 20 + b"and docs/notes.md again\n",
        "src/app.py": b"# see docs/notes.md for details",
        "crlf.txt": b"docs/notes.md\r\nmore\r\n",
        "latin.txt": b"docs/notes.md caf\xe9\n",
    }

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.catalogue = os.path.join(self.tmp, "cat")
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.catalogue)
        os.makedirs(self.repo)

    def test_preview_equals_git_diff_after_write_run(self):
        self.commit_files(self.repo, self.FILES)
        args = ("rewrite-path", "docs/notes.md", "docs/x.md", "--scan-root", self.repo)
        preview = self.assert_preview_equals_git_diff(
            self.repo,
            lambda: self.json_files(self.catalogue, *args, "--check"),
            lambda: self.json_files(self.catalogue, *args))
        self.assertEqual([f["path"] for f in preview], ["README.md", "crlf.txt", "src/app.py"])
        with open(os.path.join(self.repo, "latin.txt"), "rb") as f:
            self.assertEqual(f.read(), self.FILES["latin.txt"])


if __name__ == "__main__":
    unittest.main()
