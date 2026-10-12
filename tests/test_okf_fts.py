#!/usr/bin/env python3
"""Tests for cli/okf/fts.py — the FTS5 index, its BM25 ranking and the query tokenizer. unittest.

Run: just test tests.test_okf_fts -v
"""
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli")
if _HERE not in sys.path:  # cli/ holds the okf package
    sys.path.insert(0, _HERE)

from okf import catalogue as okf_catalogue
from okf import find_filters as okf_find_filters
from okf.find_filters import compile_where
from okf import fts as okf_fts
from okf import parser as okf_parser
from okf import parser_support as okf_parser_support


class TokenizeUnicode(unittest.TestCase):
    """B01 — the catalogue is German. Splitting on [^a-z0-9]+ tore every
    umlaut word in two ('qualitätsmanagement' -> 'qualit', 'tsmanagement'),
    which silently changed what the lexical arm searches for. The measured
    FTS arm tokenized on word characters (eval/fts_arm.py:56); the shipped
    one must match it or it is not the arm that was measured."""

    def test_umlaut_word_stays_one_token(self):
        self.assertEqual(okf_fts.tokenize("Qualitätsmanagement"),
                         ["qualitätsmanagement"])

    def test_sharp_s_stays_one_token(self):
        self.assertEqual(okf_fts.tokenize("Straßenbahn"), ["straßenbahn"])

    def test_punctuation_still_separates(self):
        self.assertEqual(okf_fts.tokenize("mockup, tailscale!"),
                         ["mockup", "tailscale"])

    def test_underscore_still_separates(self):
        self.assertEqual(okf_fts.tokenize("build_tagvec"), ["build", "tagvec"])

    def test_digits_survive(self):
        self.assertEqual(okf_fts.tokenize("bge-m3 2437"), ["bge", "m3", "2437"])

    def test_mixed_case_lowercased(self):
        self.assertEqual(okf_fts.tokenize("MixedCASE Wort"),
                         ["mixedcase", "wort"])

    def test_non_latin_script_stays_whole(self):
        """\\w is Unicode-aware, not just Latin-with-umlauts — a CJK term
        must survive as one token too, same as an umlaut word does."""
        self.assertEqual(okf_fts.tokenize("知識管理 system"),
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
        n, db = okf_fts.build_fts_index(self.root)
        self.assertEqual(n, 2)
        self.assertTrue(os.path.isfile(db))
        self.assertEqual(db, os.path.join(self.root, ".fts", "fts.sqlite"))

    def test_index_holds_path_type_and_tags(self):
        okf_fts.build_fts_index(self.root)
        conn = sqlite3.connect(okf_fts._fts_db_path(self.root))
        rows = dict(conn.execute("SELECT path, ctype FROM docs").fetchall())
        conn.close()
        self.assertEqual(rows, {"b/one": "Runbook", "b/two": "Konzept"})

    def test_rebuild_is_idempotent(self):
        okf_fts.build_fts_index(self.root)
        n, _db = okf_fts.build_fts_index(self.root)
        self.assertEqual(n, 2)
        conn = sqlite3.connect(okf_fts._fts_db_path(self.root))
        total = conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
        conn.close()
        self.assertEqual(total, 2)

    def test_fresh_index_is_not_stale(self):
        okf_fts.build_fts_index(self.root)
        conn = sqlite3.connect(okf_fts._fts_db_path(self.root))
        try:
            self.assertFalse(okf_fts._fts_index_stale(self.root, conn))
        finally:
            conn.close()

    def test_new_concept_makes_the_index_stale(self):
        okf_fts.build_fts_index(self.root)
        with open(os.path.join(self.root, "b", "three.md"), "w",
                  encoding="utf-8") as f:
            f.write("---\ntype: Konzept\ntitle: Three\ndescription: d\n"
                    "tags: []\n---\nbody\n")
        conn = sqlite3.connect(okf_fts._fts_db_path(self.root))
        try:
            self.assertTrue(okf_fts._fts_index_stale(self.root, conn))
        finally:
            conn.close()


class FtsIndexArchive(unittest.TestCase):
    """R-11 (okf-cli-fu7o) — the FTS index knows the archive, and its
    staleness check tracks active/archived as two separate counters rather
    than one sum. A sum would stay constant across `git mv` (mtime
    preserved), so an archive move would never surface as stale — the
    exact regression AC2/AC3 exist to close."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "b"))
        self._w("b/one.md", "Runbook", "One", "active body one.\n")
        self._w("_archive/b/two.md", "Konzept", "Two",
                "archived body two.\n")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _w(self, rel, typ, title, body):
        ap = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write("---\ntype: {}\ntitle: {}\ndescription: d\ntags: []\n"
                     "---\n{}".format(typ, title, body))

    def test_archived_concept_is_indexed_at_its_archive_path(self):
        """AC1 — build_fts_index() indexes `_archive/<bundle>/<cid>` under
        that exact path, not silently dropped by is_bundle_dir()."""
        okf_fts.build_fts_index(self.root)
        conn = sqlite3.connect(okf_fts._fts_db_path(self.root))
        rows = dict(conn.execute("SELECT path, ctype FROM docs").fetchall())
        conn.close()
        self.assertEqual(rows, {"b/one": "Runbook", "_archive/b/two": "Konzept"})

    def test_meta_records_separate_active_and_archived_counts(self):
        """AC2 — fts_meta carries two counters, not one sum."""
        okf_fts.build_fts_index(self.root)
        conn = sqlite3.connect(okf_fts._fts_db_path(self.root))
        meta = dict(conn.execute("SELECT k, v FROM fts_meta").fetchall())
        conn.close()
        self.assertEqual(meta["n_concepts"], "1")
        self.assertEqual(meta["n_archived"], "1")

    def test_sc02_fresh_build_with_archive_present_is_current(self):
        """SC-02 — immediately after a build, staleness reports current,
        with archived concepts present in the index."""
        okf_fts.build_fts_index(self.root)
        conn = sqlite3.connect(okf_fts._fts_db_path(self.root))
        try:
            self.assertFalse(okf_fts._fts_index_stale(self.root, conn))
            rows = [r[0] for r in conn.execute("SELECT path FROM docs")]
        finally:
            conn.close()
        self.assertIn("_archive/b/two", rows)

    def test_sc01_archiving_with_preserved_mtime_makes_index_stale(self):
        """SC-01/AC3 — the move-and-detect case. `git mv` preserves mtime,
        so this test moves the file with os.rename() (also a metadata-only
        rename on the same filesystem, mtime untouched) and asserts the
        move is caught anyway — through the count split, not through a
        changed timestamp."""
        okf_fts.build_fts_index(self.root)
        src = os.path.join(self.root, "b", "one.md")
        before_mtime = os.path.getmtime(src)
        dst = os.path.join(self.root, "_archive", "b", "one.md")
        os.rename(src, dst)
        after_mtime = os.path.getmtime(dst)
        self.assertEqual(before_mtime, after_mtime,
                          "test setup invalid: the move changed mtime, so "
                          "it would not exercise the mtime-preserved case "
                          "SC-01 requires")
        conn = sqlite3.connect(okf_fts._fts_db_path(self.root))
        try:
            self.assertTrue(okf_fts._fts_index_stale(self.root, conn))
        finally:
            conn.close()

    def test_staleness_check_never_reads_a_concept_body(self):
        """AC4/SC-02 (okf-cli-yixf) — stat-only, even with an archive
        present. Patches builtins.open AND io.open for the call's duration,
        not only the named okf.read_file() helper: a bare `open(ap).read()`
        added directly inside _fts_index_stale's active-tier loop stayed
        invisible to a read_file()-only patch (pathlib.Path.open() and
        Path.read_text() go through io.open, not builtins.open — codecs.open
        delegates to builtins.open — so both names are patched to close
        both routes). Neither patch is scoped to concept-body paths; nothing
        is allow-listed through, because the property under test is that
        NOTHING gets read, not that one particular path doesn't."""
        okf_fts.build_fts_index(self.root)
        conn = sqlite3.connect(okf_fts._fts_db_path(self.root))
        import builtins
        import io
        original_builtins_open = builtins.open
        original_io_open = io.open

        def _boom(file, *args, **kwargs):
            raise AssertionError(
                "staleness check opened a file: {}".format(file))

        builtins.open = _boom
        io.open = _boom
        try:
            okf_fts._fts_index_stale(self.root, conn)  # must not raise
        finally:
            builtins.open = original_builtins_open
            io.open = original_io_open
            conn.close()

    def test_pre_split_index_is_treated_as_stale_not_crashed(self):
        """Migration decision: an index built before this bean landed only
        ever wrote 'n_concepts'/'newest_mtime' to fts_meta — no
        'n_archived' key exists. _fts_index_stale() must not crash on that
        legacy schema; it must report stale (clean "please rebuild"), the
        same outcome an absent/corrupt meta table already gets."""
        db_path = okf_fts._fts_db_path(self.root)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.execute(okf_fts.FTS_SCHEMA)
        conn.execute(okf_fts.FTS_META_SCHEMA)
        conn.executemany(
            "INSERT OR REPLACE INTO fts_meta(k, v) VALUES (?, ?)",
            [("n_concepts", "1"), ("newest_mtime", repr(0.0))])
        conn.commit()
        try:
            self.assertTrue(okf_fts._fts_index_stale(self.root, conn))
        finally:
            conn.close()


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
        self.assertIsNone(okf_fts._fts_ranking(self.root, "tunnel", 10, okf_find_filters.FindFilters()))

    def test_absent_index_prints_exactly_one_stderr_note(self):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            result = okf_fts._fts_ranking(self.root, "tunnel", 10, okf_find_filters.FindFilters())
        self.assertIsNone(result)
        lines = [l for l in buf.getvalue().splitlines() if l]
        self.assertEqual(len(lines), 1)
        self.assertIn("note:", lines[0])

    def test_ranks_title_match_above_body_match(self):
        okf_fts.build_fts_index(self.root)
        ranked = okf_fts._fts_ranking(self.root, "tunnel", 10, okf_find_filters.FindFilters())
        self.assertEqual(ranked[0][0], "b/two")

    def test_type_filter_narrows(self):
        okf_fts.build_fts_index(self.root)
        ranked = okf_fts._fts_ranking(self.root, "tunnel", 10,
                                  compile_where("type = Runbook"))
        self.assertEqual([p for p, _s in ranked], ["b/one"])

    def test_tag_filter_matches_whole_tags_only(self):
        okf_fts.build_fts_index(self.root)
        ranked = okf_fts._fts_ranking(self.root, "tunnel", 10, compile_where("tag = tail"))
        self.assertEqual(ranked, [])

    def test_path_filter_narrows_to_a_bundle(self):
        okf_fts.build_fts_index(self.root)
        self.assertNotEqual(okf_fts._fts_ranking(self.root, "tunnel", 10, compile_where("path ~ b/")), [])
        self.assertEqual(okf_fts._fts_ranking(self.root, "tunnel", 10, compile_where("path ~ zz/")), [])

    def test_a_filter_the_index_cannot_apply_is_applied_before_the_limit(self):
        """The status key is not in the docs table: the residual runs over the ranked rows, and
        a LIMIT in SQL would have cut before it and starved the answer of the matching rows."""
        okf_fts.build_fts_index(self.root)
        for name in ("three", "four"):
            with open(os.path.join(self.root, "b", name + ".md"), "w", encoding="utf-8") as f:
                f.write("---\ntype: Concept\ntitle: {}\nstatus: draft\ndescription: d\n"
                        "tags: []\n---\ntunnel\n".format(name))
        okf_fts.build_fts_index(self.root)
        every = [p for p, _s in okf_fts._fts_ranking(self.root, "tunnel", 10, compile_where(None))]
        self.assertGreater(len(every), 2)
        draft = compile_where("status = draft")
        ranked = okf_fts._fts_ranking(self.root, "tunnel", 1, draft)
        self.assertEqual(len(ranked), 1)
        self.assertIn(ranked[0][0], ("b/three", "b/four"))
        both = okf_fts._fts_ranking(self.root, "tunnel", 10, draft)
        self.assertEqual(sorted(p for p, _s in both), ["b/four", "b/three"])

    def test_equal_bm25_scores_break_the_tie_by_path(self):
        """OKFT-rx72 — ORDER BY r alone leaves tied bm25 rows in whatever
        order the FTS5 doc table happens to store them, which is not a
        contract SQLite promises to keep stable across rebuilds. `zzz`/`aaa`
        share identical title/tags/body, so their bm25 scores tie exactly;
        the path secondary key must place `b/aaa` before `b/zzz`."""
        for name in ("zzz", "aaa"):
            with open(os.path.join(self.root, "b", name + ".md"), "w",
                      encoding="utf-8") as f:
                f.write("---\ntype: Concept\ntitle: Tiebreak Term\n"
                        "description: d\ntags: []\n---\n"
                        "Tiebreak term appears once in the body.\n")
        okf_fts.build_fts_index(self.root)
        ranked = okf_fts._fts_ranking(self.root, "tiebreak", 10, okf_find_filters.FindFilters())
        tied_paths = [p for p, _s in ranked if p in ("b/aaa", "b/zzz")]
        tied_scores = [s for p, s in ranked if p in ("b/aaa", "b/zzz")]
        self.assertEqual(tied_scores[0], tied_scores[1])
        self.assertEqual(tied_paths, ["b/aaa", "b/zzz"])

    def test_corrupt_index_degrades_to_none(self):
        okf_fts.build_fts_index(self.root)
        with open(okf_fts._fts_db_path(self.root), "wb") as f:
            f.write(b"not a database")
        self.assertIsNone(okf_fts._fts_ranking(self.root, "tunnel", 10, okf_find_filters.FindFilters()))

    def test_corrupt_index_prints_exactly_one_stderr_note(self):
        import io
        import contextlib
        okf_fts.build_fts_index(self.root)
        with open(okf_fts._fts_db_path(self.root), "wb") as f:
            f.write(b"not a database")
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            result = okf_fts._fts_ranking(self.root, "tunnel", 10, okf_find_filters.FindFilters())
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
        okf_fts.build_fts_index(self.root)
        db_path = okf_fts._fts_db_path(self.root)
        os.chmod(db_path, 0o000)
        try:
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                result = okf_fts._fts_ranking(self.root, "tunnel", 10, okf_find_filters.FindFilters())
        finally:
            os.chmod(db_path, 0o644)
        self.assertIsNone(result)
        lines = [l for l in buf.getvalue().splitlines() if l]
        self.assertEqual(len(lines), 1)
        self.assertIn("note:", lines[0])


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
        okf_fts.build_fts_index(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_title_weight_outranks_denser_body_match(self):
        ranked = okf_fts._fts_ranking(self.root, "zqxwgt", 10, okf_find_filters.FindFilters())
        self.assertEqual(ranked[0][0], "b/titlehit")

    def test_unweighted_bm25_would_rank_body_first(self):
        """Control probe (not exercising production code): confirms the
        fixture's crossover claim so the test above cannot be a fluke of
        this specific corpus."""
        conn = sqlite3.connect(okf_fts._fts_db_path(self.root))
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
        okf_fts.build_fts_index(self.root)
        conn = sqlite3.connect(okf_fts._fts_db_path(self.root))
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
            self.assertTrue(okf_fts._fts_index_stale(self.root, conn))
        finally:
            conn.close()

    def test_schemaless_db_reports_stale_without_raising(self):
        db_path = os.path.join(self.root, "empty.sqlite")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE unrelated(x)")
        conn.commit()
        try:
            self.assertTrue(okf_fts._fts_index_stale(self.root, conn))
        finally:
            conn.close()


class IndexableArchiveScopedToDeclaredBundle(unittest.TestCase):
    """OKFT-n8xz test 6 / Gate B B01 — with a `bundle` key declared, an
    archived directory that is NOT the declared bundle must not surface in
    the FTS index (740/745) nor in find's --include-archive scope
    (resolve_scopes, 3312/3317/3326)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "declared-bundle"))
        self._w("declared-bundle/one.md", "One", "active body.\n")
        self._w("_archive/declared-bundle/two.md", "Two", "archived, same bundle.\n")
        self._w("_archive/other-scaffolding/three.md", "Three", "archived, other dir.\n")
        with open(os.path.join(self.tmp, ".okf.toml"), "w", encoding="utf-8") as f:
            f.write('bundle = "declared-bundle"\n')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _w(self, rel, title, body):
        ap = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: {}\n---\n{}".format(title, body))

    def test_fts_index_excludes_the_undeclared_archived_bundle(self):
        okf_fts.build_fts_index(self.tmp)
        conn = sqlite3.connect(okf_fts._fts_db_path(self.tmp))
        rows = [r[0] for r in conn.execute("SELECT path FROM docs")]
        conn.close()
        self.assertIn("declared-bundle/one", rows)
        self.assertIn("_archive/declared-bundle/two", rows)
        self.assertNotIn("_archive/other-scaffolding/three", rows)

    def test_find_include_archive_scope_excludes_the_undeclared_bundle(self):
        """Review 2026-08-13 D02: `indexable_only` is find's explicit opt-in,
        not resolve_scopes()'s default — the call below mirrors what
        `_substring_ranking` actually passes, not a bare unscoped call."""
        scopes = okf_catalogue.resolve_scopes(self.tmp, None, include_archive=True,
                                    indexable_only=True)
        names = [b for b, _ in scopes]
        self.assertIn("_archive/declared-bundle", names)
        self.assertNotIn("_archive/other-scaffolding", names)

    def test_resolve_scopes_default_stays_wide_even_with_a_bundle_key(self):
        """Review 2026-08-13 B01 — the regression itself, pinned at the
        primitive level: without indexable_only=True, resolve_scopes() must
        NOT narrow just because `.okf.toml` declares a `bundle` key. Every
        caller except find (merge-tags, remove-tags, normalize-tags, list,
        _recent_scopes, fix-xml-like-tags, fix-crosslinks, wikilinks, check)
        relies on this default."""
        scopes = okf_catalogue.resolve_scopes(self.tmp, None, include_archive=True)
        names = [b for b, _ in scopes]
        self.assertIn("_archive/other-scaffolding", names)


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
            okf_fts.cmd_build_index(self.root, args)
        return buf.getvalue()

    def test_without_flag_always_rebuilds_even_when_current(self):
        """Regression guard for the D02 promise: omitting --if-stale must
        stay byte-identical to today — an unconditional full rebuild, never
        a skip, no matter how fresh the index already is."""
        okf_fts.build_fts_index(self.root)
        db_path = okf_fts._fts_db_path(self.root)
        before = os.path.getmtime(db_path)
        out = self._run(if_stale=False)
        after = os.path.getmtime(db_path)
        self.assertIn("indexed 1 concept(s)", out)
        self.assertGreaterEqual(after, before)

    def test_if_stale_skips_rebuild_when_index_is_current(self):
        okf_fts.build_fts_index(self.root)
        db_path = okf_fts._fts_db_path(self.root)
        # os.replace() on rebuild always produces a fresh inode/mtime, so an
        # unchanged mtime is proof the rebuild branch never ran.
        before = os.path.getmtime(db_path)
        out = self._run(if_stale=True)
        after = os.path.getmtime(db_path)
        self.assertEqual(before, after)
        self.assertIn("index is current", out)
        self.assertIn(db_path, out)

    def test_if_stale_rebuilds_when_a_concept_changed(self):
        okf_fts.build_fts_index(self.root)
        with open(os.path.join(self.root, "b", "two.md"), "w",
                  encoding="utf-8") as f:
            f.write("---\ntype: Konzept\ntitle: Two\ndescription: d\n"
                    "tags: []\n---\nbody two.\n")
        out = self._run(if_stale=True)
        self.assertIn("indexed 2 concept(s)", out)
        conn = sqlite3.connect(okf_fts._fts_db_path(self.root))
        try:
            total = conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(total, 2)

    def test_if_stale_rebuilds_when_index_is_absent(self):
        # No build_fts_index() call at all — the .fts dir does not exist yet.
        out = self._run(if_stale=True)
        self.assertIn("indexed 1 concept(s)", out)
        self.assertTrue(os.path.isfile(okf_fts._fts_db_path(self.root)))

    def test_help_documents_the_flag(self):
        ap = okf_parser.build_parser()
        parsers = okf_parser_support.subcommand_parsers(ap)
        actions = okf_parser_support.parser_actions(parsers["build-index"])
        flag = next((a for a in actions if a.dest == "if_stale"), None)
        self.assertIsNotNone(flag, "build-index has no --if-stale option")
        self.assertTrue((flag.help or "").strip())
