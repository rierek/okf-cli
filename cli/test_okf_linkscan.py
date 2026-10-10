#!/usr/bin/env python3
"""Tests for cli/okf/linkscan.py — link scanning. Stdlib unittest, no deps.

Run: python3 -m unittest test_okf_linkscan -v
"""
import os
import shutil
import tempfile
import unittest

from okf import linkscan as okf_linkscan


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
        hits = okf_linkscan.build_ref_matrix(self.tmp, os.path.join(self.tmp, "docs/arch.md"))
        self.assertEqual(self._sources(hits), ["README.md", "docs/overview.md"])

    def test_catalogue_root_leading_slash_resolves(self):
        self._w("docs/arch.md", "# Arch\n")
        # /docs/arch.md — leading / is the CATALOGUE root, so the bundle
        # segment is part of the link.
        self._w("docs/x.md", "see [a](/docs/arch.md)\n")
        hits = okf_linkscan.build_ref_matrix(self.tmp, os.path.join(self.tmp, "docs/arch.md"))
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
        hits = okf_linkscan.build_ref_matrix(self.tmp, os.path.join(self.tmp, "b1/x.md"))
        self.assertEqual(self._sources(hits), ["b1/foo.md", "b2/bar.md"])

    def test_http_and_anchor_and_fenced_ignored(self):
        self._w("docs/arch.md", "# Arch\n")
        self._w("docs/x.md",
                "[ext](https://arch.md)\n[frag](arch.md#top)\n```\n[fenced](arch.md)\n```\n")
        hits = okf_linkscan.build_ref_matrix(self.tmp, os.path.join(self.tmp, "docs/arch.md"))
        # only the anchor link resolves to arch.md; http + fenced excluded
        self.assertEqual(self._sources(hits), ["docs/x.md"])
        self.assertEqual(len(hits), 1)

    def test_git_and_node_modules_pruned(self):
        self._w("docs/arch.md", "# Arch\n")
        self._w(".git/x.md", "[a](../docs/arch.md)\n")
        self._w("node_modules/y.md", "[a](../docs/arch.md)\n")
        hits = okf_linkscan.build_ref_matrix(self.tmp, os.path.join(self.tmp, "docs/arch.md"))
        self.assertEqual(hits, [])

    def test_no_inbound_is_empty(self):
        self._w("docs/arch.md", "# Arch\n")
        hits = okf_linkscan.build_ref_matrix(self.tmp, os.path.join(self.tmp, "docs/arch.md"))
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
