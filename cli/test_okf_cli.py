#!/usr/bin/env python3
"""Tests for okf-cli.py — stdlib unittest, no deps.

Run: python3 -m unittest test_okf_cli -v
"""
import argparse
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import struct
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("okf_cli", os.path.join(_HERE, "okf-cli.py"))
okf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(okf)

M0, M1 = okf.MARK_START, okf.MARK_END


class ConvertFlatIndex(unittest.TestCase):
    """T01 — smart --init: wrap a flat hand-curated list, skip bespoke curation."""

    def test_flat_single_section_gets_converted(self):
        text = (
            "# Architekturmethodik\n\n"
            "Methodische Kernschicht.\n\n"
            "## Concepts\n\n"
            "* [A](a.md) - desc a\n"
            "* [B](b.md) - desc b\n"
        )
        new, status = okf.convert_flat_index(text)
        self.assertEqual(status, "converted")
        # markers present, old bullets gone, H1 + intro + heading preserved
        self.assertIn(M0, new)
        self.assertIn(M1, new)
        self.assertNotIn("* [A](a.md)", new)
        self.assertNotIn("* [B](b.md)", new)
        self.assertIn("# Architekturmethodik", new)
        self.assertIn("Methodische Kernschicht.", new)
        self.assertIn("## Concepts", new)
        # marker block sits after the heading, start before end
        self.assertLess(new.index("## Concepts"), new.index(M0))
        self.assertLess(new.index(M0), new.index(M1))

    def test_multi_section_is_skipped(self):
        text = (
            "# Title\n\nIntro.\n\n"
            "## Section One\n\n* [A](a.md)\n\n"
            "## Section Two\n\n* [B](b.md)\n"
        )
        new, status = okf.convert_flat_index(text)
        self.assertEqual(status, "skip-multi-section")
        self.assertEqual(new, text)

    def test_already_managed_is_left_alone(self):
        text = (
            "# Title\n\n## Contents\n\n"
            + M0 + "\n* [A](a.md)\n" + M1 + "\n"
        )
        new, status = okf.convert_flat_index(text)
        self.assertEqual(status, "already-managed")
        self.assertEqual(new, text)

    def test_trailing_prose_after_list_is_skipped(self):
        # bullets do not run to EOF -> unsafe to auto-wrap
        text = (
            "# Title\n\n## Concepts\n\n"
            "* [A](a.md)\n\n"
            "Some trailing note that must not be lost.\n"
        )
        new, status = okf.convert_flat_index(text)
        self.assertEqual(status, "skip-trailing-content")
        self.assertEqual(new, text)

    def test_no_list_section_is_skipped(self):
        # single h2 but no bullet list under it
        text = "# Title\n\nIntro only, no sections, no bullets.\n"
        new, status = okf.convert_flat_index(text)
        self.assertEqual(status, "skip-no-list")
        self.assertEqual(new, text)


class InitIndexesRecursion(unittest.TestCase):
    """T02 — recursive, guarded --init over a subtree, with a dry-run mode."""

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

    def _build(self):
        self._w("b/index.md", "# B\n\nintro\n\n## Contents\n\n"
                              "* [Sub1](sub1/index.md)\n* [Sub2](sub2/index.md)\n")
        self._w("b/sub1/index.md", "# Sub1\n\n## Concepts\n\n* [X](x.md) - d\n")
        self._w("b/sub2/index.md", "# Sub2\n\n## Alpha\n\n* [Y](y.md)\n\n## Beta\n\n* [Z](z.md)\n")

    def test_recurses_and_writes_conversions(self):
        self._build()
        results = dict(okf.init_indexes(self.tmp, os.path.join(self.tmp, "b"), dry_run=False))
        self.assertEqual(results["b/index.md"], "converted")
        self.assertEqual(results["b/sub1/index.md"], "converted")
        self.assertEqual(results["b/sub2/index.md"], "skip-multi-section")
        # writes happened for the converted ones
        self.assertIn(M0, self._r("b/index.md"))
        self.assertIn(M0, self._r("b/sub1/index.md"))
        # bespoke multi-section left byte-for-byte intact
        self.assertNotIn(M0, self._r("b/sub2/index.md"))
        self.assertIn("## Beta", self._r("b/sub2/index.md"))

    def test_dry_run_reports_but_writes_nothing(self):
        self._build()
        before = self._r("b/sub1/index.md")
        results = dict(okf.init_indexes(self.tmp, os.path.join(self.tmp, "b"), dry_run=True))
        self.assertEqual(results["b/sub1/index.md"], "converted")
        # no write in dry-run
        self.assertEqual(self._r("b/sub1/index.md"), before)
        self.assertNotIn(M0, self._r("b/sub1/index.md"))

    def test_recognizes_uppercase_index_filename(self):
        # Real-world repos sometimes use INDEX.md — discovery must be
        # case-insensitive (matches the already-case-insensitive RESERVED
        # check) instead of silently skipping the dir (B-2026-07-08).
        self._w("b/sub3/INDEX.md", "# Sub3\n\n## Concepts\n\n* [W](w.md) - d\n")
        results = dict(okf.init_indexes(self.tmp, os.path.join(self.tmp, "b"), dry_run=False))
        self.assertEqual(results["b/sub3/INDEX.md"], "converted")
        self.assertIn(M0, self._r("b/sub3/INDEX.md"))


class EnsureMarkersCreateOnly(unittest.TestCase):
    """ensure_markers must not naively append to a marker-less file that has
    content (convert_flat_index owns that case now). It only creates if missing."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_creates_index_when_missing(self):
        okf.ensure_markers(self.tmp)
        idx = os.path.join(self.tmp, "index.md")
        self.assertTrue(os.path.isfile(idx))
        with open(idx, encoding="utf-8") as f:
            self.assertIn(M0, f.read())

    def test_leaves_markerless_content_untouched(self):
        idx = os.path.join(self.tmp, "index.md")
        body = "# T\n\n## Concepts\n\n* [A](a.md)\n"
        with open(idx, "w", encoding="utf-8") as f:
            f.write(body)
        okf.ensure_markers(self.tmp)
        with open(idx, encoding="utf-8") as f:
            self.assertEqual(f.read(), body)  # no naive append


class UncoveredIndexDirs(unittest.TestCase):
    """I02 — a marker-less index.md that has concept files is UNCOVERED: no
    safety net proves the files appear in the index. Empty dirs are fine."""

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

    def test_flags_markerless_dir_with_concepts(self):
        self._w("b/index.md", "# B\n\n## A\n\n* [x](x.md)\n\n## Z\n\n* [y](y.md)\n")  # curated, no markers
        self._w("b/x.md", "---\ntype: Concept\n---\n# X\n")
        self._w("b/y.md", "---\ntype: Concept\n---\n# Y\n")
        un = okf.uncovered_index_dirs(self.tmp, os.path.join(self.tmp, "b"))
        self.assertIn("b/index.md", un)

    def test_managed_dir_is_not_uncovered(self):
        self._w("b/index.md", "# B\n\n" + M0 + "\n" + M1 + "\n")
        self._w("b/x.md", "---\ntype: Concept\n---\n# X\n")
        un = okf.uncovered_index_dirs(self.tmp, os.path.join(self.tmp, "b"))
        self.assertEqual(un, [])

    def test_markerless_but_empty_dir_is_not_uncovered(self):
        self._w("b/index.md", "# B\n\nno concepts here\n")
        un = okf.uncovered_index_dirs(self.tmp, os.path.join(self.tmp, "b"))
        self.assertEqual(un, [])

    def test_flags_uppercase_index_filename(self):
        # B-2026-07-08: uppercase INDEX.md must not be silently invisible.
        self._w("b/INDEX.md", "# B\n\n## A\n\n* [x](x.md)\n")
        self._w("b/x.md", "---\ntype: Concept\n---\n# X\n")
        un = okf.uncovered_index_dirs(self.tmp, os.path.join(self.tmp, "b"))
        self.assertIn("b/INDEX.md", un)


class ForceFlattenAndExempt(unittest.TestCase):
    """Q01 — --force flattens a pure multi-section listing (sections optional);
    a content page marked exempt is dropped from the coverage gate."""

    def test_force_flattens_pure_multi_section(self):
        text = ("# T\n\nintro\n\n## Alpha\n\n* [A](a.md)\n\n## Beta\n\n* [B](b.md)\n")
        new, status = okf.convert_flat_index(text, force=True)
        self.assertEqual(status, "converted")
        self.assertIn(M0, new)
        self.assertIn("intro", new)          # intro before first ## preserved
        self.assertNotIn("## Alpha", new)     # sub-section headings dropped
        self.assertNotIn("* [A](a.md)", new)  # old bullets removed (reindex refills)

    def test_force_refuses_when_prose_present(self):
        text = ("# T\n\n## Alpha\n\n| tbl | col |\n\n## Beta\n\n* [B](b.md)\n")
        new, status = okf.convert_flat_index(text, force=True)
        self.assertNotEqual(status, "converted")   # table = real content, not flattened
        self.assertEqual(new, text)

    def test_without_force_multi_section_still_skipped(self):
        text = ("# T\n\n## Alpha\n\n* [A](a.md)\n\n## Beta\n\n* [B](b.md)\n")
        new, status = okf.convert_flat_index(text, force=False)
        self.assertEqual(status, "skip-multi-section")

    def test_uncovered_skips_exempt_index(self):
        import tempfile
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "b"))
            with open(os.path.join(tmp, "b", "index.md"), "w") as f:
                f.write("# B\n\n" + okf.EXEMPT + "\n\ncurated content page\n")
            with open(os.path.join(tmp, "b", "x.md"), "w") as f:
                f.write("---\ntype: Concept\n---\n# X\n")
            un = okf.uncovered_index_dirs(tmp, os.path.join(tmp, "b"))
            self.assertEqual(un, [])
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class RenderGitLog(unittest.TestCase):
    """T04 — render git history as a SPEC §7 date-grouped flat list."""

    def test_groups_by_date_newest_first(self):
        rows = [
            ("2026-07-04", "feat(x): a"),
            ("2026-07-04", "chore(y): b"),
            ("2026-07-03", "fix(z): c"),
        ]
        md = okf.render_git_log("dev-arch-wiki", rows)
        self.assertIn("# dev-arch-wiki Update Log", md)
        # one heading per date, newest first
        self.assertEqual(md.count("## 2026-07-04"), 1)
        self.assertLess(md.index("## 2026-07-04"), md.index("## 2026-07-03"))
        # both same-day commits land under the one date heading, as bullets
        self.assertIn("* feat(x): a", md)
        self.assertIn("* chore(y): b", md)
        self.assertIn("* fix(z): c", md)
        # bullet b sits after its date heading and before the next date heading
        self.assertLess(md.index("* chore(y): b"), md.index("## 2026-07-03"))

    def test_empty_history_still_has_header(self):
        md = okf.render_git_log("dev-arch-wiki", [])
        self.assertIn("# dev-arch-wiki Update Log", md)


class SpliceLog(unittest.TestCase):
    """T05 — --write is marker-bounded: refresh the snapshot, never clobber the
    hand-authored archive that lives outside the markers."""

    def test_replaces_only_between_markers(self):
        existing = (
            "# Catalogue Update Log\n\n> notice\n\n"
            + okf.LOG_START + "\nOLD SNAPSHOT\n" + okf.LOG_END
            + "\n\n## Archiv\n* precious hand entry\n"
        )
        new = okf.splice_log(existing, "NEW SNAPSHOT")
        self.assertIn("NEW SNAPSHOT", new)
        self.assertNotIn("OLD SNAPSHOT", new)
        self.assertIn("* precious hand entry", new)   # archive outside markers preserved
        self.assertIn("> notice", new)

    def test_wraps_markerless_file_and_preserves_content_as_archive(self):
        existing = "# Catalogue Update Log\n\n## 2026-07-04\n* precious hand entry\n"
        new = okf.splice_log(existing, "SNAP")
        self.assertIn(okf.LOG_START, new)
        self.assertIn("SNAP", new)
        self.assertIn("* precious hand entry", new)    # old content kept, not lost
        # snapshot block comes before the preserved archive
        self.assertLess(new.index("SNAP"), new.index("* precious hand entry"))


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
                              + okf.MARK_START + "\n* [X](x.md)\n" + okf.MARK_END + "\n")
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


class FixCrosslinksCommand(unittest.TestCase):
    """T09 — fix_crosslinks: file-level orchestration, frontmatter untouched,
    reserved files skipped (parity with check_crosslink_format's own scope),
    dry-run writes nothing."""

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


class OkfConfig(unittest.TestCase):
    """.okf.toml is the machine-truth config; absent or empty -> {}.
    ~ in path values is expanded."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _w(self, rel, text):
        with open(os.path.join(self.tmp, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def test_absent_config_is_empty_dict(self):
        self.assertEqual(okf.load_okf_config(self.tmp), {})

    def test_parses_keys(self):
        self._w(".okf.toml", 'kc_root = "~/Obsidian/Knowledge-Catalogue"\n'
                             'types_source = "~/Obsidian/Knowledge-Catalogue/TYPES.md"\n'
                             'bundle = "demo-okf"\n')
        cfg = okf.load_okf_config(self.tmp)
        self.assertEqual(cfg["bundle"], "demo-okf")
        self.assertFalse(cfg["types_source"].startswith("~"))  # expanduser ran
        self.assertTrue(cfg["types_source"].endswith("Knowledge-Catalogue/TYPES.md"))


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


class RefMatrix(unittest.TestCase):
    """build_ref_matrix: every markdown link under scan_root resolving to the
    target file. Same link-regex as bundle_graph; code fences stripped; http/
    anchors ignored; relative + catalogue-root-absolute (/) both resolved."""

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

    def _sources(self, hits):
        return sorted(s for s, _ in hits)

    def test_same_dir_and_subdir_inbound(self):
        self._w("docs/arch.md", "# Arch\n")
        self._w("docs/overview.md", "see [arch](arch.md)\n")
        self._w("README.md", "see [arch](docs/arch.md)\n")
        hits = okf.build_ref_matrix(self.tmp, os.path.join(self.tmp, "docs/arch.md"))
        self.assertEqual(self._sources(hits), ["README.md", "docs/overview.md"])

    def test_catalogue_root_leading_slash_resolves(self):
        self._w("docs/arch.md", "# Arch\n")
        # /docs/arch.md — leading / is the CATALOGUE root, so the bundle
        # segment is part of the link.
        self._w("docs/x.md", "see [a](/docs/arch.md)\n")
        hits = okf.build_ref_matrix(self.tmp, os.path.join(self.tmp, "docs/arch.md"))
        self.assertEqual(self._sources(hits), ["docs/x.md"])

    def test_leading_slash_is_scan_root_not_bundle_root(self):
        """Inverted from the old bundle-root rule (and renamed, so the name
        stops asserting the opposite of the code): `/b1/x.md` names the same
        file no matter which bundle the link sits in, so BOTH sources are
        inbound references. Under the old reading the link in b2 would have
        meant b2/x.md and been unrelated."""
        self._w("b1/x.md", "# X\n")
        self._w("b1/foo.md", "[x](/b1/x.md)\n")
        self._w("b2/bar.md", "[x](/b1/x.md)\n")
        hits = okf.build_ref_matrix(self.tmp, os.path.join(self.tmp, "b1/x.md"))
        self.assertEqual(self._sources(hits), ["b1/foo.md", "b2/bar.md"])

    def test_http_and_anchor_and_fenced_ignored(self):
        self._w("docs/arch.md", "# Arch\n")
        self._w("docs/x.md",
                "[ext](https://arch.md)\n[frag](arch.md#top)\n```\n[fenced](arch.md)\n```\n")
        hits = okf.build_ref_matrix(self.tmp, os.path.join(self.tmp, "docs/arch.md"))
        # only the anchor link resolves to arch.md; http + fenced excluded
        self.assertEqual(self._sources(hits), ["docs/x.md"])
        self.assertEqual(len(hits), 1)

    def test_git_and_node_modules_pruned(self):
        self._w("docs/arch.md", "# Arch\n")
        self._w(".git/x.md", "[a](../docs/arch.md)\n")
        self._w("node_modules/y.md", "[a](../docs/arch.md)\n")
        hits = okf.build_ref_matrix(self.tmp, os.path.join(self.tmp, "docs/arch.md"))
        self.assertEqual(hits, [])

    def test_no_inbound_is_empty(self):
        self._w("docs/arch.md", "# Arch\n")
        hits = okf.build_ref_matrix(self.tmp, os.path.join(self.tmp, "docs/arch.md"))
        self.assertEqual(hits, [])


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

    def test_missing_target_exits_nonzero(self):
        import types
        args = types.SimpleNamespace(path="ghost.md", scan_root=self.tmp, json=True)
        with self.assertRaises(SystemExit) as cm:
            okf.cmd_refs(os.path.join(self.tmp, "docs"), args)
        self.assertNotEqual(cm.exception.code, 0)


class ResolveScopesTargets(unittest.TestCase):
    """resolve_scopes feeds check, fix-crosslinks, fix-xml-tags, reindex and
    every --scope. Normalising the target for the wikilink opt-in gate reaches
    all of them, so the other target forms are pinned here."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        for b in ("alpha", "beta"):
            os.makedirs(os.path.join(self.tmp, b, "sub"), exist_ok=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_relative_forms(self):
        for target, bundle, tail in (
            ("alpha", "alpha", "alpha"),
            ("alpha/", "alpha", "alpha"),
            ("alpha//", "alpha", "alpha"),
            ("./alpha", "alpha", "alpha"),
            ("alpha/sub", "alpha", "alpha/sub"),
            ("alpha/../beta", "beta", "beta"),
        ):
            got = okf.resolve_scopes(self.tmp, target)
            self.assertEqual(got[0][0], bundle, target)
            self.assertEqual(got[0][1], os.path.join(self.tmp, tail), target)

    def test_absolute_target_still_addresses_that_directory(self):
        """os.path.join(root, "/x") discards root, so an absolute target used to
        work by accident. Normalising it into a relative segment rescoped the
        scan onto a path that does not exist and reported a clean run."""
        ap = os.path.join(self.tmp, "beta")
        self.assertEqual(okf.resolve_scopes(self.tmp, ap), [("beta", ap)])

    def test_dot_target_means_the_whole_catalogue(self):
        """`.` yielded a bundle literally named "." — every bundle-name-keyed
        rule then failed to match while the scan still walked the root."""
        for target in (".", "./"):
            self.assertEqual(okf.resolve_scopes(self.tmp, target),
                             okf.resolve_scopes(self.tmp, None), target)


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
        self.assertIsNone(okf.load_tags(self.tmp))

    def test_unknown_tag_warns(self):
        self._w("TAGS.md", okf.TAGS_HEADER + "| `known` |  |\n")
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\ntags:\n  - known\n  - novel\n---\n# X\n")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertIn("tag-registered", self._names(warnings))
        msgs = [m for n, _p, m in warnings if n == "tag-registered"]
        self.assertTrue(any("novel" in m for m in msgs))
        self.assertFalse(any("known" in m for m in msgs))

    def test_all_known_tags_clean(self):
        self._w("TAGS.md", okf.TAGS_HEADER + "| `a` |  |\n| `b` |  |\n")
        self._w("c/x.md", "---\ntype: Concept\ntitle: X\ntags:\n  - a\n  - b\n---\n# X\n")
        errors, warnings = okf.run_checks(self.tmp, "c")
        self.assertNotIn("tag-registered", self._names(warnings))

    def test_register_creates_and_appends(self):
        added, already = okf.register_tags(self.tmp, ["zebra", "alpha"])
        self.assertEqual(set(added), {"zebra", "alpha"})
        self.assertEqual(already, [])
        self.assertEqual(okf.load_tags(self.tmp), {"zebra", "alpha"})
        # idempotent + casefold-sorted output (alpha before zebra)
        added2, already2 = okf.register_tags(self.tmp, ["alpha", "mid"])
        self.assertEqual(added2, ["mid"])
        self.assertEqual(already2, ["alpha"])
        body = open(os.path.join(self.tmp, "TAGS.md"), encoding="utf-8").read()
        self.assertLess(body.index("`alpha`"), body.index("`mid`"))
        self.assertLess(body.index("`mid`"), body.index("`zebra`"))

    def test_register_preserves_descriptions(self):
        self._w("TAGS.md", okf.TAGS_HEADER + "| `a` | keep me |\n")
        okf.register_tags(self.tmp, ["b"])
        body = open(os.path.join(self.tmp, "TAGS.md"), encoding="utf-8").read()
        self.assertIn("| `a` | keep me |", body)


class AutoEmbedOnRegister(unittest.TestCase):
    """cmd_tags --register must auto-embed new tags (bge-m3) so registration
    and embedding coverage never drift apart (PO-review reject 2026-07-25,
    bean okf-cli-3geg: 125/418 tags were unembedded at review time because
    embedding was a fully manual, separate step). Best-effort: an embedding
    failure (e.g. Ollama down) must never block registration itself."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.bt = okf._load_build_tagvec()
        self._orig_embed = self.bt.embed_bge_m3

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.bt.embed_bge_m3 = self._orig_embed

    def test_register_command_auto_embeds_without_manual_produce(self):
        import types
        self.bt.embed_bge_m3 = lambda texts: [[0.1, 0.2, 0.3] for _ in texts]
        args = types.SimpleNamespace(register=["freshly-minted"])
        okf.cmd_tags(self.tmp, args)
        db_path = os.path.join(self.tmp, ".tagvec", "tag_vectors.sqlite")
        delta_after = self.bt.plan_delta({"freshly-minted"}, "bge-m3", db_path)
        self.assertEqual(delta_after, [])

    def test_embedding_failure_never_blocks_registration(self):
        import types
        def _boom(texts):
            raise RuntimeError("connection refused")
        self.bt.embed_bge_m3 = _boom
        args = types.SimpleNamespace(register=["still-registered"])
        okf.cmd_tags(self.tmp, args)  # must not raise
        self.assertEqual(okf.load_tags(self.tmp), {"still-registered"})


class RemoveTags(unittest.TestCase):
    """remove-tags: strip tags from frontmatter (no merge target), dry-run default,
    empties strip the whole tags field."""

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
        return ap

    def _run(self, tags, scope=None, apply=True):
        import types
        import contextlib
        import io
        args = types.SimpleNamespace(tags=tags, scope=scope, apply=apply)
        with contextlib.redirect_stdout(io.StringIO()):
            okf.cmd_remove_tags(self.tmp, args)

    def test_field_removal_block_form(self):
        text = "---\ntype: Concept\ntitle: X\ntags:\n  - a\n  - b\n---\n# X\n"
        out = okf.remove_tags_field(text)
        self.assertNotIn("tags:", out)
        self.assertIn("title: X", out)
        self.assertIn("# X", out)

    def test_field_removal_inline_form(self):
        text = "---\ntype: Concept\ntags: [a, b]\ntitle: X\n---\n# X\n"
        out = okf.remove_tags_field(text)
        self.assertNotIn("tags:", out)
        self.assertNotIn("[a, b]", out)
        self.assertIn("title: X", out)

    def test_field_removal_no_tags_returns_none(self):
        self.assertIsNone(okf.remove_tags_field("---\ntype: Concept\ntitle: X\n---\n# X\n"))

    def test_removes_one_keeps_others(self):
        ap = self._w("b/x.md", "---\ntype: Concept\ntitle: X\ntags:\n  - keep\n  - drop\n---\n# X\n")
        self._run(["drop"])
        new = open(ap, encoding="utf-8").read()
        self.assertIn("  - keep", new)
        self.assertNotIn("drop", new)

    def test_emptying_strips_tags_field(self):
        ap = self._w("b/x.md", "---\ntype: Concept\ntitle: X\ntags:\n  - only\n---\n# X\n")
        self._run(["only"])
        new = open(ap, encoding="utf-8").read()
        self.assertNotIn("tags:", new)
        self.assertIn("title: X", new)

    def test_dry_run_writes_nothing(self):
        original = "---\ntype: Concept\ntitle: X\ntags:\n  - drop\n---\n# X\n"
        ap = self._w("b/x.md", original)
        self._run(["drop"], apply=False)
        self.assertEqual(open(ap, encoding="utf-8").read(), original)

    def test_scope_limits_rewrite(self):
        a = self._w("b/x.md", "---\ntype: Concept\ntitle: X\ntags:\n  - drop\n---\n# X\n")
        b = self._w("c/y.md", "---\ntype: Concept\ntitle: Y\ntags:\n  - drop\n---\n# Y\n")
        self._run(["drop"], scope="b")
        self.assertNotIn("drop", open(a, encoding="utf-8").read())
        self.assertIn("drop", open(b, encoding="utf-8").read())  # out of scope, untouched


class RenderBundleLine(unittest.TestCase):
    """T-okf-cli-dwcq — compact one-liner for prime's default bundle listing."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _concept(self, bundle, name):
        ap = os.path.join(self.tmp, bundle, name)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: {}\n---\n# {}\n".format(name, name))

    def test_line_has_bundle_name_and_concept_count(self):
        self._concept("b", "one.md")
        self._concept("b", "two.md")
        line = okf.render_bundle_line(self.tmp, "b")
        self.assertEqual(line, "b (2 concepts)")

    def test_zero_concepts_still_renders(self):
        os.makedirs(os.path.join(self.tmp, "empty"))
        line = okf.render_bundle_line(self.tmp, "empty")
        self.assertEqual(line, "empty (0 concepts)")


class CmdPrimeBundleListing(unittest.TestCase):
    """T-okf-cli-dwcq — prime defaults to compact per-bundle lines; --full keeps
    today's full per-bundle blocks (description/directories/types/tags)."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, "CLAUDE.md"), "w", encoding="utf-8") as f:
            f.write("# Guide\n")
        ap = os.path.join(self.tmp, "b", "one.md")
        os.makedirs(os.path.dirname(ap))
        with open(ap, "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: One\n---\n# One\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _prime(self, full=False):
        import io, contextlib, types
        args = types.SimpleNamespace(full=full)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf.cmd_prime(self.tmp, args)
        return buf.getvalue()

    def test_default_uses_compact_line_not_description(self):
        out = self._prime(full=False)
        self.assertIn("b (1 concepts)", out)
        self.assertNotIn("description:", out)
        self.assertNotIn("directories:", out)

    def test_full_keeps_description_and_directories(self):
        out = self._prime(full=True)
        self.assertIn("description:", out)
        self.assertIn("concepts: 1", out)


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


class CmdIndexJson(unittest.TestCase):
    """okf-cli-83vq (B01) — `index <bundle> --json` emits a json.loads-parseable
    object with the bundle's concepts; non-json output stays unchanged."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        ap = os.path.join(self.tmp, "b", "one.md")
        os.makedirs(os.path.dirname(ap))
        with open(ap, "w", encoding="utf-8") as f:
            f.write("---\ntype: Runbook\ntitle: One\ndescription: first\n---\n# One\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, bundle=None, json_flag=False, full=False):
        import io, contextlib, types
        args = types.SimpleNamespace(bundle=bundle, full=full, json=json_flag)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf.cmd_index(self.tmp, args)
        return buf.getvalue()

    def test_json_output_with_bundle_is_parseable_object(self):
        import json
        out = self._run(bundle="b", json_flag=True)
        data = json.loads(out)
        self.assertEqual(data["bundle"], "b")
        self.assertIsInstance(data["concepts"], list)
        self.assertEqual(len(data["concepts"]), 1)
        concept = data["concepts"][0]
        self.assertTrue(all(k in concept for k in ("id", "title", "type", "description")))

    def test_json_output_without_bundle_is_parseable_object(self):
        import json
        out = self._run(bundle=None, json_flag=True)
        data = json.loads(out)
        self.assertIsInstance(data["bundles"], list)
        self.assertTrue(any(entry.get("bundle") == "b" for entry in data["bundles"]))

    def test_non_json_output_unchanged(self):
        out_json_false = self._run(bundle="b", json_flag=False)
        out_no_flag = self._run(bundle="b")
        self.assertEqual(out_json_false, out_no_flag)
        self.assertIn("* [One]", out_json_false)
        self.assertNotIn("{", out_json_false)

    def test_json_without_bundle_reports_a_concept_count_not_the_list(self):
        """okf-cli-7u5z (D01) — the catalogue-wide shape mirrors the text
        branch, which prints a count. Enumerating every concept of every
        bundle produced 794 KB against the real catalogue."""
        import json
        entry = json.loads(self._run(bundle=None, json_flag=True))["bundles"][0]
        self.assertEqual(entry["concepts"], 1)

    def test_json_without_bundle_carries_description_and_directories(self):
        """okf-cli-7u5z (D01) — the other two fields the text block shows."""
        import json
        os.makedirs(os.path.join(self.tmp, "b", "sub"))
        with open(os.path.join(self.tmp, "b", "index.md"), "w", encoding="utf-8") as f:
            f.write("# B\n\nthe b bundle\n")
        entry = json.loads(self._run(bundle=None, json_flag=True))["bundles"][0]
        self.assertEqual(entry["description"], "the b bundle")
        self.assertEqual(entry["directories"], ["sub"])


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
        got = okf.catalogue_root(self.tmp)
        self.assertEqual(got, os.path.abspath(self.tmp))

    def test_no_root_no_catalogue_returns_none(self):
        os.chdir(self.tmp)
        self.assertIsNone(okf.catalogue_root(None))

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
        self.assertEqual(okf.catalogue_root(None), os.getcwd())

    def test_auto_detect_spec_types_marker(self):
        # SC-003
        open(os.path.join(self.tmp, "SPEC.md"), "w", encoding="utf-8").close()
        open(os.path.join(self.tmp, "TYPES.md"), "w", encoding="utf-8").close()
        os.chdir(self.tmp)
        self.assertEqual(okf.catalogue_root(None), os.getcwd())

    def test_partial_marker_not_enough(self):
        open(os.path.join(self.tmp, "SPEC.md"), "w", encoding="utf-8").close()
        os.chdir(self.tmp)
        self.assertIsNone(okf.catalogue_root(None))

    def test_auto_detect_walks_up_from_subdir(self):
        # SC-003: ancestor lookup
        open(os.path.join(self.tmp, ".okf.toml"), "w", encoding="utf-8").close()
        sub = os.path.join(self.tmp, "a", "b")
        os.makedirs(sub)
        os.chdir(sub)
        expected = os.path.dirname(os.path.dirname(os.getcwd()))
        self.assertEqual(okf.catalogue_root(None), expected)


class FindFilterContract(unittest.TestCase):
    """I01 — --scope/--type/--tag constrain the ANSWER, not one arm of it.

    The regression this locks down (B01): the filters used to be applied by
    whichever arm happened to implement them, so the moment fuse_conditional
    handed ranking ownership to the semantic arm, a scoped query returned
    concepts from entirely different bundles. Testing an arm in isolation
    cannot catch that — which arm answers is decided per query at runtime. So
    every case here drives cmd_find, the seam where the user sets the filter,
    across all three ownership regimes:

      lexical   FTS index present, literal query -> the lexical arm owns
      semantic  FTS index present, no literal match -> the semantic arm owns
      degraded  no FTS index -> the substring scan answers

    Each case pairs a NEGATIVE assertion (the bait violating the filter is
    absent) with a POSITIVE one (the wanted concept is present). Without the
    positive half a filter that wrongly drops everything would pass."""

    # (filter kwarg, bait that must not survive it)
    DIMENSIONS = [
        ("scope", "keep/inner", ["keep/outer", "bait/cross"]),
        ("type", "Concept", ["keep/inner/type-bait"]),
        ("tag", "keeper", ["keep/inner/tag-bait"]),
    ]
    WANTED = "keep/inner/wanted"
    LITERAL = "zqxcontract"
    PARAPHRASE = "zzz-no-keyword-match-zzz"

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        body = "{} appears in every fixture body.\n".format(self.LITERAL)
        self._w("keep/inner/wanted.md", "Concept", "Wanted", ["keeper"], body)
        self._w("keep/inner/type-bait.md", "Pattern", "Type Bait", ["keeper"],
                body)
        self._w("keep/inner/tag-bait.md", "Concept", "Tag Bait", ["other"],
                body)
        # in-scope bundle but outside the scoped SUBDIR
        self._w("keep/outer.md", "Concept", "Outer Bait", ["keeper"], body)
        # different bundle entirely — the shape the user actually reported
        self._w("bait/cross.md", "Concept", "Cross Bait", ["keeper"], body)
        self._orig_embed = okf._embed_query_voyage
        okf._QUERY_VEC_CACHE.clear()
        # Every concept embeds to the same vector: which one the semantic arm
        # would rank first is irrelevant here, only which ones it may return.
        self._make_tagvec([
            ("k1", "keep/inner/wanted"), ("k2", "keep/inner/type-bait"),
            ("k3", "keep/inner/tag-bait"), ("k4", "keep/outer"),
            ("k5", "bait/cross"),
        ])
        okf._embed_query_voyage = lambda text: [1.0, 0.0]

    def tearDown(self):
        import shutil
        okf._embed_query_voyage = self._orig_embed
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _w(self, rel, typ, title, tags, body):
        ap = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(
                "---\ntype: {}\ntitle: {}\ntags: [{}]\ndescription: d\n---\n"
                "# {}\n\n{}".format(typ, title, ", ".join(tags), title, body)
            )

    def _make_tagvec(self, rows):
        db = os.path.join(self.tmp, ".tagvec", "tag_vectors.sqlite")
        os.makedirs(os.path.dirname(db), exist_ok=True)
        import sqlite3, struct
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE concept_emb(key TEXT PRIMARY KEY, path TEXT, "
            "model TEXT, dim INT, vec BLOB)"
        )
        for key, path in rows:
            conn.execute(
                "INSERT INTO concept_emb VALUES (?,?,?,?,?)",
                (key, path, "voyage-3-large", 2,
                 struct.pack("<2f", 1.0, 0.0)),
            )
        conn.commit()
        conn.close()

    def _paths(self, query, **kw):
        import io, contextlib, types
        args = types.SimpleNamespace(
            query=query, limit=10, type=None, tag=None, scope=None,
            breakdown=False,
        )
        for k, v in kw.items():
            setattr(args, k, v)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), \
                contextlib.redirect_stderr(io.StringIO()):
            okf.cmd_find(self.tmp, args)
        return [l[len("path: "):] for l in buf.getvalue().splitlines()
                if l.startswith("path: ")]

    def _check_every_dimension(self, query, regime):
        for kwarg, value, baits in self.DIMENSIONS:
            with self.subTest(regime=regime, filter=kwarg):
                paths = self._paths(query, **{kwarg: value})
                for bait in baits:
                    self.assertNotIn(bait, paths)
                self.assertIn(self.WANTED, paths)

    def _silence_semantic_arm(self):
        """Make the semantic arm unavailable so a lexical case really tests
        the lexical arm. Without this the arms cover for each other: the
        semantic arm reads its paths from concept_emb, so it would happily
        supply a correctly-filtered hit for a concept the lexical arm had
        just mangled or dropped, and the case would pass for the wrong
        reason (caught by mutation-testing this very class)."""
        def _unavailable(_text):
            raise OSError("semantic arm disabled for this regime")
        okf._embed_query_voyage = _unavailable

    def test_lexical_owned_ranking_honours_every_filter(self):
        okf.build_fts_index(self.tmp)
        self._silence_semantic_arm()
        self._check_every_dimension(self.LITERAL, "lexical")

    def test_semantic_owned_ranking_honours_every_filter(self):
        okf.build_fts_index(self.tmp)
        # Guard the regime itself: if a literal match crept in, the lexical
        # arm would own the ranking and this would silently retest the case
        # above instead of the one B01 broke.
        self.assertEqual(self._paths(self.PARAPHRASE, scope="keep/inner"),
                         [self.WANTED, "keep/inner/type-bait",
                          "keep/inner/tag-bait"])
        self._check_every_dimension(self.PARAPHRASE, "semantic")

    def test_substring_fallback_honours_every_filter(self):
        # no build_fts_index() — _rank_lexically degrades to the full scan
        self.assertFalse(os.path.isfile(okf._fts_db_path(self.tmp)))
        self._silence_semantic_arm()
        self._check_every_dimension(self.LITERAL, "degraded")

    def test_scoped_substring_fallback_reports_the_real_path(self):
        """B04 — with --scope <bundle>/<subdir> the substring arm built its
        path from the BUNDLE name plus a cid relative to the SUBDIR, printing
        `keep/wanted` for a concept living at `keep/inner/wanted`: a path no
        `okf-cli read` can resolve. Unscoped output is unaffected, which is
        what keeps the frozen eval baseline valid."""
        self.assertFalse(os.path.isfile(okf._fts_db_path(self.tmp)))
        self._silence_semantic_arm()
        self.assertEqual(sorted(self._paths(self.LITERAL, scope="keep/inner")),
                         ["keep/inner/tag-bait", "keep/inner/type-bait",
                          "keep/inner/wanted"])


class FindFilterComposition(unittest.TestCase):
    """P8/8a (okf-cli-8uaf, FIL03/FIL04) — find gains --type/--tag/--scope
    so keyword search is composable with exact-match filters. --bundle was
    a duplicate --scope alias, removed D02 (PO-grilling 2026-07-26)."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self._w("correct/one.md", "Runbook", "One", ["alpha"],
                "zqxfil appears here in the body.\n")
        self._w("correct/two.md", "Concept", "Two", ["beta"],
                "zqxfil appears here too, different type.\n")
        self._w("wrong/three.md", "Runbook", "Three", ["alpha"],
                "zqxfil appears in the wrong bundle.\n")

    def _w(self, rel, typ, title, tags, body):
        ap = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(
                "---\ntype: {}\ntitle: {}\ntags: [{}]\ndescription: d\n---\n"
                "# {}\n\n{}".format(typ, title, ", ".join(tags), title, body)
            )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, query="zqxfil", **kw):
        import io, contextlib, types
        args = types.SimpleNamespace(
            query=query, limit=10, type=None, tag=None, scope=None,
            breakdown=False,
        )
        for k, v in kw.items():
            setattr(args, k, v)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            okf.cmd_find(self.tmp, args)
        return buf.getvalue()

    def test_no_filters_behavior_unchanged_all_three_hit(self):
        out = self._run()
        self.assertEqual(out.count("path: "), 3)

    def test_type_filter_excludes_other_types(self):
        out = self._run(type="Runbook")
        self.assertIn("path: correct/one", out)
        self.assertIn("path: wrong/three", out)
        self.assertNotIn("path: correct/two", out)

    def test_tag_filter_excludes_non_matching_tag(self):
        out = self._run(tag="beta")
        self.assertIn("path: correct/two", out)
        self.assertNotIn("path: correct/one", out)
        self.assertNotIn("path: wrong/three", out)

    def test_scope_filter_excludes_other_bundle(self):
        out = self._run(scope="correct")
        self.assertIn("path: correct/one", out)
        self.assertIn("path: correct/two", out)
        self.assertNotIn("path: wrong/three", out)

    def test_composed_filters_type_tag_scope(self):
        out = self._run(type="Runbook", tag="alpha", scope="correct")
        self.assertIn("path: correct/one", out)
        self.assertNotIn("path: correct/two", out)
        self.assertNotIn("path: wrong/three", out)


class FindScoreBreakdown(unittest.TestCase):
    """P8/8b (okf-cli-8uaf, SCO03) — --breakdown lists which field(s)/term(s)
    contributed to each hit's score; without it, output is byte-identical."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        ap = os.path.join(self.tmp, "b", "one.md")
        os.makedirs(os.path.dirname(ap))
        with open(ap, "w", encoding="utf-8") as f:
            f.write(
                "---\ntype: Runbook\ntitle: Zqxbrk One\ntags: [zqxbrk]\n"
                "description: d\n---\n# Untitled Heading\n\nbody prose only.\n"
            )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, breakdown=False):
        import io, contextlib, types
        args = types.SimpleNamespace(
            query="zqxbrk", limit=10, type=None, tag=None, scope=None,
            breakdown=breakdown,
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            okf.cmd_find(self.tmp, args)
        return buf.getvalue()

    def test_breakdown_lists_contributing_fields(self):
        out = self._run(breakdown=True)
        self.assertIn("contrib: ", out)
        self.assertIn("title=[zqxbrk]", out)
        self.assertIn("tags=[zqxbrk]", out)
        self.assertNotIn("body=[zqxbrk]", out)  # term not in body prose

    def test_default_output_unchanged_without_breakdown(self):
        out_flag_false = self._run(breakdown=False)
        self.assertNotIn("contrib:", out_flag_false)
        # F04 (post-review) — SC-002 says "byte-identical to today"; pin the
        # FULL exact output, not just the absence of a "contrib:" substring
        # (a weaker check could miss e.g. a stray blank line or reordering).
        self.assertEqual(
            out_flag_false,
            "------\n"
            "score: 5/6\n"
            "title: Zqxbrk One\n"
            "type: Runbook\n"
            "path: b/one\n"
            "description: d\n"
            "body-snippet: # Untitled Heading body prose only.…\n"
            "------\n",
        )


def _h(path, score, provenance):
    return {"path": path, "score": score, "provenance": provenance,
            "title": path, "type": "", "desc": "", "snip": ""}


class FuseConditional(unittest.TestCase):
    """D12/R43 — decide WHICH arm owns the ranking; never blend two
    incomparable scales. Measured: worst case 0.437 MRR vs 0.201 for RRF and
    0.029 for the pin+blend rule shipped before this plan."""

    def test_confident_lexical_owns_the_ranking(self):
        lex = [_h("a", 100, "lexical"), _h("b", 40, "lexical")]
        sem = [_h("c", 90, "semantic")]
        out, lex_owned = okf.fuse_conditional(lex, sem, 10)
        self.assertTrue(lex_owned)
        self.assertEqual([h["path"] for h in out], ["a", "b", "c"])

    def test_ambiguous_lexical_hands_the_ranking_to_semantic(self):
        lex = [_h("a", 100, "lexical"), _h("b", 95, "lexical")]
        sem = [_h("c", 60, "semantic")]
        out, lex_owned = okf.fuse_conditional(lex, sem, 10)
        self.assertFalse(lex_owned)
        self.assertEqual([h["path"] for h in out], ["c", "a", "b"])

    def test_single_lexical_hit_is_treated_as_confident(self):
        lex = [_h("a", 100, "lexical")]
        sem = [_h("c", 90, "semantic")]
        out, lex_owned = okf.fuse_conditional(lex, sem, 10)
        self.assertTrue(lex_owned)
        self.assertEqual([h["path"] for h in out], ["a", "c"])

    def test_empty_lexical_hands_over(self):
        out, lex_owned = okf.fuse_conditional([], [_h("c", 60, "semantic")], 10)
        self.assertFalse(lex_owned)
        self.assertEqual([h["path"] for h in out], ["c"])

    def test_duplicate_paths_keep_the_owning_arms_entry(self):
        lex = [_h("a", 100, "lexical"), _h("b", 95, "lexical")]
        sem = [_h("b", 70, "semantic"), _h("c", 60, "semantic")]
        out, lex_owned = okf.fuse_conditional(lex, sem, 10)
        self.assertFalse(lex_owned)
        self.assertEqual([h["path"] for h in out], ["b", "c", "a"])
        self.assertEqual(out[0]["provenance"], "semantic")

    def test_limit_is_respected(self):
        lex = [_h("a", 100, "lexical")]
        sem = [_h("c", 90, "semantic"), _h("d", 80, "semantic")]
        out, _lex_owned = okf.fuse_conditional(lex, sem, 2)
        self.assertEqual([h["path"] for h in out], ["a", "c"])

    def test_semantic_never_precedes_a_confident_lexical_top1(self):
        lex = [_h("a", 30, "lexical"), _h("b", 5, "lexical")]
        sem = [_h("c", 99, "semantic")]
        out, lex_owned = okf.fuse_conditional(lex, sem, 10)
        self.assertTrue(lex_owned)
        self.assertEqual(out[0]["path"], "a")

    def test_margin_band_matches_the_measured_rule(self):
        """The measured rule is top1 >= 1.5*top2 (eval/hybrid_eval.py:151).
        The pre-plan arithmetic was top1 >= 2*top2. 100 vs 60 sits inside the
        band where the two disagree: the measured rule says the lexical arm
        is confident, the old one says it is not. Pin the measured one."""
        lex = [_h("a", 100, "lexical"), _h("b", 60, "lexical")]
        sem = [_h("c", 90, "semantic")]
        out, lex_owned = okf.fuse_conditional(lex, sem, 10)
        self.assertTrue(lex_owned)
        self.assertEqual([h["path"] for h in out], ["a", "b", "c"])

    def test_just_below_the_band_hands_over(self):
        lex = [_h("a", 100, "lexical"), _h("b", 68, "lexical")]
        sem = [_h("c", 90, "semantic")]
        _out, lex_owned = okf.fuse_conditional(lex, sem, 10)
        self.assertFalse(lex_owned)


class NoiseRatioIsGone(unittest.TestCase):
    """The absolute noise floor was a crutch for the blend rule; conditional
    handover subsumes it. Leaving it in place would mean two competing gates."""

    def test_constant_removed(self):
        self.assertFalse(hasattr(okf, "SEMANTIC_NOISE_RATIO"))


class SemanticBackstop(unittest.TestCase):
    """P8/8c (okf-cli-8uaf, D04) — find's semantic pass is a best-effort
    backstop: fires only on zero/weak keyword hits, degrades gracefully on
    any failure (cache absent, backend unreachable), and never overrides a
    strong keyword top-hit."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self._w("b/near.md", "Near Concept", [], "alpha beta near-body prose.\n")
        self._w("b/far.md", "Far Concept", [], "alpha beta far-body prose.\n")
        self._w("b/strong.md", "Zqxstrong Sanity", ["zqxstrong"],
                "zqxstrong appears in title tags and body.\n")
        self._orig_embed = okf._embed_query_voyage
        self._orig_cosine = okf._cosine
        okf._QUERY_VEC_CACHE.clear()

    def tearDown(self):
        import shutil
        okf._embed_query_voyage = self._orig_embed
        okf._cosine = self._orig_cosine
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _w(self, rel, title, tags, body):
        ap = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(
                "---\ntype: Concept\ntitle: {}\ntags: [{}]\ndescription: d\n---\n"
                "# Untitled\n\n{}".format(title, ", ".join(tags), body)
            )

    def _make_tagvec(self, rows):
        db = os.path.join(self.tmp, ".tagvec", "tag_vectors.sqlite")
        os.makedirs(os.path.dirname(db), exist_ok=True)
        import sqlite3, struct
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE concept_emb(key TEXT PRIMARY KEY, path TEXT, "
            "model TEXT, dim INT, vec BLOB)"
        )
        for key, path, vec in rows:
            conn.execute(
                "INSERT INTO concept_emb VALUES (?,?,?,?,?)",
                (key, path, "voyage-3-large", len(vec), struct.pack("<{}f".format(len(vec)), *vec)),
            )
        conn.commit()
        conn.close()
        return db

    def _run(self, query, **kw):
        import io, contextlib, types
        args = types.SimpleNamespace(
            query=query, limit=10, type=None, tag=None, scope=None,
            breakdown=False,
        )
        for k, v in kw.items():
            setattr(args, k, v)
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            okf.cmd_find(self.tmp, args)
        return out_buf.getvalue(), err_buf.getvalue()

    def test_no_tagvec_cache_degrades_gracefully(self):
        out, err = self._run("zzz-no-keyword-match-zzz")
        self.assertIn("(no matches", out)
        self.assertIn("semantic arm skipped", err)

    def test_empty_concept_emb_table_degrades_gracefully(self):
        self._make_tagvec([])
        out, err = self._run("zzz-no-keyword-match-zzz")
        self.assertIn("(no matches", out)
        self.assertIn("semantic arm skipped", err)

    def test_embedding_backend_failure_degrades_gracefully(self):
        self._make_tagvec([("k1", "b/near", [1.0, 0.0])])

        def _raise(_text):
            raise OSError("connection refused")
        okf._embed_query_voyage = _raise
        out, err = self._run("zzz-no-keyword-match-zzz")
        self.assertIn("(no matches", out)
        self.assertIn("semantic arm skipped", err)

    def test_zero_keyword_hit_is_rescued_with_provenance(self):
        self._make_tagvec([("k1", "b/near", [1.0, 0.0])])
        okf._embed_query_voyage = lambda text: [1.0, 0.0]
        out, err = self._run("zzz-no-keyword-match-zzz")
        self.assertIn("path: b/near", out)
        self.assertIn("provenance: semantic", out)

    def test_strong_keyword_top_hit_is_never_overridden(self):
        # Backend guarded to raise if ever called — proves the semantic
        # pass does not even fire when the keyword top hit is strong.
        self._make_tagvec([("k1", "b/near", [1.0, 0.0])])

        def _must_not_be_called(_text):
            raise AssertionError("semantic backstop must not fire on a strong hit")
        okf._embed_query_voyage = _must_not_be_called
        out, err = self._run("zqxstrong")
        lines = out.splitlines()
        self.assertEqual(lines[4], "path: b/strong")  # Top-1
        self.assertNotIn("provenance: semantic", out)

    def test_noise_single_hit_still_fires_backstop(self):
        """P12 re-measure finding (8c EARS, S3 rescue): a paraphrase query
        against a real catalogue rarely gets ZERO keyword hits — it gets
        NOISE (a stray body-word match, e.g. 1/24 = 0.042). A single such
        hit must not suppress the backstop: the wanted concept has to
        surface (rank >= 2, noise top-1 stays pinned)."""
        self._w("b/noise.md", "Unrelated Note", [],
                "mentions classification once in passing.\n")
        self._w("b/wanted.md", "Wanted Concept", [],
                "totally different content words only.\n")
        self._make_tagvec([("k1", "b/wanted", [1.0, 0.0])])
        okf._embed_query_voyage = lambda text: [1.0, 0.0]
        out, err = self._run("unmarked item lacking classification")
        self.assertIn("path: b/wanted", out)
        self.assertIn("provenance: semantic", out)
        # pin: the keyword hit (noise or not) keeps rank 1
        first_path = [l for l in out.splitlines()
                      if l.startswith("path: ")][0]
        self.assertEqual(first_path, "path: b/noise")

    def test_noise_top1_with_clear_margin_still_fires_backstop(self):
        """Same finding, margin variant (real S3-paraphrase shape: top-1
        3/24 vs runner-up 1/24 — margin 0.667 looks 'confident' but both
        are noise). An absolute noise floor must fire the backstop even
        when the margin gate would not."""
        self._w("b/noise3.md", "Unrelated Prose Note", [],
                "item classification unmarked in passing prose.\n")
        self._w("b/noise1.md", "Other Note", [],
                "classification mentioned once.\n")
        self._w("b/wanted.md", "Wanted Concept", [],
                "totally different content words only.\n")
        self._make_tagvec([("k1", "b/wanted", [1.0, 0.0])])
        okf._embed_query_voyage = lambda text: [1.0, 0.0]
        out, err = self._run("unmarked item lacking classification")
        self.assertIn("path: b/wanted", out)
        self.assertIn("provenance: semantic", out)

    def test_scope_confines_the_semantic_arm(self):
        """B01 — --scope is a filter on the ANSWER, not on one arm. The
        lexical arm confines itself (SQL path predicate / resolve_scopes),
        so a scoped query used to return out-of-scope concepts only when
        the semantic arm owned the ranking: the user asked for
        home-lab-wiki/services and got agent-memory and qm-wiki hits."""
        self._w("other/leak.md", "Leaked Concept", [],
                "totally different content words only.\n")
        self._make_tagvec([("k1", "other/leak", [1.0, 0.0])])
        okf._embed_query_voyage = lambda text: [1.0, 0.0]
        out, err = self._run("zzz-no-keyword-match-zzz", scope="b")
        self.assertNotIn("path: other/leak", out)

    def test_type_filter_confines_the_semantic_arm(self):
        """B02 — same defect class as B01: --type is applied to the lexical
        arm's SQL only, so a semantic-owned ranking returns the wrong type."""
        self._w("b/other-type.md", "Wrong Type", [],
                "totally different content words only.\n")
        ap = os.path.join(self.tmp, "b/other-type.md")
        with open(ap, encoding="utf-8") as f:
            txt = f.read()
        with open(ap, "w", encoding="utf-8") as f:
            f.write(txt.replace("type: Concept", "type: Pattern"))
        self._make_tagvec([("k1", "b/other-type", [1.0, 0.0])])
        okf._embed_query_voyage = lambda text: [1.0, 0.0]
        out, err = self._run("zzz-no-keyword-match-zzz", type="Concept")
        self.assertNotIn("path: b/other-type", out)

    def test_tag_filter_confines_the_semantic_arm(self):
        """B03 — same defect class as B01 for --tag."""
        self._w("b/untagged.md", "Untagged Concept", [],
                "totally different content words only.\n")
        self._make_tagvec([("k1", "b/untagged", [1.0, 0.0])])
        okf._embed_query_voyage = lambda text: [1.0, 0.0]
        out, err = self._run("zzz-no-keyword-match-zzz", tag="zqxstrong")
        self.assertNotIn("path: b/untagged", out)

    def test_confident_literal_top1_survives_unrelated_semantic_scale(self):
        """T08/D12 update of the former F01 regression (pre-plan absolute
        pin, removed by this task). fuse_conditional decides ownership from
        the intra-lexical top1/top2 margin ONLY — it never compares a
        lexical raw score against a semantic-converted one (bean PRELUDE,
        reviewer-confirmed property). This still has to hold even when an
        UNRELATED semantic candidate's cosine (~0.7, ordinary model
        background noise) converts to a raw score HIGHER than the lexical
        top-1's own score: top1=5 (title 3 + tags 2), runner-up=3
        (title-only match, no shared body term) -> 5 >= 1.5*3 (4.5), so the
        lexical arm IS confident under the measured rule and owns the
        ranking; its own order [top1, rival] must come first regardless of
        the semantic arm's inflated raw number (70/100 from cosine 0.7)."""
        self._w("b/top1.md", "Zqxmargin One", ["zqxmargin"],
                "no second query term appears here.\n")
        # top1: "zqxmargin" hits title(3)+tags(2)=5; "raretermxyz" hits
        # nothing -> score 5/12.
        self._w("b/rival.md", "Rival Zqxmargin Concept", [],
                "a competing concept with no shared body terms.\n")
        # rival: "zqxmargin" hits title(3) only -> score 3/12. Margin
        # 5 >= 1.5*3 -> CONFIDENT (unlike the pre-T08 fixture, which used a
        # body-matching rival at 4/12 to land in the ambiguous band on
        # purpose; that scenario now hands over by design and is covered by
        # FuseConditional's own band tests, not here).
        self._w("b/unrelated.md", "Totally Unrelated Concept", [],
                "nothing to do with the query at all.\n")
        self._make_tagvec([("k1", "b/unrelated", [0.0, 1.0])])
        okf._embed_query_voyage = lambda text: [1.0, 0.0]
        okf._cosine = lambda a, b: 0.7  # reviewer's exact repro value
        out, _err = self._run("zqxmargin raretermxyz")
        lines = out.splitlines()
        self.assertEqual(lines[4], "path: b/top1")  # confident lexical top-1
        self.assertIn("path: b/unrelated", out)  # still surfaced, appended
        self.assertNotEqual(lines[4], "path: b/unrelated")

    def test_ambiguous_lexical_hands_over_but_keeps_its_hits_appended_behind(self):
        """I01 (review round 1) / SUPERVISOR RULING item 2 — the hard case at
        cmd_find level: the lexical arm has REAL, NONZERO, AMBIGUOUS hits
        (ratio inside the 1.0x-1.5x band, not zero hits like the other
        SemanticBackstop rescue tests) AND semantic candidates are present.
        Required: the semantic arm owns the ranking (D12), AND the lexical
        top-1 (and runner-up) are still PRESENT in the result, appended
        behind, in their own order. That second property is what makes
        handover tolerable in production — an ambiguous-but-real lexical
        hit must not vanish, only yield first place. Reviewer's exact repro
        shape: lexical pair scores in a 1.0x-1.5x ratio (ambiguous under
        BOTH the pre-plan 2x rule and the measured 1.5x rule) plus one
        semantic-only candidate. Builds a real FTS index
        (okf.build_fts_index) so the lexical arm is NOT ALSO degraded,
        matching the reviewer's live-probe setup exactly: one stderr note
        (handover), not two (handover + degradation)."""
        self._w("b/amba.md", "Zqxambig A", ["zqxambig"],
                "no second query term appears here.\n")
        self._w("b/ambb.md", "Zqxambig B", [],
                "zqxambig body only, a close competing score.\n")
        self._w("b/ambc.md", "Semantic Only Concept", [],
                "nothing lexically related here.\n")
        okf.build_fts_index(self.tmp)
        self._make_tagvec([("k1", "b/ambc", [1.0, 0.0])])
        okf._embed_query_voyage = lambda text: [1.0, 0.0]
        out, err = self._run("zqxambig")
        lines = out.splitlines()
        lex_top1, lex_top2 = None, None
        for i, l in enumerate(lines):
            if l == "path: b/amba":
                lex_top1 = int(lines[i - 3].split("score: ")[1].split("/")[0])
            if l == "path: b/ambb":
                lex_top2 = int(lines[i - 3].split("score: ")[1].split("/")[0])
        self.assertIsNotNone(lex_top1)
        self.assertIsNotNone(lex_top2)
        self.assertTrue(
            1.0 <= lex_top1 / lex_top2 < 1.5,
            "fixture must land the lexical pair inside the ambiguous band, "
            "got {}/{}".format(lex_top1, lex_top2),
        )
        paths = [l[len("path: "):] for l in lines if l.startswith("path: ")]
        self.assertEqual(paths, ["b/ambc", "b/amba", "b/ambb"])
        notes = [l for l in err.splitlines() if l]
        self.assertEqual(len(notes), 1)
        self.assertIn("semantic arm owns this ranking", notes[0])

    def test_semantic_rescue_ranks_nearer_concept_first(self):
        self._make_tagvec([
            ("k1", "b/near", [1.0, 0.0]),
            ("k2", "b/far", [0.1, 0.99]),
        ])
        okf._embed_query_voyage = lambda text: [1.0, 0.0]
        out, _err = self._run("zzz-no-keyword-match-zzz")
        paths = [line[len("path: "):] for line in out.splitlines()
                 if line.startswith("path: ")]
        self.assertEqual(paths, ["b/near", "b/far"])

    def test_strong_semantic_hit_is_not_crowded_out_by_weak_keyword_noise(self):
        """Real-catalogue smoke finding (P8/8c): many weak keyword
        noise-hits must not push a strong semantic candidate past --limit.
        Fusion must be a score-interleave, not a keyword-hits-first append."""
        for i in range(8):
            self._w("b/noise{}.md".format(i), "Noise {}".format(i), [],
                    "zzz-no-keyword-match-zzz appears once, weakly.\n")
        self._make_tagvec([("k1", "b/near", [1.0, 0.0])])
        okf._embed_query_voyage = lambda text: [1.0, 0.0]
        out, _err = self._run("zzz-no-keyword-match-zzz", limit=3)
        paths = [line[len("path: "):] for line in out.splitlines()
                 if line.startswith("path: ")]
        self.assertIn("b/near", paths)

    def test_mutation_self_test_inverted_cosine_breaks_ranking(self):
        """LL-01 forward-guard: prove the ranking assertion actually
        detects a broken fusion — invert cosine, watch the order assertion
        fail, then revert."""
        self._make_tagvec([
            ("k1", "b/near", [1.0, 0.0]),
            ("k2", "b/far", [0.1, 0.99]),
        ])
        okf._embed_query_voyage = lambda text: [1.0, 0.0]
        orig_cosine = okf._cosine
        okf._cosine = lambda a, b: -orig_cosine(a, b)
        try:
            out, _err = self._run("zzz-no-keyword-match-zzz")
            paths = [line[len("path: "):] for line in out.splitlines()
                     if line.startswith("path: ")]
            with self.assertRaises(AssertionError):
                self.assertEqual(paths, ["b/near", "b/far"])
        finally:
            okf._cosine = orig_cosine

    # test_shim_backfills_when_excluded_paths_rank_inside_the_window removed
    # (T08/SC-SHIM): it pinned the T07 cmd_find shim's over-fetch-by-
    # len(exclude) backfill behaviour, which existed only to protect a
    # post-hoc exclude filter. fuse_conditional does not pre-filter or
    # over-fetch — dedup happens after both arms return, per D12 — so the
    # scenario's premise (a starved semantic window) no longer applies, and
    # its score pair (5 vs 3, margin 0.4) is additionally CONFIDENT under
    # the measured 1.5x rule (this task), unlike under the pre-plan 2x rule
    # the fixture was tuned against. No replacement test: the shim's
    # invariant is gone by design, not narrowed.


class VoyageQueryEmbedding(unittest.TestCase):
    """D13/D16 — the query path speaks voyage-3-large with input_type=query
    (the asymmetric form the measurement used, eval/hybrid_eval.py:73-80),
    and it degrades to lexical-only on any failure. Network is faked."""

    def setUp(self):
        self.orig_env = os.environ.get("VOYAGE_API_KEY")
        os.environ["VOYAGE_API_KEY"] = "test-key"

    def tearDown(self):
        if self.orig_env is None:
            os.environ.pop("VOYAGE_API_KEY", None)
        else:
            os.environ["VOYAGE_API_KEY"] = self.orig_env

    def test_request_uses_query_input_type_and_bearer_auth(self):
        seen = {}

        class _Resp:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

            def read(self_inner):
                return json.dumps(
                    {"data": [{"embedding": [0.5, 0.5]}]}).encode("utf-8")

        def _fake_urlopen(req, timeout=None):
            seen["payload"] = json.loads(req.data.decode("utf-8"))
            seen["auth"] = req.get_header("Authorization")
            return _Resp()

        orig = okf.urllib.request.urlopen
        okf.urllib.request.urlopen = _fake_urlopen
        try:
            vec = okf._embed_query_voyage("mockup tailscale")
        finally:
            okf.urllib.request.urlopen = orig

        self.assertEqual(vec, [0.5, 0.5])
        self.assertEqual(seen["payload"]["model"], "voyage-3-large")
        self.assertEqual(seen["payload"]["input_type"], "query")
        self.assertEqual(seen["payload"]["input"], ["mockup tailscale"])
        self.assertEqual(seen["auth"], "Bearer test-key")

    def test_missing_api_key_raises_so_the_caller_can_degrade(self):
        os.environ.pop("VOYAGE_API_KEY", None)
        with self.assertRaises(RuntimeError):
            okf._embed_query_voyage("x")


class SemanticRankingDegradation(unittest.TestCase):
    """R05/D16 — every failure mode returns [] plus one stderr note, and none
    of them raises."""

    def test_absent_cache_returns_empty(self):
        root = tempfile.mkdtemp()
        try:
            self.assertEqual(okf.semantic_ranking(root, "x", 10, okf.FindFilters()), [])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_unreachable_backend_returns_empty(self):
        root = tempfile.mkdtemp()
        try:
            db = okf._tagvec_db_path(root)
            os.makedirs(os.path.dirname(db))
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE concept_emb(key TEXT, path TEXT, "
                         "model TEXT, dim INT, vec BLOB)")
            conn.execute("INSERT INTO concept_emb VALUES(?,?,?,?,?)",
                         ("k", "b/one", "voyage-3-large", 2,
                          struct.pack("<2f", 1.0, 0.0)))
            conn.commit()
            conn.close()

            def _raise(_text):
                raise RuntimeError("no network")

            orig = okf._embed_query_voyage
            okf._embed_query_voyage = _raise
            try:
                self.assertEqual(okf.semantic_ranking(root, "x", 10, okf.FindFilters()), [])
            finally:
                okf._embed_query_voyage = orig
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TokenizeUnicode(unittest.TestCase):
    """B01 — the catalogue is German. Splitting on [^a-z0-9]+ tore every
    umlaut word in two ('qualitätsmanagement' -> 'qualit', 'tsmanagement'),
    which silently changed what the lexical arm searches for. The measured
    FTS arm tokenized on word characters (eval/fts_arm.py:56); the shipped
    one must match it or it is not the arm that was measured."""

    def test_umlaut_word_stays_one_token(self):
        self.assertEqual(okf.tokenize("Qualitätsmanagement"),
                         ["qualitätsmanagement"])

    def test_sharp_s_stays_one_token(self):
        self.assertEqual(okf.tokenize("Straßenbahn"), ["straßenbahn"])

    def test_punctuation_still_separates(self):
        self.assertEqual(okf.tokenize("mockup, tailscale!"),
                         ["mockup", "tailscale"])

    def test_underscore_still_separates(self):
        self.assertEqual(okf.tokenize("build_tagvec"), ["build", "tagvec"])

    def test_digits_survive(self):
        self.assertEqual(okf.tokenize("bge-m3 2437"), ["bge", "m3", "2437"])

    def test_mixed_case_lowercased(self):
        self.assertEqual(okf.tokenize("MixedCASE Wort"),
                         ["mixedcase", "wort"])

    def test_non_latin_script_stays_whole(self):
        """\\w is Unicode-aware, not just Latin-with-umlauts — a CJK term
        must survive as one token too, same as an umlaut word does."""
        self.assertEqual(okf.tokenize("知識管理 system"),
                         ["知識管理", "system"])


class FtsIndexBuild(unittest.TestCase):
    """D15 — the lexical index is a persistent artefact under <root>/.fts/."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "b"))
        with open(os.path.join(self.root, "b", "one.md"), "w",
                  encoding="utf-8") as f:
            f.write("---\ntype: Runbook\ntitle: Serve Excalidraw drafts\n"
                    "description: d\ntags: [excalidraw, tailscale]\n---\n"
                    "Render the drawing to PNG and expose it over the tunnel.\n")
        with open(os.path.join(self.root, "b", "two.md"), "w",
                  encoding="utf-8") as f:
            f.write("---\ntype: Konzept\ntitle: Qualitätsmanagement\n"
                    "description: d\ntags: [qm]\n---\nProzesse und Audits.\n")
        with open(os.path.join(self.root, "b", "index.md"), "w",
                  encoding="utf-8") as f:
            f.write("# B\n")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_build_creates_the_artefact_and_counts_concepts(self):
        n, db = okf.build_fts_index(self.root)
        self.assertEqual(n, 2)
        self.assertTrue(os.path.isfile(db))
        self.assertEqual(db, os.path.join(self.root, ".fts", "fts.sqlite"))

    def test_index_holds_path_type_and_tags(self):
        okf.build_fts_index(self.root)
        conn = sqlite3.connect(okf._fts_db_path(self.root))
        rows = dict(conn.execute("SELECT path, ctype FROM docs").fetchall())
        conn.close()
        self.assertEqual(rows, {"b/one": "Runbook", "b/two": "Konzept"})

    def test_rebuild_is_idempotent(self):
        okf.build_fts_index(self.root)
        n, _db = okf.build_fts_index(self.root)
        self.assertEqual(n, 2)
        conn = sqlite3.connect(okf._fts_db_path(self.root))
        total = conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
        conn.close()
        self.assertEqual(total, 2)

    def test_fresh_index_is_not_stale(self):
        okf.build_fts_index(self.root)
        conn = sqlite3.connect(okf._fts_db_path(self.root))
        try:
            self.assertFalse(okf._fts_index_stale(self.root, conn))
        finally:
            conn.close()

    def test_new_concept_makes_the_index_stale(self):
        okf.build_fts_index(self.root)
        with open(os.path.join(self.root, "b", "three.md"), "w",
                  encoding="utf-8") as f:
            f.write("---\ntype: Konzept\ntitle: Three\ndescription: d\n"
                    "tags: []\n---\nbody\n")
        conn = sqlite3.connect(okf._fts_db_path(self.root))
        try:
            self.assertTrue(okf._fts_index_stale(self.root, conn))
        finally:
            conn.close()


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
            okf.cmd_build_index(self.root, args)
        return buf.getvalue()

    def test_without_flag_always_rebuilds_even_when_current(self):
        """Regression guard for the D02 promise: omitting --if-stale must
        stay byte-identical to today — an unconditional full rebuild, never
        a skip, no matter how fresh the index already is."""
        okf.build_fts_index(self.root)
        db_path = okf._fts_db_path(self.root)
        before = os.path.getmtime(db_path)
        out = self._run(if_stale=False)
        after = os.path.getmtime(db_path)
        self.assertIn("indexed 1 concept(s)", out)
        self.assertGreaterEqual(after, before)

    def test_if_stale_skips_rebuild_when_index_is_current(self):
        okf.build_fts_index(self.root)
        db_path = okf._fts_db_path(self.root)
        # os.replace() on rebuild always produces a fresh inode/mtime, so an
        # unchanged mtime is proof the rebuild branch never ran.
        before = os.path.getmtime(db_path)
        out = self._run(if_stale=True)
        after = os.path.getmtime(db_path)
        self.assertEqual(before, after)
        self.assertIn("index is current", out)
        self.assertIn(db_path, out)

    def test_if_stale_rebuilds_when_a_concept_changed(self):
        okf.build_fts_index(self.root)
        with open(os.path.join(self.root, "b", "two.md"), "w",
                  encoding="utf-8") as f:
            f.write("---\ntype: Konzept\ntitle: Two\ndescription: d\n"
                    "tags: []\n---\nbody two.\n")
        out = self._run(if_stale=True)
        self.assertIn("indexed 2 concept(s)", out)
        conn = sqlite3.connect(okf._fts_db_path(self.root))
        try:
            total = conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(total, 2)

    def test_if_stale_rebuilds_when_index_is_absent(self):
        # No build_fts_index() call at all — the .fts dir does not exist yet.
        out = self._run(if_stale=True)
        self.assertIn("indexed 1 concept(s)", out)
        self.assertTrue(os.path.isfile(okf._fts_db_path(self.root)))

    def test_help_documents_the_flag(self):
        ap = okf.build_parser()
        parsers = okf.subcommand_parsers(ap)
        actions = okf.parser_actions(parsers["build-index"])
        flag = next((a for a in actions if a.dest == "if_stale"), None)
        self.assertIsNotNone(flag, "build-index has no --if-stale option")
        self.assertTrue((flag.help or "").strip())


def _run_find(root, query, **kw):
    """Module-level twin of the per-class _run() helper at
    cli/test_okf_cli.py:1381 — same in-process convention (SimpleNamespace
    args, cmd_find, redirected streams), but parameterised by root so the new
    suites can each use their own temp catalogue. Returns stdout."""
    import io
    import contextlib
    import types
    args = types.SimpleNamespace(
        query=query, limit=10, type=None, tag=None, scope=None,
        breakdown=False,
    )
    for k, v in kw.items():
        setattr(args, k, v)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        okf.cmd_find(root, args)
    return buf.getvalue()


class FtsRanking(unittest.TestCase):
    """T13 — the lexical arm is BM25 over the index, and it degrades to the
    substring scan rather than failing when the artefact is missing (D15)."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "b"))
        with open(os.path.join(self.root, "b", "one.md"), "w",
                  encoding="utf-8") as f:
            f.write("---\ntype: Runbook\ntitle: Serve Excalidraw drafts\n"
                    "description: d\ntags: [excalidraw, tailscale]\n---\n"
                    "Render the drawing to PNG and expose it over the tunnel.\n")
        with open(os.path.join(self.root, "b", "two.md"), "w",
                  encoding="utf-8") as f:
            f.write("---\ntype: Konzept\ntitle: Tunnel basics\n"
                    "description: d\ntags: [tailscale]\n---\nA tunnel primer.\n")
        with open(os.path.join(self.root, "b", "index.md"), "w",
                  encoding="utf-8") as f:
            f.write("# B\n")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_returns_none_without_an_index(self):
        self.assertIsNone(okf._fts_ranking(self.root, "tunnel", 10, okf.FindFilters()))

    def test_absent_index_prints_exactly_one_stderr_note(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            result = okf._fts_ranking(self.root, "tunnel", 10, okf.FindFilters())
        self.assertIsNone(result)
        lines = [l for l in buf.getvalue().splitlines() if l]
        self.assertEqual(len(lines), 1)
        self.assertIn("note:", lines[0])

    def test_ranks_title_match_above_body_match(self):
        okf.build_fts_index(self.root)
        ranked = okf._fts_ranking(self.root, "tunnel", 10, okf.FindFilters())
        self.assertEqual(ranked[0][0], "b/two")

    def test_type_filter_narrows(self):
        okf.build_fts_index(self.root)
        ranked = okf._fts_ranking(self.root, "tunnel", 10,
                                  okf.FindFilters(type="Runbook"))
        self.assertEqual([p for p, _s in ranked], ["b/one"])

    def test_tag_filter_matches_whole_tags_only(self):
        okf.build_fts_index(self.root)
        ranked = okf._fts_ranking(self.root, "tunnel", 10,
                                  okf.FindFilters(tag="tail"))
        self.assertEqual(ranked, [])

    def test_scope_filter_narrows_to_a_bundle(self):
        okf.build_fts_index(self.root)
        self.assertNotEqual(okf._fts_ranking(self.root, "tunnel", 10, okf.FindFilters(scope="b")), [])
        self.assertEqual(okf._fts_ranking(self.root, "tunnel", 10, okf.FindFilters(scope="zz")), [])

    def test_corrupt_index_degrades_to_none(self):
        okf.build_fts_index(self.root)
        with open(okf._fts_db_path(self.root), "wb") as f:
            f.write(b"not a database")
        self.assertIsNone(okf._fts_ranking(self.root, "tunnel", 10, okf.FindFilters()))

    def test_corrupt_index_prints_exactly_one_stderr_note(self):
        import io
        import contextlib
        okf.build_fts_index(self.root)
        with open(okf._fts_db_path(self.root), "wb") as f:
            f.write(b"not a database")
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            result = okf._fts_ranking(self.root, "tunnel", 10, okf.FindFilters())
        self.assertIsNone(result)
        lines = [l for l in buf.getvalue().splitlines() if l]
        self.assertEqual(len(lines), 1)
        self.assertIn("note:", lines[0])

    def test_unreadable_index_degrades_to_none_with_one_note(self):
        """D15's third case (permission-denied): sqlite3.OperationalError is
        a subclass of DatabaseError (verified via __mro__), so the same
        except clause that catches corruption also catches this. Proven
        here, not assumed."""
        import io
        import contextlib
        okf.build_fts_index(self.root)
        db_path = okf._fts_db_path(self.root)
        os.chmod(db_path, 0o000)
        try:
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                result = okf._fts_ranking(self.root, "tunnel", 10, okf.FindFilters())
        finally:
            os.chmod(db_path, 0o644)
        self.assertIsNone(result)
        lines = [l for l in buf.getvalue().splitlines() if l]
        self.assertEqual(len(lines), 1)
        self.assertIn("note:", lines[0])


class FindDegradesWithoutIndex(unittest.TestCase):
    """D15 — no artefact, no crash: the substring path still answers, and
    its output shape is unchanged from before this plan."""

    def test_find_without_index_still_prints_a_hit(self):
        root = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(root, "b"))
            with open(os.path.join(root, "b", "one.md"), "w",
                      encoding="utf-8") as f:
                f.write("---\ntype: Runbook\ntitle: Tunnel\ndescription: d\n"
                        "tags: [net]\n---\nbody\n")
            with open(os.path.join(root, "b", "index.md"), "w",
                      encoding="utf-8") as f:
                f.write("# B\n")
            out = _run_find(root, "tunnel")
            self.assertIn("path: b/one", out)
            self.assertIn("score: 3/6", out)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_find_without_index_prints_exactly_one_note_per_degraded_arm(self):
        """T08/D12 update: under conditional handover the semantic arm now
        also fires whenever the lexical list is too short to fill --limit
        (SC-05), independent of confidence — here a single lexical hit
        against limit=10. Both arms are degraded in this fixture (no .fts,
        no .tagvec), so PF-4 ("every degradation branch emits exactly one
        stderr note") now yields TWO notes, one per arm, not one for the
        whole command. Was: asserted a single total note, which relied on
        the pre-T08 gate never invoking the semantic arm for a lone
        confident hit at all."""
        import io
        import contextlib
        root = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(root, "b"))
            with open(os.path.join(root, "b", "one.md"), "w",
                      encoding="utf-8") as f:
                f.write("---\ntype: Runbook\ntitle: Tunnel\ndescription: d\n"
                        "tags: [net]\n---\nbody\n")
            with open(os.path.join(root, "b", "index.md"), "w",
                      encoding="utf-8") as f:
                f.write("# B\n")
            import types
            args = types.SimpleNamespace(
                query="tunnel", limit=10, type=None, tag=None, scope=None,
                breakdown=False,
            )
            out_buf, err_buf = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
                okf.cmd_find(root, args)
            lines = [l for l in err_buf.getvalue().splitlines() if l]
            self.assertEqual(len(lines), 2)
            self.assertIn("note:", lines[0])
            self.assertIn("lexical index absent", lines[0])
            self.assertIn("note:", lines[1])
            self.assertIn("semantic arm skipped", lines[1])
        finally:
            shutil.rmtree(root, ignore_errors=True)


class FtsBm25WeightsApplied(unittest.TestCase):
    """FTS_BM25_WEIGHTS is DEFINED (title 3 / tags 2 / body 1) but was
    consumed nowhere before this task — applying it in the ranking call is
    the point, not a side-effect. Chosen fixture (3 body occurrences) is a
    measured crossover point, not a guess: with unweighted bm25() bodyhit
    ranks first (denser text wins on raw term frequency); only when the
    title=3/body=1 weights are actually passed into bm25() does the single
    title occurrence outrank it. Verified empirically before committing —
    at 1-3 body reps weighted favours the title, unweighted always favours
    the body; the crossover for weighted flips only above ~4 reps."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "b"))
        with open(os.path.join(self.root, "b", "titlehit.md"), "w",
                  encoding="utf-8") as f:
            f.write("---\ntype: Konzept\ntitle: zqxwgt marker\n"
                    "description: d\ntags: []\n---\n"
                    "unrelated body text filler words here.\n")
        with open(os.path.join(self.root, "b", "bodyhit.md"), "w",
                  encoding="utf-8") as f:
            f.write(
                "---\ntype: Konzept\ntitle: other concept\ndescription: d\n"
                "tags: []\n---\n" + ("zqxwgt " * 3)
                + "filler body text more words.\n"
            )
        with open(os.path.join(self.root, "b", "index.md"), "w",
                  encoding="utf-8") as f:
            f.write("# B\n")
        okf.build_fts_index(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_title_weight_outranks_denser_body_match(self):
        ranked = okf._fts_ranking(self.root, "zqxwgt", 10, okf.FindFilters())
        self.assertEqual(ranked[0][0], "b/titlehit")

    def test_unweighted_bm25_would_rank_body_first(self):
        """Control probe (not exercising production code): confirms the
        fixture's crossover claim so the test above cannot be a fluke of
        this specific corpus."""
        conn = sqlite3.connect(okf._fts_db_path(self.root))
        try:
            rows = conn.execute(
                "SELECT path FROM docs WHERE docs MATCH ? "
                "ORDER BY bm25(docs)", ('"zqxwgt"*',)
            ).fetchall()
        finally:
            conn.close()
        self.assertEqual(rows[0][0], "b/bodyhit")


class FtsTokenizerRegression(unittest.TestCase):
    """I01 (T05 review 2026-07-26, ce-specs-reviewer on okf-cli-ntc8) — the
    FTS_TOKENIZER config (porter unicode61 remove_diacritics 2) was
    unprotected: the reviewer reduced it to bare "unicode61" and every
    FtsIndexBuild test stayed green. This test queries the REAL
    build_fts_index() output and only passes when porter stemming is active
    — "study"* (query stem "studi") bridges to an indexed "studies" (also
    stems to "studi"); a plain prefix match would not, because "study" is
    not a literal prefix of "studies" (stud-Y vs stud-IES diverge)."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "b"))
        with open(os.path.join(self.root, "b", "one.md"), "w",
                  encoding="utf-8") as f:
            f.write("---\ntype: Konzept\ntitle: Process notes\n"
                    "description: d\ntags: []\n---\n"
                    "Ongoing studies of the process.\n")
        with open(os.path.join(self.root, "b", "index.md"), "w",
                  encoding="utf-8") as f:
            f.write("# B\n")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_porter_stem_bridges_study_query_to_studies_token(self):
        okf.build_fts_index(self.root)
        conn = sqlite3.connect(okf._fts_db_path(self.root))
        try:
            rows = conn.execute(
                'SELECT path FROM docs WHERE docs MATCH \'"study"*\''
            ).fetchall()
        finally:
            conn.close()
        self.assertEqual([r[0] for r in rows], ["b/one"])


class FtsIndexStaleDegrades(unittest.TestCase):
    """I02 (T05 review 2026-07-26) — bean AC7 of T05 ("IF index metadata is
    missing or unreadable THEN the staleness check SHALL report stale") had
    no committed test; only a live reviewer probe verified it. This locks it
    in: a garbage-byte file and a schema-less-but-openable sqlite file must
    both make _fts_index_stale report True without raising."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_garbage_byte_file_reports_stale_without_raising(self):
        db_path = os.path.join(self.root, "garbage.sqlite")
        with open(db_path, "wb") as f:
            f.write(b"not a database")
        conn = sqlite3.connect(db_path)
        try:
            self.assertTrue(okf._fts_index_stale(self.root, conn))
        finally:
            conn.close()

    def test_schemaless_db_reports_stale_without_raising(self):
        db_path = os.path.join(self.root, "empty.sqlite")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE unrelated(x)")
        conn.commit()
        try:
            self.assertTrue(okf._fts_index_stale(self.root, conn))
        finally:
            conn.close()


class ZeroHitSuggestions(unittest.TestCase):
    """T07/Q13 — a zero hit should hand the caller something to reformulate
    with, not just '(no matches)'."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "b"))
        with open(os.path.join(self.root, "b", "one.md"), "w",
                  encoding="utf-8") as f:
            f.write("---\ntype: Runbook\ntitle: One\ndescription: d\n"
                    "tags: [excalidraw, tailscale]\n---\nbody\n")
        with open(os.path.join(self.root, "b", "index.md"), "w",
                  encoding="utf-8") as f:
            f.write("# B\n")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_near_miss_term_suggests_the_registered_tag(self):
        # A TYPO, not a truncation. "tailscal" is a substring of the tag
        # "tailscale", and the substring scan matches against the raw
        # frontmatter tag string — so it scores a real hit and the zero-hit
        # branch never runs. Truncations can never reach this feature at
        # all: substring match and FTS prefix match both catch them by
        # construction. Only typos and synonyms get here.
        got = okf._zero_hit_suggestions(self.root, "tailscael")
        self.assertIn("tailscale", got)

    def test_unrelated_query_may_return_nothing(self):
        got = okf._zero_hit_suggestions(self.root, "zzzzqqqq")
        self.assertEqual(got, [])

    def test_output_names_the_suggestions(self):
        out = _run_find(self.root, "tailscael")
        self.assertIn("(no matches for: tailscael)", out)
        self.assertIn("tailscale", out)

    def test_output_has_no_suggestion_line_when_no_tag_is_close(self):
        """AC-2 — IF no tag is close enough THEN plain no-match line, no
        suggestions. Integration-level counterpart to
        test_unrelated_query_may_return_nothing (which only proves the
        helper returns []); this proves cmd_find's zero-hit branch actually
        stays silent end-to-end and does not regress into always printing a
        (possibly empty) suggestion line."""
        out = _run_find(self.root, "zzzzqqqq")
        self.assertEqual(out, "(no matches for: zzzzqqqq)\n")
        self.assertNotIn("nearest registered tags", out)
        self.assertNotIn("try: okf-cli find", out)


class ZeroHitSuggestionsPF4(unittest.TestCase):
    """PF-4 — a degradation path and a zero-hit can coincide (no .fts index,
    no .tagvec cache, and a query with no lexical or semantic hits). The
    zero-hit branch must not add a stderr note of its own: exactly one note
    per degraded arm, never a third for the zero-hit message itself."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "b"))
        with open(os.path.join(self.root, "b", "one.md"), "w",
                  encoding="utf-8") as f:
            f.write("---\ntype: Runbook\ntitle: One\ndescription: d\n"
                    "tags: [excalidraw, tailscale]\n---\nbody\n")
        with open(os.path.join(self.root, "b", "index.md"), "w",
                  encoding="utf-8") as f:
            f.write("# B\n")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_exactly_one_note_per_degraded_arm_no_third_for_zero_hit(self):
        import io
        import contextlib
        import types
        args = types.SimpleNamespace(
            query="tailscael", limit=10, type=None, tag=None, scope=None,
            breakdown=False,
        )
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            okf.cmd_find(self.root, args)
        err_lines = [l for l in err_buf.getvalue().splitlines() if l]
        self.assertEqual(len(err_lines), 2, err_lines)
        self.assertIn("lexical index absent", err_lines[0])
        self.assertIn("semantic arm skipped", err_lines[1])
        stdout = out_buf.getvalue()
        self.assertIn("(no matches for: tailscael)", stdout)
        self.assertIn("nearest registered tags: tailscale", stdout)
        self.assertIn("try: okf-cli find \"tailscale\"", stdout)


class ExpandQueryTags(unittest.TestCase):
    """T05/Q05 — the tag vectors are already populated and clean (R09); this
    asks whether they can pull a synonym into the lexical query."""

    def setUp(self):
        okf._QUERY_VEC_CACHE.clear()

    def _seed(self, root, rows):
        db = okf._tagvec_db_path(root)
        os.makedirs(os.path.dirname(db), exist_ok=True)
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE IF NOT EXISTS emb(key TEXT PRIMARY KEY, "
                     "tag TEXT, model TEXT, dim INT, vec BLOB)")
        conn.executemany("INSERT OR REPLACE INTO emb VALUES(?,?,?,?,?)", rows)
        conn.commit()
        conn.close()

    def test_returns_nearest_tag_above_the_floor(self):
        root = tempfile.mkdtemp()
        try:
            self._seed(root, [
                ("k1", "excalidraw", "voyage-3-large", 2,
                 struct.pack("<2f", 1.0, 0.0)),
                ("k2", "invoicing", "voyage-3-large", 2,
                 struct.pack("<2f", 0.0, 1.0)),
            ])
            orig = okf._embed_query_voyage
            okf._embed_query_voyage = lambda _t: [1.0, 0.0]
            try:
                got = okf._expand_query_tags(root, "mockup")
            finally:
                okf._embed_query_voyage = orig
            self.assertEqual(got, ["excalidraw"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_returns_empty_without_a_cache(self):
        root = tempfile.mkdtemp()
        try:
            self.assertEqual(okf._expand_query_tags(root, "mockup"), [])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_returns_empty_when_nothing_clears_the_floor(self):
        root = tempfile.mkdtemp()
        try:
            self._seed(root, [("k1", "invoicing", "voyage-3-large", 2,
                               struct.pack("<2f", 0.0, 1.0))])
            orig = okf._embed_query_voyage
            okf._embed_query_voyage = lambda _t: [1.0, 0.0]
            try:
                self.assertEqual(okf._expand_query_tags(root, "mockup"), [])
            finally:
                okf._embed_query_voyage = orig
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_find_without_the_flag_does_not_expand(self):
        root = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(root, "b"))
            with open(os.path.join(root, "b", "one.md"), "w",
                      encoding="utf-8") as f:
                f.write("---\ntype: Runbook\ntitle: One\ndescription: d\n"
                        "tags: [excalidraw]\n---\nbody\n")
            with open(os.path.join(root, "b", "index.md"), "w",
                      encoding="utf-8") as f:
                f.write("# B\n")
            out = _run_find(root, "mockup")
            self.assertIn("(no matches for: mockup)", out)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_confident_lexical_arm_skips_expansion_entirely(self):
        """AC-2 (F06-forced): expansion is a rescue path, not a blanket
        cost. A single hit makes _keyword_top1_is_confident() True by
        construction (nothing to be ambiguous against), so the flag being on
        must never even call _expand_query_tags — spied with a raiser, not
        just checked for a stderr note, so a future refactor that widens the
        gate condition fails loudly instead of silently billing a network
        call per query."""
        root = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(root, "b"))
            with open(os.path.join(root, "b", "one.md"), "w",
                      encoding="utf-8") as f:
                f.write("---\ntype: Runbook\ntitle: Zzzznique concept\n"
                        "description: d\ntags: [excalidraw]\n---\nbody\n")
            with open(os.path.join(root, "b", "index.md"), "w",
                      encoding="utf-8") as f:
                f.write("# B\n")

            def _spy(*_a, **_kw):
                raise AssertionError(
                    "_expand_query_tags must not be called when the "
                    "lexical arm is already confident")

            orig = okf._expand_query_tags
            okf._expand_query_tags = _spy
            try:
                out = _run_find(root, "zzzznique", expand_tags=True)
            finally:
                okf._expand_query_tags = orig
            self.assertIn("path: b/one", out)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_rescue_rerun_does_not_double_the_degradation_note(self):
        """B02/PF-4 — --expand-tags reruns the lexical arm a second time
        within one `find`, over the SAME (missing) .fts index. Without
        notify=False on the rescue rerun, `_fts_ranking`'s "index absent"
        note would print twice, with the expansion note sandwiched between
        them — a degradation note describes the invocation, not the
        individual arm pass."""
        root = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(root, "b"))
            with open(os.path.join(root, "b", "one.md"), "w",
                      encoding="utf-8") as f:
                f.write("---\ntype: Runbook\ntitle: One\ndescription: d\n"
                        "tags: [widget]\n---\nbody\n")
            with open(os.path.join(root, "b", "index.md"), "w",
                      encoding="utf-8") as f:
                f.write("# B\n")

            db = okf._tagvec_db_path(root)
            os.makedirs(os.path.dirname(db), exist_ok=True)
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE IF NOT EXISTS emb(key TEXT PRIMARY "
                         "KEY, tag TEXT, model TEXT, dim INT, vec BLOB)")
            conn.executemany(
                "INSERT OR REPLACE INTO emb VALUES(?,?,?,?,?)",
                [("k1", "widget", "voyage-3-large", 2,
                  struct.pack("<2f", 1.0, 0.0))])
            conn.commit()
            conn.close()

            import io
            import contextlib
            import types
            orig = okf._embed_query_voyage
            okf._embed_query_voyage = lambda _t: [1.0, 0.0]
            try:
                args = types.SimpleNamespace(
                    query="gizmo", limit=10, type=None, tag=None,
                    scope=None, breakdown=False, expand_tags=True)
                out_buf, err_buf = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out_buf), \
                     contextlib.redirect_stderr(err_buf):
                    okf.cmd_find(root, args)
            finally:
                okf._embed_query_voyage = orig

            err_lines = [l for l in err_buf.getvalue().splitlines() if l]
            absent_notes = [l for l in err_lines
                            if "lexical index absent" in l]
            self.assertEqual(len(absent_notes), 1, err_lines)
            self.assertIn("note: query expanded with tag(s): widget",
                          err_buf.getvalue())
        finally:
            shutil.rmtree(root, ignore_errors=True)


class ParserExtraction(unittest.TestCase):
    """build_parser() renders the surface without executing a command."""

    def test_every_registered_command_is_dispatchable(self):
        parsers = okf.subcommand_parsers(okf.build_parser())
        self.assertEqual(set(parsers), set(okf.COMMAND_DISPATCH))

    def test_parser_actions_skips_the_auto_help_action(self):
        parsers = okf.subcommand_parsers(okf.build_parser())
        dests = [a.dest for a in okf.parser_actions(parsers["read"])]
        self.assertNotIn("help", dests)
        self.assertIn("path", dests)


class CommandDirectory(unittest.TestCase):
    """Every command carries a summary, at exactly one authored place."""

    def test_find_index_read_are_no_longer_invisible(self):
        parsers = okf.subcommand_parsers(okf.build_parser())
        for name in ("find", "index", "read"):
            self.assertTrue((parsers[name].description or "").strip(),
                            "{} has no summary".format(name))

    def test_the_summary_reaches_both_help_levels(self):
        ap = okf.build_parser()
        parsers = okf.subcommand_parsers(ap)
        summary = parsers["read"].description
        self.assertIn(summary, parsers["read"].format_help())
        self.assertIn("find", ap.format_help())

    def test_every_command_declares_a_group(self):
        parsers = okf.subcommand_parsers(okf.build_parser())
        self.assertEqual(set(okf.COMMAND_GROUPS), set(parsers))

    def test_find_help_explains_both_score_scales(self):
        parsers = okf.subcommand_parsers(okf.build_parser())
        text = parsers["find"].format_help()
        self.assertIn("100", text)
        self.assertIn("6 * number of terms", text)
        self.assertIn("provenance", text)


class FindOptionHelp(unittest.TestCase):
    """find's options describe themselves, and truthfully."""

    def _find_action(self, dest):
        parsers = okf.subcommand_parsers(okf.build_parser())
        for act in okf.parser_actions(parsers["find"]):
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
        names = list(okf.subcommand_parsers(okf.build_parser()))
        self.assertEqual(names, sorted(names))

    def test_top_level_help_points_at_per_command_help(self):
        self.assertIn("<command> --help", okf.build_parser().format_help())


class GroupedOverview(unittest.TestCase):

    def test_overview_names_every_group_that_has_commands(self):
        text = okf.build_parser().format_help()
        self.assertIn("commands by purpose:", text)
        for group in okf._GROUP_ORDER:
            self.assertIn("  {}:".format(group), text)

    def test_overview_covers_every_command(self):
        text = okf.build_parser().format_help()
        overview = text.split("commands by purpose:", 1)[1]
        for name in okf.COMMAND_GROUPS:
            self.assertRegex(overview, r"\n\s+{}\s".format(re.escape(name)))

    def test_module_docstring_no_longer_lists_commands_by_hand(self):
        self.assertNotIn("okf-cli.py find", okf.__doc__)
        self.assertNotIn("okf-cli.py merge-tags", okf.__doc__)


class CommandHelpConformance(unittest.TestCase):
    """An undocumented command or option is unmergeable, not merely
    noticeable (D02). This is the gate the 2026-07-26 PO review asked for."""

    def setUp(self):
        self.ap = okf.build_parser()
        self.parsers = okf.subcommand_parsers(self.ap)

    def test_every_subcommand_has_a_summary(self):
        missing = sorted(n for n, p in self.parsers.items()
                         if not (p.description or "").strip())
        self.assertEqual(missing, [])

    def test_every_option_and_positional_has_help(self):
        missing = []
        for name, parser in sorted(self.parsers.items()):
            for act in okf.parser_actions(parser):
                if not (act.help or "").strip():
                    missing.append("{} {}".format(name, act.dest))
        self.assertEqual(missing, [])

    def test_every_command_is_grouped_and_dispatchable(self):
        self.assertEqual(set(okf.COMMAND_GROUPS), set(self.parsers))
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
        missing = [act.dest for act in okf.parser_actions(self.ap)
                   if not isinstance(act, argparse._SubParsersAction)
                   and not (act.help or "").strip()]
        self.assertEqual(missing, [])


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
        self.assertEqual(len(okf.wikilink_scan_text(text)), len(text))
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

    def test_indented_fence_in_a_block_scalar_keeps_the_block_yaml(self):
        """An indented fence may be the content of a YAML block scalar.
        Rejecting the whole block for it hid every link property in the file."""
        recs = okf.parse_wikilinks(
            '---\nexample: |\n    ```\n    code\n    ```\nrelated:\n\n'
            '    - "[[b]]"\n---\n# X\n')
        self.assertEqual([(r["region"], r["page"]) for r in recs],
                         [("frontmatter", "b")])

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
        the block — masking it would swallow a link on the next line."""
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

    def test_percent_comment_in_frontmatter_is_masked(self):
        self.assertEqual(okf.parse_wikilinks("---\nx: %%[[a]]%%\n---\n# X\n"), [])

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
            self.assertEqual(text[okf._frontmatter_end(text):],
                             okf.split_frontmatter(text)[1], repr(text))


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
        before = set(okf.split_frontmatter(self._r("a/src.md"))[0])
        self._rename("a/old.md", "a/new.md", apply=True)
        after_text = self._r("a/src.md")
        self.assertIn('- "[[new]]"', after_text)
        self.assertEqual(set(okf.split_frontmatter(after_text)[0]), before)

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

    def test_differently_cased_source_path_still_matches(self):
        """On a case-insensitive filesystem `A/old.md` reaches `a/old.md`, so
        the path the caller typed and the path in the index differ in case. A
        case-sensitive comparison of the two rewrote nothing and reported
        success — the silent-orphan path again, one layer down."""
        self._w("a/src.md", "---\ntype: Concept\n---\nSee [[old]].\n")
        self._rename("A/old.md", "A/new.md", apply=True)
        self.assertIn("[[new]]", self._r("a/src.md"))

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

    def test_whitespace_destination_basename_is_refused(self):
        """The scanner strips the page part, the index does not strip filenames,
        so the rewritten link could never meet its target."""
        self._w("a/src.md", "---\ntype: Concept\n---\nSee [[old]].\n")
        with self.assertRaises(SystemExit):
            self._rename("a/old.md", "a/ sp .md", apply=True)
        self.assertIn("[[old]]", self._r("a/src.md"))

    def test_control_character_destination_basename_is_refused(self):
        self._w("a/src.md", "---\ntype: Concept\n---\nSee [[old]].\n")
        with self.assertRaises(SystemExit):
            self._rename("a/old.md", "a/ne\nw.md", apply=True)
        self.assertIn("[[old]]", self._r("a/src.md"))

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
        declines to make."""
        self._w("b/index.md", "# B\n\nIntro.\n")
        self._w("a/target.md", "---\ntype: Concept\n---\n# T\n")
        self._w("a/mover.md", "---\ntype: Concept\n---\n"
                              "Real [T](/a/target.md)\n\n```\n[T](/a/target.md)\n```\n")
        out = self._rename("a/mover.md", "b/mover.md")
        self.assertIn("0 outbound link(s)", out)

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
            got = okf.wikilink_checked_bundles(okf.load_okf_config(self.tmp), self.tmp)
        self.assertEqual(got, set())
        self.assertIn("must be an array", err.getvalue())

    def test_unknown_bundle_in_config_is_announced(self):
        import contextlib
        import io
        self._optin("nosuchbundle")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            okf.wikilink_checked_bundles(okf.load_okf_config(self.tmp), self.tmp)
        self.assertIn("nosuchbundle", err.getvalue())

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
            got = okf.wikilink_checked_bundles(okf.load_okf_config(self.tmp), self.tmp)
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


if __name__ == "__main__":
    unittest.main()
