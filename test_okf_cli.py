#!/usr/bin/env python3
"""Tests for okf-cli.py — stdlib unittest, no deps.

Run: python3 -m unittest test_okf_cli -v
"""
import importlib.util
import os
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

    def test_bundle_relative_crosslink_is_clean(self):
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n# X\n\n[Y](/y.md)\n")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertNotIn("crosslink-format", self._names(warnings))

    def test_cross_bundle_dotdot_link_is_clean(self):
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\n---\n# X\n\n[Y](../other/y.md)\n")
        errors, warnings = okf.run_checks(self.tmp, "b")
        self.assertNotIn("crosslink-format", self._names(warnings))

    def test_clean_bundle_has_zero_violations(self):
        self._w("TYPES.md", "| type | Meaning |\n|---|---|\n| `Concept` | x |\n")
        self._w("b/index.md", "# B\n\n## Contents\n\n"
                              + okf.MARK_START + "\n* [X](x.md)\n" + okf.MARK_END + "\n")
        self._w("b/x.md", "---\ntype: Concept\ntitle: X\ntags: [a]\n---\n# X\n\n[Y](/other.md)\n")
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
    that keeps doc examples pointing at non-existent paths untouched)."""

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
        self.assertEqual(got, "/y.md")

    def test_subdir_target_resolves_from_bundle_root(self):
        self._w("b/sub/y.md", "")
        got = okf.resolve_crosslink_target(self.tmp, "b", "", "sub/y.md")
        self.assertEqual(got, "/sub/y.md")

    def test_target_resolves_relative_to_source_cdir(self):
        self._w("b/sub/y.md", "")
        got = okf.resolve_crosslink_target(self.tmp, "b", "sub", "y.md")
        self.assertEqual(got, "/sub/y.md")

    def test_dotslash_target_normalizes(self):
        self._w("b/y.md", "")
        got = okf.resolve_crosslink_target(self.tmp, "b", "", "./y.md")
        self.assertEqual(got, "/y.md")

    def test_nonexistent_target_returns_none(self):
        got = okf.resolve_crosslink_target(self.tmp, "b", "", "ghost.md")
        self.assertIsNone(got)

    def test_index_md_target_resolves(self):
        self._w("b/sub/index.md", "")
        got = okf.resolve_crosslink_target(self.tmp, "b", "", "sub/index.md")
        self.assertEqual(got, "/sub/index.md")


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
        self.assertEqual(new, "See [Y](/y.md) for details.")
        self.assertEqual(changed, 1)
        self.assertEqual(unresolved, [])

    def test_preserves_anchor_fragment(self):
        self._w("b/y.md", "")
        new, changed, unresolved = okf.rewrite_crosslinks_in_body(
            self.tmp, "b", "", "[Y](y.md#section)")
        self.assertEqual(new, "[Y](/y.md#section)")
        self.assertEqual(changed, 1)

    def test_unresolvable_target_left_untouched(self):
        body = "[Ghost](ghost.md)"
        new, changed, unresolved = okf.rewrite_crosslinks_in_body(self.tmp, "b", "", body)
        self.assertEqual(new, body)
        self.assertEqual(changed, 0)
        self.assertEqual(unresolved, ["ghost.md"])

    def test_already_bundle_relative_link_untouched(self):
        self._w("b/y.md", "")
        body = "[Y](/y.md)"
        new, changed, unresolved = okf.rewrite_crosslinks_in_body(self.tmp, "b", "", body)
        self.assertEqual(new, body)
        self.assertEqual(changed, 0)

    def test_cross_bundle_dotdot_link_untouched(self):
        body = "[Y](../other-bundle/y.md)"
        new, changed, unresolved = okf.rewrite_crosslinks_in_body(self.tmp, "b", "", body)
        self.assertEqual(new, body)
        self.assertEqual(changed, 0)

    def test_multiple_occurrences_all_rewritten(self):
        self._w("b/y.md", "")
        body = "[Y](y.md) and again [Y2](y.md)"
        new, changed, unresolved = okf.rewrite_crosslinks_in_body(self.tmp, "b", "", body)
        self.assertEqual(new, "[Y](/y.md) and again [Y2](/y.md)")
        self.assertEqual(changed, 2)

    def test_subdir_relative_link_from_root_rewritten(self):
        self._w("b/sub/y.md", "")
        new, changed, unresolved = okf.rewrite_crosslinks_in_body(
            self.tmp, "b", "", "[Y](sub/y.md)")
        self.assertEqual(new, "[Y](/sub/y.md)")
        self.assertEqual(changed, 1)


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
        self.assertIn("[Y](/y.md)", content)
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


if __name__ == "__main__":
    unittest.main()
