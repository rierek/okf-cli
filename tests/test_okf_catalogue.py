#!/usr/bin/env python3
"""Tests for cli/okf/catalogue.py — the shared catalogue layer. Stdlib unittest, no deps.

Run: python3 -m unittest tests.test_okf_catalogue -v
"""
import contextlib
import io
import json
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
from okf import check as okf_check
from okf.errors import EXIT_CODES, OkfError
from tests.okf_testkit import CtxFixtureMixin, E, _scan


M0, M1 = okf_catalogue.MARK_START, okf_catalogue.MARK_END


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
            with self.assertRaises(OkfError) as cm:
                okf_catalogue.load_okf_config(self.tmp)
        self.assertEqual(cm.exception.kind, "invalid_input")
        self.assertIn(".okf.toml is not valid TOML", cm.exception.message)


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
        with self.assertRaises(OkfError) as cm:
            okf_catalogue.resolve_concept(self.tmp, "empty")
        self.assertEqual(cm.exception.kind, "not_found")

    def test_missing_reference_still_fails(self):
        with self.assertRaises(OkfError) as cm:
            okf_catalogue.resolve_concept(self.tmp, "nope")
        self.assertEqual((cm.exception.kind, cm.exception.message), ("not_found", "not found: nope"))


class IterHeadings(unittest.TestCase):
    """OKFT-ir4m — the one heading function: (level, text, line) per ATX heading
    outside fenced code, `line` the 0-based index in body.splitlines()."""

    def _h(self, body):
        return list(okf_catalogue.iter_headings(body))

    def test_duplicate_nested_and_fenced_fixture_exact_tuples(self):
        body = "\n".join([
            "# Top",                      # 0
            "intro",                      # 1
            "## Dup",                     # 2
            "### Deep",                   # 3
            "#### Deeper ####",           # 4
            "## Dup",                     # 5
            "```py",                      # 6
            "# fake backtick",            # 7
            "```",                        # 8
            "~~~",                        # 9
            "# fake tilde",               # 10
            "~~~",                        # 11
            "````",                       # 12
            "```",                        # 13
            "# fake four",                # 14
            "```",                        # 15
            "````",                       # 16
            "## After",                   # 17
        ]) + "\n"
        self.assertEqual(self._h(body), [
            (1, "Top", 0), (2, "Dup", 2), (3, "Deep", 3), (4, "Deeper", 4),
            (2, "Dup", 5), (2, "After", 17)])

    def test_duplicate_heading_keeps_distinct_lines(self):
        self.assertEqual(self._h("## A\nx\n## A\n"), [(2, "A", 0), (2, "A", 2)])

    def test_levels_one_to_four_nest_in_document_order(self):
        self.assertEqual(self._h("# a\n## b\n### c\n#### d\n### e\n# f\n"),
                         [(1, "a", 0), (2, "b", 1), (3, "c", 2), (4, "d", 3),
                          (3, "e", 4), (1, "f", 5)])

    def test_tilde_fence_hides_headings(self):
        self.assertEqual(self._h("~~~\n# no\n~~~\n# yes\n"), [(1, "yes", 3)])

    def test_long_fence_is_not_closed_by_shorter_one(self):
        self.assertEqual(self._h("````\n```\n# no\n```\n````\n# yes\n"), [(1, "yes", 5)])

    def test_closer_must_use_the_openers_character(self):
        self.assertEqual(self._h("```\n~~~\n# no\n```\n# yes\n"), [(1, "yes", 4)])

    def test_fence_line_with_info_string_does_not_close(self):
        self.assertEqual(self._h("```\n```py\n# no\n```\n# yes\n"), [(1, "yes", 4)])

    def test_unclosed_fence_runs_to_end_of_body(self):
        self.assertEqual(self._h("# a\n```\n# no\n## no\n"), [(1, "a", 0)])

    def test_indent_up_to_three_spaces_opens_a_fence(self):
        self.assertEqual(self._h("   ```\n# no\n   ```\n# yes\n"), [(1, "yes", 3)])

    def test_four_space_indent_does_not_open_a_fence(self):
        self.assertEqual(self._h("    ```\n# yes\n"), [(1, "yes", 1)])


class IndexH1AndDescIgnoresFences(unittest.TestCase):
    """OKFT-ir4m AC5 — the H1 of an index.md comes from the one heading function."""

    def _h1_desc(self, body):
        with tempfile.TemporaryDirectory() as d:
            ap = os.path.join(d, "index.md")
            with open(ap, "w", encoding="utf-8") as f:
                f.write(body)
            return okf_catalogue.index_h1_and_desc(ap)

    def test_fenced_h1_is_not_the_title(self):
        self.assertEqual(self._h1_desc("```\n# Fake\nnot intro\n```\n# Real\nIntro.\n"),
                         ("Real", "Intro."))

    def test_plain_h1_and_intro_unchanged(self):
        self.assertEqual(self._h1_desc("# B\n\nIntro.\n## Contents\n"), ("B", "Intro."))
        self.assertEqual(self._h1_desc("# B\n## Contents\n"), ("B", ""))


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


class SplitManagedBlockUnit(unittest.TestCase):
    """Direct unit coverage for `_split_managed_block`'s byte boundary —
    an end-to-end `fix_crosslinks` test cannot observe this: a boundary
    mutated by one byte (leaking the trailing `>` of MARK_END into
    `after` instead of `block`) reconstructs an identical final rewrite
    whenever the leaked byte is never itself a rewritable crosslink, so
    it passes every file-level test unchanged. Reviewer finding on
    62e867f, closed here at the function boundary instead."""

    def test_complete_pair_bounds_block_exactly(self):
        body = "before\n" + M0 + "\nX\n" + M1 + "\nafter\n"
        before, block, after = okf_catalogue._split_managed_block(body)
        self.assertEqual(before + block + after, body)
        self.assertEqual(block, M0 + "\nX\n" + M1)
        self.assertEqual(before, "before\n")
        self.assertEqual(after, "\nafter\n")
        self.assertFalse(after.startswith(">"))

    def test_unterminated_start_protects_to_eof(self):
        body = "before\n" + M0 + "\nX\n"
        before, block, after = okf_catalogue._split_managed_block(body)
        self.assertEqual(before + block + after, body)
        self.assertTrue(block.startswith(M0))
        self.assertEqual(before, "before\n")
        self.assertEqual(after, "")

    def test_no_marker_returns_whole_body_as_before(self):
        body = "just prose, no markers\n"
        before, block, after = okf_catalogue._split_managed_block(body)
        self.assertEqual(before, body)
        self.assertEqual(block, "")
        self.assertEqual(after, "")


# --- the ctx storage layer of okf.catalogue: slugs, parse/render, load/save, findings ---


class CtxSlugs(CtxFixtureMixin, unittest.TestCase):
    def test_paths(self):
        self.assertEqual(okf_catalogue.ctx_dir(self.root), os.path.join(self.root, "_ctx"))
        self.assertEqual(okf_catalogue.ctx_file(self.root, "x"), os.path.join(self.root, "_ctx", "x.md"))

    def test_slugs_missing_dir_is_empty(self):
        self.assertEqual(okf_catalogue.ctx_slugs(self.root), [])

    def test_slugs_sorted_and_reserved_filenames_excluded(self):
        for n in ("zeta.md", "alpha.md", "index.md", "README.md", "log.md", "notes.txt"):
            self._w("_ctx/" + n, "x")
        self.assertEqual(okf_catalogue.ctx_slugs(self.root), ["alpha", "zeta"])

    def test_slug_problem(self):
        self.assertIsNone(okf_catalogue.ctx_slug_problem("a-b1"))
        self.assertIsNone(okf_catalogue.ctx_slug_problem("1a"))
        msg = "use lowercase letters, digits and hyphens"
        for bad in ("A", "-a", "a_b", "a b", ""):
            self.assertEqual(okf_catalogue.ctx_slug_problem(bad), msg, bad)
        for res in ("add", "index", "index-map", "readme", "log", "toc"):
            self.assertEqual(okf_catalogue.ctx_slug_problem(res), '"%s" is a reserved name' % res)


class CtxParseRender(CtxFixtureMixin, unittest.TestCase):
    def test_render_exact(self):
        out = okf_catalogue.render_ctx("my-ctx", 'say "hi"', [
            E(1, "pflicht", "b/one.md", "a|b\nc"),
            E(None, "nachschlag", "~/notes/out.md", "x"),
            E(None, "nachschlag", "/abs/p.md", ""),
        ])
        self.assertEqual(out, (
            '---\ntype: Context\ndescription: "say \\"hi\\""\n---\n\n# my-ctx\n\n'
            "| pos | mode | path | comment |\n|---|---|---|---|\n"
            "| 1 | pflicht | [one](/b/one.md) | a\\|b c |\n"
            "| - | nachschlag | `~/notes/out.md` | x |\n"
            "| - | nachschlag | `/abs/p.md` |  |\n"))

    def test_roundtrip(self):
        entries = [E(1, "pflicht", "b/one.md", "a|b c"),
                   E(2, "pflicht", "b/notes (draft).md", ""),
                   E(None, "nachschlag", "~/notes/out.md", "x")]
        desc, got, problems = okf_catalogue.parse_ctx(okf_catalogue.render_ctx("s", 'q"q', entries))
        self.assertEqual((desc, got, problems), ('q"q', entries, []))

    def test_parse_problems(self):
        base = "---\ntype: Context\ndescription: d\n---\n\n# s\n\n"
        _, e, p = okf_catalogue.parse_ctx(base + "no table\n")
        self.assertEqual((e, p), ([], ['no table with header "pos | mode | path | comment"']))
        hdr = "| Pos | Mode | Path | Comment |\n|---|---|---|---|\n"
        _, e, p = okf_catalogue.parse_ctx(base + hdr + "| 1 | pflicht | [a](/a.md) |\n")
        self.assertEqual((e, p), ([], ["row 1: expected 4 cells, found 3"]))
        _, e, p = okf_catalogue.parse_ctx(base + hdr + "| 1 | pflicht | [a](/a.md) | c |\n| x | pflicht | [a](/a.md) | c |\n")
        self.assertEqual(p, ['row 2: pos "x" is neither an integer nor -'])
        self.assertEqual(len(e), 1)
        _, e, p = okf_catalogue.parse_ctx(base + hdr + "| 1 | pflicht | plain | c |\n")
        self.assertEqual(p, ["row 1: path cell is neither a catalogue link nor a code span"])

    def test_parse_rows_end_at_first_non_table_line_and_mode_lowercased(self):
        text = ("---\ntype: Context\ndescription: d\n---\n\n# s\n\n"
                "| pos | mode | path | comment |\n|---|---|---|---|\n"
                "| 1 | PFLICHT | [a](/b/one.md) | c |\n\ntrailing | not | a | row |\n")
        _, e, p = okf_catalogue.parse_ctx(text)
        self.assertEqual(e, [E(1, "pflicht", "b/one.md", "c")])
        self.assertEqual(p, [])

    def test_parse_ignores_link_text(self):
        text = ("---\ntype: Context\ndescription: d\n---\n\n"
                "| pos | mode | path | comment |\n|---|---|---|---|\n"
                "| 1 | pflicht | [whatever](/b/one.md) |  |\n")
        self.assertEqual(okf_catalogue.parse_ctx(text)[1][0]["path"], "b/one.md")


class CtxLoadSave(CtxFixtureMixin, unittest.TestCase):
    def test_save_renumbers_stable_partition_and_roundtrips(self):
        ctx = {"slug": "s", "description": "d", "entries": [
            E(None, "nachschlag", "b/two.md", "n1"),
            E(7, "pflicht", "b/one.md", "p1"),
            E(None, "bogus", "ext/three.md", "n2"),
            E(3, "pflicht", "~/notes/out.md", "p2")]}
        okf_catalogue.save_ctx(self.root, ctx)
        got = okf_catalogue.load_ctx(self.root, "s")
        self.assertEqual(got["slug"], "s")
        self.assertEqual(got["description"], "d")
        self.assertEqual(got["problems"], [])
        self.assertEqual(got["entries"], [
            E(1, "pflicht", "b/one.md", "p1"), E(2, "pflicht", "~/notes/out.md", "p2"),
            E(None, "nachschlag", "b/two.md", "n1"), E(None, "bogus", "ext/three.md", "n2")])

    def test_save_ignores_problems_key(self):
        ctx = {"slug": "s", "description": "d", "entries": [E(1, "pflicht", "b/one.md")],
               "problems": ["row 9: junk"]}
        okf_catalogue.save_ctx(self.root, ctx)
        self.assertNotIn("junk", okf_catalogue.read_file(okf_catalogue.ctx_file(self.root, "s")))

    def test_save_creates_index_skeleton_and_refreshes_index(self):
        okf_catalogue.save_ctx(self.root, {"slug": "s", "description": "my desc", "entries": []})
        idx = okf_catalogue.read_file(os.path.join(self.root, "_ctx", "index.md"))
        self.assertTrue(idx.startswith(
            "# Context bundles\n\nCurated, ordered reading lists per topic — one file per ctx slug, "
            "managed by `okf ctx`.\n\n## Contents\n\n" + okf_catalogue.MARK_START + "\n"))
        self.assertIn("my desc", idx)
        self.assertIn("(/_ctx/s.md)", idx)

    def test_save_keeps_existing_index_text(self):
        self._w("_ctx/index.md", "# Mine\n\nHand written.\n\n" + okf_catalogue.MARK_START + "\n" + okf_catalogue.MARK_END + "\n")
        okf_catalogue.save_ctx(self.root, {"slug": "s", "description": "d", "entries": []})
        idx = okf_catalogue.read_file(os.path.join(self.root, "_ctx", "index.md"))
        self.assertTrue(idx.startswith("# Mine\n\nHand written.\n"))
        self.assertIn("(/_ctx/s.md)", idx)

    def test_load_missing_slug_is_not_found_with_message(self):
        with self.assertRaises(OkfError) as cm:
            okf_catalogue.load_ctx(self.root, "nope")
        self.assertEqual((cm.exception.kind, cm.exception.message),
                         ("not_found", "ctx: unknown slug: nope"))

    def test_load_reports_parse_problems(self):
        self._w("_ctx/s.md", "---\ntype: Context\ndescription: d\n---\n\n# s\n")
        self.assertEqual(okf_catalogue.load_ctx(self.root, "s")["problems"],
                         ['no table with header "pos | mode | path | comment"'])

    def test_sc02_list_type_context_shows_saved_ctx(self):
        okf_catalogue.save_ctx(self.root, {"slug": "s", "description": "d", "entries": []})
        r = self._cli("list", "--type", "Context")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("_ctx/s", r.stdout)


class CtxNormalize(CtxFixtureMixin, unittest.TestCase):
    def n(self, raw, must_exist=True):
        with self._home():
            return okf_catalogue.ctx_normalize_path(self.root, raw, must_exist)

    def test_catalogue_forms(self):
        for raw in ("b/one.md", "b/one", "/b/one.md", "/b/one", "  b/../b/one  ", "./b/one"):
            self.assertEqual(self.n(raw), "b/one.md", raw)

    def test_leading_slash_falls_back_to_filesystem(self):
        p = os.path.join(self.home, "notes", "out.md")
        self.assertEqual(self.n(p), "~/notes/out.md")

    def test_absolute_inside_root_becomes_relative(self):
        self.assertEqual(self.n(os.path.join(self.root, "b", "one.md")), "b/one.md")

    def test_symlinked_bundle_realpath_maps_back(self):
        self.assertEqual(self.n(os.path.join(self.ext, "three.md")), "ext/three.md")
        self.assertEqual(self.n("ext/three.md"), "ext/three.md")

    def test_home_forms(self):
        self.assertEqual(self.n("~/notes/out.md"), "~/notes/out.md")

    def test_outside_home_stays_absolute(self):
        other = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, other, True)
        p = os.path.join(other, "x.md")
        open(p, "w").close()
        self.assertEqual(self.n(p), os.path.abspath(p))

    def test_relative_existing_cwd_file_is_filesystem_path(self):
        cwd = os.getcwd()
        os.chdir(os.path.join(self.home, "notes"))
        self.addCleanup(os.chdir, cwd)
        self.assertEqual(self.n("out.md"), "~/notes/out.md")

    def test_dotdot_escape_is_filesystem(self):
        rel = os.path.relpath(os.path.join(self.ext, "three.md"), self.root)
        self.assertTrue(rel.startswith(".."))
        self.assertEqual(self.n(rel), "ext/three.md")

    def test_missing_file_none_unless_must_exist_false(self):
        self.assertIsNone(self.n("b/nope.md"))
        self.assertIsNone(self.n("~/nope.md"))
        self.assertEqual(self.n("b/nope.md", must_exist=False), "b/nope.md")
        self.assertEqual(self.n("~/nope.md", must_exist=False), "~/nope.md")


class CtxEntryAbspathMemberships(CtxFixtureMixin, unittest.TestCase):
    def test_entry_abspath(self):
        with self._home():
            self.assertEqual(okf_catalogue.ctx_entry_abspath(self.root, "~/notes/out.md"),
                             os.path.join(self.home, "notes", "out.md"))
        self.assertEqual(okf_catalogue.ctx_entry_abspath(self.root, "/abs/p.md"), "/abs/p.md")
        self.assertEqual(okf_catalogue.ctx_entry_abspath(self.root, "b/one.md"),
                         os.path.join(self.root, "b", "one.md"))

    def test_memberships(self):
        okf_catalogue.save_ctx(self.root, {"slug": "a", "description": "d", "entries": [E(1, "pflicht", "b/one.md", "ca")]})
        okf_catalogue.save_ctx(self.root, {"slug": "b-ctx", "description": "d", "entries": [
            E(None, "nachschlag", "b/one.md", "cb"), E(None, "nachschlag", "b/two.md", "x")]})
        with self._home():
            got = okf_catalogue.ctx_memberships(self.root, "/b/one")
            self.assertEqual(got, [("a", E(1, "pflicht", "b/one.md", "ca")),
                                   ("b-ctx", E(None, "nachschlag", "b/one.md", "cb"))])
            self.assertEqual(okf_catalogue.ctx_memberships(self.root, "b/gone.md"), [])


class CtxSaveEffects(CtxFixtureMixin, unittest.TestCase):
    def _save_full(self):
        okf_catalogue.save_ctx(self.root, {"slug": "s", "description": "d", "entries": [
            E(1, "pflicht", "b/one.md", "c1"), E(2, "pflicht", "ext/three.md", "c2"),
            E(None, "nachschlag", "~/notes/out.md", "c3")]})

    def test_saved_file_has_link_and_code_span_forms(self):
        self._save_full()
        text = okf_catalogue.read_file(okf_catalogue.ctx_file(self.root, "s"))
        self.assertIn("| 1 | pflicht | [one](/b/one.md) | c1 |", text)
        self.assertIn("| 2 | pflicht | [three](/ext/three.md) | c2 |", text)
        self.assertIn("| - | nachschlag | `~/notes/out.md` | c3 |", text)

    def test_check_reports_nothing_for_ctx(self):
        self._save_full()
        errors, warnings = _scan(self.root, None)
        names = ("kc/asset/entry-file-description", "kc/asset/placement", "kc/type/registered")
        bad = [x for x in errors + warnings if x[0] in names and "_ctx" in repr(x)]
        self.assertEqual(bad, [])

    def test_save_leaves_members_byte_identical(self):
        paths = [os.path.join(self.root, "b", "one.md"), os.path.join(self.ext, "three.md"),
                 os.path.join(self.home, "notes", "out.md")]
        before = [okf_catalogue.read_file(p) for p in paths]
        self._save_full()
        self.assertEqual([okf_catalogue.read_file(p) for p in paths], before)


class CtxFindings(CtxFixtureMixin, unittest.TestCase):
    """ctx_findings, the `kc/ctx/*` sub-rules of run_checks and `ctx check`."""

    def _ctx(self, slug="demo", entries=None, desc="Demo", typ="Context"):
        if entries is None:
            entries = [E(1, "pflicht", "b/one.md"), E(2, "pflicht", "b/two.md")]
        text = okf_catalogue.render_ctx(slug, desc, entries).replace("type: Context", "type: " + typ, 1)
        self._w("_ctx/{}.md".format(slug), text)
        return os.path.join(self.root, "_ctx", slug + ".md")

    def _f(self, ap, **kw):
        return okf_catalogue.ctx_findings(self.root, ap, **kw)

    def _run_checks_ctx(self):
        errs, warns = _scan(self.root, None)
        return ([(n, m) for n, _, m in errs if n.startswith("kc/ctx/")],
                [(n, m) for n, _, m in warns if n.startswith("kc/ctx/")])

    def _sc01(self):
        return self._ctx(entries=[E(1, "pflicht", "b/one.md"), E(3, "pflicht", "b/two.md"),
                                  E(None, "nachschlag", "b/one.md"),
                                  E(None, "nachschlag", "b/gone.md")])

    SC01 = [("kc/ctx/required-positions", "required positions are not 1..2 in table order: 1, 3"),
            ("kc/ctx/duplicate-entry", "duplicate entry: b/one.md"),
            ("kc/ctx/dead-entry", "dead entry: b/gone.md")]

    def test_sc01_check_and_ctx_check_three_errors(self):
        ap = self._sc01()
        self.assertEqual(self._f(ap), self.SC01)
        self.assertEqual(self._run_checks_ctx(), (self.SC01, []))
        r = self._cli("ctx", "check")
        self.assertEqual((r.returncode, r.stderr), (EXIT_CODES["non_conformant"], ""))
        self.assertEqual(r.stdout.splitlines(), [
            "ERROR    {:<20} _ctx/demo.md  ({})".format(rule, m) for rule, m in self.SC01]
            + ["3 VIOLATIONS"])

    def test_sc02_clean_ctx(self):
        ap = self._ctx()
        self.assertEqual(self._f(ap), [])
        self.assertEqual(self._run_checks_ctx(), ([], []))
        for argv in (("ctx", "check"), ("ctx", "check", "demo")):
            r = self._cli(*argv)
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "OK — 0 violations\n", ""))

    def test_wrong_type(self):
        self.assertEqual(self._f(self._ctx(typ="Concept")),
                         [("kc/ctx/type", 'type is "Concept", expected "Context"')])

    def test_invalid_slug(self):
        ap = self._ctx(slug="Bad_Slug")
        self.assertEqual(self._f(ap), [
            ("kc/ctx/slug", 'slug "Bad_Slug" invalid: use lowercase letters, digits and hyphens')])

    def test_parse_problems_all_report_row_format(self):
        demo = os.path.join(self.root, "_ctx", "demo.md")
        self._w("_ctx/demo.md", "---\ntype: Context\ndescription: \"d\"\n---\n\n# demo\n\nno table\n")
        self.assertEqual(self._f(demo), [
            ("kc/ctx/row-format", 'no table with header "pos | mode | path | comment"')])
        self._w("_ctx/demo.md", "---\ntype: Context\ndescription: \"d\"\n---\n\n# demo\n\n"
                                "| pos | mode | path | comment |\n|---|---|---|---|\n"
                                "| 1 | pflicht | [one](/b/one.md) |\n"
                                "| x | pflicht | [one](/b/one.md) | c |\n"
                                "| 2 | pflicht | plain | c |\n")
        self.assertEqual(self._f(demo), [
            ("kc/ctx/row-format", "row 1: expected 4 cells, found 3"),
            ("kc/ctx/row-format", 'row 2: pos "x" is neither an integer nor -'),
            ("kc/ctx/row-format",
             "row 3: path cell is neither a catalogue link nor a code span")])

    def test_unknown_mode_with_and_without_pos(self):
        ap = self._ctx(entries=[E(1, "pflicht", "b/one.md"), E(2, "maybe", "b/two.md"),
                                E(None, "wat", "ext/three.md")])
        self.assertEqual(self._f(ap), [
            ("kc/ctx/mode", 'pos 2: mode "maybe" is not pflicht or nachschlag'),
            ("kc/ctx/mode", 'pos -: mode "wat" is not pflicht or nachschlag')])

    def test_required_positions_not_1_to_n(self):
        ap = self._ctx(entries=[E(2, "pflicht", "b/one.md"), E(1, "pflicht", "b/two.md")])
        self.assertEqual(self._f(ap), [
            ("kc/ctx/required-positions", "required positions are not 1..2 in table order: 2, 1")])
        ap = self._ctx(entries=[E(1, "pflicht", "b/one.md"), E(None, "pflicht", "b/two.md")])
        self.assertEqual(self._f(ap), [
            ("kc/ctx/required-positions", "required positions are not 1..2 in table order: 1, -")])

    def test_reference_entry_with_pos(self):
        ap = self._ctx(entries=[E(1, "pflicht", "b/one.md"), E(5, "nachschlag", "b/two.md")])
        self.assertEqual(self._f(ap), [
            ("kc/ctx/reference-position", "reference entry carries pos 5 (use -)")])

    def test_dead_entry_only(self):
        ap = self._ctx(entries=[E(1, "pflicht", "b/gone.md")])
        self.assertEqual(self._f(ap), [("kc/ctx/dead-entry", "dead entry: b/gone.md")])

    def test_duplicate_entry_only(self):
        ap = self._ctx(entries=[E(1, "pflicht", "b/one.md"), E(None, "nachschlag", "b/one.md")])
        self.assertEqual(self._f(ap), [("kc/ctx/duplicate-entry", "duplicate entry: b/one.md")])

    def test_empty_description_is_warning_only(self):
        ap = self._ctx(desc="")
        self.assertEqual(self._f(ap), [("kc/ctx/empty-description", "empty description")])
        self.assertEqual(self._run_checks_ctx(),
                         ([], [("kc/ctx/empty-description", "empty description")]))

    def test_archive_entry_is_warning_only(self):
        self._w("_archive/b/old.md", "---\ntype: Concept\n---\n\n# Old\n")
        ap = self._ctx(entries=[E(1, "pflicht", "_archive/b/old.md")])
        self.assertEqual(self._f(ap), [
            ("kc/ctx/archived-entry", "entry under _archive/: _archive/b/old.md")])

    def test_stale_member_warns_only_with_flag(self):
        ap = self._ctx()
        os.utime(ap, (1000, 1000))
        os.utime(os.path.join(self.root, "b", "one.md"), (2000, 2000))
        os.utime(os.path.join(self.root, "b", "two.md"), (500, 500))
        self.assertEqual(self._f(ap), [])
        self.assertEqual(self._f(ap, stale=True), [
            ("kc/ctx/stale-entry", "stale: b/one.md changed after this ctx file")])

    def test_stale_skips_dead_members(self):
        ap = self._ctx(entries=[E(1, "pflicht", "b/gone.md")])
        self.assertEqual(self._f(ap, stale=True), [("kc/ctx/dead-entry", "dead entry: b/gone.md")])

    def test_reserved_index_of_ctx_bundle_is_skipped(self):
        okf_catalogue.save_ctx(self.root, {"slug": "demo", "description": "D", "entries": []})
        self.assertTrue(os.path.isfile(os.path.join(self.root, "_ctx", "index.md")))
        self.assertEqual(self._run_checks_ctx(), ([], []))

    def test_only_ctx_bundle_files_are_checked(self):
        # a Concept file elsewhere with a ctx-looking table is not a ctx
        self._w("b/three.md", "---\ntype: Concept\n---\n\n| pos | mode | path | comment |\n"
                              "|---|---|---|---|\n| 1 | pflicht | [x](/b/nope.md) | |\n")
        self.assertEqual(self._run_checks_ctx(), ([], []))

    def test_ctx_check_one_slug_unknown_json_stale_warning_exit(self):
        self._ctx(slug="bad", entries=[E(1, "pflicht", "b/gone.md")])
        self._ctx(slug="good", desc="")
        r = self._cli("ctx", "check", "good")
        self.assertEqual((r.returncode, r.stdout),
                         (0, "WARNING  kc/ctx/empty-description _ctx/good.md  (empty description)\n"
                             "OK — 0 violations\n"))
        r = self._cli("ctx", "check", "nope")
        self.assertEqual((r.returncode, r.stdout, r.stderr),
                         (EXIT_CODES["not_found"], "", "ctx: unknown slug: nope\n"))
        r = self._cli("ctx", "check", "--json")
        self.assertEqual((r.returncode, json.loads(r.stdout)["data"]), (EXIT_CODES["non_conformant"], {
            "findings": [
                {"rule": "kc/ctx/dead-entry", "severity": "error", "path": "_ctx/bad.md",
                 "message": "dead entry: b/gone.md"},
                {"rule": "kc/ctx/empty-description", "severity": "warning",
                 "path": "_ctx/good.md", "message": "empty description"}]}))
        ap = os.path.join(self.root, "_ctx", "good.md")
        os.utime(ap, (1000, 1000))
        os.utime(os.path.join(self.root, "b", "two.md"), (500, 500))
        r = self._cli("ctx", "check", "good", "--stale")
        self.assertEqual((r.returncode, r.stdout.splitlines()[:2]), (0, [
            "WARNING  kc/ctx/empty-description _ctx/good.md  (empty description)",
            "WARNING  kc/ctx/stale-entry   _ctx/good.md  (stale: b/one.md changed after this ctx file)"]))

    def test_ctx_findings_and_registry_name_the_same_rules(self):
        """Every ctx problem kind is reportable and every reported ID is registered:
        one fixture trips all kinds, so a ctx_findings ID missing from RULES (or a
        RULES ctx entry no problem can reach) fails here."""
        self._w("_archive/b/old.md", "---\ntype: Concept\n---\n\n# Old\n")
        self._w("_ctx/Bad_Slug.md",
                "---\ntype: Concept\ndescription: \"\"\n---\n\n# x\n\n"
                "| pos | mode | path | comment |\n|---|---|---|---|\n"
                "| 1 | pflicht | [one](/b/one.md) |\n"
                "| 3 | pflicht | [two](/b/two.md) | c |\n"
                "| - | wat | [two](/b/two.md) | c |\n"
                "| 5 | nachschlag | [one](/b/one.md) | c |\n"
                "| - | nachschlag | [gone](/b/gone.md) | c |\n"
                "| - | nachschlag | [old](/_archive/b/old.md) | c |\n")
        ap = os.path.join(self.root, "_ctx", "Bad_Slug.md")
        os.utime(ap, (1000, 1000))
        os.utime(os.path.join(self.root, "b", "one.md"), (2000, 2000))
        reported = {rule for rule, _ in self._f(ap, stale=True)}
        registered = {r.id for r in okf_check.RULES if r.id.startswith("kc/ctx/")}
        self.assertEqual(reported, registered)
        errs, warns = _scan(self.root, "_ctx")
        self.assertEqual({n for n, _, _ in errs + warns if n.startswith("kc/ctx/")},
                         registered - {"kc/ctx/stale-entry"})


if __name__ == "__main__":
    unittest.main()
