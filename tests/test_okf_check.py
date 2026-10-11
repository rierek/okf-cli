#!/usr/bin/env python3
"""Tests for cli/okf/check.py — the conformance scan: its rules, the check
engine, and the fix-crosslinks and fix-xml-tags repairs. unittest.

Run: just test tests.test_okf_check -v
"""
import argparse
import contextlib
import io
import json
import os
import re
import shutil
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
from okf import check as okf_check
from okf.diffs import write_plan
from okf.errors import EXIT_CODES
from okf import rename as okf_rename
from okf import sync as okf_sync
from okf import tags as okf_tags
from okf import wikilinks as okf_wikilinks
from tests.git_preview import HAS_GIT, GitPreviewMixin
from tests.okf_testkit import SyncFixtureMixin, _cli, _scan, needs_case_insensitive_fs
from tests.test_okf_wikilinks import WikilinkFixtureMixin


def _applied(planner, root, *args, **kwargs):
    """Run a fix planner, write its plan and return its result unchanged. The plan is the third
    entry of fix_crosslinks' result and the second of the others."""
    result = planner(root, *args, **kwargs)
    write_plan(root, result[2] if len(result) == 4 else result[1])
    return result


class CheckCommand(unittest.TestCase):
    """T06 — okf-cli check: the conformance scan over the RULES registry.
    error = §9 hard rules + filename/asset placement (exit 4).
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
        errors, warnings = _scan(self.tmp, "b")
        self.assertIn("okf/frontmatter/parseable", self._names(errors))
        self.assertNotIn("okf/frontmatter/type-nonempty", self._names(errors))  # not double-flagged

    def test_invalid_yaml_is_one_parseable_error_with_the_parser_reason_and_no_other_finding(self):
        self._w("b/bad.md", "---\ntype: Note\ndescription: Stack-Umzug: Vergleich\ntitel: x\n"
                            "tags: [a]\n---\n# Bad\n")
        errors, warnings = _scan(self.tmp, "b")
        self.assertEqual([e for e in errors + warnings if e[1] == "b/bad.md"], [(
            "okf/frontmatter/parseable", "b/bad.md",
            "no parseable frontmatter: mapping values are not allowed here (line 3, column 25)")])

    def test_a_block_that_is_not_a_mapping_is_a_parseable_error_too(self):
        self._w("b/list.md", "---\n- a\n- b\n---\n# L\n")
        errors, _warnings = _scan(self.tmp, "b")
        self.assertEqual([e for e in errors if e[1] == "b/list.md"], [(
            "okf/frontmatter/parseable", "b/list.md", "no parseable frontmatter: block is not a mapping")])

    def test_typed_yaml_values_are_checked_without_error(self):
        self._w("b/typed.md", "---\ntype: 7\ntitle: 2026-08-07\ntags: 5\nsuperseded_by: true\n"
                              "nested:\n  a:\n    - 1\n---\n# T\n")
        errors, warnings = _scan(self.tmp, "b")
        self.assertEqual([e for e in errors + warnings if e[1] == "b/typed.md"], [
            ("kc/supersede/resolves", "b/typed.md", "superseded_by target does not resolve: true"),
            ("kc/supersede/scope", "b/typed.md",
             "superseded_by used on non-Decision concept (type=7)")])

    def test_empty_type_is_error(self):
        self._w("b/x.md", "---\ntype: \ntitle: X\n---\n# X\n")
        errors, warnings = _scan(self.tmp, "b")
        self.assertIn("okf/frontmatter/type-nonempty", self._names(errors))
        self.assertNotIn("okf/frontmatter/parseable", self._names(errors))

    def test_reserved_file_with_type_is_error(self):
        self._w("b/index.md", "---\ntype: Concept\n---\n# B\n")
        errors, warnings = _scan(self.tmp, "b")
        self.assertIn("okf/type/reserved-no-type", self._names(errors))

    def test_filename_forbidden_char_is_error(self):
        self._w("b/weird%name.md", "---\ntype: Concept\n---\n# W\n")
        errors, warnings = _scan(self.tmp, "b")
        self.assertIn("kc/name/filename-chars", self._names(errors))

    def test_asset_outside_assets_dir_is_error(self):
        self._w("b/index.md", "# B\n")
        self._w("b/diagram.png", "not a real png")
        errors, warnings = _scan(self.tmp, "b")
        self.assertIn("kc/asset/placement", self._names(errors))

    def test_asset_inside_assets_dir_is_clean(self):
        self._w("b/index.md", "# B\n")
        self._w("b/assets/diagram.png", "not a real png")
        errors, warnings = _scan(self.tmp, "b")
        self.assertNotIn("kc/asset/placement", self._names(errors))

    def test_asset_inside_nested_assets_dir_is_clean(self):
        self._w("b/index.md", "# B\n")
        self._w("b/sub/assets/diagram.png", "not a real png")
        errors, warnings = _scan(self.tmp, "b")
        self.assertNotIn("kc/asset/placement", self._names(errors))

    def test_underscore_prefixed_dir_is_excluded_from_scan(self):
        # mirrors is_bundle_dir's convention: "_"-prefixed dirs are staging,
        # not catalogue content — same exemption applied one level down.
        self._w("b/index.md", "# B\n\nBundle entry with an intro paragraph.\n")
        self._w("b/_intake/raw.md", "# no frontmatter\n")
        self._w("b/_intake/notes.tsv", "col1\tcol2\n")
        errors, warnings = _scan(self.tmp, "b")
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_unregistered_type_is_warning(self):
        self._w("TYPES.md", "| type | Meaning |\n|---|---|\n| `Concept` | x |\n")
        self._w("b/x.md", "---\ntype: Bogus\ntitle: X\n---\n# X\n")
        errors, warnings = _scan(self.tmp, "b")
        self.assertIn("kc/type/registered", self._names(warnings))
        self.assertNotIn("kc/type/registered", self._names(errors))

    def test_registered_type_has_no_warning(self):
        self._w("TYPES.md", "| type | Meaning |\n|---|---|\n| `Concept` | x |\n")
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n# X\n")
        errors, warnings = _scan(self.tmp, "b")
        self.assertNotIn("kc/type/registered", self._names(warnings))

    def test_no_types_md_skips_type_registered_check(self):
        self._w("b/x.md", "---\ntype: AnythingGoes\ntitle: X\n---\n# X\n")
        errors, warnings = _scan(self.tmp, "b")
        self.assertNotIn("kc/type/registered", self._names(warnings))

    def test_german_frontmatter_key_is_warning(self):
        self._w("b/x.md", "---\ntype: Concept\ntitel: X\n---\n# X\n")
        errors, warnings = _scan(self.tmp, "b")
        self.assertIn("kc/frontmatter/english-keys", self._names(warnings))

    def test_relative_crosslink_is_warning(self):
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n# X\n\n[Y](y.md)\n")
        errors, warnings = _scan(self.tmp, "b")
        self.assertIn("kc/link/crosslink-format", self._names(warnings))

    def test_catalogue_root_crosslink_is_clean(self):
        self._w("b/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n# X\n\n[Y](/b/y.md)\n")
        errors, warnings = _scan(self.tmp, "b")
        self.assertNotIn("kc/link/crosslink-format", self._names(warnings))

    def test_reserved_file_relative_link_outside_marker_is_warning(self):
        """D-rx51-01 (OKFT-rx51): a hand-authored relative link in index.md's
        prose, outside the managed `<!-- okf:index -->` block, is a real
        crosslink and must be caught the same as one in a concept file."""
        self._w("b/index.md", "# B\n\nSee [Old](old.md) for background.\n\n"
                              + okf_catalogue.MARK_START + "\n" + okf_catalogue.MARK_END + "\n")
        errors, warnings = _scan(self.tmp, "b")
        self.assertIn("kc/link/crosslink-format", self._names(warnings))

    def test_reserved_file_link_inside_marker_is_clean(self):
        """D-rx51-01: the managed block is masked before the scan, so a
        generated (relative-by-convention) link inside it never warns —
        RESERVED files becoming a scan source must not regress the common
        case of an ordinary reindexed index.md."""
        self._w("b/index.md", "# B\n\n" + okf_catalogue.MARK_START + "\n* [X](x.md)\n"
                              + okf_catalogue.MARK_END + "\n")
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n# X\n")
        errors, warnings = _scan(self.tmp, "b")
        self.assertNotIn("kc/link/crosslink-format", self._names(warnings))

    def test_cross_bundle_dotdot_link_is_flagged(self):
        """Inverted with the canonical form: check_crosslink_format flags ANY
        relative link now, `../other/y.md` included, because it resolves
        inconsistently and orphans in Obsidian. fix-crosslinks migrates it."""
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n# X\n\n[Y](../other/y.md)\n")
        errors, warnings = _scan(self.tmp, "b")
        self.assertIn("kc/link/crosslink-format", self._names(warnings))

    def test_clean_bundle_has_zero_violations(self):
        self._w("TYPES.md", "| type | Meaning |\n|---|---|\n| `Concept` | x |\n")
        self._w("b/index.md", "# B\n\nBundle entry with an intro paragraph.\n\n## Contents\n\n"
                              + okf_catalogue.MARK_START + "\n* [X](x.md)\n" + okf_catalogue.MARK_END + "\n")
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\ntags:\n  - a\n---\n# X\n\n[Y](/b/index.md)\n")
        errors, warnings = _scan(self.tmp, "b")
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_whole_catalogue_scan_when_no_target(self):
        self._w("b1/x.md", "# X\n\nno frontmatter.\n")
        self._w("b2/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        errors, warnings = _scan(self.tmp, None)
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
        touched, unresolved, _plan, _skipped = _applied(okf_check.fix_crosslinks, self.tmp, "b")
        self.assertEqual(len(touched), 1)
        self.assertEqual(unresolved, [])
        content = self._r("b/x.md")
        self.assertIn("[Y](/b/y.md)", content)
        self.assertTrue(content.startswith("---\ntype: Concept\ntitle: X\n---\n"))

    def test_dry_run_does_not_write(self):
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n[Y](y.md)\n")
        self._w("b/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        before = self._r("b/x.md")
        touched, unresolved, _plan, _skipped = okf_check.fix_crosslinks(self.tmp, "b")
        self.assertEqual(len(touched), 1)
        self.assertEqual(self._r("b/x.md"), before)

    def test_reserved_file_is_not_rewritten(self):
        self._w("b/index.md", "# B\n\n[X](x.md)\n")
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n# X\n")
        touched, unresolved, _plan, _skipped = _applied(okf_check.fix_crosslinks, self.tmp, "b")
        self.assertNotIn("b/index.md", [t[0] for t in touched])
        self.assertIn("(x.md)", self._r("b/index.md"))

    def test_unresolved_links_are_reported(self):
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n[Ghost](ghost.md)\n")
        touched, unresolved, _plan, _skipped = _applied(okf_check.fix_crosslinks, self.tmp, "b")
        self.assertEqual(touched, [])
        self.assertIn(("b/x.md", "ghost.md"), unresolved)

    def test_include_reserved_rewrites_outside_marker_only(self):
        block = "<!-- okf:index -->\n* [Y](y.md)\n<!-- /okf:index -->"
        self._w("b/index.md",
                "# B\n\n[Rel](y.md)\n\n[Legacy](/y.md)\n\n" + block + "\n")
        self._w("b/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        touched, unresolved, _plan, _skipped = _applied(okf_check.fix_crosslinks, self.tmp, "b", include_reserved=True)
        self.assertIn("b/index.md", [t[0] for t in touched])
        content = self._r("b/index.md")
        self.assertIn(block, content)
        self.assertIn("[Rel](/b/y.md)", content)
        self.assertIn("[Legacy](/b/y.md)", content)

    def test_include_reserved_rewrites_reserved_file_without_marker(self):
        self._w("b/index.md", "# B\n\n[Y](y.md)\n")
        self._w("b/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        touched, unresolved, _plan, _skipped = _applied(okf_check.fix_crosslinks, self.tmp, "b", include_reserved=True)
        self.assertIn("b/index.md", [t[0] for t in touched])
        self.assertIn("[Y](/b/y.md)", self._r("b/index.md"))

    def test_include_reserved_does_not_change_non_reserved_behavior(self):
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n[Y](y.md)\n")
        self._w("b/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        touched, unresolved, _plan, _skipped = _applied(okf_check.fix_crosslinks, self.tmp, "b", include_reserved=True)
        self.assertEqual(len(touched), 1)
        self.assertIn("[Y](/b/y.md)", self._r("b/x.md"))

    def test_include_reserved_protects_unterminated_marker(self):
        self._w("b/index.md", "[Y](y.md)\n\n<!-- okf:index -->\n[Z](y.md)\n")
        self._w("b/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        touched, unresolved, _plan, _skipped = _applied(okf_check.fix_crosslinks, self.tmp, "b", include_reserved=True)
        content = self._r("b/index.md")
        self.assertIn("[Y](/b/y.md)", content)
        self.assertIn("<!-- okf:index -->\n[Z](y.md)\n", content)

    def test_include_reserved_dry_run_reports_without_writing(self):
        self._w("b/index.md", "[Y](y.md)\n")
        self._w("b/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        before = self._r("b/index.md")
        touched, unresolved, _plan, _skipped = okf_check.fix_crosslinks(
            self.tmp, "b", include_reserved=True)
        self.assertIn("b/index.md", [t[0] for t in touched])
        self.assertEqual(self._r("b/index.md"), before)

    def test_include_reserved_ignores_index_exempt_marker(self):
        self._w("b/index.md", "<!-- okf:index-exempt -->\n[Y](y.md)\n")
        self._w("b/y.md", "---\ntype: Concept\ntitle: Y\n---\n# Y\n")
        touched, unresolved, _plan, _skipped = _applied(okf_check.fix_crosslinks, self.tmp, "b", include_reserved=True)
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
        errors, _warnings = _scan(self.tmp, None)
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
        errors, warnings = _scan(self.tmp, None)
        findings = errors + warnings
        paths = [path for name, path, _message in findings
                 if name == "kc/link/wikilink-resolvable"]
        self.assertIn("declared-bundle/source.md", paths)
        self.assertNotIn("topic-folder/source.md", paths)


class ConfigAwareTypes(unittest.TestCase):
    """kc/type/registered check resolves TYPES.md via .okf.toml types_source,
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
        errors, warnings = _scan(self.repo, "b")
        self.assertIn("kc/type/registered", [w[0] for w in warnings])

    def test_central_types_source_accepts_registered(self):
        self._w(self.central, "TYPES.md",
                "| type | Meaning |\n|---|---|\n| `Glossary` | x |\n")
        self._w(self.repo, ".okf.toml",
                'types_source = "{}"\n'.format(os.path.join(self.central, "TYPES.md")))
        self._w(self.repo, "b/g.md", "---\ntype: Glossary\ntitle: G\n---\n# G\n")
        errors, warnings = _scan(self.repo, "b")
        self.assertNotIn("kc/type/registered", [w[0] for w in warnings])

    def test_explicit_types_source_arg_overrides_config(self):
        self._w(self.central, "TYPES.md", "| type | Meaning |\n|---|---|\n| `Concept` | x |\n")
        self._w(self.repo, "b/x.md", "---\ntype: Concept\ntitle: X\n---\n# X\n")
        errors, warnings = _scan(
            self.repo, "b", types_source=os.path.join(self.central, "TYPES.md"))
        self.assertNotIn("kc/type/registered", [w[0] for w in warnings])


class TagRegistryGate(unittest.TestCase):
    """Closed-tag-vocabulary: kc/tag/registered check + register_tags/load_tags.
    TAGS.md is the allow-list; unknown tags warn (`--strict` counts them toward the exit code).
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
        errors, warnings = _scan(self.tmp, "b")
        self.assertNotIn("kc/tag/registered", self._names(warnings))
        self.assertIsNone(okf_catalogue.load_tags(self.tmp))

    def test_unknown_tag_warns(self):
        self._w("TAGS.md", okf_catalogue.TAGS_HEADER + "| `known` |  |\n")
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\ntags:\n  - known\n  - novel\n---\n# X\n")
        errors, warnings = _scan(self.tmp, "b")
        self.assertIn("kc/tag/registered", self._names(warnings))
        msgs = [m for n, _p, m in warnings if n == "kc/tag/registered"]
        self.assertTrue(any("novel" in m for m in msgs))
        self.assertFalse(any("known" in m for m in msgs))

    def test_all_known_tags_clean(self):
        self._w("TAGS.md", okf_catalogue.TAGS_HEADER + "| `a` |  |\n| `b` |  |\n")
        self._w("c/x.md", "---\ntype: Concept\ntitle: X\ntags:\n  - a\n  - b\n---\n# X\n")
        errors, warnings = _scan(self.tmp, "c")
        self.assertNotIn("kc/tag/registered", self._names(warnings))

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
    """REQ-13/REQ-14 — the kc/link/wikilink-resolvable check and its opt-in gate."""

    def _optin(self, *bundles):
        self._w(".okf.toml", "wikilink_checked_bundles = [{}]\n".format(
            ", ".join('"{}"'.format(b) for b in bundles)))

    def _findings(self, target=None):
        errors, warnings = _scan(self.tmp, target)
        return [(n, p, m) for n, p, m in errors + warnings if n == "kc/link/wikilink-resolvable"]

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

    def test_strict_run_exits_non_conformant(self):
        self._optin("a")
        self._w("a/index.md", "# A\n\nIntro.\n")
        self._w("a/x.md", "---\ntype: Concept\n---\nSee [[ghost]].\n")
        out = _cli(self.tmp, "check", "--strict")
        self.assertEqual(out.returncode, EXIT_CODES["non_conformant"])
        self.assertIn("kc/link/wikilink-resolvable", out.stdout)

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
        errors, warnings = _scan(self.tmp, None)
        self.assertIn("kc/link/wikilink-resolvable", [w[0] for w in warnings])
        self.assertNotIn("kc/link/wikilink-resolvable", [e[0] for e in errors])
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
            _scan(self.tmp, None)
            self.assertEqual(calls, [])
            self._optin("a")
            _scan(self.tmp, None)
            self.assertEqual(len(calls), 1)
            calls.clear()
            _scan(self.tmp, "b")        # scope excludes the opted-in bundle
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
            self.assertEqual(out.returncode, EXIT_CODES["not_found"], bad)
            self.assertIn(bad, out.stderr, bad)

    def test_malformed_config_fails_with_a_message_not_a_traceback(self):
        """load_okf_config is now on every check path, so a parse failure has to
        name the file — including when --types made it irrelevant before."""
        self._w(".okf.toml", "this is not = = toml\n")
        out = _cli(self.tmp, "check", "--types", os.path.join(self.tmp, "TYPES.md"))
        self.assertEqual(out.returncode, EXIT_CODES["invalid_input"])
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
        errors, warnings = _scan(self.tmp, "b")
        self.assertIn("kc/supersede/resolves", self._names(errors))

    def test_resolving_superseded_by_target_is_clean(self):
        self._w("b/y.md", "---\ntype: Decision\ntitle: Y\n---\n# Y\n")
        self._w("b/x.md", "---\ntype: Decision\ntitle: X\n"
                          "superseded_by: /b/y.md\n---\n# X\n")
        errors, warnings = _scan(self.tmp, "b")
        self.assertNotIn("kc/supersede/resolves", self._names(errors))

    def test_superseded_by_on_non_decision_concept_is_warning(self):
        self._w("b/y.md", "---\ntype: Decision\ntitle: Y\n---\n# Y\n")
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n"
                          "superseded_by: /b/y.md\n---\n# X\n")
        errors, warnings = _scan(self.tmp, "b")
        self.assertIn("kc/supersede/scope", self._names(warnings))

    def test_superseded_by_on_decision_concept_has_no_scope_warning(self):
        self._w("b/y.md", "---\ntype: Decision\ntitle: Y\n---\n# Y\n")
        self._w("b/x.md", "---\ntype: Decision\ntitle: X\n"
                          "superseded_by: /b/y.md\n---\n# X\n")
        errors, warnings = _scan(self.tmp, "b")
        self.assertNotIn("kc/supersede/scope", self._names(warnings))

    def test_absent_superseded_by_is_clean(self):
        self._w("b/x.md", "---\ntype: Decision\ntitle: X\n---\n# X\n")
        errors, warnings = _scan(self.tmp, "b")
        self.assertNotIn("kc/supersede/resolves", self._names(errors))
        self.assertNotIn("kc/supersede/scope", self._names(warnings))


class SyncCheckValidators(SyncFixtureMixin, unittest.TestCase):
    """The two check entries, and the laziness that keeps a catalogue without
    any materialised block from paying for the canon index."""

    def test_consumer_modified_is_an_error(self):
        self._insert()
        self._w("kc-proj/setup.md",
                self._r("kc-proj/setup.md").replace(
                    self.OWNER_PAYLOAD, "Lokal.\n"))
        errors, _ = _scan(self.tmp, None)
        self.assertIn(
            ("kc/sync/block", "kc-proj/setup.md",
             "sync block `ownership-rule` from /kc-gov/ownership.md: "
             "consumer-modified"), errors)

    def test_source_changed_is_a_warning(self):
        self._insert()
        self._w("kc-gov/ownership.md",
                self._r("kc-gov/ownership.md").replace(
                    self.OWNER_PAYLOAD, "Neuer Kanon.\n"))
        errors, warnings = _scan(self.tmp, None)
        self.assertEqual([e for e in errors if e[0] == "kc/sync/block"], [])
        self.assertIn("kc/sync/stale", [w[0] for w in warnings])

    def test_duplicate_canon_id_is_an_error(self):
        self._w("kc-gov/ownership.md",
                self._r("kc-gov/ownership.md")
                + "\n<!-- okf:canon id=ownership-rule -->\nzweimal\n"
                + okf_catalogue.CANON_END + "\n")
        errors, _ = _scan(self.tmp, None)
        self.assertIn(("kc/sync/canon-block", "kc-gov/ownership.md",
                       "canon block id `ownership-rule` declared twice"), errors)

    def test_unterminated_canon_marker_is_an_error(self):
        self._w("kc-gov/ownership.md",
                "---\ntype: Rule\ndescription: d\n---\n\n"
                "<!-- okf:canon id=x -->\ntext\n")
        errors, _ = _scan(self.tmp, None)
        self.assertIn("kc/sync/canon-block", [e[0] for e in errors])

    def test_catalogue_without_sync_blocks_never_builds_the_canon_index(self):
        calls = []
        real = okf_sync.build_canon_block_index
        okf_sync.build_canon_block_index = lambda root: (calls.append(root)
                                                         or real(root))
        try:
            errors, warnings = _scan(self.tmp, None)
        finally:
            okf_sync.build_canon_block_index = real
        self.assertEqual(calls, [])
        self.assertEqual([e for e in errors if e[0].startswith("sync")], [])
        self.assertEqual([w for w in warnings if w[0].startswith("sync")], [])


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
        touched, _, _, _ = _applied(okf_check.fix_crosslinks, self.tmp, "b")
        self.assertEqual({p for p, _ in touched},
                         {"b/published.md", "b/_intake/staged.md"})
        self.assertIn("(/b/old.md)", self._r("b/_intake/staged.md"))

    def test_fix_xml_tags_reaches_staging(self):
        touched, _, _ = _applied(okf_check.fix_xml_like_tags, self.tmp, "b")
        self.assertEqual({p for p, _ in touched},
                         {"b/published.md", "b/_intake/staged.md"})
        self.assertIn("`<PLACEHOLDER>`", self._r("b/_intake/staged.md"))

    def test_rewrite_path_reaches_staging(self):
        touched, _, _ = _applied(okf_rename.rewrite_path, self.tmp, "old/path", "new/path")
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
        _applied(okf_check.fix_crosslinks, self.tmp, None)
        self.assertEqual(self._r("kc-proj/setup.md"), self.consumer_before)

    def test_fix_xml_tags_leaves_the_block_byte_identical(self):
        _applied(okf_check.fix_xml_like_tags, self.tmp, None)
        self.assertEqual(self._r("kc-proj/setup.md"), self.consumer_before)

    def test_crosslink_and_xml_checks_report_nothing_for_the_consumer(self):
        ctx = okf_check.gather_file_context(
            self.tmp, "kc-proj", os.path.join(self.tmp, "kc-proj/setup.md"))
        self.assertEqual(okf_check.check_crosslink_format(ctx), [])
        self.assertEqual(okf_check.check_xml_like_tags(ctx), [])

    def test_wikilink_in_a_synced_payload_is_not_scanned(self):
        body = okf_catalogue.read_frontmatter(self._r("kc-proj/setup.md")).body
        self.assertEqual(okf_wikilinks.parse_wikilinks(body), [])

    def test_rename_leaves_the_payload_intact_and_rewrites_the_source(self):
        expected = okf_sync.parse_sync_blocks(
            okf_catalogue.read_frontmatter(self.consumer_before).body)[0]["payload"]
        okf_rename.perform_rename(self.tmp,
                                  os.path.join(self.tmp, "kc-proj/setup.md"),
                                  os.path.join(self.tmp, "kc-proj/setup2.md"),
                                  apply=True, force=True)
        # The payload wikilinks to the renamed concept and must NOT be
        # rewritten: the owner's copy is the one that carries that link.
        self.assertEqual(self._payload_of("kc-proj/setup2.md"), expected)
        okf_rename.perform_rename(self.tmp,
                                  os.path.join(self.tmp, "kc-gov/ownership.md"),
                                  os.path.join(self.tmp, "kc-gov/canon/ownership.md"),
                                  apply=True, force=True)
        body = okf_catalogue.read_frontmatter(self._r("kc-proj/setup2.md")).body
        self.assertEqual(okf_sync.parse_sync_blocks(body)[0]["source"],
                         "/kc-gov/canon/ownership.md")


class RuleRegistry(unittest.TestCase):
    """R-09 — RULES is the one registry of rule IDs and severities; the engine
    runs what it lists."""

    def test_every_id_matches_the_rule_id_pattern(self):
        for rule in okf_check.RULES:
            self.assertRegex(rule.id, r"^(okf|kc)/[a-z-]+/[a-z-]+$")

    def test_no_id_occurs_twice(self):
        ids = [rule.id for rule in okf_check.RULES]
        self.assertEqual(sorted(i for i in ids if ids.count(i) > 1), [])

    def test_every_severity_is_error_or_warning(self):
        for rule in okf_check.RULES:
            self.assertIn(rule.severity, ("error", "warning"), rule.id)

    def test_engine_runs_the_registry_not_a_local_list(self):
        only = okf_check.Rule("kc/test/only", "warning", "file", lambda ctx: ["boom"])
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        os.makedirs(os.path.join(tmp, "b"))
        with open(os.path.join(tmp, "b", "x.md"), "w", encoding="utf-8") as f:
            f.write("# X\n\nno frontmatter at all.\n")
        with mock.patch.object(okf_check, "RULES", [only]):
            errors, warnings = _scan(tmp, "b")
        self.assertEqual((errors, warnings), ([], [("kc/test/only", "b/x.md", "boom")]))


class FindingShape(unittest.TestCase):
    """R-09 — every finding of `check` carries rule, severity, path and message;
    `--strict` changes what counts toward the exit code, never a severity."""

    FINDING_KEYS = ["rule", "severity", "path", "message"]

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self._w(".okf.toml", "")
        self._w("b/index.md", "# B\n\nBundle entry with an intro paragraph.\n")
        # the only violation: kc/frontmatter/english-keys, a warning-severity rule
        self._w("b/g.md", "---\ntype: Concept\ntitel: X\n---\n# G\n")

    def _w(self, rel, text):
        ap = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(text)

    def _with_error(self):
        self._w("b/nofm.md", "# no frontmatter\n")  # okf/frontmatter/parseable, error

    def test_engine_returns_one_list_of_findings_with_severity(self):
        self._with_error()
        findings = okf_check.run_checks(self.tmp, "b")
        self.assertIsInstance(findings, list)
        self.assertEqual(sorted((f.rule, f.severity, f.path) for f in findings), [
            ("kc/frontmatter/english-keys", "warning", "b/g.md"),
            ("okf/frontmatter/parseable", "error", "b/nofm.md")])

    def test_json_is_one_object_with_only_findings_each_with_exact_keys(self):
        self._with_error()
        r = _cli(self.tmp, "check", "--json")
        self.assertEqual((r.returncode, r.stderr), (EXIT_CODES["non_conformant"], ""))
        env = json.loads(r.stdout)
        self.assertEqual(list(env), ["command", "ok", "data", "warnings", "error"])
        self.assertEqual(env["warnings"], [])  # findings never travel as call warnings
        out = env["data"]
        self.assertEqual(list(out), ["findings"])
        self.assertEqual([list(f) for f in out["findings"]], [self.FINDING_KEYS] * 2)
        self.assertEqual(sorted((f["rule"], f["severity"], f["path"]) for f in out["findings"]), [
            ("kc/frontmatter/english-keys", "warning", "b/g.md"),
            ("okf/frontmatter/parseable", "error", "b/nofm.md")])

    def test_strict_json_keeps_the_warning_severity_and_still_fails(self):
        r = _cli(self.tmp, "check", "--strict", "--json")
        self.assertEqual((r.returncode, r.stderr), (EXIT_CODES["non_conformant"], ""))
        out = json.loads(r.stdout)["data"]
        self.assertEqual([(f["rule"], f["severity"]) for f in out["findings"]],
                         [("kc/frontmatter/english-keys", "warning")])

    def test_without_strict_a_warning_is_reported_and_exits_0(self):
        r = _cli(self.tmp, "check", "--json")
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertEqual([(f["rule"], f["severity"]) for f in json.loads(r.stdout)["data"]["findings"]],
                         [("kc/frontmatter/english-keys", "warning")])

    def test_text_line_starts_with_own_severity_and_summary_counts_errors_only(self):
        self._with_error()
        r = _cli(self.tmp, "check")
        self.assertEqual(r.returncode, EXIT_CODES["non_conformant"])
        lines = r.stdout.splitlines()
        self.assertEqual([(l.split()[0], l.split()[1]) for l in lines[:-1]], [
            ("ERROR", "okf/frontmatter/parseable"),
            ("WARNING", "kc/frontmatter/english-keys")])
        self.assertEqual(lines[-1], "1 VIOLATIONS")

    def test_text_under_strict_keeps_warning_label_and_counts_it(self):
        r = _cli(self.tmp, "check", "--strict")
        self.assertEqual(r.returncode, EXIT_CODES["non_conformant"])
        lines = r.stdout.splitlines()
        self.assertEqual([l.split()[:2] for l in lines[:-1]],
                         [["WARNING", "kc/frontmatter/english-keys"]])
        self.assertEqual(lines[-1], "1 VIOLATIONS")

    def test_text_without_counting_finding_ends_ok_summary(self):
        r = _cli(self.tmp, "check")
        self.assertEqual(r.returncode, 0)
        lines = r.stdout.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("WARNING  kc/frontmatter/english-keys"), lines[0])
        self.assertEqual(lines[1], "OK — 0 violations")

    def test_clean_tree_text_is_the_ok_summary_alone(self):
        os.remove(os.path.join(self.tmp, "b", "g.md"))
        r = _cli(self.tmp, "check")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "OK — 0 violations\n", ""))

    def test_output_order_does_not_depend_on_discovery_order(self):
        findings = [okf_check.Finding(rule, sev, path, "m") for rule, sev, path in (
            ("kc/a/w", "warning", "b/z.md"), ("kc/a/e", "error", "b/y.md"),
            ("kc/a/w", "warning", "b/a.md"), ("kc/a/e", "error", "b/b.md"))]

        def report(fs, as_json):
            """The printed text; in envelope mode what the failure carries as its result."""
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                with self.assertRaises(okf_check.OkfError) as raised:
                    okf_check.report_findings(fs, False, as_json)
            return raised.exception.result if as_json else buf.getvalue()

        for as_json in (False, True):
            self.assertEqual(report(findings, as_json), report(findings[::-1], as_json))
        self.assertEqual([f["path"] for f in report(findings, True)["findings"]],
                         ["b/b.md", "b/y.md", "b/a.md", "b/z.md"])


class SuppressRules(unittest.TestCase):
    """R-10 — `check --ignore <pattern>` (repeatable) and `.okf.toml`
    `ignore_rules` silence rules by exact ID or by prefix with a trailing `*`;
    a suppressed finding neither prints nor counts, with or without --strict."""

    KC_ERROR = "kc/name/filename-chars"
    OKF_ERROR = "okf/frontmatter/parseable"
    KC_WARNING = "kc/frontmatter/english-keys"
    OK = "OK — 0 violations\n"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self._w("b/index.md", "# B\n\nBundle entry with an intro paragraph.\n")

    def _w(self, rel, text):
        ap = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(text)

    def _config(self, body=""):
        self._w(".okf.toml", body)

    def _kc_error(self):
        self._w("b/weird%name.md", "---\ntype: Concept\n---\n# W\n")

    def _okf_error(self):
        self._w("b/nofm.md", "# no frontmatter\n")

    def _kc_warning(self):
        self._w("b/g.md", "---\ntype: Concept\ntitel: X\n---\n# G\n")

    def _rules(self, r):
        return [f["rule"] for f in json.loads(r.stdout)["data"]["findings"]]

    def test_ignore_prefix_turns_exit_4_into_0(self):
        self._config()
        self._kc_error()
        control = _cli(self.tmp, "check")
        self.assertEqual((control.returncode, control.stderr),
                         (EXIT_CODES["non_conformant"], ""))
        self.assertIn(self.KC_ERROR, control.stdout)
        r = _cli(self.tmp, "check", "--ignore", "kc/*")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, self.OK, ""))

    def test_ignore_rules_config_entry_turns_exit_4_into_0(self):
        self._kc_error()
        self._config("")
        self.assertEqual(_cli(self.tmp, "check").returncode, EXIT_CODES["non_conformant"])
        self._config('ignore_rules = ["{}"]\n'.format(self.KC_ERROR))
        r = _cli(self.tmp, "check")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, self.OK, ""))

    def test_pattern_without_star_matches_only_the_identical_id(self):
        self._config()
        self._kc_error()
        for pattern in ("kc/name", "kc/name/filename", "kc/name/filename-chars-x", "kc/*/filename-chars",
                        "kc/name/filename.chars", "KC/NAME/FILENAME-CHARS"):
            with self.subTest(pattern=pattern):
                r = _cli(self.tmp, "check", "--ignore", pattern)
                self.assertEqual(r.returncode, EXIT_CODES["non_conformant"], r.stdout)
        r = _cli(self.tmp, "check", "--ignore", self.KC_ERROR)
        self.assertEqual((r.returncode, r.stdout), (0, self.OK))

    def test_trailing_star_matches_every_id_with_that_prefix(self):
        self._config()
        self._kc_error()
        for pattern in ("kc/name/*", "kc/n*", "kc/name/filename-chars*", "kc/*", "*"):
            with self.subTest(pattern=pattern):
                r = _cli(self.tmp, "check", "--ignore", pattern)
                self.assertEqual((r.returncode, r.stdout), (0, self.OK))
        for pattern in ("okf/*", "kc/type/*", "kc/name/x*"):
            with self.subTest(pattern=pattern):
                r = _cli(self.tmp, "check", "--ignore", pattern)
                self.assertEqual(r.returncode, EXIT_CODES["non_conformant"])

    def test_a_suppressed_finding_is_absent_from_text_and_json_the_rest_stays(self):
        self._config()
        self._kc_error()
        self._okf_error()
        text = _cli(self.tmp, "check", "--ignore", "kc/*")
        self.assertEqual(text.returncode, EXIT_CODES["non_conformant"])
        self.assertNotIn(self.KC_ERROR, text.stdout)
        self.assertIn(self.OKF_ERROR, text.stdout)
        self.assertEqual(text.stdout.splitlines()[-1], "1 VIOLATIONS")
        js = _cli(self.tmp, "check", "--ignore", "kc/*", "--json")
        self.assertEqual(js.returncode, EXIT_CODES["non_conformant"])
        self.assertEqual(self._rules(js), [self.OKF_ERROR])

    def test_strict_does_not_count_a_suppressed_warning(self):
        self._config()
        self._kc_warning()
        strict = _cli(self.tmp, "check", "--strict")
        self.assertEqual(strict.returncode, EXIT_CODES["non_conformant"])
        r = _cli(self.tmp, "check", "--strict", "--ignore", "kc/frontmatter/*")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, self.OK, ""))
        js = _cli(self.tmp, "check", "--strict", "--json", "--ignore", self.KC_WARNING)
        self.assertEqual((js.returncode, json.loads(js.stdout)["data"]), (0, {"findings": []}))

    def test_flag_and_config_patterns_are_united_and_the_flag_repeats(self):
        self._kc_error()
        self._okf_error()
        self._config('ignore_rules = ["kc/*"]\n')
        for argv in (("--ignore", "okf/*"), ("--ignore", self.OKF_ERROR)):
            with self.subTest(argv=argv):
                r = _cli(self.tmp, "check", *argv)
                self.assertEqual((r.returncode, r.stdout), (0, self.OK))
        only_config = _cli(self.tmp, "check")
        self.assertEqual(only_config.returncode, EXIT_CODES["non_conformant"])
        self._config("")
        r = _cli(self.tmp, "check", "--ignore", "kc/*", "--ignore", "okf/*")
        self.assertEqual((r.returncode, r.stdout), (0, self.OK))

    def test_malformed_ignore_rules_suppresses_nothing_and_says_so_on_stderr(self):
        self._kc_error()
        for toml, shown in (('"kc/*"', "'kc/*'"), ("7", "7"), ("true", "True"),
                            ('["kc/*", 1]', "['kc/*', 1]"), ("[[1]]", "[[1]]")):
            with self.subTest(value=toml):
                self._config("ignore_rules = {}\n".format(toml))
                r = _cli(self.tmp, "check")
                self.assertEqual(r.returncode, EXIT_CODES["non_conformant"], r.stdout)
                self.assertIn(self.KC_ERROR, r.stdout)
                self.assertTrue(r.stderr.startswith("note: ignore_rules "), r.stderr)
                self.assertIn("got {} ".format(shown), r.stderr)

    def test_a_flag_still_applies_when_the_config_value_is_malformed(self):
        self._kc_error()
        self._config('ignore_rules = "kc/*"\n')
        r = _cli(self.tmp, "check", "--ignore", self.KC_ERROR)
        self.assertEqual((r.returncode, r.stdout), (0, self.OK))
        self.assertTrue(r.stderr.startswith("note: ignore_rules "), r.stderr)

    def test_absent_or_empty_ignore_rules_suppresses_nothing_silently(self):
        self._kc_error()
        for body in ("", "ignore_rules = []\n"):
            with self.subTest(body=body):
                self._config(body)
                r = _cli(self.tmp, "check")
                self.assertEqual((r.returncode, r.stderr), (EXIT_CODES["non_conformant"], ""))
                self.assertIn(self.KC_ERROR, r.stdout)


@unittest.skipUnless(HAS_GIT, "git not installed")
class FixVerbPreviewEqualsGitDiff(GitPreviewMixin, unittest.TestCase):
    """OKFT-d6an SC-01 — per file, the `--check` preview of fix-crosslinks (with and without
    --include-reserved) and fix-xml-tags equals the `git diff` after the write run; a file that is not
    valid UTF-8 is reported and never rewritten."""

    FILES = {
        "b/x.md": b"---\ntype: Concept\ntitle: X\n---\n[Y](y.md)\n" + b"line\n" * 20 + b"<PLACEHOLDER> [Y](y.md)\n",
        "b/y.md": b"---\ntype: Concept\ntitle: Y\n---\n# Y\n",
        "b/sub/crlf.md": b"---\r\ntype: Concept\r\ntitle: C\r\n---\r\n[Y](../y.md)\r\n<A.B>\r\n",
        "b/nonl.md": b"---\ntype: Concept\ntitle: N\n---\n[Y](y.md) <TAG>",
        "b/index.md": b"# B\n\n[Rel](y.md)\n\n<!-- okf:index -->\n* [Y](y.md)\n<!-- /okf:index -->\n",
        "b/latin.md": b"---\ntype: Concept\ntitle: L\n---\n[Y](y.md) <TAG> caf\xe9\n",
    }

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_preview_equals_git_diff_after_write_run(self):
        for verb, extra in (("fix-crosslinks", []), ("fix-crosslinks", ["--include-reserved"]),
                            ("fix-xml-tags", [])):
            with self.subTest(verb=verb, extra=extra):
                shutil.rmtree(self.tmp, ignore_errors=True)
                os.makedirs(self.tmp)
                self.commit_files(self.tmp, self.FILES)
                preview = self.assert_preview_equals_git_diff(
                    self.tmp,
                    lambda: self.json_files(self.tmp, verb, "b", "--check", *extra),
                    lambda: self.json_files(self.tmp, verb, "b", *extra))
                paths = [f["path"] for f in preview]
                self.assertEqual(paths, sorted(paths))
                self.assertNotIn("b/latin.md", paths)
                with open(os.path.join(self.tmp, "b/latin.md"), "rb") as f:
                    self.assertEqual(f.read(), self.FILES["b/latin.md"])
                self.assertEqual("b/index.md" in paths, bool(extra))


if __name__ == "__main__":
    unittest.main()
