#!/usr/bin/env python3
"""Tests for cli/okf/find_filters.py — the filters every search arm shares. Stdlib unittest, no deps.

Run: python3 -m unittest tests.test_okf_find_filters -v
"""
import os
import sys
import unittest

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli")
if _HERE not in sys.path:  # cli/ holds the okf package
    sys.path.insert(0, _HERE)

from okf import find_filters as okf_find_filters


class PathInScopeArchiveRule(unittest.TestCase):
    """path_in_scope() directly — the one named, reusable primitive R-08/R-09
    live in (okf-cli-pn72). The FTS arm (FindIncludeArchive in test_okf_find.py) proves it
    end to end against a real build_fts_index() over real `_archive/...`
    fixture files (R-11, okf-cli-fu7o) — this class proves the primitive
    itself is correct standalone, independent of any one caller's traversal
    shape, so a future caller that starts feeding it archived paths
    inherits correct behaviour immediately, not a silently-dead branch."""

    def test_archived_path_excluded_by_default(self):
        f = okf_find_filters.FindFilters()
        self.assertFalse(f.path_in_scope("_archive/bundle-a/hidden"))
        self.assertTrue(f.path_in_scope("bundle-a/active"))

    def test_archived_path_included_when_flagged(self):
        f = okf_find_filters.FindFilters(include_archive=True)
        self.assertTrue(f.path_in_scope("_archive/bundle-a/hidden"))

    def test_scope_compares_against_archive_stripped_path(self):
        f = okf_find_filters.FindFilters(scope="bundle-a", include_archive=True)
        self.assertTrue(f.path_in_scope("_archive/bundle-a/hidden"))
        self.assertFalse(f.path_in_scope("_archive/bundle-b/other-hidden"))
