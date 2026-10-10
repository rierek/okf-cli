#!/usr/bin/env python3
"""Tests for okf-cli.py — stdlib unittest, no deps.

Run: python3 -m unittest test_okf_cli -v
"""
import argparse
import contextlib
import io
import importlib.util
import json
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
from okf import find as okf_find
from okf import find_filters as okf_find_filters
from okf import fts as okf_fts
from okf import index as okf_index
from okf import linkscan as okf_linkscan
from okf import parser_support as okf_parser_support
from okf import semantic as okf_semantic
from okf import sync as okf_sync
from okf_testkit import SyncFixtureMixin, run_find


def _fs_is_case_insensitive():
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "a"), "w").close()
        return os.path.exists(os.path.join(d, "A"))


needs_case_insensitive_fs = unittest.skipUnless(
    _fs_is_case_insensitive(), "braucht case-insensitives Dateisystem (APFS)")
_spec = importlib.util.spec_from_file_location("okf_cli", os.path.join(_HERE, "okf-cli.py"))
okf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(okf)

M0, M1 = okf_catalogue.MARK_START, okf_catalogue.MARK_END


class CheckCommand(unittest.TestCase):
    """T06 — okf-cli check: pluggable (name, severity, check_fn) conformance
    scan. error = §9 hard rules + filename/asset placement (exit 1).
    warning = type registration / English keys / cross-link format."""

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

    def _names(self, entries):
        return [e[0] for e in entries]

    def test_missing_frontmatter_is_error(self):
        self._w("b/x.md", "# X\n\nno frontmatter at all.\n")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertIn("frontmatter-parseable", self._names(errors))
        self.assertNotIn("type-nonempty", self._names(errors))  # not double-flagged

    def test_empty_type_is_error(self):
        self._w("b/x.md", "---\ntype: \ntitle: X\n---\n# X\n")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertIn("type-nonempty", self._names(errors))
        self.assertNotIn("frontmatter-parseable", self._names(errors))

    def test_reserved_file_with_type_is_error(self):
        self._w("b/index.md", "---\ntype: Concept\n---\n# B\n")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertIn("reserved-no-type", self._names(errors))

    def test_filename_forbidden_char_is_error(self):
        self._w("b/weird%name.md", "---\ntype: Concept\n---\n# W\n")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertIn("filename-chars", self._names(errors))

    def test_asset_outside_assets_dir_is_error(self):
        self._w("b/index.md", "# B\n")
        self._w("b/diagram.png", "not a real png")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertIn("asset-placement", self._names(errors))

    def test_asset_inside_assets_dir_is_clean(self):
        self._w("b/index.md", "# B\n")
        self._w("b/assets/diagram.png", "not a real png")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertNotIn("asset-placement", self._names(errors))

    def test_asset_inside_nested_assets_dir_is_clean(self):
        self._w("b/index.md", "# B\n")
        self._w("b/sub/assets/diagram.png", "not a real png")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertNotIn("asset-placement", self._names(errors))

    def test_underscore_prefixed_dir_is_excluded_from_scan(self):
        # mirrors is_bundle_dir's convention: "_"-prefixed dirs are staging,
        # not catalogue content — same exemption applied one level down.
        self._w("b/index.md", "# B\n\nBundle entry with an intro paragraph.\n")
        self._w("b/_intake/raw.md", "# no frontmatter\n")
        self._w("b/_intake/notes.tsv", "col1\tcol2\n")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_unregistered_type_is_warning(self):
        self._w("TYPES.md", "| type | Meaning |\n|---|---|\n| `Concept` | x |\n")
        self._w("b/x.md", "---\ntype: Bogus\ntitle: X\n---\n# X\n")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertIn("type-registered", self._names(warnings))
        self.assertNotIn("type-registered", self._names(errors))

    def test_registered_type_has_no_warning(self):
        self._w("TYPES.md", "| type | Meaning |\n|---|---|\n| `Concept` | x |\n")
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n# X\n")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertNotIn("type-registered", self._names(warnings))

    def test_no_types_md_skips_type_registered_check(self):
        self._w("b/x.md", "---\ntype: AnythingGoes\ntitle: X\n---\n# X\n")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertNotIn("type-registered", self._names(warnings))

    def test_german_frontmatter_key_is_warning(self):
        self._w("b/x.md", "---\ntype: Concept\ntitel: X\n---\n# X\n")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertIn("english-keys", self._names(warnings))

    def test_relative_crosslink_is_warning(self):
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n# X\n\n[Y](y.md)\n")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertIn("crosslink-format", self._names(warnings))

    def test_catalogue_root_crosslink_is_clean(self):
        self._w("b/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n# X\n\n[Y](/b/y.md)\n")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertNotIn("crosslink-format", self._names(warnings))

    def test_reserved_file_relative_link_outside_marker_is_warning(self):
        """D-rx51-01 (OKFT-rx51): a hand-authored relative link in index.md's
        prose, outside the managed `<!-- okf:index -->` block, is a real
        crosslink and must be caught the same as one in a concept file."""
        self._w("b/index.md", "# B\n\nSee [Old](old.md) for background.\n\n"
                              + okf_catalogue.MARK_START + "\n" + okf_catalogue.MARK_END + "\n")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertIn("crosslink-format", self._names(warnings))

    def test_reserved_file_link_inside_marker_is_clean(self):
        """D-rx51-01: the managed block is masked before the scan, so a
        generated (relative-by-convention) link inside it never warns —
        RESERVED files becoming a scan source must not regress the common
        case of an ordinary reindexed index.md."""
        self._w("b/index.md", "# B\n\n" + okf_catalogue.MARK_START + "\n* [X](x.md)\n"
                              + okf_catalogue.MARK_END + "\n")
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n# X\n")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertNotIn("crosslink-format", self._names(warnings))

    def test_cross_bundle_dotdot_link_is_flagged(self):
        """Inverted with the canonical form: check_crosslink_format flags ANY
        relative link now, `../other/y.md` included, because it resolves
        inconsistently and orphans in Obsidian. fix-crosslinks migrates it."""
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n# X\n\n[Y](../other/y.md)\n")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertIn("crosslink-format", self._names(warnings))

    def test_clean_bundle_has_zero_violations(self):
        self._w("TYPES.md", "| type | Meaning |\n|---|---|\n| `Concept` | x |\n")
        self._w("b/index.md", "# B\n\nBundle entry with an intro paragraph.\n\n## Contents\n\n"
                              + okf_catalogue.MARK_START + "\n* [X](x.md)\n" + okf_catalogue.MARK_END + "\n")
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\ntags:\n  - a\n---\n# X\n\n[Y](/b/index.md)\n")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_whole_catalogue_scan_when_no_target(self):
        self._w("b1/x.md", "# X\n\nno frontmatter.\n")
        self._w("b2/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        errors, warnings = okf.run_checks(self.tmp, None)
        self.assertIn("b1/x.md", [e[1] for e in errors])


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


class ResolveCrosslinkTarget(unittest.TestCase):
    """T07 — resolve_crosslink_target reuses bundle_graph's cdir-relative
    normalization formula, gated by a real isfile() check (the safety anchor
    that keeps doc examples pointing at non-existent paths untouched).

    Expectations are catalogue-root-absolute (`/bundle/subdir/concept.md`,
    leading `/` = catalogue root = Obsidian vault root). This class used to
    assert the older bundle-relative form (`/y.md`); the canonical form moved
    on and the tests did not, which is why they had been failing."""

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

    def test_same_dir_target_resolves(self):
        self._w("b/y.md", "")
        got = okf.resolve_crosslink_target(self.tmp, "b", "", "y.md")
        self.assertEqual(got, "/b/y.md")

    def test_subdir_target_resolves_from_bundle_root(self):
        self._w("b/sub/y.md", "")
        got = okf.resolve_crosslink_target(self.tmp, "b", "", "sub/y.md")
        self.assertEqual(got, "/b/sub/y.md")

    def test_target_resolves_relative_to_source_cdir(self):
        self._w("b/sub/y.md", "")
        got = okf.resolve_crosslink_target(self.tmp, "b", "sub", "y.md")
        self.assertEqual(got, "/b/sub/y.md")

    def test_dotslash_target_normalizes(self):
        self._w("b/y.md", "")
        got = okf.resolve_crosslink_target(self.tmp, "b", "", "./y.md")
        self.assertEqual(got, "/b/y.md")

    def test_nonexistent_target_returns_none(self):
        got = okf.resolve_crosslink_target(self.tmp, "b", "", "ghost.md")
        self.assertIsNone(got)

    def test_index_md_target_resolves(self):
        self._w("b/sub/index.md", "")
        got = okf.resolve_crosslink_target(self.tmp, "b", "", "sub/index.md")
        self.assertEqual(got, "/b/sub/index.md")


class RewriteCrosslinksInBody(unittest.TestCase):
    """T08 — rewrite_crosslinks_in_body: same link-detection filter as
    check_crosslink_format, but rewrites resolvable targets in place."""

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

    def test_rewrites_resolvable_same_dir_link(self):
        self._w("b/y.md", "")
        new, changed, unresolved = okf.rewrite_crosslinks_in_body(
            self.tmp, "b", "", "See [Y](y.md) for details.")
        self.assertEqual(new, "See [Y](/b/y.md) for details.")
        self.assertEqual(changed, 1)
        self.assertEqual(unresolved, [])

    def test_preserves_anchor_fragment(self):
        self._w("b/y.md", "")
        new, changed, unresolved = okf.rewrite_crosslinks_in_body(
            self.tmp, "b", "", "[Y](y.md#section)")
        self.assertEqual(new, "[Y](/b/y.md#section)")
        self.assertEqual(changed, 1)

    def test_unresolvable_target_left_untouched(self):
        body = "[Ghost](ghost.md)"
        new, changed, unresolved = okf.rewrite_crosslinks_in_body(self.tmp, "b", "", body)
        self.assertEqual(new, body)
        self.assertEqual(changed, 0)
        self.assertEqual(unresolved, ["ghost.md"])

    def test_already_canonical_link_untouched(self):
        """Idempotence now belongs to the catalogue-root-absolute form: a
        second fix-crosslinks pass must leave a migrated link byte-identical."""
        self._w("b/y.md", "")
        body = "[Y](/b/y.md)"
        new, changed, unresolved = okf.rewrite_crosslinks_in_body(self.tmp, "b", "", body)
        self.assertEqual(new, body)
        self.assertEqual(changed, 0)

    def test_legacy_bundle_relative_link_is_migrated(self):
        """The other half of that rule: `/y.md` was the OLD canonical form
        (leading / = bundle root), so it is legacy input to be rewritten, not
        a link to leave alone. resolve_crosslink_target tries the legacy
        reading first precisely so this migration works."""
        self._w("b/y.md", "")
        new, changed, unresolved = okf.rewrite_crosslinks_in_body(
            self.tmp, "b", "", "[Y](/y.md)")
        self.assertEqual(new, "[Y](/b/y.md)")
        self.assertEqual(changed, 1)

    def test_cross_bundle_dotdot_link_untouched(self):
        body = "[Y](../other-bundle/y.md)"
        new, changed, unresolved = okf.rewrite_crosslinks_in_body(self.tmp, "b", "", body)
        self.assertEqual(new, body)
        self.assertEqual(changed, 0)

    def test_multiple_occurrences_all_rewritten(self):
        self._w("b/y.md", "")
        body = "[Y](y.md) and again [Y2](y.md)"
        new, changed, unresolved = okf.rewrite_crosslinks_in_body(self.tmp, "b", "", body)
        self.assertEqual(new, "[Y](/b/y.md) and again [Y2](/b/y.md)")
        self.assertEqual(changed, 2)

    def test_subdir_relative_link_from_root_rewritten(self):
        self._w("b/sub/y.md", "")
        new, changed, unresolved = okf.rewrite_crosslinks_in_body(
            self.tmp, "b", "", "[Y](sub/y.md)")
        self.assertEqual(new, "[Y](/b/sub/y.md)")
        self.assertEqual(changed, 1)

    def test_link_in_inline_code_is_not_unresolved(self):
        """A link inside backticks is prose about link syntax, not a link —
        Obsidian never resolves it. check_crosslink_format masks code spans
        for exactly this reason; the rewrite path must agree, or the OKF
        documentation bundles report their own examples as broken links."""
        body = "Bundle-relative form: `[customers](/tables/customers.md)`."
        new, changed, unresolved = okf.rewrite_crosslinks_in_body(self.tmp, "b", "", body)
        self.assertEqual(new, body)
        self.assertEqual(changed, 0)
        self.assertEqual(unresolved, [])

    def test_resolvable_link_in_fence_is_not_rewritten(self):
        """The sharper half: a fenced example whose path happens to resolve
        must stay byte-identical. Rewriting it would silently mutate the
        documentation example it illustrates."""
        self._w("b/y.md", "")
        body = "```markdown\n[Y](y.md)\n```"
        new, changed, unresolved = okf.rewrite_crosslinks_in_body(self.tmp, "b", "", body)
        self.assertEqual(new, body)
        self.assertEqual(changed, 0)
    def test_four_backtick_fence_blocks_are_masked(self):
        """Verify that code fences with 4+ backticks are handled correctly.
        Markdown allows any number of backticks >= 3. The regex must match
        the opening fence marker and expect the same number of backticks
        to close the block."""
        self._w("b/y.md", "")
        body = "````markdown\n[Y](y.md)\n````\n\nAnother ```` fence with 4 tildes:\n~~~~\n[Z](z.md)\n~~~~"
        new, changed, unresolved = okf.rewrite_crosslinks_in_body(self.tmp, "b", "", body)
        # Links inside fences should not be rewritten
        self.assertEqual(new, body)
        self.assertEqual(changed, 0)
        self.assertEqual(unresolved, [])

    def test_five_backtick_fence_blocks_are_masked(self):
        """Test 5-backtick fences (common for escaping code examples that
        themselves contain triple-backtick examples)."""
        self._w("b/inner.md", "")
        body = "`````\n[Y](inner.md)\n`````"
        new, changed, unresolved = okf.rewrite_crosslinks_in_body(self.tmp, "b", "", body)
        self.assertEqual(new, body)
        self.assertEqual(changed, 0)
        self.assertEqual(unresolved, [])

    def test_multiple_fence_styles_same_document(self):
        """Verify that various fence styles don't interfere with each other."""
        self._w("b/a.md", "")
        self._w("b/b.md", "")
        body = "```\n[A](a.md)\n```\n\n````\n[B](b.md)\n````\n\n~~~\n[A](a.md)\n~~~"
        new, changed, unresolved = okf.rewrite_crosslinks_in_body(self.tmp, "b", "", body)
        self.assertEqual(new, body)
        self.assertEqual(changed, 0)
        self.assertEqual(unresolved, [])


class FixCrosslinksCommand(unittest.TestCase):
    """T09 — fix_crosslinks: file-level orchestration, frontmatter untouched,
    reserved files never rewritten (D-rx51-01 kept this unchanged even though
    check_crosslink_format now scans RESERVED files as a source), dry-run
    writes nothing."""

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

    def test_writes_rewritten_files_by_default(self):
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n[Y](y.md)\n")
        self._w("b/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        touched, unresolved = okf.fix_crosslinks(self.tmp, "b")
        self.assertEqual(len(touched), 1)
        self.assertEqual(unresolved, [])
        content = self._r("b/x.md")
        self.assertIn("[Y](/b/y.md)", content)
        self.assertTrue(content.startswith("---\ntype: Concept\ntitle: X\n---\n"))

    def test_dry_run_does_not_write(self):
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n[Y](y.md)\n")
        self._w("b/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        before = self._r("b/x.md")
        touched, unresolved = okf.fix_crosslinks(self.tmp, "b", dry_run=True)
        self.assertEqual(len(touched), 1)
        self.assertEqual(self._r("b/x.md"), before)

    def test_reserved_file_is_not_rewritten(self):
        self._w("b/index.md", "# B\n\n[X](x.md)\n")
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n# X\n")
        touched, unresolved = okf.fix_crosslinks(self.tmp, "b")
        self.assertNotIn("b/index.md", [t[0] for t in touched])
        self.assertIn("(x.md)", self._r("b/index.md"))

    def test_unresolved_links_are_reported(self):
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n[Ghost](ghost.md)\n")
        touched, unresolved = okf.fix_crosslinks(self.tmp, "b")
        self.assertEqual(touched, [])
        self.assertIn(("b/x.md", "ghost.md"), unresolved)

    def test_include_reserved_rewrites_outside_marker_only(self):
        block = "<!-- okf:index -->\n* [Y](y.md)\n<!-- /okf:index -->"
        self._w("b/index.md",
                "# B\n\n[Rel](y.md)\n\n[Legacy](/y.md)\n\n" + block + "\n")
        self._w("b/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        touched, unresolved = okf.fix_crosslinks(self.tmp, "b", include_reserved=True)
        self.assertIn("b/index.md", [t[0] for t in touched])
        content = self._r("b/index.md")
        self.assertIn(block, content)
        self.assertIn("[Rel](/b/y.md)", content)
        self.assertIn("[Legacy](/b/y.md)", content)

    def test_include_reserved_rewrites_reserved_file_without_marker(self):
        self._w("b/index.md", "# B\n\n[Y](y.md)\n")
        self._w("b/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        touched, unresolved = okf.fix_crosslinks(self.tmp, "b", include_reserved=True)
        self.assertIn("b/index.md", [t[0] for t in touched])
        self.assertIn("[Y](/b/y.md)", self._r("b/index.md"))

    def test_include_reserved_does_not_change_non_reserved_behavior(self):
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n[Y](y.md)\n")
        self._w("b/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        touched, unresolved = okf.fix_crosslinks(self.tmp, "b", include_reserved=True)
        self.assertEqual(len(touched), 1)
        self.assertIn("[Y](/b/y.md)", self._r("b/x.md"))

    def test_include_reserved_protects_unterminated_marker(self):
        self._w("b/index.md", "[Y](y.md)\n\n<!-- okf:index -->\n[Z](y.md)\n")
        self._w("b/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        touched, unresolved = okf.fix_crosslinks(self.tmp, "b", include_reserved=True)
        content = self._r("b/index.md")
        self.assertIn("[Y](/b/y.md)", content)
        self.assertIn("<!-- okf:index -->\n[Z](y.md)\n", content)

    def test_include_reserved_dry_run_reports_without_writing(self):
        self._w("b/index.md", "[Y](y.md)\n")
        self._w("b/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        before = self._r("b/index.md")
        touched, unresolved = okf.fix_crosslinks(
            self.tmp, "b", dry_run=True, include_reserved=True)
        self.assertIn("b/index.md", [t[0] for t in touched])
        self.assertEqual(self._r("b/index.md"), before)

    def test_include_reserved_ignores_index_exempt_marker(self):
        self._w("b/index.md", "<!-- okf:index-exempt -->\n[Y](y.md)\n")
        self._w("b/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        touched, unresolved = okf.fix_crosslinks(self.tmp, "b", include_reserved=True)
        self.assertIn("b/index.md", [t[0] for t in touched])
        self.assertIn("[Y](/b/y.md)", self._r("b/index.md"))


class BundleKeyDoesNotNarrowResolution(unittest.TestCase):
    """Acceptance guard (OKFT-n8xz, test 5) — the resolution call sites keep
    seeing the WIDE bundle set even when `.okf.toml` declares a narrower
    `bundle` key: a wikilink to a concept outside the declared bundle must
    stay resolvable. Narrowing the index/search corpus must not narrow
    resolution, or the exact defect
    okf-tools-okf/archive-lifecycle/active-beats-archived-in-wikilink-resolution
    describes for archiving recurs here for scaffolding."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "declared-bundle"))
        os.makedirs(os.path.join(self.tmp, "other-scaffolding"))
        with open(os.path.join(self.tmp, ".okf.toml"), "w", encoding="utf-8") as f:
            f.write('bundle = "declared-bundle"\n')
        with open(os.path.join(self.tmp, "declared-bundle", "source.md"),
                  "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: Source\n---\n"
                    "See [[outside]].\n")
        with open(os.path.join(self.tmp, "other-scaffolding", "outside.md"),
                  "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: Outside\n---\nbody\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_wikilink_to_a_concept_outside_the_declared_bundle_resolves(self):
        index = okf.build_concept_basename_index(self.tmp)
        status, candidates = okf.resolve_wikilink(
            index, "declared-bundle/source.md", "outside")
        self.assertEqual(status, "resolved")
        self.assertEqual(candidates, ["/other-scaffolding/outside.md"])



class WikilinkSourceOutsideDeclaredBundle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "declared-bundle"))
        os.makedirs(os.path.join(self.tmp, "topic-folder"))
        with open(os.path.join(self.tmp, ".okf.toml"), "w", encoding="utf-8") as f:
            f.write('bundle = "declared-bundle"\n')
        with open(os.path.join(self.tmp, "topic-folder", "source.md"),
                  "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: Source\n---\nSee [[target]].\n")
        with open(os.path.join(self.tmp, "declared-bundle", "target.md"),
                  "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: Target\n---\nbody\n")

    def test_wikilink_from_outside_the_declared_bundle_resolves(self):
        index = okf.build_concept_basename_index(self.tmp)
        with open(os.path.join(self.tmp, "topic-folder", "source.md"),
                  encoding="utf-8") as f:
            records = okf.resolve_wikilink_records(
                index, okf.parse_wikilinks(f.read(), "topic-folder/source.md"))
        self.assertEqual(records[0]["status"], "resolved")
        self.assertEqual(records[0]["candidates"], ["/declared-bundle/target.md"])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

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


class CheckAndWikilinksStayWideWithDeclaredBundle(unittest.TestCase):
    """Review 2026-08-13 I01 — the required behavioural guard. A docs root
    with a declared `bundle` key, a real violation sitting in an UNDECLARED
    directory, and the assertion that an unscoped `check`/`wikilinks` run
    still reports it. This is the reviewer's own experiment, reproduced as a
    test: unscoped `check` against a copy of the real okf-tools/docs went
    from 33 reported violations to 0 once resolve_scopes() narrowed its
    default. `BundleKeyDoesNotNarrowResolution` alone did not catch that —
    it only exercises `build_concept_basename_index`, never the
    `run_checks`/`scan_wikilinks` traversal through `resolve_scopes`."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "declared-bundle"))
        os.makedirs(os.path.join(self.tmp, "other-scaffolding"))
        with open(os.path.join(self.tmp, ".okf.toml"), "w", encoding="utf-8") as f:
            f.write('bundle = "declared-bundle"\n')
        # clean concept in the declared bundle
        with open(os.path.join(self.tmp, "declared-bundle", "clean.md"),
                  "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: Clean\n---\nSee "
                    "[[still-clean]].\n")
        with open(os.path.join(self.tmp, "declared-bundle", "still-clean.md"),
                  "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: Still Clean\n---\nbody\n")
        # a REAL violation, sitting entirely outside the declared bundle: no
        # parseable frontmatter at all (check_fm_parseable) AND a wikilink to
        # a target that exists nowhere in the tree (resolve_wikilink).
        with open(os.path.join(self.tmp, "other-scaffolding", "bad.md"),
                  "w", encoding="utf-8") as f:
            f.write("no frontmatter here.\n\nSee [[does-not-exist-anywhere]].\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_unscoped_check_still_reports_the_violation_outside_the_bundle(self):
        errors, _warnings = okf.run_checks(self.tmp, None)
        rels = [rel for _name, rel, _msg in errors]
        self.assertIn("other-scaffolding/bad.md", rels)

    def test_unscoped_wikilinks_still_reports_the_unresolved_link(self):
        links = okf.scan_wikilinks(self.tmp, None)
        unresolved = [r for r in links if r["status"] == "unresolved"]
        self.assertTrue(
            any(r["source"] == "other-scaffolding/bad.md" for r in unresolved),
            "expected an unresolved wikilink reported from "
            "other-scaffolding/bad.md, got: {}".format(unresolved))

class WikilinkCheckedBundleConfigGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        for directory in ("declared-bundle", "topic-folder"):
            os.makedirs(os.path.join(self.tmp, directory))
        with open(os.path.join(self.tmp, ".okf.toml"), "w", encoding="utf-8") as f:
            f.write('bundle = "declared-bundle"\n'
                    'wikilink_checked_bundles = ["declared-bundle"]\n')
        for directory in ("declared-bundle", "topic-folder"):
            with open(os.path.join(self.tmp, directory, "source.md"),
                      "w", encoding="utf-8") as f:
                f.write("---\ntype: Concept\ntitle: Source\n---\nSee [[dead-link]].\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_gate_checks_declared_bundle_but_ignores_topic_folder(self):
        errors, warnings = okf.run_checks(self.tmp, None)
        findings = errors + warnings
        paths = [path for name, path, _message in findings
                 if name == "wikilink-resolvable"]
        self.assertIn("declared-bundle/source.md", paths)
        self.assertNotIn("topic-folder/source.md", paths)


class ConfigAwareTypes(unittest.TestCase):
    """type-registered check resolves TYPES.md via .okf.toml types_source,
    so a repo bundle points at the central catalogue's TYPES.md (no local copy)."""

    def setUp(self):
        import tempfile
        self.central = tempfile.mkdtemp()
        self.repo = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.central, ignore_errors=True)
        shutil.rmtree(self.repo, ignore_errors=True)

    def _w(self, base, rel, text):
        ap = os.path.join(base, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(text)

    def test_central_types_source_flags_unregistered(self):
        # central TYPES.md registers only `Concept`; repo has NO local TYPES.md
        self._w(self.central, "TYPES.md", "| type | Meaning |\n|---|---|\n| `Concept` | x |\n")
        self._w(self.repo, ".okf.toml",
                'types_source = "{}"\n'.format(os.path.join(self.central, "TYPES.md")))
        self._w(self.repo, "b/x.md", "---\ntype: Bogus\ntitle: X\n---\n# X\n")
        errors, warnings = okf.run_checks(self.repo, "b")
        self.assertIn("type-registered", [w[0] for w in warnings])

    def test_central_types_source_accepts_registered(self):
        self._w(self.central, "TYPES.md",
                "| type | Meaning |\n|---|---|\n| `Glossary` | x |\n")
        self._w(self.repo, ".okf.toml",
                'types_source = "{}"\n'.format(os.path.join(self.central, "TYPES.md")))
        self._w(self.repo, "b/g.md", "---\ntype: Glossary\ntitle: G\n---\n# G\n")
        errors, warnings = okf.run_checks(self.repo, "b")
        self.assertNotIn("type-registered", [w[0] for w in warnings])

    def test_explicit_types_source_arg_overrides_config(self):
        self._w(self.central, "TYPES.md", "| type | Meaning |\n|---|---|\n| `Concept` | x |\n")
        self._w(self.repo, "b/x.md", "---\ntype: Concept\ntitle: X\n---\n# X\n")
        errors, warnings = okf.run_checks(
            self.repo, "b", types_source=os.path.join(self.central, "TYPES.md"))
        self.assertNotIn("type-registered", [w[0] for w in warnings])


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


class TagRegistryGate(unittest.TestCase):
    """Closed-tag-vocabulary: tag-registered check + register_tags/load_tags.
    TAGS.md is the allow-list; unknown tags warn (escalate to error via --strict).
    Absent TAGS.md → no-op."""

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

    def _names(self, entries):
        return [e[0] for e in entries]

    def test_no_tags_md_is_noop(self):
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\ntags:\n  - anything\n---\n# X\n")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertNotIn("tag-registered", self._names(warnings))
        self.assertIsNone(okf_catalogue.load_tags(self.tmp))

    def test_unknown_tag_warns(self):
        self._w("TAGS.md", okf_catalogue.TAGS_HEADER + "| `known` |  |\n")
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\ntags:\n  - known\n  - novel\n---\n# X\n")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertIn("tag-registered", self._names(warnings))
        msgs = [m for n, _p, m in warnings if n == "tag-registered"]
        self.assertTrue(any("novel" in m for m in msgs))
        self.assertFalse(any("known" in m for m in msgs))

    def test_all_known_tags_clean(self):
        self._w("TAGS.md", okf_catalogue.TAGS_HEADER + "| `a` |  |\n| `b` |  |\n")
        self._w("c/x.md", "---\ntype: Concept\ntitle: X\ntags:\n  - a\n  - b\n---\n# X\n")
        errors, warnings = okf.run_checks(self.tmp, "c")
        self.assertNotIn("tag-registered", self._names(warnings))

    def test_register_creates_and_appends(self):
        added, already = okf_catalogue.register_tags(self.tmp, [("zebra", "z"), ("alpha", "a")])
        self.assertEqual(set(added), {"zebra", "alpha"})
        self.assertEqual(already, [])
        self.assertEqual(okf_catalogue.load_tags(self.tmp), {"zebra", "alpha"})
        # idempotent + casefold-sorted output (alpha before zebra)
        added2, already2 = okf_catalogue.register_tags(self.tmp, [("alpha", "other"), ("mid", "m")])
        self.assertEqual(added2, ["mid"])
        self.assertEqual(already2, ["alpha"])
        body = open(os.path.join(self.tmp, "TAGS.md"), encoding="utf-8").read()
        self.assertLess(body.index("`alpha`"), body.index("`mid`"))
        self.assertLess(body.index("`mid`"), body.index("`zebra`"))
        self.assertIn("| `alpha` | a |", body)  # existing description is kept, not overwritten

    def test_register_preserves_descriptions(self):
        self._w("TAGS.md", okf_catalogue.TAGS_HEADER + "| `a` | keep me |\n")
        okf_catalogue.register_tags(self.tmp, [("b", "bee")])
        body = open(os.path.join(self.tmp, "TAGS.md"), encoding="utf-8").read()
        self.assertIn("| `a` | keep me |", body)
        self.assertIn("| `b` | bee |", body)

    def test_description_limit_is_150_and_nothing_is_written_on_refusal(self):
        okf_catalogue.register_tags(self.tmp, [("ok", "x" * 150)])
        for bad in ("x" * 151, "", "   ", "a|b", "a\nb"):
            with self.assertRaises(ValueError):
                okf_catalogue.register_tags(self.tmp, [("fine", "good"), ("bad", bad)])
        self.assertEqual(okf_catalogue.load_tags(self.tmp), {"ok"})

    def test_register_option_needs_tag_and_description(self):
        ap = okf.build_parser()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                ap.parse_args(["tags", "--register", "only-a-tag"])
        ns = ap.parse_args(["tags", "--register", "a", "da", "--register", "b", "db"])
        self.assertEqual(ns.register, [["a", "da"], ["b", "db"]])


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


def _cli(root, *argv):
    """Drive the REAL cli/okf-cli.py as a subprocess. The `command:` acceptance
    criteria of docs/wikilink-awareness/SPEC.md are written against the shell
    surface (exit code, stdout shape), which an in-process call cannot pin."""
    import subprocess
    import sys
    return subprocess.run(
        [sys.executable, os.path.join(_HERE, "okf-cli.py"), "--root", root] + list(argv),
        capture_output=True, text=True)


class WikilinkFixtureMixin:
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

    def _index(self):
        return okf.build_concept_basename_index(self.tmp)

    def _status(self, source_rel, page):
        return okf.resolve_wikilink(self._index(), source_rel, page)


class WikilinkExtraction(unittest.TestCase):
    """REQ-01 — one record per [[…]] occurrence, with page/alias/suffix/embed
    split out and the region tagged. Pure text parse, no filesystem."""

    def test_shapes(self):
        recs = okf.parse_wikilinks(
            "[[a]] [[a|b]] [[a#h]] [[a#^blk]] ![[a]] [[dir/a]]")
        self.assertEqual([r["page"] for r in recs],
                         ["a", "a", "a", "a", "a", "dir/a"])
        self.assertEqual([r["alias"] for r in recs],
                         [None, "b", None, None, None, None])
        self.assertEqual([r["suffix"] for r in recs],
                         [None, None, "h", "^blk", None, None])
        self.assertEqual([r["embed"] for r in recs],
                         [False, False, False, False, True, False])

    def test_region_is_tagged(self):
        recs = okf.parse_wikilinks(
            '---\ntype: Concept\nrelated:\n  - "[[a]]"\n---\nProse with [[b]].\n')
        self.assertEqual([(r["region"], r["page"]) for r in recs],
                         [("frontmatter", "a"), ("body", "b")])

    def test_code_spans_are_not_links(self):
        recs = okf.parse_wikilinks(
            "```\n[[x]]\n```\n\n~~~\n[[x]]\n~~~\n\nand `[[x]]` inline.\n")
        self.assertEqual(recs, [])

    def test_md_suffix_is_stripped(self):
        self.assertEqual([r["page"] for r in okf.parse_wikilinks("[[a.md]] [[a]]")],
                         ["a", "a"])
        self.assertEqual([r["page"] for r in okf.parse_wikilinks("[[8.3.3]]")],
                         ["8.3.3"])

    def test_unclosed_is_not_a_link(self):
        for text in ("[[a", "[a]]", "[[a\n]]"):
            self.assertEqual(okf.parse_wikilinks(text), [], text)

    def test_raw_excludes_the_embed_marker(self):
        """`raw` is a substitutable link token, so it starts at `[[` — the `!`
        is carried by `embed` instead. The report format depends on it."""
        rec = okf.parse_wikilinks("![[a|Label]]")[0]
        self.assertEqual(rec["raw"], "[[a|Label]]")
        self.assertTrue(rec["embed"])

    def test_in_file_anchor_is_not_a_link(self):
        """`[[#Heading]]` addresses a position in the current file, not another
        concept — a record for it would be reported unresolved forever."""
        self.assertEqual(okf.parse_wikilinks("[[#Heading]] and [[#^blk]]"), [])

    def test_hash_in_an_alias_is_not_a_suffix(self):
        """Obsidian's `#` binds to the page part. `C#` and `bug #42` are
        realistic alias text and must survive as alias, not be split."""
        rec = okf.parse_wikilinks("[[dotnet|C#]]")[0]
        self.assertEqual((rec["page"], rec["alias"], rec["suffix"]), ("dotnet", "C#", None))
        rec = okf.parse_wikilinks("[[issue|bug #42]]")[0]
        self.assertEqual((rec["alias"], rec["suffix"]), ("bug #42", None))

    def test_empty_suffix_is_none_not_empty_string(self):
        self.assertIsNone(okf.parse_wikilinks("[[a#]]")[0]["suffix"])

    def test_page_part_is_stripped(self):
        self.assertEqual(okf.parse_wikilinks("[[ a ]]")[0]["page"], "a")

    def test_comments_are_not_links(self):
        """Obsidian excludes `%%`-commented text from its link index, and an
        HTML comment is never rendered at all."""
        recs = okf.parse_wikilinks(
            "<!-- TODO revisit [[a]] -->\n%% draft: [[b]] %%\nreal [[c]]\n")
        self.assertEqual([r["page"] for r in recs], ["c"])

    def test_indented_code_block_is_not_a_link(self):
        """A 4-space-indented block is a code block that the fence/backtick
        masker does not see. Rewriting inside one corrupts a documentation
        sample, so the wikilink mask has to cover it."""
        recs = okf.parse_wikilinks("Example:\n\n    Use [[a]] in a note.\n\nEnd.\n")
        self.assertEqual(recs, [])

    def test_leading_thematic_rule_does_not_expose_a_fence(self):
        """A body whose first line is `---` is classified as frontmatter by
        split_frontmatter's arithmetic, which _frontmatter_end mirrors. That
        region must be masked too, or a fenced example inside it becomes a
        rewritable link."""
        recs = okf.parse_wikilinks(
            "---\n\nIntro\n\n```\nexample: [[a]]\n```\n\n---\n\nreal body\n")
        self.assertEqual(recs, [])

    def test_list_continuation_is_not_code(self):
        """Indentation alone is not a code block — the same shape is markdown's
        list-continuation form, and Obsidian indexes links in it."""
        recs = okf.parse_wikilinks("- bullet\n\n    A continuation with [[a]].\n")
        self.assertEqual([r["page"] for r in recs], ["a"])

    def test_comment_regexes_do_not_span_two_comments(self):
        """A greedy comment pattern would swallow everything between the first
        opener and the last closer, hiding every link in between."""
        recs = okf.parse_wikilinks(
            "%% one %%\nlive [[a]]\n%% two %%\n"
            "<!-- three -->\nlive [[b]]\n<!-- four -->\n")
        self.assertEqual([r["page"] for r in recs], ["a", "b"])

    def test_fence_pattern_does_not_span_two_fences(self):
        """A greedy fence pattern reaches from the first opener to the last
        closer and swallows every link in the prose between them."""
        recs = okf.parse_wikilinks(
            "```\nfirst\n```\n\nlive [[a]]\n\n```\nsecond\n```\n")
        self.assertEqual([r["page"] for r in recs], ["a"])

    def test_comment_inside_a_fence_does_not_break_the_fence(self):
        """One alternation matched left to right: whichever construct opens
        first owns the span, so a `%%` inside a fence cannot end it early."""
        self.assertEqual(
            okf.parse_wikilinks("```\n%% x %%\n[[a]]\n```\n"), [])

    def test_frontmatter_indentation_is_structure_not_code(self):
        """The one body rule that must not apply to YAML: a block list under a
        blank line is valid YAML and looks exactly like an indented code block.
        Inline code IS masked here — see test_thematic_rule_region_gets_body_rules
        for why exempting it cost more than it bought."""
        recs = okf.parse_wikilinks(
            '---\ntype: Concept\nrelated:\n\n    - "[[b]]"\n    - "[[c]]"\n---\n# X\n')
        self.assertEqual([(r["region"], r["page"]) for r in recs],
                         [("frontmatter", "b"), ("frontmatter", "c")])

    def test_indented_line_without_a_blank_line_is_not_code(self):
        """A code block needs a blank line to open it. Without that rule every
        continuation line in a wrapped paragraph becomes a dead zone."""
        recs = okf.parse_wikilinks("Some prose\n    continued with [[a]] indented\n")
        self.assertEqual([r["page"] for r in recs], ["a"])

    def test_mask_preserves_length_so_spans_address_the_original(self):
        """The span each record carries is what a rewrite splices on. If the
        mask changed length the offsets would point at the wrong bytes."""
        text = "---\ntype: Concept\n---\n`code` and [[a]] and <!-- c -->\n"
        self.assertEqual(len(okf_linkscan.wikilink_scan_text(text)), len(text))
        a, b = okf.parse_wikilinks(text)[0]["span"]
        self.assertEqual(text[a:b], "[[a]]")

    def test_four_backtick_fence_masks_its_contents(self):
        """A regex pairs backtick runs left to right with no notion of line
        start or fence width, so one prose ``` mention or a 4-backtick fence
        shifted every later pairing by one and left a real code block exposed
        to the rewriter. One live catalogue file carried exactly this shape."""
        self.assertEqual(okf.parse_wikilinks(
            "Use ``` to open a fence.\n\n````\nS = \"[[a]]\"\n````\n"), [])
        self.assertEqual(okf.parse_wikilinks(
            "````\n```\nnested [[a]]\n```\n````\n"), [])

    def test_fence_closing_rules(self):
        """Each closing condition separately: a closer must be at least as wide
        as its opener, must use the same character, and must carry nothing but
        the marker. Any one of them dropped and a fence ends early, exposing
        prose-looking code to the rewriter."""
        # a narrower run does not close a wider fence
        self.assertEqual(okf.parse_wikilinks("````\n```\n[[a]]\n````\n"), [])
        # a tilde run does not close a backtick fence
        self.assertEqual(okf.parse_wikilinks("```\n[[a]]\n~~~\n[[b]]\n```\n"), [])
        # a closer carrying an info string does not close
        self.assertEqual(okf.parse_wikilinks("```\n``` end\n[[a]]\n```\n"), [])
        # a wider run does close a narrower fence
        recs = okf.parse_wikilinks("```\ncode\n````\n\nlive [[a]]\n")
        self.assertEqual([r["page"] for r in recs], ["a"])

    def test_indented_fence_is_recognised(self):
        """Up to three spaces of indent still opens a fence (CommonMark)."""
        self.assertEqual(okf.parse_wikilinks("   ```\n   [[a]]\n   ```\n"), [])

    def test_tab_indented_code_masks(self):
        self.assertEqual(okf.parse_wikilinks("intro\n\n\tcode [[a]] here\n"), [])

    def test_indented_first_line_is_not_code(self):
        """No blank line can precede line 0, so an indented opening line is
        prose (or YAML), never a code block."""
        recs = okf.parse_wikilinks("    [[a]] on the first line\n")
        self.assertEqual([r["page"] for r in recs], ["a"])

    def test_wikilink_pattern_rejects_newlines_and_brackets(self):
        """Load-bearing: a token containing a newline can never be found again
        by a later scan, so a rename must not be able to produce one."""
        self.assertEqual(okf.parse_wikilinks("[[a\nb]]"), [])
        self.assertEqual(okf.parse_wikilinks("[[a[b]]"), [])

    def test_empty_frontmatter_block_is_frontmatter(self):
        recs = okf.parse_wikilinks("---\n---\nBody [[a]]\n")
        self.assertEqual([(r["region"], r["page"]) for r in recs], [("body", "a")])

    def test_empty_frontmatter_block_still_bounds_the_region(self):
        """`---\\n---` is an empty head, not a thematic rule. The region label of
        what follows is `body` either way, so only the BOUNDARY shows the
        difference — and the boundary is what decides which mask the bytes
        before it get. Asserting the label alone left this unpinned."""
        self.assertTrue(okf_linkscan.is_yaml_frontmatter_block(""))
        self.assertEqual(okf_linkscan.wikilink_regions("---\n---\n\n[[A]]\n")[0],
                         ("frontmatter", 0, 7))

    def test_indented_fence_in_a_block_scalar_keeps_the_block_yaml(self):
        """An indented fence may be the content of a YAML block scalar.
        Rejecting the whole block for it hid every link property in the file.

        The indent has to be one FENCE_START_RE can see (up to three spaces): a
        four-space fence never matches the pattern at all, so a fixture built
        that way passes without the guard existing."""
        recs = okf.parse_wikilinks(
            '---\nexample: |\n  ```\n  code\n  ```\nrelated: "[[b]]"\n---\n# X\n')
        self.assertEqual([(r["region"], r["page"]) for r in recs],
                         [("frontmatter", "b")])
        recs = okf.parse_wikilinks(
            '---\nexample: |\n    ```\n    code\n    ```\nrelated:\n\n'
            '    - "[[b]]"\n---\n# X\n')
        self.assertEqual([(r["region"], r["page"]) for r in recs],
                         [("frontmatter", "b")])

    def test_unindented_continuation_line_keeps_the_block_yaml(self):
        """A plain scalar continued on an unindented line is sloppy YAML but
        common here — 432 qm-wiki files carry a multi-line German description
        that way. Requiring EVERY line to read as YAML reclassified them as body
        and shifted 555 links between regions; the FIRST line decides."""
        recs = okf.parse_wikilinks(
            '---\ndescription: Eine Beschreibung,\n'
            'die hier unindentiert weitergeht\ntags:\n  - x\n'
            'related:\n  - "[[X]]"\n---\nBody [[B]].\n')
        self.assertEqual([(r["region"], r["page"]) for r in recs],
                         [("frontmatter", "X"), ("body", "B")])

    def test_indented_first_line_of_a_file_is_not_code(self):
        """An indented run opens a code block only after a blank line. Reading
        the predecessor of line 0 wraps to the LAST line, so a file ending in a
        blank line would open a phantom block on its own first line and drop the
        link — which is why line 0 is excluded outright."""
        recs = okf.parse_wikilinks("    [[A]]\nprose\n\n")
        self.assertEqual([r["page"] for r in recs], ["A"])

    def test_md_suffix_is_stripped_case_insensitively(self):
        self.assertEqual(okf.parse_wikilinks("[[Old.MD]]")[0]["page"], "Old")

    def test_unclosed_fence_runs_to_end_of_file(self):
        """Obsidian renders an unterminated fence as code to EOF, so the
        rewriter must not treat what follows as prose."""
        self.assertEqual(okf.parse_wikilinks("intro\n\n```\ncode [[a]]\n"), [])

    def test_info_string_with_a_backtick_is_not_a_fence(self):
        recs = okf.parse_wikilinks("``` not `a` fence\nstill prose [[a]]\n")
        self.assertEqual([r["page"] for r in recs], ["a"])

    def test_thematic_rule_region_gets_body_rules(self):
        """A head that is not YAML is body text: inline code and indented code
        in it must mask, or the rewriter edits a documentation sample."""
        self.assertEqual(okf.parse_wikilinks(
            "---\n\nWrite `[[a]]` to link.\n\n---\n\nTail.\n"), [])
        self.assertEqual(okf.parse_wikilinks(
            "---\n\nIntro.\n\n    code sample: [[a]]\n\n---\n\nTail.\n"), [])

    def test_yaml_block_with_umlaut_and_colon_keys_is_frontmatter(self):
        """`Übersicht … ISO 9001:2015:` is a real key in this catalogue; an
        ASCII-only key pattern rejected 432 files and pushed their link
        properties into the body region under body masking rules."""
        recs = okf.parse_wikilinks(
            '---\nQualitätsmanagement Grundlagen: "[[a]]"\n'
            'Übersicht dokumentierter Informationen ISO 9001:2015:\n'
            '  - "[[b]]"\n---\n# X\n')
        self.assertEqual([(r["region"], r["page"]) for r in recs],
                         [("frontmatter", "a"), ("frontmatter", "b")])

    def test_nested_dead_zone_does_not_leak_into_raw(self):
        """`raw` is cut from the original text, so a masked span inside the
        brackets cannot put NUL bytes into the record or break `text[span] ==
        raw` — which every rewrite depends on."""
        for text in ("[[a`x`b]]", "[[a<!--c-->b]]", "[[o%%z%%ld]]"):
            recs = okf.parse_wikilinks(text)
            self.assertTrue(recs, text)
            for r in recs:
                self.assertNotIn("\x00", r["raw"], text)
                self.assertEqual(text[r["span"][0]:r["span"][1]], r["raw"], text)

    def test_region_boundary_is_exclusive_at_fm_end(self):
        """The first body byte must be body: an off-by-one here mislabels the
        region and, with the two masks differing, changes what is even seen."""
        text = "---\na: 1\n---[[y]]\n"
        self.assertEqual([r["region"] for r in okf.parse_wikilinks(text)], ["body"])

    def test_inline_code_needs_content(self):
        recs = okf.parse_wikilinks("a `` [[x]] `` b\n")
        self.assertEqual(recs, [])

    def test_nested_list_continuation_is_not_code(self):
        recs = okf.parse_wikilinks("- a\n  - b\n\n      deep [[x]]\n")
        self.assertEqual([r["page"] for r in recs], ["x"])

    def test_second_indented_paragraph_after_a_list_is_not_code(self):
        recs = okf.parse_wikilinks("- item\n\n    cont\n\n    more [[x]]\n")
        self.assertEqual([r["page"] for r in recs], ["x"])

    def test_indented_block_after_two_blank_lines_is_still_list_continuation(self):
        recs = okf.parse_wikilinks("- item\n\n\n    [[x]]\n")
        self.assertEqual([r["page"] for r in recs], ["x"])

    def test_indented_code_span_stops_at_the_last_indented_line(self):
        """A trailing blank line belongs to the prose after the block, not to
        the block. This cannot cost a link: the span already ends before the
        first line that is neither blank nor indented, so the trim only ever
        crosses whitespace — 40 000 fuzzed documents cannot tell the trimmed
        span from the untrimmed one. Kept for the offsets it reports, not for a
        masking difference."""
        recs = okf.parse_wikilinks("intro\n\n    code\n   \n[[x]]\n")
        self.assertEqual([r["page"] for r in recs], ["x"])

    def test_blank_line_inside_an_indented_block_does_not_end_it(self):
        self.assertEqual(okf.parse_wikilinks("intro\n\n    a\n\n    b [[x]]\n"), [])

    def test_fence_in_a_key_like_block_still_means_body(self):
        """A block can open with a real `key:` line and still be body text with
        a fence in it. Only the fence check catches that, and it decides which
        mask the prose AFTER the fence gets."""
        recs = okf.parse_wikilinks(
            "---\ntype: Concept\n```\nf\n```\nSee `[[a]]` here\n---\nTail\n")
        self.assertEqual(recs, [])

    def test_tilde_fence_in_a_key_like_block_still_means_body(self):
        """A tilde fence is as valid as a backtick one in CommonMark. Matching
        only backticks let an unindented `~~~` block sit inside a key-like head
        and the whole thing be judged YAML — frontmatter masking over prose."""
        recs = okf.parse_wikilinks(
            "---\nNote: a line that reads like a key\n~~~\nsample\n~~~\n"
            "and [[X]] here\n---\nBody [[B]].\n")
        self.assertEqual([(r["region"], r["page"]) for r in recs],
                         [("body", "X"), ("body", "B")])

    def test_percent_comment_in_frontmatter_is_masked(self):
        self.assertEqual(okf.parse_wikilinks("---\nx: %%[[a]]%%\n---\n# X\n"), [])

    def test_inline_code_in_frontmatter_is_masked(self):
        """Inline code is masked in BOTH regions. Exempting it in frontmatter
        cost more than it bought: a `---` thematic rule whose first line happens
        to read like `key: value` lands in the YAML branch, and its prose
        backticks then become rewritable. A genuine backticked link property has
        zero occurrences catalogue-wide — under-reported, never corrupted."""
        recs = okf.parse_wikilinks(
            '---\ntype: Concept\nnote: "see `[[X]]` for details"\n---\nBody [[B]].\n')
        self.assertEqual([(r["region"], r["page"]) for r in recs], [("body", "B")])

    def test_frontmatter_end_agrees_with_split_frontmatter(self):
        """The region split is derived arithmetic; if it drifts from
        split_frontmatter by even one byte the two halves of a rename disagree
        about where frontmatter stops."""
        for text in (
            "---\ntype: Concept\n---\nbody\n",
            "no frontmatter at all\n",
            "---\ntype: Concept\nbody never closes\n",
            "---\ntype: Concept\n---\nbody with a --- rule\n",
            "﻿---\ntype: Concept\n---\nbom first\n",
            "---\r\ntype: Concept\r\n---\r\ncrlf body\r\n",
        ):
            self.assertEqual(text[okf_linkscan._frontmatter_end(text):],
                             okf_catalogue.split_frontmatter(text)[1], repr(text))


class WikilinkResolve(WikilinkFixtureMixin, unittest.TestCase):
    """REQ-02..REQ-05 — basename resolution, same-bundle tie-break, ambiguity,
    unresolved."""

    def test_unique_basename(self):
        self._w("b/x.md", "---\ntype: Concept\n---\nSee [[y]].\n")
        self._w("other/sub/y.md", "---\ntype: Concept\n---\n# Y\n")
        self.assertEqual(self._status("b/x.md", "y"),
                         ("resolved", ["/other/sub/y.md"]))

    def test_alias_and_suffix_do_not_affect_resolution(self):
        self._w("b/x.md", "---\ntype: Concept\n---\n"
                          "[[y]] [[y|Label]] [[y#Heading]] [[y#^blk]] [[y.md]]\n")
        self._w("other/sub/y.md", "---\ntype: Concept\n---\n# Y\n")
        recs = okf.resolve_wikilink_records(
            self._index(), okf.parse_wikilinks(self._r("b/x.md"), "b/x.md"))
        self.assertEqual([r["candidates"] for r in recs],
                         [["/other/sub/y.md"]] * 5)

    def test_same_bundle_wins(self):
        self._w("a/x.md", "---\ntype: Concept\n---\nSee [[g]].\n")
        self._w("a/g.md", "---\ntype: Concept\n---\n# G\n")
        self._w("b/g.md", "---\ntype: Concept\n---\n# G\n")
        self.assertEqual(self._status("a/x.md", "g"), ("resolved", ["/a/g.md"]))

    def test_tie_break_compares_bundles_case_insensitively(self):
        """D10 — on this filesystem `A/x.md` and `a/x.md` are one file. A
        case-sensitive tie-break made the same link resolve from one spelling
        and go ambiguous from the other."""
        self._w("a/g.md", "---\ntype: Concept\n---\n# G\n")
        self._w("b/g.md", "---\ntype: Concept\n---\n# G\n")
        self.assertEqual(self._status("A/x.md", "g"), ("resolved", ["/a/g.md"]))

    def test_case_folding_matches_obsidian_not_unicode_casefold(self):
        """Obsidian folds with JavaScript `toLowerCase()`, which leaves ß alone.
        `casefold()` maps ß to ss, so it would resolve `[[STRASSE]]` here and
        leave the link broken in the app — and on a case-sensitive checkout it
        would collapse `Straße.md` and `Strasse.md` into one shadowing key."""
        self._w("a/Straße.md", "---\ntype: Concept\n---\n# S\n")
        self.assertEqual(self._status("a/x.md", "straße"),
                         ("resolved", ["/a/Straße.md"]))
        self.assertEqual(self._status("a/x.md", "STRASSE"), ("unresolved", []))

    def test_path_form_tail_is_compared_case_insensitively(self):
        self._w("b/sub/name.md", "---\ntype: Concept\n---\n# N\n")
        self.assertEqual(self._status("b/x.md", "Sub/Name"),
                         ("resolved", ["/b/sub/name.md"]))
        # …and with the casing on the DISK side, which a one-sided casefold
        # of the query alone would still get wrong.
        self._w("c/Sub/Name.md", "---\ntype: Concept\n---\n# N\n")
        self.assertEqual(self._status("c/x.md", "sub/name"),
                         ("resolved", ["/c/Sub/Name.md"]))

    def test_reserved_file_participates_as_a_source(self):
        """D04 — reserved files are not link TARGETS but they do carry links,
        and the reporting surface must list them."""
        self._w("a/index.md", "# A\n\nIntro.\n\nSee [[y]].\n")
        self._w("a/y.md", "---\ntype: Concept\n---\n# Y\n")
        links = okf.scan_wikilinks(self.tmp, "a")
        self.assertEqual([(l["source"], l["status"]) for l in links],
                         [("a/index.md", "resolved")])

    def test_candidate_order_is_deterministic(self):
        """An unsorted candidate list makes an ambiguous report differ between
        runs on the same tree, and AC-04.1 rests on the order."""
        for b in ("d", "a", "c", "b"):
            self._w("{}/g.md".format(b), "---\ntype: Concept\n---\n# G\n")
        status, cands = self._status("z/x.md", "g")
        self.assertEqual((status, cands),
                         ("ambiguous", ["/a/g.md", "/b/g.md", "/c/g.md", "/d/g.md"]))

    def test_ambiguous_across_foreign_bundles(self):
        self._w("c/x.md", "---\ntype: Concept\n---\nSee [[g]].\n")
        self._w("a/g.md", "---\ntype: Concept\n---\n# G\n")
        self._w("b/g.md", "---\ntype: Concept\n---\n# G\n")
        self.assertEqual(self._status("c/x.md", "g"),
                         ("ambiguous", ["/a/g.md", "/b/g.md"]))

    def test_ambiguous_within_one_bundle(self):
        """The tie-break is bundle-level, not directory-level: two candidates in
        the linking file's own bundle stay ambiguous."""
        self._w("a/x.md", "---\ntype: Concept\n---\nSee [[g]].\n")
        self._w("a/g.md", "---\ntype: Concept\n---\n# G\n")
        self._w("a/sub/g.md", "---\ntype: Concept\n---\n# G\n")
        self.assertEqual(self._status("a/x.md", "g"),
                         ("ambiguous", ["/a/g.md", "/a/sub/g.md"]))

    def test_missing_target(self):
        self._w("a/x.md", "---\ntype: Concept\n---\nSee [[ghost]].\n")
        self.assertEqual(self._status("a/x.md", "ghost"), ("unresolved", []))

    def test_path_form_target_uses_last_segment(self):
        self._w("a/x.md", "---\ntype: Concept\n---\n[[800 Bank/Claude Code Skills]]\n")
        page = okf.parse_wikilinks(self._r("a/x.md"))[0]["page"]
        self.assertEqual(page, "800 Bank/Claude Code Skills")
        self.assertEqual(self._status("a/x.md", page), ("unresolved", []))

    def test_non_concept_target_is_unresolved(self):
        """No extension-based exclusion exists (D05 retired): a clause number and
        an image name are looked up like any other page part and reported."""
        self._w("a/x.md", "---\ntype: Concept\n---\n[[8.3.3]] and [[diagram.png]]\n")
        recs = okf.resolve_wikilink_records(
            self._index(), okf.parse_wikilinks(self._r("a/x.md"), "a/x.md"))
        self.assertEqual([r["page"] for r in recs], ["8.3.3", "diagram.png"])
        self.assertEqual([r["status"] for r in recs], ["unresolved", "unresolved"])

    def test_resolution_is_case_insensitive(self):
        """The store's filesystem is case-insensitive and Obsidian resolves
        accordingly: `[[YAML]]` opens `yaml.md`. A case-sensitive table calls
        96 live catalogue links dead and lets rename orphan them unannounced."""
        self._w("a/yaml.md", "---\ntype: Concept\n---\n# YAML\n")
        self._w("a/GLOSSARY.md", "---\ntype: Concept\n---\n# Glossary\n")
        self._w("a/x.md", "---\ntype: Concept\n---\nSee [[YAML]] and [[glossary]].\n")
        # Both directions: an uppercase link onto a lowercase file, and a
        # lowercase link onto an uppercase file. Casefolding only the lookup
        # side passes the first and fails the second.
        self.assertEqual(self._status("a/x.md", "YAML"), ("resolved", ["/a/yaml.md"]))
        self.assertEqual(self._status("a/x.md", "glossary"), ("resolved", ["/a/GLOSSARY.md"]))

    def test_path_form_target_is_honoured_when_it_matches(self):
        """An author who spelled the directory out meant it. Answering with the
        candidate that spelling excludes is worse than answering unresolved."""
        self._w("a/old.md", "---\ntype: Concept\n---\n# A\n")
        self._w("z/deep/old.md", "---\ntype: Concept\n---\n# Z\n")
        self._w("z/x.md", "---\ntype: Concept\n---\nSee [[a/old]].\n")
        self.assertEqual(self._status("z/x.md", "a/old"), ("resolved", ["/a/old.md"]))
        self.assertEqual(self._status("a/src.md", "z/deep/old"),
                         ("resolved", ["/z/deep/old.md"]))

    def test_path_form_that_matches_nothing_is_unresolved(self):
        """No fallback to the bare basename: falling back answered with the very
        candidate the spelled-out path excludes. With `a/_plan/old.md` unindexed
        as staging, `[[_plan/old]]` used to resolve to `a/old.md` — a different
        file — and rename then rewrote it."""
        self._w("a/y.md", "---\ntype: Concept\n---\n# Y\n")
        self.assertEqual(self._status("a/x.md", "gone/y"), ("unresolved", []))
        self._w("a/old.md", "---\ntype: Concept\n---\n# Old\n")
        self._w("a/_plan/old.md", "---\ntype: Concept\n---\n# Draft\n")
        self.assertEqual(self._status("c/x.md", "_plan/old"), ("unresolved", []))

    def test_reserved_file_is_not_a_resolution_target(self):
        """`index.md` is bundle furniture, not a concept — every bundle has one,
        so `[[index]]` could never address a unique file."""
        self._w("a/index.md", "# A\n\nIntro.\n")
        self.assertEqual(self._status("a/x.md", "index"), ("unresolved", []))

    def test_staging_concept_is_not_a_resolution_target(self):
        """No reporting or check surface scans `_`-prefixed staging, so a draft
        there must not be able to satisfy a link either — otherwise a link
        resolves against a file nothing ever audits."""
        self._w("a/_inbox/draft.md", "---\ntype: Concept\n---\n# Draft\n")
        self.assertEqual(self._status("a/x.md", "draft"), ("unresolved", []))

    def test_symlinked_bundle_concepts_are_resolvable_targets(self):
        """os.walk does not descend into a symlinked SUBdirectory, so the index
        walks per bundle — five catalogue bundles are symlinks and a root-level
        walk would make every concept in them unresolvable."""
        import tempfile
        ext = tempfile.mkdtemp()
        try:
            with open(os.path.join(ext, "mounted.md"), "w", encoding="utf-8") as f:
                f.write("---\ntype: Concept\n---\n# Mounted\n")
            os.symlink(ext, os.path.join(self.tmp, "ext-bundle"))
            self._w("a/x.md", "---\ntype: Concept\n---\nSee [[mounted]].\n")
            self.assertEqual(self._status("a/x.md", "mounted"),
                             ("resolved", ["/ext-bundle/mounted.md"]))
        finally:
            import shutil
            shutil.rmtree(ext, ignore_errors=True)

    def test_nfd_filename_matches_nfc_link(self):
        """OKFT-gm5k: APFS delivers filenames in NFD, but users type links
        in NFC. build_concept_basename_index normalizes filenames; resolve_wikilink
        normalizes link text. Both must use the same order (NFC + lowercase) to
        match bidirectionally."""
        import unicodedata
        # Create a concept with an umlaut filename in NFD (APFS form).
        name_nfd = unicodedata.normalize('NFD', 'Größe')  # ö = o + combining diacritic
        self._w(f"a/{name_nfd}.md", "---\ntype: Concept\n---\n# Größe\n")
        # Type the same word in NFC (user input) and check it resolves.
        name_nfc = unicodedata.normalize('NFC', 'Größe')  # ö = single precomposed char
        self.assertEqual(self._status("a/x.md", name_nfc),
                         ("resolved", [f"/a/{name_nfd}.md"]))

    def test_nfc_filename_matches_nfd_link(self):
        """Reverse of above: file created with NFC normalization (e.g., from
        editor or git), link queried with NFD (rare but possible on clipboard
        paste). Both forms must resolve to the same concept."""
        import unicodedata
        name_nfc = unicodedata.normalize('NFC', 'Größe')
        self._w(f"a/{name_nfc}.md", "---\ntype: Concept\n---\n# Größe\n")
        name_nfd = unicodedata.normalize('NFD', 'Größe')
        self.assertEqual(self._status("a/x.md", name_nfd),
                         ("resolved", [f"/a/{name_nfc}.md"]))

    def test_case_folding_does_not_use_casefold_preserving_d06(self):
        """D06 regression test: casefold() would map ß → ss, causing [[STRASSE]]
        to resolve to Straße.md. JavaScript toLowerCase() (which Obsidian uses)
        leaves ß alone. Our _normalize_key() matches that, using .lower() not
        casefold()."""
        self._w("a/Straße.md", "---\ntype: Concept\n---\n# S\n")
        # Uppercase german eszett does not exist in lowercase form; [[STRASSE]]
        # should not resolve.
        self.assertEqual(self._status("a/x.md", "STRASSE"),
                         ("unresolved", []))
        # But [[straße]] should resolve just fine.
        self.assertEqual(self._status("a/x.md", "straße"),
                         ("resolved", ["/a/Straße.md"]))


class WikilinkArchiveResolution(WikilinkFixtureMixin, unittest.TestCase):
    """R-05/R-06 (docs/okf-archive-lifecycle/SPEC.md) — build_concept_basename_index
    picks up _archive/<bundle>/** as a resolution target, active candidates
    take precedence over archived ones, and existing ambiguity among active
    candidates is unaffected by the archive being resolvable at all."""

    # -- A05/AC1/AC3: archive as a resolution target ---------------------
    def test_archived_concept_is_a_resolution_target(self):
        """A link into a concept that only exists under _archive/ must not go
        unresolved the moment archiving moves the file there."""
        self._w("_archive/a/old.md", "---\ntype: Concept\n---\n# Old\n")
        self.assertEqual(self._status("b/x.md", "old"),
                         ("resolved", ["/_archive/a/old.md"]))

    def test_archived_candidate_used_only_when_no_active_one_exists(self):
        """AC3 — with no active candidate, resolution falls back to the
        archived candidate(s)."""
        self._w("_archive/z/old.md", "---\ntype: Concept\n---\n# Archived Old\n")
        self.assertEqual(self._status("b/x.md", "old"),
                         ("resolved", ["/_archive/z/old.md"]))

    def test_two_archived_candidates_with_no_active_are_ambiguous(self):
        """Symmetric to AC4 in the archived tier: no active candidate at all
        and two archived ones of the same basename stay ambiguous rather than
        one being picked arbitrarily."""
        self._w("_archive/a/g.md", "---\ntype: Concept\n---\n# G\n")
        self._w("_archive/b/g.md", "---\ntype: Concept\n---\n# G\n")
        self.assertEqual(self._status("c/x.md", "g"),
                         ("ambiguous", ["/_archive/a/g.md", "/_archive/b/g.md"]))

    # -- T01/AC2 (okf-cli-yixf): existing-but-empty _archive/ -------------
    def test_existing_but_empty_archive_directory_does_not_crash_or_contribute(self):
        """AC2 — _archive/ can exist while holding no bundle at all (e.g. a
        hand-created directory, or a race with an external mkdir):
        list_bundles(archive_root) then returns [], the
        `if os.path.isdir(archive_root):` branch (cli/okf-cli.py:3436) is
        taken, and its loop body never runs. Geometry only: build must not
        crash, and resolution of an unrelated active concept must be
        unaffected — a bogus empty _archive/ must not itself become a
        candidate or otherwise perturb the index.

        Not a precedence-sensitive test: with zero archived candidates for
        any basename here, _apply_archive_precedence's active/archived
        filter is a no-op regardless of whether it runs at all — mutating or
        removing it cannot change this test's outcome. See this leaf's
        closing report (okf-cli-yixf) for that reading, flagged rather than
        silently claimed as SC-03 coverage."""
        os.makedirs(os.path.join(self.tmp, "_archive"))
        self._w("a/old.md", "---\ntype: Concept\n---\n# Old\n")
        idx = self._index()
        self.assertEqual(idx.get("old"), ["/a/old.md"])
        self.assertEqual(self._status("b/x.md", "old"), ("resolved", ["/a/old.md"]))

    # -- A06/AC2/SC-02: precedence — active wins over archived ------------
    def test_active_candidate_wins_over_an_archived_one_of_the_same_name(self):
        """SC-02/SC-03 — with an active AND an archived concept sharing a
        basename, the link resolves to the active one rather than reporting
        ambiguity. This is also the guard-reversal test named by SC-03:
        removing the active-before-archived precedence from
        build_concept_basename_index turns this assertion red."""
        self._w("a/old.md", "---\ntype: Concept\n---\n# Active Old\n")
        self._w("_archive/z/old.md", "---\ntype: Concept\n---\n# Archived Old\n")
        self.assertEqual(self._status("b/x.md", "old"),
                         ("resolved", ["/a/old.md"]))

    # -- A07/AC4/SC-04 (Gate-B finding F01): active ambiguity unchanged ---
    def test_two_active_candidates_stay_ambiguous_even_with_an_archived_third(self):
        """SC-04 — two active concepts sharing a basename still report
        ambiguous once archive resolution is in place; a same-named archived
        concept must not silently join the candidate set or defuse the
        ambiguity."""
        self._w("a/g.md", "---\ntype: Concept\n---\n# G\n")
        self._w("b/g.md", "---\ntype: Concept\n---\n# G\n")
        self._w("_archive/z/g.md", "---\ntype: Concept\n---\n# Archived G\n")
        self.assertEqual(self._status("c/x.md", "g"),
                         ("ambiguous", ["/a/g.md", "/b/g.md"]))


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


class WikilinkCommand(WikilinkFixtureMixin, unittest.TestCase):
    """REQ-06..REQ-09 — the `wikilinks` reporting command."""

    def setUp(self):
        super().setUp()
        self._w("a/index.md", "# A\n\nBundle entry with an intro paragraph.\n")
        self._w("a/y.md", "---\ntype: Concept\n---\n# Y\n")
        self._w("a/x.md", '---\ntype: Concept\nrelated:\n  - "[[ghost]]"\n---\n'
                          "Good [[y]] and bad [[nowhere]].\n")
        self._w("b/z.md", "---\ntype: Concept\n---\nAlso [[y]].\n")

    def test_report_line_shape(self):
        out = _cli(self.tmp, "wikilinks")
        self.assertEqual(out.returncode, 0, out.stderr)
        lines = [l for l in out.stdout.splitlines() if not l.startswith("wikilinks:")]
        self.assertEqual(len(lines), 4)
        for line in lines:
            self.assertRegex(
                line,
                r"^(resolved|ambiguous|unresolved)\s+(body|frontmatter)\s+\S+\s+\[\[.*\]\]")

    def test_summary_line_shape(self):
        out = _cli(self.tmp, "wikilinks")
        self.assertRegex(out.stdout.splitlines()[-1],
                         r"^wikilinks: \d+ link\(s\), \d+ resolved, \d+ ambiguous, "
                         r"\d+ unresolved$")

    def test_exit_code_is_zero_with_findings(self):
        """The report is a report, not a gate — `check` is where a wikilink can
        fail a run, and only for an opted-in bundle."""
        out = _cli(self.tmp, "wikilinks")
        self.assertIn("unresolved", out.stdout)
        self.assertEqual(out.returncode, 0)

    def test_unresolved_filter_keeps_summary_totals(self):
        out = _cli(self.tmp, "wikilinks", "--unresolved")
        lines = [l for l in out.stdout.splitlines() if not l.startswith("wikilinks:")]
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(l.startswith("unresolved") for l in lines), lines)
        self.assertIn("wikilinks: 4 link(s), 2 resolved, 0 ambiguous, 2 unresolved",
                      out.stdout)

    def test_json_is_parseable(self):
        out = _cli(self.tmp, "wikilinks", "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        json.loads(out.stdout)

    def test_json_shape(self):
        data = json.loads(_cli(self.tmp, "wikilinks", "--json").stdout)
        keys = {"source", "region", "raw", "page", "alias", "suffix", "embed",
                "status", "candidates"}
        for link in data["links"]:
            self.assertTrue(keys.issubset(link), sorted(keys - set(link)))
        total = sum(sum(c.values()) for c in data["by_bundle"].values())
        self.assertEqual(total, len(data["links"]))
        self.assertEqual(sorted(data["by_bundle"]), ["a", "b"])

    def test_target_argument_scopes_the_scan(self):
        scoped = json.loads(_cli(self.tmp, "wikilinks", "a", "--json").stdout)
        whole = json.loads(_cli(self.tmp, "wikilinks", "--json").stdout)
        self.assertEqual(sorted(scoped["by_bundle"]), ["a"])
        self.assertGreater(len(whole["links"]), len(scoped["links"]))

    def test_missing_target_exits_one(self):
        out = _cli(self.tmp, "wikilinks", "nosuchbundle")
        self.assertEqual(out.returncode, 1)
        self.assertIn("nosuchbundle", out.stderr)

    def test_by_bundle_never_contradicts_the_link_list(self):
        """Under --unresolved the two must still agree; a by_bundle computed
        over the unfiltered set would report counts the caller cannot see."""
        data = json.loads(_cli(self.tmp, "wikilinks", "--unresolved", "--json").stdout)
        self.assertTrue(data["filtered"])
        self.assertEqual(sum(sum(c.values()) for c in data["by_bundle"].values()),
                         len(data["links"]))
        self.assertEqual(data["totals"],
                         {"resolved": 2, "ambiguous": 0, "unresolved": 2})

    def test_embed_is_visible_in_the_report(self):
        """`raw` drops the `!`, so without a marker an embed and a plain link
        print identically."""
        self._w("a/e.md", "---\ntype: Concept\n---\n![[y]]\n")
        out = _cli(self.tmp, "wikilinks", "a")
        self.assertIn("(embed)", out.stdout)

    def test_target_must_name_a_bundle(self):
        """`..` walked out of the catalogue and `_plan` scanned a staging
        directory the reporting surface is defined to exclude."""
        self._w("_plan/note.md", "---\ntype: Concept\n---\nSee [[ghost]].\n")
        self._w("a/_plan/note.md", "---\ntype: Concept\n---\nSee [[ghost]].\n")
        self._w("a/assets/note.md", "---\ntype: Concept\n---\nSee [[ghost]].\n")
        # iter_all_md prunes these names from `dirnames`, never from the
        # directory it is handed, so a target naming one scans it regardless.
        for bad in ("..", ".", "./", "_plan", "a/_plan", "a/assets",
                    "a/nosuchsubdir", "nosuchbundle"):
            out = _cli(self.tmp, "wikilinks", bad)
            self.assertEqual(out.returncode, 1, bad)
            self.assertRegex(out.stderr, r"not a (directory|scannable bundle path)", bad)
            self.assertIn(bad, out.stderr, bad)


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
        after_index = okf.build_concept_basename_index(self.tmp)
        self.assertEqual(
            okf.resolve_wikilink(after_index, "a/other.md", "old"),
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


class WikilinkCheck(WikilinkFixtureMixin, unittest.TestCase):
    """REQ-13/REQ-14 — the wikilink-resolvable check and its opt-in gate."""

    def _optin(self, *bundles):
        self._w(".okf.toml", "wikilink_checked_bundles = [{}]\n".format(
            ", ".join('"{}"'.format(b) for b in bundles)))

    def _findings(self, target=None):
        errors, warnings = okf.run_checks(self.tmp, target)
        return [(n, p, m) for n, p, m in errors + warnings if n == "wikilink-resolvable"]

    def test_warns_for_opted_in_bundle(self):
        self._optin("a")
        self._w("a/x.md", "---\ntype: Concept\n---\nSee [[ghost]].\n")
        found = self._findings()
        self.assertEqual([f[1] for f in found], ["a/x.md"])

    def test_one_warning_per_file_lists_every_target(self):
        self._optin("a")
        self._w("a/x.md", "---\ntype: Concept\n---\n[[g1]] [[g2]] [[g3]]\n")
        found = self._findings()
        self.assertEqual(len(found), 1)
        for target in ("[[g1]]", "[[g2]]", "[[g3]]"):
            self.assertIn(target, found[0][2])

    def test_frontmatter_only_file_is_flagged(self):
        self._optin("a")
        self._w("a/x.md", '---\ntype: Concept\nrelated:\n  - "[[ghost]]"\n---\n# X\n')
        self.assertEqual([f[1] for f in self._findings()], ["a/x.md"])

    def test_reserved_file_participates(self):
        self._optin("a")
        self._w("a/index.md", "# A\n\nIntro.\n\nSee [[ghost]].\n")
        self.assertEqual([f[1] for f in self._findings()], ["a/index.md"])

    def test_link_into_the_archive_does_not_warn(self):
        """SC-01 — archiving a concept that an active concept links to must
        not turn a clean check into a violation in a file nobody touched."""
        self._optin("a")
        self._w("a/x.md", "---\ntype: Concept\n---\nSee [[old]].\n")
        self._w("_archive/z/old.md", "---\ntype: Concept\n---\n# Old\n")
        self.assertEqual(self._findings(), [])

    def test_symlinked_bundle_participates(self):
        import tempfile
        ext = tempfile.mkdtemp()
        try:
            with open(os.path.join(ext, "x.md"), "w", encoding="utf-8") as f:
                f.write("---\ntype: Concept\n---\nSee [[ghost]].\n")
            os.symlink(ext, os.path.join(self.tmp, "mounted"))
            self._optin("mounted")
            self.assertEqual([f[1] for f in self._findings()], ["mounted/x.md"])
        finally:
            import shutil
            shutil.rmtree(ext, ignore_errors=True)

    def test_strict_run_exits_one(self):
        self._optin("a")
        self._w("a/index.md", "# A\n\nIntro.\n")
        self._w("a/x.md", "---\ntype: Concept\n---\nSee [[ghost]].\n")
        out = _cli(self.tmp, "check", "--strict")
        self.assertEqual(out.returncode, 1)
        self.assertIn("wikilink-resolvable", out.stdout)

    def test_absent_config_is_silent(self):
        """The state the live catalogue is in today: 1930 unresolved wikilinks
        and not one warning, because no .okf.toml opts a bundle in."""
        self._w("a/x.md", "---\ntype: Concept\n---\nSee [[ghost]].\n")
        self.assertEqual(self._findings(), [])

    def test_partial_optin_is_scoped(self):
        self._optin("a")
        self._w("a/x.md", "---\ntype: Concept\n---\nSee [[ghost]].\n")
        self._w("b/y.md", "---\ntype: Concept\n---\nSee [[phantom]].\n")
        self.assertEqual([f[1] for f in self._findings()], ["a/x.md"])

    def test_resolved_wikilink_in_opted_in_bundle_is_clean(self):
        self._optin("a")
        self._w("a/x.md", "---\ntype: Concept\n---\nSee [[y]].\n")
        self._w("a/y.md", "---\ntype: Concept\n---\n# Y\n")
        self.assertEqual(self._findings(), [])

    def test_severity_is_warning_not_error(self):
        """The rule ships silent and non-blocking: an opted-in bundle with dead
        wikilinks must not fail a plain `check`. As an error it would fail 457
        files the day `qm-wiki` opts in."""
        self._optin("a")
        self._w("a/index.md", "# A\n\nIntro.\n")
        self._w("a/x.md", "---\ntype: Concept\n---\nSee [[ghost]].\n")
        errors, warnings = okf.run_checks(self.tmp, None)
        self.assertIn("wikilink-resolvable", [w[0] for w in warnings])
        self.assertNotIn("wikilink-resolvable", [e[0] for e in errors])
        self.assertEqual(_cli(self.tmp, "check").returncode, 0)

    def test_dotted_target_does_not_defeat_the_gate(self):
        """`./a` yielded bundle "." and switched this one check off while every
        other check kept firing."""
        self._optin("a")
        self._w("a/x.md", "---\ntype: Concept\n---\nSee [[ghost]].\n")
        self.assertEqual([f[1] for f in self._findings("./a")], ["a/x.md"])

    def test_index_is_not_built_without_an_opt_in(self):
        """The index costs a full catalogue walk. Nothing else pins that an
        unconfigured catalogue skips it."""
        calls = []
        real = okf.build_concept_basename_index
        okf.build_concept_basename_index = lambda root: (calls.append(root), real(root))[1]
        try:
            self._w("a/x.md", "---\ntype: Concept\n---\nSee [[ghost]].\n")
            okf.run_checks(self.tmp, None)
            self.assertEqual(calls, [])
            self._optin("a")
            okf.run_checks(self.tmp, None)
            self.assertEqual(len(calls), 1)
            calls.clear()
            okf.run_checks(self.tmp, "b")        # scope excludes the opted-in bundle
            self.assertEqual(calls, [])
        finally:
            okf.build_concept_basename_index = real

    def test_non_array_config_is_announced_not_swallowed(self):
        """A config that reads as if it opted a bundle in, but does not, is
        worse than no config: the run looks clean for the wrong reason."""
        import contextlib
        import io
        self._w(".okf.toml", 'wikilink_checked_bundles = "a"\n')
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            got = okf.wikilink_checked_bundles(okf_catalogue.load_okf_config(self.tmp), self.tmp)
        self.assertEqual(got, set())
        self.assertIn("must be an array", err.getvalue())

    def test_unknown_bundle_in_config_is_announced(self):
        import contextlib
        import io
        self._optin("nosuchbundle")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            okf.wikilink_checked_bundles(okf_catalogue.load_okf_config(self.tmp), self.tmp)
        self.assertIn("nosuchbundle", err.getvalue())

    @needs_case_insensitive_fs
    def test_case_variant_bundle_name_does_not_defeat_the_gate(self):
        """The store's filesystem is case-insensitive, so `check A` reaches
        bundle `a` with ctx["bundle"] reading "A". An exact-string gate switched
        this one check off there while every other check kept firing."""
        self._optin("a")
        self._w("a/x.md", "---\ntype: Concept\n---\nSee [[ghost]].\n")
        self.assertEqual([f[1] for f in self._findings("A")], ["A/x.md"])
        # …and the other direction: the config's own casing must not matter.
        self._optin("A")
        self.assertEqual([f[1] for f in self._findings()], ["a/x.md"])

    def test_ambiguous_wikilink_also_warns(self):
        """REQ-13 names unresolved AND ambiguous; only the first half was
        asserted, so dropping the second survived every test."""
        self._optin("c")
        self._w("a/g.md", "---\ntype: Concept\n---\n# G\n")
        self._w("b/g.md", "---\ntype: Concept\n---\n# G\n")
        self._w("c/x.md", "---\ntype: Concept\n---\nSee [[g]].\n")
        self.assertEqual([f[1] for f in self._findings()], ["c/x.md"])

    def test_staging_subdir_target_is_not_checked(self):
        """iter_all_md prunes staging from `dirnames`, never from the directory
        it is handed, so `check <bundle>/_plan` walked into a tree the
        Non-Goals exclude from every reporting surface."""
        self._optin("a")
        self._w("a/_plan/x.md", "---\ntype: Concept\n---\nSee [[ghost]].\n")
        self._w("a/assets/y.md", "---\ntype: Concept\n---\nSee [[ghost]].\n")
        self.assertEqual(self._findings("a/_plan"), [])
        self.assertEqual(self._findings("a/assets"), [])

    def test_unknown_bundle_note_respects_case(self):
        """The note said the opposite of what happened: the gate casefolded the
        config entries, the diagnostic did not."""
        import contextlib
        import io
        self._w("a/x.md", "---\ntype: Concept\n---\n# X\n")
        self._optin("A")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            got = okf.wikilink_checked_bundles(okf_catalogue.load_okf_config(self.tmp), self.tmp)
        self.assertEqual(got, {"a"})
        self.assertNotIn("non-bundle", err.getvalue())

    def test_missing_target_directory_is_not_a_clean_run(self):
        """`check b/nope` scanned nothing and exited 0 — a clean bill of health
        for a directory that does not exist. A renamed bundle passed CI green."""
        self._w("a/index.md", "# A\n\nIntro.\n")
        for bad in ("a/nope", "nosuchbundle"):
            out = _cli(self.tmp, "check", bad)
            self.assertEqual(out.returncode, 1, bad)
            self.assertIn(bad, out.stderr, bad)

    def test_malformed_config_fails_with_a_message_not_a_traceback(self):
        """load_okf_config is now on every check path, so a parse failure has to
        name the file — including when --types made it irrelevant before."""
        self._w(".okf.toml", "this is not = = toml\n")
        out = _cli(self.tmp, "check", "--types", os.path.join(self.tmp, "TYPES.md"))
        self.assertEqual(out.returncode, 1)
        self.assertIn(".okf.toml is not valid TOML", out.stderr)
        self.assertNotIn("Traceback", out.stderr)


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


class CheckSupersededBy(unittest.TestCase):
    """OKFT-gpcx / D01 — two new check rules: a `superseded_by` target that
    does not resolve is an ERROR (same class as a dead crosslink); a
    `superseded_by` on a concept whose own `type` is not `Decision` is a
    WARNING (the scope guard, not a failure)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _w(self, rel, text):
        ap = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(text)

    def _names(self, entries):
        return [e[0] for e in entries]

    def test_dangling_superseded_by_target_is_error(self):
        self._w("b/x.md", "---\ntype: Decision\ntitle: X\n"
                          "superseded_by: /b/nope.md\n---\n# X\n")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertIn("superseded-by-resolves", self._names(errors))

    def test_resolving_superseded_by_target_is_clean(self):
        self._w("b/y.md", "---\ntype: Decision\ntitle: Y\n---\n# Y\n")
        self._w("b/x.md", "---\ntype: Decision\ntitle: X\n"
                          "superseded_by: /b/y.md\n---\n# X\n")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertNotIn("superseded-by-resolves", self._names(errors))

    def test_superseded_by_on_non_decision_concept_is_warning(self):
        self._w("b/y.md", "---\ntype: Decision\ntitle: Y\n---\n# Y\n")
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n"
                          "superseded_by: /b/y.md\n---\n# X\n")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertIn("superseded-by-scope", self._names(warnings))

    def test_superseded_by_on_decision_concept_has_no_scope_warning(self):
        self._w("b/y.md", "---\ntype: Decision\ntitle: Y\n---\n# Y\n")
        self._w("b/x.md", "---\ntype: Decision\ntitle: X\n"
                          "superseded_by: /b/y.md\n---\n# X\n")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertNotIn("superseded-by-scope", self._names(warnings))

    def test_absent_superseded_by_is_clean(self):
        self._w("b/x.md", "---\ntype: Decision\ntitle: X\n---\n# X\n")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertNotIn("superseded-by-resolves", self._names(errors))
        self.assertNotIn("superseded-by-scope", self._names(warnings))


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
        touched, _ = okf.fix_crosslinks(self.tmp, "b")
        self.assertEqual({p for p, _ in touched},
                         {"b/published.md", "b/_intake/staged.md"})
        self.assertIn("(/b/old.md)", self._r("b/_intake/staged.md"))

    def test_fix_xml_tags_reaches_staging(self):
        touched = okf.fix_xml_like_tags(self.tmp, "b")
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


class SyncCheckValidators(SyncFixtureMixin, unittest.TestCase):
    """The two check entries, and the laziness that keeps a catalogue without
    any materialised block from paying for the canon index."""

    def test_consumer_modified_is_an_error(self):
        self._insert()
        self._w("kc-proj/setup.md",
                self._r("kc-proj/setup.md").replace(
                    self.OWNER_PAYLOAD, "Lokal.\n"))
        errors, _ = okf.run_checks(self.tmp, None)
        self.assertIn(
            ("sync-block", "kc-proj/setup.md",
             "sync block `ownership-rule` from /kc-gov/ownership.md: "
             "consumer-modified"), errors)

    def test_source_changed_is_a_warning(self):
        self._insert()
        self._w("kc-gov/ownership.md",
                self._r("kc-gov/ownership.md").replace(
                    self.OWNER_PAYLOAD, "Neuer Kanon.\n"))
        errors, warnings = okf.run_checks(self.tmp, None)
        self.assertEqual([e for e in errors if e[0] == "sync-block"], [])
        self.assertIn("sync-stale", [w[0] for w in warnings])

    def test_duplicate_canon_id_is_an_error(self):
        self._w("kc-gov/ownership.md",
                self._r("kc-gov/ownership.md")
                + "\n<!-- okf:canon id=ownership-rule -->\nzweimal\n"
                + okf_catalogue.CANON_END + "\n")
        errors, _ = okf.run_checks(self.tmp, None)
        self.assertIn(("canon-block", "kc-gov/ownership.md",
                       "canon block id `ownership-rule` declared twice"), errors)

    def test_unterminated_canon_marker_is_an_error(self):
        self._w("kc-gov/ownership.md",
                "---\ntype: Rule\ndescription: d\n---\n\n"
                "<!-- okf:canon id=x -->\ntext\n")
        errors, _ = okf.run_checks(self.tmp, None)
        self.assertIn("canon-block", [e[0] for e in errors])

    def test_catalogue_without_sync_blocks_never_builds_the_canon_index(self):
        calls = []
        real = okf_sync.build_canon_block_index
        okf_sync.build_canon_block_index = lambda root: (calls.append(root)
                                                         or real(root))
        try:
            errors, warnings = okf.run_checks(self.tmp, None)
        finally:
            okf_sync.build_canon_block_index = real
        self.assertEqual(calls, [])
        self.assertEqual([e for e in errors if e[0].startswith("sync")], [])
        self.assertEqual([w for w in warnings if w[0].startswith("sync")], [])


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
        okf.fix_crosslinks(self.tmp, None)
        self.assertEqual(self._r("kc-proj/setup.md"), self.consumer_before)

    def test_fix_xml_tags_leaves_the_block_byte_identical(self):
        okf.fix_xml_like_tags(self.tmp, None)
        self.assertEqual(self._r("kc-proj/setup.md"), self.consumer_before)

    def test_crosslink_and_xml_checks_report_nothing_for_the_consumer(self):
        ctx = okf.gather_file_context(
            self.tmp, "kc-proj", os.path.join(self.tmp, "kc-proj/setup.md"))
        self.assertEqual(okf.check_crosslink_format(ctx), [])
        self.assertEqual(okf.check_xml_like_tags(ctx), [])

    def test_wikilink_in_a_synced_payload_is_not_scanned(self):
        _, body = okf_catalogue.split_frontmatter(self._r("kc-proj/setup.md"))
        self.assertEqual(okf.parse_wikilinks(body), [])

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
