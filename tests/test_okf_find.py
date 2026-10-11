#!/usr/bin/env python3
"""Tests for cli/okf/find.py — the find command: filters across arms, lexical and semantic hand-over, fusion, degradation notes. Stdlib unittest, no deps.

Run: just test tests.test_okf_find -v
"""
import argparse
import contextlib
import io
import os
import shutil
import sqlite3
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
from okf import find as okf_find
from okf import find_filters as okf_find_filters
from okf import fts as okf_fts
from okf import parser as okf_parser
from okf import semantic as okf_semantic
from tests.okf_testkit import run_find


class FindFilterContract(unittest.TestCase):
    """I01 — --where constrains the ANSWER, not one arm of it.

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

    # (--where expression, baits that must not survive it)
    DIMENSIONS = [
        ("path ~ keep/inner/", ["keep/outer", "bait/cross"]),
        ("type = Concept", ["keep/inner/type-bait"]),
        ("tag = keeper", ["keep/inner/tag-bait"]),
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
        self._orig_embed = okf_semantic._embed_query_voyage
        okf_semantic._QUERY_VEC_CACHE.clear()
        # Every concept embeds to the same vector: which one the semantic arm
        # would rank first is irrelevant here, only which ones it may return.
        self._make_tagvec([
            ("k1", "keep/inner/wanted"), ("k2", "keep/inner/type-bait"),
            ("k3", "keep/inner/tag-bait"), ("k4", "keep/outer"),
            ("k5", "bait/cross"),
        ])
        okf_semantic._embed_query_voyage = lambda text: [1.0, 0.0]

    def tearDown(self):
        import shutil
        okf_semantic._embed_query_voyage = self._orig_embed
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
            query=query, limit=10, where=None,
            breakdown=False,
        )
        for k, v in kw.items():
            setattr(args, k, v)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), \
                contextlib.redirect_stderr(io.StringIO()):
            okf_find.cmd_find(self.tmp, args)
        return [l[len("path: "):] for l in buf.getvalue().splitlines()
                if l.startswith("path: ")]

    def _check_every_dimension(self, query, regime):
        for expression, baits in self.DIMENSIONS:
            with self.subTest(regime=regime, where=expression):
                paths = self._paths(query, where=expression)
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
        okf_semantic._embed_query_voyage = _unavailable

    def test_lexical_owned_ranking_honours_every_filter(self):
        okf_fts.build_fts_index(self.tmp)
        self._silence_semantic_arm()
        self._check_every_dimension(self.LITERAL, "lexical")

    def test_semantic_owned_ranking_honours_every_filter(self):
        okf_fts.build_fts_index(self.tmp)
        # Guard the regime itself: if a literal match crept in, the lexical
        # arm would own the ranking and this would silently retest the case
        # above instead of the one B01 broke.
        # OKFT-rx72: order among these three is not the point (all three
        # embed to the identical vector by construction, see setUp) — only
        # membership is. assertCountEqual (not assertEqual) keeps this from
        # re-pinning whatever tiebreak order the fix below happens to give.
        self.assertCountEqual(self._paths(self.PARAPHRASE, where="path ~ keep/inner/"),
                               [self.WANTED, "keep/inner/type-bait",
                                "keep/inner/tag-bait"])
        self._check_every_dimension(self.PARAPHRASE, "semantic")

    def test_substring_fallback_honours_every_filter(self):
        # no build_fts_index() — _rank_lexically degrades to the full scan
        self.assertFalse(os.path.isfile(okf_fts._fts_db_path(self.tmp)))
        self._silence_semantic_arm()
        self._check_every_dimension(self.LITERAL, "degraded")

    def test_scoped_substring_fallback_reports_the_real_path(self):
        """B04 — a hit's path must be the concept's true position below the
        root. The substring arm once built it from the BUNDLE name plus a cid
        relative to a narrowed SUBDIR, printing `keep/wanted` for a concept
        living at `keep/inner/wanted`: a path no `okf-cli read` can resolve.
        Unfiltered output is unaffected, which is what keeps the frozen eval
        baseline valid."""
        self.assertFalse(os.path.isfile(okf_fts._fts_db_path(self.tmp)))
        self._silence_semantic_arm()
        self.assertEqual(sorted(self._paths(self.LITERAL, where="path ~ keep/inner/")),
                         ["keep/inner/tag-bait", "keep/inner/type-bait",
                          "keep/inner/wanted"])


class FindFilterComposition(unittest.TestCase):
    """P8/8a (okf-cli-8uaf, FIL03/FIL04) — find composes keyword search with a
    --where expression: exact-match type and tag, path containment, and their
    combination."""

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
            query=query, limit=10, where=None,
            breakdown=False,
        )
        for k, v in kw.items():
            setattr(args, k, v)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            okf_find.cmd_find(self.tmp, args)
        return buf.getvalue()

    def test_no_filters_behavior_unchanged_all_three_hit(self):
        out = self._run()
        self.assertEqual(out.count("path: "), 3)

    def test_type_filter_excludes_other_types(self):
        out = self._run(where="type = Runbook")
        self.assertIn("path: correct/one", out)
        self.assertIn("path: wrong/three", out)
        self.assertNotIn("path: correct/two", out)

    def test_tag_filter_excludes_non_matching_tag(self):
        out = self._run(where="tag = beta")
        self.assertIn("path: correct/two", out)
        self.assertNotIn("path: correct/one", out)
        self.assertNotIn("path: wrong/three", out)

    def test_scope_filter_excludes_other_bundle(self):
        out = self._run(where="path ~ correct/")
        self.assertIn("path: correct/one", out)
        self.assertIn("path: correct/two", out)
        self.assertNotIn("path: wrong/three", out)

    def test_composed_filters_type_tag_scope(self):
        out = self._run(where="type = Runbook and tag = alpha and path ~ correct/")
        self.assertIn("path: correct/one", out)
        self.assertNotIn("path: correct/two", out)
        self.assertNotIn("path: wrong/three", out)


class FindIncludeArchive(unittest.TestCase):
    """R-08/R-09/R-10 (okf-cli-pn72) — the archive as a part of the expression:
    hidden by default, reached by naming `archived`, path-aware.

    build_fts_index() indexes _archive/ for real since R-11 (okf-cli-fu7o)
    landed, so the fixture files below are indexed by the ordinary
    build_fts_index(self.tmp) call — no manual docs-table insert needed or
    wanted (a manual insert alongside the real one would just duplicate the
    row); this class stays about the FILTER, R-11's own leaf tests the
    build."""

    LITERAL = "zqxarch"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        body = "{} appears in every fixture body.\n".format(self.LITERAL)
        self._w("bundle-a/active.md", "Concept", "Active", ["k"], body)
        self._w("_archive/bundle-a/hidden.md", "Concept", "Hidden", ["k"],
                body)
        self._w("_archive/bundle-b/other-hidden.md", "Concept",
                "Other Hidden", ["k"], body)
        # AC4's regression target: a bundle whose name literally starts with
        # "archive" preceded by an ordinary character must not be caught by
        # an unescaped `_archive/%` LIKE pattern (`_` is a 1-char wildcard).
        self._w("xarchive/visible.md", "Concept", "Visible", ["k"], body)
        okf_fts.build_fts_index(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _w(self, rel, typ, title, tags, body):
        ap = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(
                "---\ntype: {}\ntitle: {}\ntags: [{}]\ndescription: d\n---\n"
                "# {}\n\n{}".format(typ, title, ", ".join(tags), title, body)
            )

    def _paths(self, query, **kw):
        import io, contextlib, types
        args = types.SimpleNamespace(
            query=query, limit=10, where=None,
            breakdown=False,
        )
        for k, v in kw.items():
            setattr(args, k, v)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), \
                contextlib.redirect_stderr(io.StringIO()):
            okf_find.cmd_find(self.tmp, args)
        return [l[len("path: "):] for l in buf.getvalue().splitlines()
                if l.startswith("path: ")]

    def test_sc01_default_excludes_archived_concept_present_in_index(self):
        paths = self._paths(self.LITERAL)
        self.assertIn("bundle-a/active", paths)
        self.assertNotIn("_archive/bundle-a/hidden", paths)
        self.assertNotIn("_archive/bundle-b/other-hidden", paths)

    def test_sc02_archived_expression_returns_it_under_its_archive_path(self):
        paths = self._paths(self.LITERAL, where="archived in (true, false)")
        self.assertIn("_archive/bundle-a/hidden", paths)

    def test_sc03_scoped_include_archive_reaches_only_that_bundle(self):
        paths = self._paths(self.LITERAL,
                            where="path ~ bundle-a/ and archived in (true, false)")
        self.assertIn("_archive/bundle-a/hidden", paths)
        self.assertNotIn("_archive/bundle-b/other-hidden", paths)

    def test_sc04_bundle_named_xarchive_stays_visible_without_the_flag(self):
        paths = self._paths(self.LITERAL)
        self.assertIn("xarchive/visible", paths)


class FindScopeLikeEscaping(unittest.TestCase):
    """okf-cli-pn72 review B01 — a `path ~` value is bound into the SQL
    push-down, and LIKE's `_`/`%` are single-char/any-sequence wildcards
    unless escaped, so an unescaped value leaks matches from a similarly-named
    foreign bundle — the exact I01/B01 divergence class FindFilters exists to
    prevent, this time inside one arm's own SQL rather than between arms. The
    Python-side arm compares literally, so the SQL arm has to as well."""

    LITERAL = "zqxesc"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        body = "{} appears in every fixture body.\n".format(self.LITERAL)
        # underscore leak vector: unescaped `_` in a LIKE pattern matches
        # ANY single character, so `path ~ my_bundle/` would also match
        # "myXbundle" (X standing in for the wildcard slot).
        self._w("my_bundle/active.md", "Concept", "Active", ["k"], body)
        self._w("myXbundle/leak.md", "Concept", "Leak", ["k"], body)
        self._w("_archive/my_bundle/hidden.md", "Concept", "Hidden", ["k"],
                body)
        self._w("_archive/myXbundle/hidden.md", "Concept", "Archived Leak",
                ["k"], body)
        # percent leak vector: unescaped `%` matches ANY sequence, so
        # `path ~ 'c%d/'` would also match "cZZd".
        self._w("c%d/active.md", "Concept", "Percent Active", ["k"], body)
        self._w("cZZd/leak.md", "Concept", "Percent Leak", ["k"], body)
        # the default archive exclusion binds `_archive/` as a LIKE pattern:
        # its own leading `_` is a single-char wildcard, so unescaped it would
        # also hide a top-level bundle named "Xarchive" (any single character
        # followed by "archive"). "Xarchive" is an ordinary bundle (no leading
        # `_`), so build_fts_index() indexes it on its own, same as the
        # `_archive/...` fixtures above since R-11 (okf-cli-fu7o).
        self._w("Xarchive/my_bundle/hidden2.md", "Concept",
                "Prefix Leak", ["k"], body)
        okf_fts.build_fts_index(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _w(self, rel, typ, title, tags, body):
        ap = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(
                "---\ntype: {}\ntitle: {}\ntags: [{}]\ndescription: d\n---\n"
                "# {}\n\n{}".format(typ, title, ", ".join(tags), title, body)
            )

    def _paths(self, query, **kw):
        import io, contextlib, types
        args = types.SimpleNamespace(
            query=query, limit=10, where=None,
            breakdown=False,
        )
        for k, v in kw.items():
            setattr(args, k, v)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), \
                contextlib.redirect_stderr(io.StringIO()):
            okf_find.cmd_find(self.tmp, args)
        return [l[len("path: "):] for l in buf.getvalue().splitlines()
                if l.startswith("path: ")]

    def test_underscore_path_without_archived_excludes_lookalike(self):
        """Covers the active-catalogue branch of the push-down."""
        paths = self._paths(self.LITERAL, where="path ~ my_bundle/")
        self.assertIn("my_bundle/active", paths)
        self.assertNotIn("myXbundle/leak", paths)

    def test_underscore_path_with_archived_excludes_lookalike(self):
        """Covers the archived form (R-09/AC3)."""
        paths = self._paths(self.LITERAL,
                            where="path ~ my_bundle/ and archived in (true, false)")
        self.assertIn("my_bundle/active", paths)
        self.assertIn("_archive/my_bundle/hidden", paths)
        self.assertNotIn("myXbundle/leak", paths)
        self.assertNotIn("_archive/myXbundle/hidden", paths)

    def test_percent_path_excludes_lookalike_bundle(self):
        paths = self._paths(self.LITERAL, where="path ~ 'c%d/'")
        self.assertIn("c%d/active", paths)
        self.assertNotIn("cZZd/leak", paths)

    def test_archive_prefix_itself_unescaped_does_not_hide_a_prefix_lookalike(self):
        """Review round 3, B01 (rest): the default exclusion's own `_archive/`
        pattern has a leading `_` that, unescaped, would hide a top-level dir
        named e.g. "Xarchive" from every answer."""
        for expression in (None, "type = Concept", "path ~ my_bundle/"):
            with self.subTest(where=expression):
                self.assertIn("Xarchive/my_bundle/hidden2",
                              self._paths(self.LITERAL, where=expression))
        self.assertNotIn("_archive/my_bundle/hidden", self._paths(self.LITERAL))


class SubstringRankingArchive(unittest.TestCase):
    """R-12/AC2-AC4 (okf-cli-iwx4) — the substring fallback (no FTS index)
    reaches the archive the same way `list` does, through resolve_scopes(),
    and matches_loaded() keeps discriminating every hit the widened
    traversal now surfaces (AC4 — the I01 regression guard: a changed
    traversal shape must not silently drop the per-hit predicate)."""

    LITERAL = "zqxsubarch"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        body = "{} appears in every fixture body.\n".format(self.LITERAL)
        self._w("bundle-a/active.md", "Runbook", "Active", body)
        self._w("_archive/bundle-a/hidden.md", "Runbook", "Hidden", body)
        self._w("_archive/bundle-b/other.md", "Concept", "Other", body)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _w(self, rel, typ, title, body):
        ap = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write("---\ntype: {}\ntitle: {}\ndescription: d\ntags: []\n"
                    "---\n# {}\n\n{}".format(typ, title, title, body))

    def _paths(self, **kw):
        out = run_find(self.tmp, self.LITERAL, **kw)
        return [l[len("path: "):] for l in out.splitlines()
                if l.startswith("path: ")]

    def test_sc01_default_excludes_archived_concept(self):
        paths = self._paths()
        self.assertIn("bundle-a/active", paths)
        self.assertNotIn("_archive/bundle-a/hidden", paths)
        self.assertNotIn("_archive/bundle-b/other", paths)

    def test_ac2_ac3_flag_reaches_archive_under_its_true_path(self):
        paths = self._paths(where="archived in (true, false)")
        self.assertIn("_archive/bundle-a/hidden", paths)
        self.assertIn("_archive/bundle-b/other", paths)

    def test_ac4_matches_loaded_still_discriminates_every_hit(self):
        paths = self._paths(where="type = Runbook and archived in (true, false)")
        self.assertIn("bundle-a/active", paths)
        self.assertIn("_archive/bundle-a/hidden", paths)
        self.assertNotIn("_archive/bundle-b/other", paths)  # type Concept


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
            query="zqxbrk", limit=10, where=None,
            breakdown=breakdown,
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            okf_find.cmd_find(self.tmp, args)
        return buf.getvalue()

    def test_breakdown_lists_contributing_fields(self):
        out = self._run(breakdown=True)
        self.assertIn("contrib: ", out)
        self.assertIn("title=[zqxbrk]", out)
        self.assertIn("tags=[zqxbrk]", out)
        self.assertNotIn("body=[zqxbrk]", out)  # term not in body prose
        # D01 (OKFT-3rb6) — the raw lexical score moved into this block.
        self.assertIn("score: 5/6", out)

    def test_default_output_unchanged_without_breakdown(self):
        out_flag_false = self._run(breakdown=False)
        self.assertNotIn("contrib:", out_flag_false)
        self.assertNotIn("score:", out_flag_false)
        # F04 (post-review) — SC-002 says "byte-identical to today"; pin the
        # FULL exact output, not just the absence of a "contrib:" substring
        # (a weaker check could miss e.g. a stray blank line or reordering).
        # The `provenance:` line joined this block with Modus-B B01: it is
        # attribution, present on every hit, and stays independent of the
        # opt-in `--score-breakdown` detail this test guards. D01 (OKFT-3rb6)
        # replaced the raw `score: a/b` headline with `rank: N` — the one
        # scale comparable across a mixed-arm list — and moved the raw score
        # into --breakdown (see test_breakdown_lists_contributing_fields).
        self.assertEqual(
            out_flag_false,
            "------\n"
            "rank: 1\n"
            "title: Zqxbrk One\n"
            "type: Runbook\n"
            "path: b/one\n"
            "description: d\n"
            "body-snippet: # Untitled Heading body prose only.…\n"
            "provenance: lexical\n"
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
        out, lex_owned = okf_find.fuse_conditional(lex, sem, 10)
        self.assertTrue(lex_owned)
        self.assertEqual([h["path"] for h in out], ["a", "b", "c"])

    def test_ambiguous_lexical_hands_the_ranking_to_semantic(self):
        lex = [_h("a", 100, "lexical"), _h("b", 95, "lexical")]
        sem = [_h("c", 60, "semantic")]
        out, lex_owned = okf_find.fuse_conditional(lex, sem, 10)
        self.assertFalse(lex_owned)
        self.assertEqual([h["path"] for h in out], ["c", "a", "b"])

    def test_single_lexical_hit_is_treated_as_confident(self):
        lex = [_h("a", 100, "lexical")]
        sem = [_h("c", 90, "semantic")]
        out, lex_owned = okf_find.fuse_conditional(lex, sem, 10)
        self.assertTrue(lex_owned)
        self.assertEqual([h["path"] for h in out], ["a", "c"])

    def test_empty_lexical_hands_over(self):
        out, lex_owned = okf_find.fuse_conditional([], [_h("c", 60, "semantic")], 10)
        self.assertFalse(lex_owned)
        self.assertEqual([h["path"] for h in out], ["c"])

    def test_duplicate_paths_keep_the_owning_arms_entry(self):
        lex = [_h("a", 100, "lexical"), _h("b", 95, "lexical")]
        sem = [_h("b", 70, "semantic"), _h("c", 60, "semantic")]
        out, lex_owned = okf_find.fuse_conditional(lex, sem, 10)
        self.assertFalse(lex_owned)
        self.assertEqual([h["path"] for h in out], ["b", "c", "a"])
        self.assertEqual(out[0]["provenance"], "semantic")

    def test_limit_is_respected(self):
        lex = [_h("a", 100, "lexical")]
        sem = [_h("c", 90, "semantic"), _h("d", 80, "semantic")]
        out, _lex_owned = okf_find.fuse_conditional(lex, sem, 2)
        self.assertEqual([h["path"] for h in out], ["a", "c"])

    def test_semantic_never_precedes_a_confident_lexical_top1(self):
        lex = [_h("a", 30, "lexical"), _h("b", 5, "lexical")]
        sem = [_h("c", 99, "semantic")]
        out, lex_owned = okf_find.fuse_conditional(lex, sem, 10)
        self.assertTrue(lex_owned)
        self.assertEqual(out[0]["path"], "a")

    def test_margin_band_matches_the_measured_rule(self):
        """The measured rule is top1 >= 1.5*top2 (eval/hybrid_eval.py:151).
        The pre-plan arithmetic was top1 >= 2*top2. 100 vs 60 sits inside the
        band where the two disagree: the measured rule says the lexical arm
        is confident, the old one says it is not. Pin the measured one."""
        lex = [_h("a", 100, "lexical"), _h("b", 60, "lexical")]
        sem = [_h("c", 90, "semantic")]
        out, lex_owned = okf_find.fuse_conditional(lex, sem, 10)
        self.assertTrue(lex_owned)
        self.assertEqual([h["path"] for h in out], ["a", "b", "c"])

    def test_just_below_the_band_hands_over(self):
        lex = [_h("a", 100, "lexical"), _h("b", 68, "lexical")]
        sem = [_h("c", 90, "semantic")]
        _out, lex_owned = okf_find.fuse_conditional(lex, sem, 10)
        self.assertFalse(lex_owned)


class NoiseRatioIsGone(unittest.TestCase):
    """The absolute noise floor was a crutch for the blend rule; conditional
    handover subsumes it. Leaving it in place would mean two competing gates."""

    def test_constant_removed(self):
        self.assertFalse(hasattr(okf_find, "SEMANTIC_NOISE_RATIO"))


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
        self._orig_embed = okf_semantic._embed_query_voyage
        self._orig_cosine = okf_semantic._cosine
        okf_semantic._QUERY_VEC_CACHE.clear()

    def tearDown(self):
        import shutil
        okf_semantic._embed_query_voyage = self._orig_embed
        okf_semantic._cosine = self._orig_cosine
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
            query=query, limit=10, where=None,
            breakdown=False,
        )
        for k, v in kw.items():
            setattr(args, k, v)
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            okf_find.cmd_find(self.tmp, args)
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
        okf_semantic._embed_query_voyage = _raise
        out, err = self._run("zzz-no-keyword-match-zzz")
        self.assertIn("(no matches", out)
        self.assertIn("semantic arm skipped", err)

    def test_zero_keyword_hit_is_rescued_with_provenance(self):
        self._make_tagvec([("k1", "b/near", [1.0, 0.0])])
        okf_semantic._embed_query_voyage = lambda text: [1.0, 0.0]
        out, err = self._run("zzz-no-keyword-match-zzz")
        self.assertIn("path: b/near", out)
        self.assertIn("provenance: semantic", out)

    def test_semantic_hit_score_line_uses_its_own_scale_not_a_fraction(self):
        """The printed score line must not read like the lexical arm's a/100
        fraction — a semantic hit's number is round(100 * cosine), a scale
        incomparable to BM25-relative-to-top, and printing it as 'a/100'
        invites exactly the cross-arm comparison D12 rejected (fuse_conditional
        hands over, it never blends by score). D01 (OKFT-3rb6) moved this raw
        value out of the default headline (now `rank: N`) into --breakdown,
        so the default output must carry neither scale at all, and the
        --breakdown output must still carry the semantic arm's own one."""
        self._make_tagvec([("k1", "b/near", [1.0, 0.0])])
        okf_semantic._embed_query_voyage = lambda text: [1.0, 0.0]
        out_default, _err = self._run("zzz-no-keyword-match-zzz")
        self.assertNotIn("score:", out_default)
        self.assertNotIn("cosine", out_default)
        out_breakdown, _err = self._run("zzz-no-keyword-match-zzz",
                                        breakdown=True)
        score_lines = [l for l in out_breakdown.splitlines()
                       if l.startswith("score: ")]
        self.assertEqual(len(score_lines), 1)
        self.assertTrue(score_lines[0].startswith("score: cosine "),
                        score_lines[0])
        self.assertNotIn("/100", score_lines[0])

    def test_strong_keyword_top_hit_is_never_overridden(self):
        # Backend guarded to raise if ever called — proves the semantic
        # pass does not even fire when the keyword top hit is strong.
        self._make_tagvec([("k1", "b/near", [1.0, 0.0])])

        def _must_not_be_called(_text):
            raise AssertionError("semantic backstop must not fire on a strong hit")
        okf_semantic._embed_query_voyage = _must_not_be_called
        out, err = self._run("zqxstrong")
        lines = out.splitlines()
        self.assertEqual(lines[4], "path: b/strong")  # Top-1
        self.assertNotIn("provenance: semantic", out)

    def test_lexical_hit_names_its_own_arm(self):
        """Modus-B B01: a consumer must not have to infer provenance from the
        ABSENCE of a marker. The `semantic arm owns this ranking` banner spans
        the whole list, so a lexical hit inside a semantic-owned list carried
        no attribution at all — in the live run the answering hit sat at rank 5
        with no provenance line while four semantic hits above it had one.
        Every result line names its arm."""
        self._make_tagvec([("k1", "b/near", [1.0, 0.0])])

        def _must_not_be_called(_text):
            raise AssertionError("semantic backstop must not fire on a strong hit")
        okf_semantic._embed_query_voyage = _must_not_be_called
        out, _err = self._run("zqxstrong")
        self.assertIn("provenance: lexical", out)
        self.assertEqual(out.count("path: "), out.count("provenance: "))

    def test_every_hit_of_a_mixed_list_names_its_arm(self):
        """The mixed case the banner actually obscures: one lexical hit and one
        semantic hit in the same list, each attributed on its own line."""
        self._w("b/noise.md", "Unrelated Note", [], "alpha once in passing.\n")
        self._make_tagvec([("k1", "b/far", [1.0, 0.0])])
        okf_semantic._embed_query_voyage = lambda text: [1.0, 0.0]
        out, _err = self._run("alpha")
        self.assertIn("provenance: lexical", out)
        self.assertIn("provenance: semantic", out)
        self.assertEqual(out.count("path: "), out.count("provenance: "))

    def test_mixed_arm_query_uses_one_rank_scale(self):
        """SC-001/D01 (OKFT-3rb6) — a result list that provably mixes both
        arms carries one comparable scale, `rank: N` (the 1-based list
        position), and NEITHER raw arm scale in the default output. Same
        fixture as test_every_hit_of_a_mixed_list_names_its_arm (proven
        mixed: b/far is semantic-only, b/noise and b/near are lexical
        substring hits, all three present in one list) so this is a proof
        over a genuinely mixed-arm result, not a single-arm one."""
        self._w("b/noise.md", "Unrelated Note", [], "alpha once in passing.\n")
        self._make_tagvec([("k1", "b/far", [1.0, 0.0])])
        okf_semantic._embed_query_voyage = lambda text: [1.0, 0.0]
        out, _err = self._run("alpha")
        self.assertIn("provenance: lexical", out)
        self.assertIn("provenance: semantic", out)
        self.assertNotIn("score:", out)
        self.assertNotIn("cosine", out)
        rank_lines = [l for l in out.splitlines() if l.startswith("rank: ")]
        self.assertEqual(rank_lines, ["rank: 1", "rank: 2", "rank: 3"])

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
        okf_semantic._embed_query_voyage = lambda text: [1.0, 0.0]
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
        okf_semantic._embed_query_voyage = lambda text: [1.0, 0.0]
        out, err = self._run("unmarked item lacking classification")
        self.assertIn("path: b/wanted", out)
        self.assertIn("provenance: semantic", out)

    def test_scope_confines_the_semantic_arm(self):
        """B01 — --where is a filter on the ANSWER, not on one arm. The
        lexical arm confines itself (SQL path predicate / resolve_scopes),
        so a scoped query used to return out-of-scope concepts only when
        the semantic arm owned the ranking: the user asked for
        home-lab-wiki/services and got agent-memory and qm-wiki hits."""
        self._w("other/leak.md", "Leaked Concept", [],
                "totally different content words only.\n")
        self._make_tagvec([("k1", "other/leak", [1.0, 0.0])])
        okf_semantic._embed_query_voyage = lambda text: [1.0, 0.0]
        out, err = self._run("zzz-no-keyword-match-zzz", where="path ~ b/")
        self.assertNotIn("path: other/leak", out)

    def test_type_filter_confines_the_semantic_arm(self):
        """B02 — same defect class as B01: `type` is applied to the lexical
        arm's SQL only, so a semantic-owned ranking returns the wrong type."""
        self._w("b/other-type.md", "Wrong Type", [],
                "totally different content words only.\n")
        ap = os.path.join(self.tmp, "b/other-type.md")
        with open(ap, encoding="utf-8") as f:
            txt = f.read()
        with open(ap, "w", encoding="utf-8") as f:
            f.write(txt.replace("type: Concept", "type: Pattern"))
        self._make_tagvec([("k1", "b/other-type", [1.0, 0.0])])
        okf_semantic._embed_query_voyage = lambda text: [1.0, 0.0]
        out, err = self._run("zzz-no-keyword-match-zzz", where="type = Concept")
        self.assertNotIn("path: b/other-type", out)

    def test_tag_filter_confines_the_semantic_arm(self):
        """B03 — same defect class as B01 for --tag."""
        self._w("b/untagged.md", "Untagged Concept", [],
                "totally different content words only.\n")
        self._make_tagvec([("k1", "b/untagged", [1.0, 0.0])])
        okf_semantic._embed_query_voyage = lambda text: [1.0, 0.0]
        out, err = self._run("zzz-no-keyword-match-zzz", where="tag = zqxstrong")
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
        okf_semantic._embed_query_voyage = lambda text: [1.0, 0.0]
        okf_semantic._cosine = lambda a, b: 0.7  # reviewer's exact repro value
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
        okf_fts.build_fts_index(self.tmp)
        self._make_tagvec([("k1", "b/ambc", [1.0, 0.0])])
        okf_semantic._embed_query_voyage = lambda text: [1.0, 0.0]
        # D01 (OKFT-3rb6) moved the raw lexical score this assertion needs
        # out of the default output into --breakdown; ask for it explicitly
        # rather than reading the (now rank-only) default block.
        out, err = self._run("zqxambig", breakdown=True)
        lines = out.splitlines()
        lex_top1, lex_top2 = None, None
        for i, l in enumerate(lines):
            if l == "path: b/amba":
                lex_top1 = int(lines[i + 4].split("score: ")[1].split("/")[0])
            if l == "path: b/ambb":
                lex_top2 = int(lines[i + 4].split("score: ")[1].split("/")[0])
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
        okf_semantic._embed_query_voyage = lambda text: [1.0, 0.0]
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
        okf_semantic._embed_query_voyage = lambda text: [1.0, 0.0]
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
        okf_semantic._embed_query_voyage = lambda text: [1.0, 0.0]
        orig_cosine = okf_semantic._cosine
        okf_semantic._cosine = lambda a, b: -orig_cosine(a, b)
        try:
            out, _err = self._run("zzz-no-keyword-match-zzz")
            paths = [line[len("path: "):] for line in out.splitlines()
                     if line.startswith("path: ")]
            with self.assertRaises(AssertionError):
                self.assertEqual(paths, ["b/near", "b/far"])
        finally:
            okf_semantic._cosine = orig_cosine

    def test_equal_cosine_scores_break_the_tie_by_path(self):
        """OKFT-rx72 — sorted(..., key=lambda x: -x[0]) alone leaves tied
        cosines in whatever order concept_emb's unordered SELECT returned
        them, which two separate runs are not guaranteed to agree on. `zzz`
        and `aaa` share the exact same vector as the query, so their cosine
        ties at 1.0; the path secondary key must place `b/aaa` first."""
        self._make_tagvec([
            ("k1", "b/zzz", [1.0, 0.0]),
            ("k2", "b/aaa", [1.0, 0.0]),
        ])
        okf_semantic._embed_query_voyage = lambda text: [1.0, 0.0]
        ranked = okf_semantic.semantic_ranking(self.tmp, "zzz-no-keyword-match-zzz", 10,
                                       okf_find_filters.FindFilters())
        self.assertEqual(ranked[0][0], ranked[1][0])
        self.assertEqual([p for _c, p in ranked], ["b/aaa", "b/zzz"])

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


class SemanticArmArchiveNote(unittest.TestCase):
    """R-13 (okf-cli-6dsl) — the embedding build (build_tagvec.py:174) stays
    on the active catalogue by design; `archived` in --where only widens the
    lexical/substring traversal (R-12) and cmd_list. An unannounced limit is
    a trap: a searcher who named `archived` and got an answer shaped by
    the semantic arm would read an empty archive slice as an absence, not as
    an arm that never looked. AC1's conjunction is the risk: the note fires
    only when the expression names `archived` AND the semantic arm actually
    contributed hits, not on the expression alone (PF-4: at most one note per
    invocation)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig_embed = okf_semantic._embed_query_voyage
        self._orig_cosine = okf_semantic._cosine
        okf_semantic._QUERY_VEC_CACHE.clear()

    def tearDown(self):
        import shutil
        okf_semantic._embed_query_voyage = self._orig_embed
        okf_semantic._cosine = self._orig_cosine
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _w(self, rel, title, body):
        ap = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(
                "---\ntype: Concept\ntitle: {}\ntags: []\ndescription: d\n---\n"
                "# Untitled\n\n{}".format(title, body)
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
                (key, path, "voyage-3-large", len(vec),
                 struct.pack("<{}f".format(len(vec)), *vec)),
            )
        conn.commit()
        conn.close()
        return db

    def _run(self, query, **kw):
        import io, contextlib, types
        args = types.SimpleNamespace(
            query=query, limit=10, where=None,
            breakdown=False,
        )
        for k, v in kw.items():
            setattr(args, k, v)
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            okf_find.cmd_find(self.tmp, args)
        return out_buf.getvalue(), err_buf.getvalue()

    def test_sc01_flag_set_and_semantic_hits_present_notes_once(self):
        """AC1/SC-01: flag set, semantic arm contributes -> exactly one note,
        naming the lexical arm as the flag's actual reach."""
        self._w("b/near.md", "Near Concept", "alpha beta near-body prose.\n")
        self._make_tagvec([("k1", "b/near", [1.0, 0.0])])
        okf_semantic._embed_query_voyage = lambda text: [1.0, 0.0]
        out, err = self._run("zzz-no-keyword-match-zzz", where="archived in (true, false)")
        self.assertIn("path: b/near", out)  # sanity: semantic arm contributed
        notes = [l for l in err.splitlines()
                 if "archive" in l.lower() and "lexical" in l.lower()]
        self.assertEqual(notes, [
            "note: `archived` in --where covers the lexical arm only; "
            "embeddings stay on the active catalogue"])

    def test_sc02_flag_not_set_writes_no_note(self):
        """AC2/SC-02: same query, no flag -> no such note at all."""
        self._w("b/near.md", "Near Concept", "alpha beta near-body prose.\n")
        self._make_tagvec([("k1", "b/near", [1.0, 0.0])])
        okf_semantic._embed_query_voyage = lambda text: [1.0, 0.0]
        out, err = self._run("zzz-no-keyword-match-zzz", where="type = Concept")
        self.assertIn("path: b/near", out)
        self.assertNotIn("covers the lexical arm only", err)

    def test_ac1_conjunction_flag_set_but_no_semantic_hits_writes_no_note(self):
        """AC1's conjunction: naming `archived` alone is not enough. No tagvec cache at
        all -> semantic arm is skipped, contributes zero hits, so the note
        must stay silent even though `archived` is named."""
        out, err = self._run("zzz-no-keyword-match-zzz", where="archived in (true, false)")
        self.assertIn("(no matches", out)
        self.assertNotIn("covers the lexical arm only", err)

    def test_ac3_note_appears_at_most_once_with_multiple_semantic_hits(self):
        """AC3: several semantic hits in one answer still yield one note."""
        self._w("b/near.md", "Near Concept", "alpha beta near-body prose.\n")
        self._w("b/far.md", "Far Concept", "alpha beta far-body prose.\n")
        self._make_tagvec([
            ("k1", "b/near", [1.0, 0.0]),
            ("k2", "b/far", [0.9, 0.1]),
        ])
        okf_semantic._embed_query_voyage = lambda text: [1.0, 0.0]
        out, err = self._run("zzz-no-keyword-match-zzz", where="archived in (true, false)")
        notes = [l for l in err.splitlines()
                 if "covers the lexical arm only" in l]
        self.assertEqual(len(notes), 1)


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
            out = run_find(root, "tunnel")
            self.assertIn("path: b/one", out)
            self.assertIn("rank: 1", out)
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
                query="tunnel", limit=10, where=None,
                breakdown=False,
            )
            out_buf, err_buf = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
                okf_find.cmd_find(root, args)
            lines = [l for l in err_buf.getvalue().splitlines() if l]
            self.assertEqual(len(lines), 2)
            self.assertIn("note:", lines[0])
            self.assertIn("lexical index absent", lines[0])
            self.assertIn("note:", lines[1])
            self.assertIn("semantic arm skipped", lines[1])
        finally:
            shutil.rmtree(root, ignore_errors=True)


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
        got = okf_find._zero_hit_suggestions(self.root, "tailscael")
        self.assertIn("tailscale", got)

    def test_unrelated_query_may_return_nothing(self):
        got = okf_find._zero_hit_suggestions(self.root, "zzzzqqqq")
        self.assertEqual(got, [])

    def test_output_names_the_suggestions(self):
        out = run_find(self.root, "tailscael")
        self.assertIn("(no matches for: tailscael)", out)
        self.assertIn("tailscale", out)

    def test_output_has_no_suggestion_line_when_no_tag_is_close(self):
        """AC-2 — IF no tag is close enough THEN plain no-match line, no
        suggestions. Integration-level counterpart to
        test_unrelated_query_may_return_nothing (which only proves the
        helper returns []); this proves cmd_find's zero-hit branch actually
        stays silent end-to-end and does not regress into always printing a
        (possibly empty) suggestion line."""
        out = run_find(self.root, "zzzzqqqq")
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
            query="tailscael", limit=10, where=None,
            breakdown=False,
        )
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            okf_find.cmd_find(self.root, args)
        err_lines = [l for l in err_buf.getvalue().splitlines() if l]
        self.assertEqual(len(err_lines), 2, err_lines)
        self.assertIn("lexical index absent", err_lines[0])
        self.assertIn("semantic arm skipped", err_lines[1])
        stdout = out_buf.getvalue()
        self.assertIn("(no matches for: tailscael)", stdout)
        self.assertIn("nearest registered tags: tailscale", stdout)
        self.assertIn("try: okf-cli find \"tailscale\"", stdout)


class FindSupersededByField(unittest.TestCase):
    """OKFT-gpcx — a hit carrying frontmatter `superseded_by` surfaces it in
    the printed hit block itself (not only under --breakdown); a hit without
    the field stays byte-identical to the pre-existing block shape."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_hit_without_superseded_by_is_byte_identical(self):
        os.makedirs(os.path.join(self.root, "b"))
        with open(os.path.join(self.root, "b", "one.md"), "w",
                  encoding="utf-8") as f:
            f.write("---\ntype: Runbook\ntitle: Tunnel\ndescription: d\n"
                    "tags: [net]\n---\nbody\n")
        with open(os.path.join(self.root, "b", "index.md"), "w",
                  encoding="utf-8") as f:
            f.write("# B\n")
        out = run_find(self.root, "tunnel")
        expected = (
            "------\n"
            "rank: 1\n"
            "title: Tunnel\n"
            "type: Runbook\n"
            "path: b/one\n"
            "description: d\n"
            "body-snippet: body…\n"
            "provenance: lexical\n"
            "------\n"
        )
        self.assertEqual(out, expected)
        self.assertNotIn("superseded_by", out)

    def test_hit_with_superseded_by_shows_the_relation(self):
        os.makedirs(os.path.join(self.root, "b"))
        with open(os.path.join(self.root, "b", "new.md"), "w",
                  encoding="utf-8") as f:
            f.write("---\ntype: Decision\ntitle: New\n---\n# New\n")
        with open(os.path.join(self.root, "b", "old.md"), "w",
                  encoding="utf-8") as f:
            f.write("---\ntype: Decision\ntitle: Tunnel decision\n"
                    "description: d\nsuperseded_by: /b/new.md\n---\nbody\n")
        with open(os.path.join(self.root, "b", "index.md"), "w",
                  encoding="utf-8") as f:
            f.write("# B\n")
        out = run_find(self.root, "tunnel")
        self.assertIn("type: Decision\nsuperseded_by: /b/new.md\npath: b/old",
                       out)


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
            query="UniqueTopicNeedle", limit=10, where=None,
            include_topics=True,
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
        parser = okf_parser.build_parser()
        self.assertTrue(parser.parse_args(["build-index", "--include-topics"]).include_topics)
        self.assertTrue(parser.parse_args(["find", "needle", "--include-topics"]).include_topics)
