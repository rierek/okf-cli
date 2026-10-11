#!/usr/bin/env python3
"""Tests for cli/okf/index.py — the index and reindex commands, the bundle
summary renderers and the flat-index migration. unittest.

Run: just test tests.test_okf_index -v
"""
import argparse
import os
import re
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli")
if _HERE not in sys.path:  # cli/ holds the okf package
    sys.path.insert(0, _HERE)

from okf import catalogue as okf_catalogue
from okf import index as okf_index
from okf import rename as okf_rename

M0, M1 = okf_catalogue.MARK_START, okf_catalogue.MARK_END


def _reindex_args(*argv):
    """The namespace `reindex <argv>` parses to, built by the command's own
    add_parser block."""
    ap = argparse.ArgumentParser()
    okf_index.add_reindex_parser(ap.add_subparsers(dest="cmd", required=True))
    return ap.parse_args(["reindex", *argv])


class ConvertFlatIndex(unittest.TestCase):
    """T01 — smart --init: wrap a flat hand-curated list, skip bespoke curation."""

    def test_fenced_h2_is_not_a_section(self):
        text = "# T\n\n```\n## Fake\n```\n\n## Real\n\n* [A](a.md) - a\n"
        new, status = okf_index.convert_flat_index(text)
        self.assertEqual(status, "converted")
        self.assertIn("```\n## Fake\n```", new)

    def test_fenced_h2_does_not_make_a_second_section(self):
        text = "# T\n\n## Real\n\n```\n## Fake\n```\n\n* [A](a.md) - a\n"
        self.assertEqual(okf_index.convert_flat_index(text)[1], "skip-trailing-content")

    def test_flat_single_section_gets_converted(self):
        text = (
            "# Architekturmethodik\n\n"
            "Methodische Kernschicht.\n\n"
            "## Concepts\n\n"
            "* [A](a.md) - desc a\n"
            "* [B](b.md) - desc b\n"
        )
        new, status = okf_index.convert_flat_index(text)
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
        new, status = okf_index.convert_flat_index(text)
        self.assertEqual(status, "skip-multi-section")
        self.assertEqual(new, text)

    def test_already_managed_is_left_alone(self):
        text = (
            "# Title\n\n## Contents\n\n"
            + M0 + "\n* [A](a.md)\n" + M1 + "\n"
        )
        new, status = okf_index.convert_flat_index(text)
        self.assertEqual(status, "already-managed")
        self.assertEqual(new, text)

    def test_trailing_prose_after_list_is_skipped(self):
        # bullets do not run to EOF -> unsafe to auto-wrap
        text = (
            "# Title\n\n## Concepts\n\n"
            "* [A](a.md)\n\n"
            "Some trailing note that must not be lost.\n"
        )
        new, status = okf_index.convert_flat_index(text)
        self.assertEqual(status, "skip-trailing-content")
        self.assertEqual(new, text)

    def test_no_list_section_is_skipped(self):
        # single h2 but no bullet list under it
        text = "# Title\n\nIntro only, no sections, no bullets.\n"
        new, status = okf_index.convert_flat_index(text)
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
        results = dict(okf_index.init_indexes(self.tmp, os.path.join(self.tmp, "b"), dry_run=False))
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
        results = dict(okf_index.init_indexes(self.tmp, os.path.join(self.tmp, "b"), dry_run=True))
        self.assertEqual(results["b/sub1/index.md"], "converted")
        # no write in dry-run
        self.assertEqual(self._r("b/sub1/index.md"), before)
        self.assertNotIn(M0, self._r("b/sub1/index.md"))

    def test_recognizes_uppercase_index_filename(self):
        # Real-world repos sometimes use INDEX.md — discovery must be
        # case-insensitive (matches the already-case-insensitive RESERVED
        # check) instead of silently skipping the dir (B-2026-07-08).
        self._w("b/sub3/INDEX.md", "# Sub3\n\n## Concepts\n\n* [W](w.md) - d\n")
        results = dict(okf_index.init_indexes(self.tmp, os.path.join(self.tmp, "b"), dry_run=False))
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
        okf_index.ensure_markers(self.tmp)
        idx = os.path.join(self.tmp, "index.md")
        self.assertTrue(os.path.isfile(idx))
        with open(idx, encoding="utf-8") as f:
            self.assertIn(M0, f.read())

    def test_leaves_markerless_content_untouched(self):
        idx = os.path.join(self.tmp, "index.md")
        body = "# T\n\n## Concepts\n\n* [A](a.md)\n"
        with open(idx, "w", encoding="utf-8") as f:
            f.write(body)
        okf_index.ensure_markers(self.tmp)
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
        un = okf_index.uncovered_index_dirs(self.tmp, os.path.join(self.tmp, "b"))
        self.assertIn("b/index.md", un)

    def test_managed_dir_is_not_uncovered(self):
        self._w("b/index.md", "# B\n\n" + M0 + "\n" + M1 + "\n")
        self._w("b/x.md", "---\ntype: Concept\n---\n# X\n")
        un = okf_index.uncovered_index_dirs(self.tmp, os.path.join(self.tmp, "b"))
        self.assertEqual(un, [])

    def test_markerless_but_empty_dir_is_not_uncovered(self):
        self._w("b/index.md", "# B\n\nno concepts here\n")
        un = okf_index.uncovered_index_dirs(self.tmp, os.path.join(self.tmp, "b"))
        self.assertEqual(un, [])

    def test_flags_uppercase_index_filename(self):
        # B-2026-07-08: uppercase INDEX.md must not be silently invisible.
        self._w("b/INDEX.md", "# B\n\n## A\n\n* [x](x.md)\n")
        self._w("b/x.md", "---\ntype: Concept\n---\n# X\n")
        un = okf_index.uncovered_index_dirs(self.tmp, os.path.join(self.tmp, "b"))
        self.assertIn("b/INDEX.md", un)


class ForceFlattenAndExempt(unittest.TestCase):
    """Q01 — --force flattens a pure multi-section listing (sections optional);
    a content page marked exempt is dropped from the coverage gate."""

    def test_force_flattens_pure_multi_section(self):
        text = ("# T\n\nintro\n\n## Alpha\n\n* [A](a.md)\n\n## Beta\n\n* [B](b.md)\n")
        new, status = okf_index.convert_flat_index(text, force=True)
        self.assertEqual(status, "converted")
        self.assertIn(M0, new)
        self.assertIn("intro", new)          # intro before first ## preserved
        self.assertNotIn("## Alpha", new)     # sub-section headings dropped
        self.assertNotIn("* [A](a.md)", new)  # old bullets removed (reindex refills)

    def test_force_refuses_when_prose_present(self):
        text = ("# T\n\n## Alpha\n\n| tbl | col |\n\n## Beta\n\n* [B](b.md)\n")
        new, status = okf_index.convert_flat_index(text, force=True)
        self.assertNotEqual(status, "converted")   # table = real content, not flattened
        self.assertEqual(new, text)

    def test_without_force_multi_section_still_skipped(self):
        text = ("# T\n\n## Alpha\n\n* [A](a.md)\n\n## Beta\n\n* [B](b.md)\n")
        new, status = okf_index.convert_flat_index(text, force=False)
        self.assertEqual(status, "skip-multi-section")

    def test_uncovered_skips_exempt_index(self):
        import tempfile
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "b"))
            with open(os.path.join(tmp, "b", "index.md"), "w") as f:
                f.write("# B\n\n" + okf_catalogue.EXEMPT + "\n\ncurated content page\n")
            with open(os.path.join(tmp, "b", "x.md"), "w") as f:
                f.write("---\ntype: Concept\n---\n# X\n")
            un = okf_index.uncovered_index_dirs(tmp, os.path.join(tmp, "b"))
            self.assertEqual(un, [])
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


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
        line = okf_index.render_bundle_line(self.tmp, "b")
        self.assertEqual(line, "b (2 concepts)")

    def test_zero_concepts_still_renders(self):
        os.makedirs(os.path.join(self.tmp, "empty"))
        line = okf_index.render_bundle_line(self.tmp, "empty")
        self.assertEqual(line, "empty (0 concepts)")


class RenderBundleCompact(unittest.TestCase):
    """okf-cli-t2w8 — compact one-liner for `index`'s catalogue-wide default:
    name + one-line description (not prime's name+count, I03 needs the
    *topic* to pick the right bundle, not its size)."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_line_has_bundle_name_and_description(self):
        os.makedirs(os.path.join(self.tmp, "b"))
        with open(os.path.join(self.tmp, "b", "index.md"), "w", encoding="utf-8") as f:
            f.write("# B\n\nA tidy one-line summary of bundle b.\n")
        line = okf_index.render_bundle_compact(self.tmp, "b")
        self.assertEqual(line, "b: A tidy one-line summary of bundle b.")

    def test_missing_description_still_renders(self):
        os.makedirs(os.path.join(self.tmp, "empty"))
        line = okf_index.render_bundle_compact(self.tmp, "empty")
        self.assertEqual(line, "empty: ")


class CmdIndexCatalogueCompactDefault(unittest.TestCase):
    """okf-cli-t2w8 (OKFT-t2w8) — the catalogue-wide `index` (no bundle arg)
    defaults to one line per bundle (name + one-line description); the
    always-on block (description:/concepts:/directories:[/types:/tags:])
    moves behind --full. --json makes the same default/--full split
    (SC-001/SC-002); the per-bundle form (`index <bundle>`) is untouched."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "b", "sub"))
        with open(os.path.join(self.tmp, "b", "index.md"), "w", encoding="utf-8") as f:
            f.write("# B\n\nA tidy one-line summary of bundle b.\n")
        with open(os.path.join(self.tmp, "b", "one.md"), "w", encoding="utf-8") as f:
            f.write("---\ntype: Runbook\ntitle: One\ntags: [t]\n---\n# One\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, full=False, json_flag=False):
        import io, contextlib, types
        args = types.SimpleNamespace(bundle=None, full=full, json=json_flag)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf_index.cmd_index(self.tmp, args)
        return buf.getvalue()

    def test_default_text_is_one_line_name_plus_description(self):
        out = self._run()
        self.assertEqual(out.strip(), "b: A tidy one-line summary of bundle b.")
        self.assertNotIn("description:", out)
        self.assertNotIn("concepts:", out)
        self.assertNotIn("directories:", out)

    def test_full_flag_restores_the_structured_block(self):
        out = self._run(full=True)
        self.assertIn("description: A tidy one-line summary of bundle b.", out)
        self.assertIn("concepts: 1", out)
        self.assertIn("directories:", out)
        self.assertIn("types: Runbook", out)
        self.assertIn("tags: t", out)


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
        """The text printed; with --json what the handler returns, the envelope's `data`
        (and nothing is printed)."""
        import io, contextlib, types
        args = types.SimpleNamespace(bundle=bundle, full=full, json=json_flag)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            data = okf_index.cmd_index(self.tmp, args)
        if json_flag:
            self.assertEqual(buf.getvalue(), "")
            return data
        return buf.getvalue()

    def test_json_output_with_bundle_is_parseable_object(self):
        data = self._run(bundle="b", json_flag=True)
        self.assertEqual(data["bundle"], "b")
        self.assertIsInstance(data["concepts"], list)
        self.assertEqual(len(data["concepts"]), 1)
        concept = data["concepts"][0]
        self.assertTrue(all(k in concept for k in ("id", "title", "type", "description")))

    def test_json_output_without_bundle_is_parseable_object(self):
        data = self._run(bundle=None, json_flag=True)
        self.assertIsInstance(data["bundles"], list)
        self.assertTrue(any(entry.get("bundle") == "b" for entry in data["bundles"]))

    def test_non_json_output_unchanged(self):
        out_json_false = self._run(bundle="b", json_flag=False)
        out_no_flag = self._run(bundle="b")
        self.assertEqual(out_json_false, out_no_flag)
        self.assertIn("* [One]", out_json_false)
        self.assertNotIn("{", out_json_false)

    def test_json_full_without_bundle_reports_a_concept_count_not_the_list(self):
        """okf-cli-7u5z (D01), revised okf-cli-t2w8 — the catalogue-wide
        shape mirrors the text block once --full asks for it. Enumerating
        every concept of every bundle produced 794 KB against the real
        catalogue; concepts/directories now sit behind --full for the same
        reason the compact default exists (SC-002)."""
        entry = self._run(bundle=None, json_flag=True, full=True)["bundles"][0]
        self.assertEqual(entry["concepts"], 1)

    def test_json_full_without_bundle_carries_description_and_directories(self):
        """okf-cli-7u5z (D01), revised okf-cli-t2w8 — the other two fields
        the full text block shows, now gated the same way."""
        os.makedirs(os.path.join(self.tmp, "b", "sub"))
        with open(os.path.join(self.tmp, "b", "index.md"), "w", encoding="utf-8") as f:
            f.write("# B\n\nthe b bundle\n")
        entry = self._run(bundle=None, json_flag=True, full=True)["bundles"][0]
        self.assertEqual(entry["description"], "the b bundle")
        self.assertEqual(entry["directories"], ["sub"])

    def test_json_without_bundle_defaults_to_compact_fields(self):
        """okf-cli-t2w8 SC-001/SC-002 — default catalogue-wide --json shrinks
        to bundle+description, same distinction the text form makes; no
        --full means no concepts/directories keys at all."""
        entry = self._run(bundle=None, json_flag=True)["bundles"][0]
        self.assertEqual(entry, {"bundle": "b", "description": ""})
        self.assertNotIn("concepts", entry)
        self.assertNotIn("directories", entry)


class CmdReindexBlastRadius(unittest.TestCase):
    """Ensure reindex <bundle>/<subdir> does not write to sibling directories."""
    
    def test_reindex_subdir_does_not_modify_siblings(self):
        """Verify that uncovered_index_dirs uses the scoped target path (fix for OKFT-czm9)."""
        with tempfile.TemporaryDirectory() as root:
            # Create a bundle with two subdirs, each with index.md
            bundle_path = os.path.join(root, "bundle")
            os.makedirs(os.path.join(bundle_path, "subdir1"))
            os.makedirs(os.path.join(bundle_path, "subdir2"))
            
            # Create index.md in each subdir with marker blocks
            idx1 = os.path.join(bundle_path, "subdir1", "index.md")
            idx2 = os.path.join(bundle_path, "subdir2", "index.md")
            
            okf_catalogue.write_file(idx1, "# Subdir1\n\n<!-- okf:index -->\n<!-- /okf:index -->\n")
            okf_catalogue.write_file(idx2, "# Subdir2\n\n<!-- okf:index -->\n<!-- /okf:index -->\n")
            
            # Create a concept file in each subdir
            okf_catalogue.write_file(os.path.join(bundle_path, "subdir1", "concept1.md"),
                          "---\ntitle: Concept1\n---\n")
            okf_catalogue.write_file(os.path.join(bundle_path, "subdir2", "concept2.md"),
                          "---\ntitle: Concept2\n---\n")
            
            # Reindex only subdir1 by creating args directly (no sys.argv)
            args = _reindex_args("bundle/subdir1")
            okf_index.cmd_reindex(root, args)
            
            # Verify subdir1/index.md was updated with concept1
            content1 = okf_catalogue.read_file(idx1)
            self.assertIn("concept1", content1)
            self.assertNotIn("concept2", content1)
            
            # Verify subdir2/index.md was NOT modified (regression: it should not be touched)
            content2_expected = "# Subdir2\n\n<!-- okf:index -->\n<!-- /okf:index -->\n"
            content2_actual = okf_catalogue.read_file(idx2)
            self.assertEqual(content2_actual, content2_expected,
                           "reindex <bundle>/<subdir> modified a sibling directory!")


class CmdReindexSlugCollision(unittest.TestCase):
    """README.md name collision across subdirs of one bundle (OKFT-czm9).

    README.md is excluded from concept listing via RESERVED, so it is never
    rendered as a link target and a vault-absolute alias can never be
    emitted for it. This reproduces the bean's exact repro steps (two
    README.md in different subdirs of one bundle, run reindex) and asserts
    on the actual generated index content, not just render_block in
    isolation."""

    def test_two_readmes_never_surface_as_link_targets(self):
        with tempfile.TemporaryDirectory() as root:
            bundle_path = os.path.join(root, "bundle")
            e2e = os.path.join(bundle_path, "e2e-tests")
            other = os.path.join(bundle_path, "other")
            os.makedirs(e2e)
            os.makedirs(other)
            okf_catalogue.write_file(os.path.join(e2e, "README.md"),
                          "---\ntitle: E2E Readme\ntype: guide\n---\n# E2E\n")
            okf_catalogue.write_file(os.path.join(other, "README.md"),
                          "---\ntitle: Other Readme\ntype: guide\n---\n# Other\n")
            okf_catalogue.write_file(os.path.join(e2e, "index.md"),
                          "# e2e-tests\n\n<!-- okf:index -->\n<!-- /okf:index -->\n")

            args = _reindex_args("bundle")
            okf_index.cmd_reindex(root, args)

            content = okf_catalogue.read_file(os.path.join(e2e, "index.md"))
            self.assertNotIn("README", content,
                           "README.md must never surface as a link target")
            self.assertNotIn(os.path.basename(root), content,
                           "reindex must never emit a vault-absolute path alias")

    def test_render_block_uses_bundle_relative_paths(self):
        """render_block always emits /bundle/subdir links, never a vault-absolute alias."""
        with tempfile.TemporaryDirectory() as root:
            bundle = "test-bundle"
            bundle_path = os.path.join(root, bundle)
            subdir = os.path.join(bundle_path, "sub1")
            os.makedirs(subdir)
            okf_catalogue.write_file(os.path.join(subdir, "concept.md"),
                          "---\ntitle: Test Concept\n---\n")
            subdirs = okf_catalogue.list_subdirs_with_index(subdir)
            concepts = okf_catalogue.list_dir_concepts(subdir)
            block = okf_catalogue.render_block(subdirs, concepts, "test-bundle/sub1")
            self.assertIn("/test-bundle/sub1", block,
                         "render_block must use bundle-relative paths")
            for line in block.split('\n'):
                if '.md)' in line:
                    match = re.search(r'\]\(([^)]+)\)', line)
                    if match:
                        self.assertTrue(match.group(1).startswith('/'),
                                      f"Link {match.group(1)} must start with / (bundle-relative)")


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
        okf_index.cmd_reindex(self.tmp, _reindex_args("b"))

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
        okf_rename.perform_rename(self.tmp,
                                  os.path.join(self.tmp, "b", "sub", "deep.md"),
                                  os.path.join(self.tmp, "b", "sub", "deeper.md"),
                                  apply=True, force=True)
        text = self._map()
        self.assertIn("/b/sub/deeper.md", text)
        self.assertNotIn("/b/sub/deep.md", text)


if __name__ == "__main__":
    unittest.main()
