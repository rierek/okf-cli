#!/usr/bin/env python3
"""Tests for cli/okf/catalogue.py — the shared catalogue layer. Stdlib unittest, no deps.

Run: python3 -m unittest test_okf_catalogue -v
"""
import os
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:  # cli/ holds the okf package; a repo-root run lacks it
    sys.path.insert(0, _HERE)

from okf import catalogue as okf_catalogue


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
        self.assertEqual(okf_catalogue.load_okf_config(self.tmp), {})

    def test_parses_keys(self):
        self._w(".okf.toml", 'kc_root = "~/Obsidian/Knowledge-Catalogue"\n'
                             'types_source = "~/Obsidian/Knowledge-Catalogue/TYPES.md"\n'
                             'bundle = "demo-okf"\n')
        cfg = okf_catalogue.load_okf_config(self.tmp)
        self.assertEqual(cfg["bundle"], "demo-okf")
        self.assertFalse(cfg["types_source"].startswith("~"))  # expanduser ran
        self.assertTrue(cfg["types_source"].endswith("Knowledge-Catalogue/TYPES.md"))

    def test_parses_keys_without_tomllib(self):
        """okf-cli.py is `#!/usr/bin/env python3` with no declared minimum
        version; on Python <3.11 (no stdlib `tomllib`) load_okf_config must
        still parse the same file via its dependency-free fallback, not
        crash with ModuleNotFoundError."""
        import sys
        from unittest import mock
        self._w(".okf.toml", 'kc_root = "~/Obsidian/Knowledge-Catalogue"\n'
                             'types_source = "~/Obsidian/Knowledge-Catalogue/TYPES.md"\n'
                             'bundle = "demo-okf"  # trailing comment\n'
                             'wikilink_checked_bundles = ["demo-okf"]\n')
        with mock.patch.dict(sys.modules, {"tomllib": None}):
            cfg = okf_catalogue.load_okf_config(self.tmp)
        self.assertEqual(cfg["bundle"], "demo-okf")
        self.assertEqual(cfg["wikilink_checked_bundles"], ["demo-okf"])
        self.assertFalse(cfg["types_source"].startswith("~"))  # expanduser ran
        self.assertTrue(cfg["types_source"].endswith("Knowledge-Catalogue/TYPES.md"))

    def test_malformed_config_without_tomllib_fails_with_a_message(self):
        import sys
        from unittest import mock
        self._w(".okf.toml", "this is not = = toml\n")
        with mock.patch.dict(sys.modules, {"tomllib": None}):
            with self.assertRaises(SystemExit) as cm:
                okf_catalogue.load_okf_config(self.tmp)
        self.assertIn(".okf.toml is not valid TOML", str(cm.exception))


class ListIndexableBundles(unittest.TestCase):
    """OKFT-n8xz — the narrower corpus for index/search call sites only: the
    declared `.okf.toml` `bundle` key when present, list_bundles()'s name
    filter (catalogue behaviour, unchanged) otherwise."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _mkdirs(self, *names):
        for n in names:
            os.makedirs(os.path.join(self.tmp, n), exist_ok=True)

    def _w_toml(self, text):
        with open(os.path.join(self.tmp, ".okf.toml"), "w", encoding="utf-8") as f:
            f.write(text)

    def test_declared_bundle_key_narrows_to_exactly_that_name(self):
        """AC1 — a `bundle` key wins even with other namefilter-eligible
        directories sitting right next to it (the TPIC-scaffolding shape a
        repo docs root actually has)."""
        self._mkdirs("lean-stack-okf", "some-tpic-scaffolding", "another-plan-dir")
        self._w_toml('bundle = "lean-stack-okf"\n')
        self.assertEqual(okf_catalogue.list_indexable_bundles(self.tmp), ["lean-stack-okf"])

    def test_absent_bundle_key_matches_list_bundles(self):
        """AC2 — no `bundle` key -> catalogue behaviour (list_bundles)."""
        self._mkdirs("a", "b", "_staging")
        self._w_toml('types_source = "x"\n')
        self.assertEqual(okf_catalogue.list_indexable_bundles(self.tmp),
                          okf_catalogue.list_bundles(self.tmp))

    def test_no_config_file_at_all_matches_list_bundles(self):
        """AC3 — no `.okf.toml` at all -> same fallback as AC2."""
        self._mkdirs("a", "b")
        self.assertEqual(okf_catalogue.list_indexable_bundles(self.tmp),
                          okf_catalogue.list_bundles(self.tmp))

    def test_declared_bundle_missing_on_disk_yields_empty_not_fallback(self):
        """AC4 — a `bundle` key naming a directory that does not exist is a
        positive declaration gone stale, not an invitation back to the wide
        name filter: the empty set, chosen and justified in the bean over
        falling back silently, which would resurrect every scaffolding
        directory the moment the declared path went missing."""
        self._mkdirs("some-other-dir")
        self._w_toml('bundle = "does-not-exist"\n')
        self.assertEqual(okf_catalogue.list_indexable_bundles(self.tmp), [])


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
            got = okf_catalogue.resolve_scopes(self.tmp, target)
            self.assertEqual(got[0][0], bundle, target)
            self.assertEqual(got[0][1], os.path.join(self.tmp, tail), target)

    def test_absolute_target_still_addresses_that_directory(self):
        """os.path.join(root, "/x") discards root, so an absolute target used to
        work by accident. Normalising it into a relative segment rescoped the
        scan onto a path that does not exist and reported a clean run."""
        ap = os.path.join(self.tmp, "beta")
        self.assertEqual(okf_catalogue.resolve_scopes(self.tmp, ap), [("beta", ap)])

    def test_dot_target_means_the_whole_catalogue(self):
        """`.` yielded a bundle literally named "." — every bundle-name-keyed
        rule then failed to match while the scan still walked the root."""
        for target in (".", "./"):
            self.assertEqual(okf_catalogue.resolve_scopes(self.tmp, target),
                             okf_catalogue.resolve_scopes(self.tmp, None), target)


class ResolveConceptDirectoryFallback(unittest.TestCase):
    """okf-cli-3hjr — prime lists bundles by the path an agent should type next,
    and that path is the bundle. `toc <bundle>` / `read <bundle>` therefore have
    to resolve to the bundle's own index.md instead of failing on a directory."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "b", "sub"))
        self._w("b/index.md", "# B\n\n## Contents\n")
        self._w("b/one.md", "---\ntype: Concept\ntitle: One\n---\n# One\n")
        self._w("b/sub/index.md", "# Sub\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _w(self, rel, text):
        with open(os.path.join(self.tmp, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def test_bundle_resolves_to_its_index(self):
        self.assertEqual(okf_catalogue.resolve_concept(self.tmp, "b"),
                         os.path.join(self.tmp, "b", "index.md"))

    def test_subdirectory_resolves_to_its_index(self):
        self.assertEqual(okf_catalogue.resolve_concept(self.tmp, "b/sub"),
                         os.path.join(self.tmp, "b", "sub", "index.md"))

    def test_concept_path_is_unaffected(self):
        """The fallback must not shadow a concept: b/one.md wins over any
        directory reading of the same reference."""
        self.assertEqual(okf_catalogue.resolve_concept(self.tmp, "b/one"),
                         os.path.join(self.tmp, "b", "one.md"))

    def test_directory_without_index_still_fails(self):
        os.makedirs(os.path.join(self.tmp, "empty"))
        with self.assertRaises(SystemExit):
            okf_catalogue.resolve_concept(self.tmp, "empty")

    def test_missing_reference_still_fails(self):
        with self.assertRaises(SystemExit):
            okf_catalogue.resolve_concept(self.tmp, "nope")


class IterConceptsStagingPrune(unittest.TestCase):
    """iter_concepts (okf-cli.py:117) did not prune "_"-prefixed staging
    dirs, unlike its sibling iter_all_md (:2925, clause :2930-2932) —
    in-bundle staging content was reachable via index/list/find yet skipped
    by `check`, the worst combination: reachable but unverified (OKFT-oe8t).
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _w(self, rel, text="---\ntype: Concept\ntitle: T\n---\nbody\n"):
        ap = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(text)

    def test_underscore_staging_dir_pruned(self):
        self._w("b/_intake/konzept.md")
        cids = [cid for cid, _ap in okf_catalogue.iter_concepts(os.path.join(self.tmp, "b"))]
        self.assertEqual(cids, [])

    def test_ordinary_subdir_still_walked(self):
        """The prune targets "_"-prefixed names only — a normal nested
        directory stays fully reachable."""
        self._w("b/sub/inner.md")
        cids = [cid for cid, _ap in okf_catalogue.iter_concepts(os.path.join(self.tmp, "b"))]
        self.assertEqual(cids, ["sub/inner"])

    def test_dot_dir_and_assets_still_pruned(self):
        """Unchanged behaviour — this fix adds a clause, it does not touch
        the two that were already there."""
        self._w("b/.git/hidden.md")
        self._w("b/assets/pic.md")
        self._w("b/kept.md")
        cids = sorted(cid for cid, _ap in okf_catalogue.iter_concepts(os.path.join(self.tmp, "b")))
        self.assertEqual(cids, ["kept"])

    def test_underscore_prefix_prunes_dirs_not_files(self):
        """I04 (Review 2026-08-13): the "_" rule inspects DIRECTORY names in
        `dirnames`, never file names — a file `_private.md` sitting directly
        in the bundle root is untouched by the prune and stays reachable.
        Correct today, but unpinned before this test."""
        self._w("b/_private.md")
        cids = [cid for cid, _ap in okf_catalogue.iter_concepts(os.path.join(self.tmp, "b"))]
        self.assertEqual(cids, ["_private"])

    def test_prune_staging_false_widens_the_walk(self):
        """OKFT-oe8t Review D02: prune_staging=False is the opt-out the
        three tag-mutation commands (cmd_merge_tags, cmd_remove_tags,
        cmd_normalize_tags) pass explicitly — it restores the pre-fix wide
        walk for whichever caller opts into it, without a second, duplicated
        traversal function."""
        self._w("b/_intake/konzept.md")
        cids = [cid for cid, _ap in
                okf_catalogue.iter_concepts(os.path.join(self.tmp, "b"), prune_staging=False)]
        self.assertEqual(cids, ["_intake/konzept"])


class ResolveScopesArchive(unittest.TestCase):
    """R-12 (okf-cli-iwx4) — resolve_scopes() is the ONE function `cmd_list`
    and `_substring_ranking` both traverse through; this class pins its
    include_archive behaviour directly, at the primitive level, the same way
    ResolveScopesTargets above pins the non-archive target forms."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "alpha", "sub"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "beta"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "_archive", "alpha"), exist_ok=True)
        # archive-only bundle: no active "gamma" directory exists at all —
        # R-05/R-06's basename index already discovers bundles this way
        # (build_concept_basename_index), so the shared scope resolution
        # must too.
        os.makedirs(os.path.join(self.tmp, "_archive", "gamma"), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_default_is_unchanged_by_the_new_parameter(self):
        self.assertEqual(
            okf_catalogue.resolve_scopes(self.tmp, None),
            [("alpha", os.path.join(self.tmp, "alpha")),
             ("beta", os.path.join(self.tmp, "beta"))],
        )

    def test_unscoped_include_archive_appends_every_archive_bundle(self):
        got = okf_catalogue.resolve_scopes(self.tmp, None, include_archive=True)
        self.assertEqual(got, [
            ("alpha", os.path.join(self.tmp, "alpha")),
            ("beta", os.path.join(self.tmp, "beta")),
            ("_archive/alpha", os.path.join(self.tmp, "_archive", "alpha")),
            ("_archive/gamma", os.path.join(self.tmp, "_archive", "gamma")),
        ])

    def test_scoped_include_archive_appends_only_that_bundles_archive_dir(self):
        got = okf_catalogue.resolve_scopes(self.tmp, "alpha", include_archive=True)
        self.assertEqual(got, [
            ("alpha", os.path.join(self.tmp, "alpha")),
            ("_archive/alpha", os.path.join(self.tmp, "_archive", "alpha")),
        ])
        got_other = okf_catalogue.resolve_scopes(self.tmp, "beta", include_archive=True)
        self.assertNotIn(("_archive/alpha",
                          os.path.join(self.tmp, "_archive", "alpha")),
                          got_other)

    def test_scoped_subdir_include_archive_appends_nested_archive_dir(self):
        """AC3's easiest way to break: losing or re-deriving the prefix
        during traversal. `alpha/sub` must map to the NESTED
        `_archive/alpha/sub`, not `_archive/alpha` or `_archive/sub`."""
        got = okf_catalogue.resolve_scopes(self.tmp, "alpha/sub", include_archive=True)
        self.assertEqual(got, [
            ("alpha", os.path.join(self.tmp, "alpha", "sub")),
            ("_archive/alpha",
             os.path.join(self.tmp, "_archive", "alpha", "sub")),
        ])

    def test_no_archive_directory_at_all_does_not_crash(self):
        tmp2 = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp2, "solo"))
            got = okf_catalogue.resolve_scopes(tmp2, None, include_archive=True)
            self.assertEqual(got, [("solo", os.path.join(tmp2, "solo"))])
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
