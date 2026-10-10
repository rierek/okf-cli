#!/usr/bin/env python3
"""Tests for cli/okf/check.py — the conformance scan: its rules, the check
engine, and the fix-crosslinks and fix-xml-tags repairs. Stdlib unittest, no deps.

Run: python3 -m unittest test_okf_check -v
"""
import argparse
import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:  # cli/ holds the okf package; a repo-root run lacks it
    sys.path.insert(0, _HERE)

from okf import catalogue as okf_catalogue
from okf import check as okf_check
from okf import sync as okf_sync
from okf import tags as okf_tags
from okf import wikilinks as okf_wikilinks
from okf_testkit import SyncFixtureMixin, _cli, needs_case_insensitive_fs
from test_okf_wikilinks import WikilinkFixtureMixin


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
        errors, warnings = okf_check.run_checks(self.tmp, "b")
        self.assertIn("frontmatter-parseable", self._names(errors))
        self.assertNotIn("type-nonempty", self._names(errors))  # not double-flagged

    def test_empty_type_is_error(self):
        self._w("b/x.md", "---\ntype: \ntitle: X\n---\n# X\n")
        errors, warnings = okf_check.run_checks(self.tmp, "b")
        self.assertIn("type-nonempty", self._names(errors))
        self.assertNotIn("frontmatter-parseable", self._names(errors))

    def test_reserved_file_with_type_is_error(self):
        self._w("b/index.md", "---\ntype: Concept\n---\n# B\n")
        errors, warnings = okf_check.run_checks(self.tmp, "b")
        self.assertIn("reserved-no-type", self._names(errors))

    def test_filename_forbidden_char_is_error(self):
        self._w("b/weird%name.md", "---\ntype: Concept\n---\n# W\n")
        errors, warnings = okf_check.run_checks(self.tmp, "b")
        self.assertIn("filename-chars", self._names(errors))

    def test_asset_outside_assets_dir_is_error(self):
        self._w("b/index.md", "# B\n")
        self._w("b/diagram.png", "not a real png")
        errors, warnings = okf_check.run_checks(self.tmp, "b")
        self.assertIn("asset-placement", self._names(errors))

    def test_asset_inside_assets_dir_is_clean(self):
        self._w("b/index.md", "# B\n")
        self._w("b/assets/diagram.png", "not a real png")
        errors, warnings = okf_check.run_checks(self.tmp, "b")
        self.assertNotIn("asset-placement", self._names(errors))

    def test_asset_inside_nested_assets_dir_is_clean(self):
        self._w("b/index.md", "# B\n")
        self._w("b/sub/assets/diagram.png", "not a real png")
        errors, warnings = okf_check.run_checks(self.tmp, "b")
        self.assertNotIn("asset-placement", self._names(errors))

    def test_underscore_prefixed_dir_is_excluded_from_scan(self):
        # mirrors is_bundle_dir's convention: "_"-prefixed dirs are staging,
        # not catalogue content — same exemption applied one level down.
        self._w("b/index.md", "# B\n\nBundle entry with an intro paragraph.\n")
        self._w("b/_intake/raw.md", "# no frontmatter\n")
        self._w("b/_intake/notes.tsv", "col1\tcol2\n")
        errors, warnings = okf_check.run_checks(self.tmp, "b")
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_unregistered_type_is_warning(self):
        self._w("TYPES.md", "| type | Meaning |\n|---|---|\n| `Concept` | x |\n")
        self._w("b/x.md", "---\ntype: Bogus\ntitle: X\n---\n# X\n")
        errors, warnings = okf_check.run_checks(self.tmp, "b")
        self.assertIn("type-registered", self._names(warnings))
        self.assertNotIn("type-registered", self._names(errors))

    def test_registered_type_has_no_warning(self):
        self._w("TYPES.md", "| type | Meaning |\n|---|---|\n| `Concept` | x |\n")
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n# X\n")
        errors, warnings = okf_check.run_checks(self.tmp, "b")
        self.assertNotIn("type-registered", self._names(warnings))

    def test_no_types_md_skips_type_registered_check(self):
        self._w("b/x.md", "---\ntype: AnythingGoes\ntitle: X\n---\n# X\n")
        errors, warnings = okf_check.run_checks(self.tmp, "b")
        self.assertNotIn("type-registered", self._names(warnings))

    def test_german_frontmatter_key_is_warning(self):
        self._w("b/x.md", "---\ntype: Concept\ntitel: X\n---\n# X\n")
        errors, warnings = okf_check.run_checks(self.tmp, "b")
        self.assertIn("english-keys", self._names(warnings))

    def test_relative_crosslink_is_warning(self):
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n# X\n\n[Y](y.md)\n")
        errors, warnings = okf_check.run_checks(self.tmp, "b")
        self.assertIn("crosslink-format", self._names(warnings))

    def test_catalogue_root_crosslink_is_clean(self):
        self._w("b/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n# X\n\n[Y](/b/y.md)\n")
        errors, warnings = okf_check.run_checks(self.tmp, "b")
        self.assertNotIn("crosslink-format", self._names(warnings))

    def test_reserved_file_relative_link_outside_marker_is_warning(self):
        """D-rx51-01 (OKFT-rx51): a hand-authored relative link in index.md's
        prose, outside the managed `<!-- okf:index -->` block, is a real
        crosslink and must be caught the same as one in a concept file."""
        self._w("b/index.md", "# B\n\nSee [Old](old.md) for background.\n\n"
                              + okf_catalogue.MARK_START + "\n" + okf_catalogue.MARK_END + "\n")
        errors, warnings = okf_check.run_checks(self.tmp, "b")
        self.assertIn("crosslink-format", self._names(warnings))

    def test_reserved_file_link_inside_marker_is_clean(self):
        """D-rx51-01: the managed block is masked before the scan, so a
        generated (relative-by-convention) link inside it never warns —
        RESERVED files becoming a scan source must not regress the common
        case of an ordinary reindexed index.md."""
        self._w("b/index.md", "# B\n\n" + okf_catalogue.MARK_START + "\n* [X](x.md)\n"
                              + okf_catalogue.MARK_END + "\n")
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n# X\n")
        errors, warnings = okf_check.run_checks(self.tmp, "b")
        self.assertNotIn("crosslink-format", self._names(warnings))

    def test_cross_bundle_dotdot_link_is_flagged(self):
        """Inverted with the canonical form: check_crosslink_format flags ANY
        relative link now, `../other/y.md` included, because it resolves
        inconsistently and orphans in Obsidian. fix-crosslinks migrates it."""
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n# X\n\n[Y](../other/y.md)\n")
        errors, warnings = okf_check.run_checks(self.tmp, "b")
        self.assertIn("crosslink-format", self._names(warnings))

    def test_clean_bundle_has_zero_violations(self):
        self._w("TYPES.md", "| type | Meaning |\n|---|---|\n| `Concept` | x |\n")
        self._w("b/index.md", "# B\n\nBundle entry with an intro paragraph.\n\n## Contents\n\n"
                              + okf_catalogue.MARK_START + "\n* [X](x.md)\n" + okf_catalogue.MARK_END + "\n")
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\ntags:\n  - a\n---\n# X\n\n[Y](/b/index.md)\n")
        errors, warnings = okf_check.run_checks(self.tmp, "b")
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_whole_catalogue_scan_when_no_target(self):
        self._w("b1/x.md", "# X\n\nno frontmatter.\n")
        self._w("b2/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        errors, warnings = okf_check.run_checks(self.tmp, None)
        self.assertIn("b1/x.md", [e[1] for e in errors])


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
        got = okf_check.resolve_crosslink_target(self.tmp, "b", "", "y.md")
        self.assertEqual(got, "/b/y.md")

    def test_subdir_target_resolves_from_bundle_root(self):
        self._w("b/sub/y.md", "")
        got = okf_check.resolve_crosslink_target(self.tmp, "b", "", "sub/y.md")
        self.assertEqual(got, "/b/sub/y.md")

    def test_target_resolves_relative_to_source_cdir(self):
        self._w("b/sub/y.md", "")
        got = okf_check.resolve_crosslink_target(self.tmp, "b", "sub", "y.md")
        self.assertEqual(got, "/b/sub/y.md")

    def test_dotslash_target_normalizes(self):
        self._w("b/y.md", "")
        got = okf_check.resolve_crosslink_target(self.tmp, "b", "", "./y.md")
        self.assertEqual(got, "/b/y.md")

    def test_nonexistent_target_returns_none(self):
        got = okf_check.resolve_crosslink_target(self.tmp, "b", "", "ghost.md")
        self.assertIsNone(got)

    def test_index_md_target_resolves(self):
        self._w("b/sub/index.md", "")
        got = okf_check.resolve_crosslink_target(self.tmp, "b", "", "sub/index.md")
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
        new, changed, unresolved = okf_check.rewrite_crosslinks_in_body(
            self.tmp, "b", "", "See [Y](y.md) for details.")
        self.assertEqual(new, "See [Y](/b/y.md) for details.")
        self.assertEqual(changed, 1)
        self.assertEqual(unresolved, [])

    def test_preserves_anchor_fragment(self):
        self._w("b/y.md", "")
        new, changed, unresolved = okf_check.rewrite_crosslinks_in_body(
            self.tmp, "b", "", "[Y](y.md#section)")
        self.assertEqual(new, "[Y](/b/y.md#section)")
        self.assertEqual(changed, 1)

    def test_unresolvable_target_left_untouched(self):
        body = "[Ghost](ghost.md)"
        new, changed, unresolved = okf_check.rewrite_crosslinks_in_body(self.tmp, "b", "", body)
        self.assertEqual(new, body)
        self.assertEqual(changed, 0)
        self.assertEqual(unresolved, ["ghost.md"])

    def test_already_canonical_link_untouched(self):
        """Idempotence now belongs to the catalogue-root-absolute form: a
        second fix-crosslinks pass must leave a migrated link byte-identical."""
        self._w("b/y.md", "")
        body = "[Y](/b/y.md)"
        new, changed, unresolved = okf_check.rewrite_crosslinks_in_body(self.tmp, "b", "", body)
        self.assertEqual(new, body)
        self.assertEqual(changed, 0)

    def test_legacy_bundle_relative_link_is_migrated(self):
        """The other half of that rule: `/y.md` was the OLD canonical form
        (leading / = bundle root), so it is legacy input to be rewritten, not
        a link to leave alone. resolve_crosslink_target tries the legacy
        reading first precisely so this migration works."""
        self._w("b/y.md", "")
        new, changed, unresolved = okf_check.rewrite_crosslinks_in_body(
            self.tmp, "b", "", "[Y](/y.md)")
        self.assertEqual(new, "[Y](/b/y.md)")
        self.assertEqual(changed, 1)

    def test_cross_bundle_dotdot_link_untouched(self):
        body = "[Y](../other-bundle/y.md)"
        new, changed, unresolved = okf_check.rewrite_crosslinks_in_body(self.tmp, "b", "", body)
        self.assertEqual(new, body)
        self.assertEqual(changed, 0)

    def test_multiple_occurrences_all_rewritten(self):
        self._w("b/y.md", "")
        body = "[Y](y.md) and again [Y2](y.md)"
        new, changed, unresolved = okf_check.rewrite_crosslinks_in_body(self.tmp, "b", "", body)
        self.assertEqual(new, "[Y](/b/y.md) and again [Y2](/b/y.md)")
        self.assertEqual(changed, 2)

    def test_subdir_relative_link_from_root_rewritten(self):
        self._w("b/sub/y.md", "")
        new, changed, unresolved = okf_check.rewrite_crosslinks_in_body(
            self.tmp, "b", "", "[Y](sub/y.md)")
        self.assertEqual(new, "[Y](/b/sub/y.md)")
        self.assertEqual(changed, 1)

    def test_link_in_inline_code_is_not_unresolved(self):
        """A link inside backticks is prose about link syntax, not a link —
        Obsidian never resolves it. check_crosslink_format masks code spans
        for exactly this reason; the rewrite path must agree, or the OKF
        documentation bundles report their own examples as broken links."""
        body = "Bundle-relative form: `[customers](/tables/customers.md)`."
        new, changed, unresolved = okf_check.rewrite_crosslinks_in_body(self.tmp, "b", "", body)
        self.assertEqual(new, body)
        self.assertEqual(changed, 0)
        self.assertEqual(unresolved, [])

    def test_resolvable_link_in_fence_is_not_rewritten(self):
        """The sharper half: a fenced example whose path happens to resolve
        must stay byte-identical. Rewriting it would silently mutate the
        documentation example it illustrates."""
        self._w("b/y.md", "")
        body = "```markdown\n[Y](y.md)\n```"
        new, changed, unresolved = okf_check.rewrite_crosslinks_in_body(self.tmp, "b", "", body)
        self.assertEqual(new, body)
        self.assertEqual(changed, 0)
    def test_four_backtick_fence_blocks_are_masked(self):
        """Verify that code fences with 4+ backticks are handled correctly.
        Markdown allows any number of backticks >= 3. The regex must match
        the opening fence marker and expect the same number of backticks
        to close the block."""
        self._w("b/y.md", "")
        body = "````markdown\n[Y](y.md)\n````\n\nAnother ```` fence with 4 tildes:\n~~~~\n[Z](z.md)\n~~~~"
        new, changed, unresolved = okf_check.rewrite_crosslinks_in_body(self.tmp, "b", "", body)
        # Links inside fences should not be rewritten
        self.assertEqual(new, body)
        self.assertEqual(changed, 0)
        self.assertEqual(unresolved, [])

    def test_five_backtick_fence_blocks_are_masked(self):
        """Test 5-backtick fences (common for escaping code examples that
        themselves contain triple-backtick examples)."""
        self._w("b/inner.md", "")
        body = "`````\n[Y](inner.md)\n`````"
        new, changed, unresolved = okf_check.rewrite_crosslinks_in_body(self.tmp, "b", "", body)
        self.assertEqual(new, body)
        self.assertEqual(changed, 0)
        self.assertEqual(unresolved, [])

    def test_multiple_fence_styles_same_document(self):
        """Verify that various fence styles don't interfere with each other."""
        self._w("b/a.md", "")
        self._w("b/b.md", "")
        body = "```\n[A](a.md)\n```\n\n````\n[B](b.md)\n````\n\n~~~\n[A](a.md)\n~~~"
        new, changed, unresolved = okf_check.rewrite_crosslinks_in_body(self.tmp, "b", "", body)
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
        touched, unresolved = okf_check.fix_crosslinks(self.tmp, "b")
        self.assertEqual(len(touched), 1)
        self.assertEqual(unresolved, [])
        content = self._r("b/x.md")
        self.assertIn("[Y](/b/y.md)", content)
        self.assertTrue(content.startswith("---\ntype: Concept\ntitle: X\n---\n"))

    def test_dry_run_does_not_write(self):
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n[Y](y.md)\n")
        self._w("b/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        before = self._r("b/x.md")
        touched, unresolved = okf_check.fix_crosslinks(self.tmp, "b", dry_run=True)
        self.assertEqual(len(touched), 1)
        self.assertEqual(self._r("b/x.md"), before)

    def test_reserved_file_is_not_rewritten(self):
        self._w("b/index.md", "# B\n\n[X](x.md)\n")
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n# X\n")
        touched, unresolved = okf_check.fix_crosslinks(self.tmp, "b")
        self.assertNotIn("b/index.md", [t[0] for t in touched])
        self.assertIn("(x.md)", self._r("b/index.md"))

    def test_unresolved_links_are_reported(self):
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n[Ghost](ghost.md)\n")
        touched, unresolved = okf_check.fix_crosslinks(self.tmp, "b")
        self.assertEqual(touched, [])
        self.assertIn(("b/x.md", "ghost.md"), unresolved)

    def test_include_reserved_rewrites_outside_marker_only(self):
        block = "<!-- okf:index -->\n* [Y](y.md)\n<!-- /okf:index -->"
        self._w("b/index.md",
                "# B\n\n[Rel](y.md)\n\n[Legacy](/y.md)\n\n" + block + "\n")
        self._w("b/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        touched, unresolved = okf_check.fix_crosslinks(self.tmp, "b", include_reserved=True)
        self.assertIn("b/index.md", [t[0] for t in touched])
        content = self._r("b/index.md")
        self.assertIn(block, content)
        self.assertIn("[Rel](/b/y.md)", content)
        self.assertIn("[Legacy](/b/y.md)", content)

    def test_include_reserved_rewrites_reserved_file_without_marker(self):
        self._w("b/index.md", "# B\n\n[Y](y.md)\n")
        self._w("b/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        touched, unresolved = okf_check.fix_crosslinks(self.tmp, "b", include_reserved=True)
        self.assertIn("b/index.md", [t[0] for t in touched])
        self.assertIn("[Y](/b/y.md)", self._r("b/index.md"))

    def test_include_reserved_does_not_change_non_reserved_behavior(self):
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n[Y](y.md)\n")
        self._w("b/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        touched, unresolved = okf_check.fix_crosslinks(self.tmp, "b", include_reserved=True)
        self.assertEqual(len(touched), 1)
        self.assertIn("[Y](/b/y.md)", self._r("b/x.md"))

    def test_include_reserved_protects_unterminated_marker(self):
        self._w("b/index.md", "[Y](y.md)\n\n<!-- okf:index -->\n[Z](y.md)\n")
        self._w("b/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        touched, unresolved = okf_check.fix_crosslinks(self.tmp, "b", include_reserved=True)
        content = self._r("b/index.md")
        self.assertIn("[Y](/b/y.md)", content)
        self.assertIn("<!-- okf:index -->\n[Z](y.md)\n", content)

    def test_include_reserved_dry_run_reports_without_writing(self):
        self._w("b/index.md", "[Y](y.md)\n")
        self._w("b/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        before = self._r("b/index.md")
        touched, unresolved = okf_check.fix_crosslinks(
            self.tmp, "b", dry_run=True, include_reserved=True)
        self.assertIn("b/index.md", [t[0] for t in touched])
        self.assertEqual(self._r("b/index.md"), before)

    def test_include_reserved_ignores_index_exempt_marker(self):
        self._w("b/index.md", "<!-- okf:index-exempt -->\n[Y](y.md)\n")
        self._w("b/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        touched, unresolved = okf_check.fix_crosslinks(self.tmp, "b", include_reserved=True)
        self.assertIn("b/index.md", [t[0] for t in touched])
        self.assertIn("[Y](/b/y.md)", self._r("b/index.md"))


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
        errors, _warnings = okf_check.run_checks(self.tmp, None)
        rels = [rel for _name, rel, _msg in errors]
        self.assertIn("other-scaffolding/bad.md", rels)

    def test_unscoped_wikilinks_still_reports_the_unresolved_link(self):
        links = okf_wikilinks.scan_wikilinks(self.tmp, None)
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
        errors, warnings = okf_check.run_checks(self.tmp, None)
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
        errors, warnings = okf_check.run_checks(self.repo, "b")
        self.assertIn("type-registered", [w[0] for w in warnings])

    def test_central_types_source_accepts_registered(self):
        self._w(self.central, "TYPES.md",
                "| type | Meaning |\n|---|---|\n| `Glossary` | x |\n")
        self._w(self.repo, ".okf.toml",
                'types_source = "{}"\n'.format(os.path.join(self.central, "TYPES.md")))
        self._w(self.repo, "b/g.md", "---\ntype: Glossary\ntitle: G\n---\n# G\n")
        errors, warnings = okf_check.run_checks(self.repo, "b")
        self.assertNotIn("type-registered", [w[0] for w in warnings])

    def test_explicit_types_source_arg_overrides_config(self):
        self._w(self.central, "TYPES.md", "| type | Meaning |\n|---|---|\n| `Concept` | x |\n")
        self._w(self.repo, "b/x.md", "---\ntype: Concept\ntitle: X\n---\n# X\n")
        errors, warnings = okf_check.run_checks(
            self.repo, "b", types_source=os.path.join(self.central, "TYPES.md"))
        self.assertNotIn("type-registered", [w[0] for w in warnings])


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
        errors, warnings = okf_check.run_checks(self.tmp, "b")
        self.assertNotIn("tag-registered", self._names(warnings))
        self.assertIsNone(okf_catalogue.load_tags(self.tmp))

    def test_unknown_tag_warns(self):
        self._w("TAGS.md", okf_catalogue.TAGS_HEADER + "| `known` |  |\n")
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\ntags:\n  - known\n  - novel\n---\n# X\n")
        errors, warnings = okf_check.run_checks(self.tmp, "b")
        self.assertIn("tag-registered", self._names(warnings))
        msgs = [m for n, _p, m in warnings if n == "tag-registered"]
        self.assertTrue(any("novel" in m for m in msgs))
        self.assertFalse(any("known" in m for m in msgs))

    def test_all_known_tags_clean(self):
        self._w("TAGS.md", okf_catalogue.TAGS_HEADER + "| `a` |  |\n| `b` |  |\n")
        self._w("c/x.md", "---\ntype: Concept\ntitle: X\ntags:\n  - a\n  - b\n---\n# X\n")
        errors, warnings = okf_check.run_checks(self.tmp, "c")
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
        ap = argparse.ArgumentParser()
        okf_tags.add_tags_parser(ap.add_subparsers(dest="cmd", required=True))
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                ap.parse_args(["tags", "--register", "only-a-tag"])
        ns = ap.parse_args(["tags", "--register", "a", "da", "--register", "b", "db"])
        self.assertEqual(ns.register, [["a", "da"], ["b", "db"]])


class WikilinkCheck(WikilinkFixtureMixin, unittest.TestCase):
    """REQ-13/REQ-14 — the wikilink-resolvable check and its opt-in gate."""

    def _optin(self, *bundles):
        self._w(".okf.toml", "wikilink_checked_bundles = [{}]\n".format(
            ", ".join('"{}"'.format(b) for b in bundles)))

    def _findings(self, target=None):
        errors, warnings = okf_check.run_checks(self.tmp, target)
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
        errors, warnings = okf_check.run_checks(self.tmp, None)
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
        real = okf_wikilinks.build_concept_basename_index
        okf_wikilinks.build_concept_basename_index = lambda root: (calls.append(root), real(root))[1]
        try:
            self._w("a/x.md", "---\ntype: Concept\n---\nSee [[ghost]].\n")
            okf_check.run_checks(self.tmp, None)
            self.assertEqual(calls, [])
            self._optin("a")
            okf_check.run_checks(self.tmp, None)
            self.assertEqual(len(calls), 1)
            calls.clear()
            okf_check.run_checks(self.tmp, "b")        # scope excludes the opted-in bundle
            self.assertEqual(calls, [])
        finally:
            okf_wikilinks.build_concept_basename_index = real

    def test_non_array_config_is_announced_not_swallowed(self):
        """A config that reads as if it opted a bundle in, but does not, is
        worse than no config: the run looks clean for the wrong reason."""
        import contextlib
        import io
        self._w(".okf.toml", 'wikilink_checked_bundles = "a"\n')
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            got = okf_wikilinks.wikilink_checked_bundles(okf_catalogue.load_okf_config(self.tmp), self.tmp)
        self.assertEqual(got, set())
        self.assertIn("must be an array", err.getvalue())

    def test_unknown_bundle_in_config_is_announced(self):
        import contextlib
        import io
        self._optin("nosuchbundle")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            okf_wikilinks.wikilink_checked_bundles(okf_catalogue.load_okf_config(self.tmp), self.tmp)
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
            got = okf_wikilinks.wikilink_checked_bundles(okf_catalogue.load_okf_config(self.tmp), self.tmp)
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
        errors, warnings = okf_check.run_checks(self.tmp, "b")
        self.assertIn("superseded-by-resolves", self._names(errors))

    def test_resolving_superseded_by_target_is_clean(self):
        self._w("b/y.md", "---\ntype: Decision\ntitle: Y\n---\n# Y\n")
        self._w("b/x.md", "---\ntype: Decision\ntitle: X\n"
                          "superseded_by: /b/y.md\n---\n# X\n")
        errors, warnings = okf_check.run_checks(self.tmp, "b")
        self.assertNotIn("superseded-by-resolves", self._names(errors))

    def test_superseded_by_on_non_decision_concept_is_warning(self):
        self._w("b/y.md", "---\ntype: Decision\ntitle: Y\n---\n# Y\n")
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n"
                          "superseded_by: /b/y.md\n---\n# X\n")
        errors, warnings = okf_check.run_checks(self.tmp, "b")
        self.assertIn("superseded-by-scope", self._names(warnings))

    def test_superseded_by_on_decision_concept_has_no_scope_warning(self):
        self._w("b/y.md", "---\ntype: Decision\ntitle: Y\n---\n# Y\n")
        self._w("b/x.md", "---\ntype: Decision\ntitle: X\n"
                          "superseded_by: /b/y.md\n---\n# X\n")
        errors, warnings = okf_check.run_checks(self.tmp, "b")
        self.assertNotIn("superseded-by-scope", self._names(warnings))

    def test_absent_superseded_by_is_clean(self):
        self._w("b/x.md", "---\ntype: Decision\ntitle: X\n---\n# X\n")
        errors, warnings = okf_check.run_checks(self.tmp, "b")
        self.assertNotIn("superseded-by-resolves", self._names(errors))
        self.assertNotIn("superseded-by-scope", self._names(warnings))


class SyncCheckValidators(SyncFixtureMixin, unittest.TestCase):
    """The two check entries, and the laziness that keeps a catalogue without
    any materialised block from paying for the canon index."""

    def test_consumer_modified_is_an_error(self):
        self._insert()
        self._w("kc-proj/setup.md",
                self._r("kc-proj/setup.md").replace(
                    self.OWNER_PAYLOAD, "Lokal.\n"))
        errors, _ = okf_check.run_checks(self.tmp, None)
        self.assertIn(
            ("sync-block", "kc-proj/setup.md",
             "sync block `ownership-rule` from /kc-gov/ownership.md: "
             "consumer-modified"), errors)

    def test_source_changed_is_a_warning(self):
        self._insert()
        self._w("kc-gov/ownership.md",
                self._r("kc-gov/ownership.md").replace(
                    self.OWNER_PAYLOAD, "Neuer Kanon.\n"))
        errors, warnings = okf_check.run_checks(self.tmp, None)
        self.assertEqual([e for e in errors if e[0] == "sync-block"], [])
        self.assertIn("sync-stale", [w[0] for w in warnings])

    def test_duplicate_canon_id_is_an_error(self):
        self._w("kc-gov/ownership.md",
                self._r("kc-gov/ownership.md")
                + "\n<!-- okf:canon id=ownership-rule -->\nzweimal\n"
                + okf_catalogue.CANON_END + "\n")
        errors, _ = okf_check.run_checks(self.tmp, None)
        self.assertIn(("canon-block", "kc-gov/ownership.md",
                       "canon block id `ownership-rule` declared twice"), errors)

    def test_unterminated_canon_marker_is_an_error(self):
        self._w("kc-gov/ownership.md",
                "---\ntype: Rule\ndescription: d\n---\n\n"
                "<!-- okf:canon id=x -->\ntext\n")
        errors, _ = okf_check.run_checks(self.tmp, None)
        self.assertIn("canon-block", [e[0] for e in errors])

    def test_catalogue_without_sync_blocks_never_builds_the_canon_index(self):
        calls = []
        real = okf_sync.build_canon_block_index
        okf_sync.build_canon_block_index = lambda root: (calls.append(root)
                                                         or real(root))
        try:
            errors, warnings = okf_check.run_checks(self.tmp, None)
        finally:
            okf_sync.build_canon_block_index = real
        self.assertEqual(calls, [])
        self.assertEqual([e for e in errors if e[0].startswith("sync")], [])
        self.assertEqual([w for w in warnings if w[0].startswith("sync")], [])


if __name__ == "__main__":
    unittest.main()
