#!/usr/bin/env python3
"""Tests for cli/okf/fts.py — the FTS5 index, its BM25 ranking and the query tokenizer. Stdlib unittest, no deps.

Run: python3 -m unittest test_okf_fts -v
"""
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:  # cli/ holds the okf package; a repo-root run lacks it
    sys.path.insert(0, _HERE)

from okf import find_filters as okf_find_filters
from okf import fts as okf_fts


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
                                  okf_find_filters.FindFilters(type="Runbook"))
        self.assertEqual([p for p, _s in ranked], ["b/one"])

    def test_tag_filter_matches_whole_tags_only(self):
        okf_fts.build_fts_index(self.root)
        ranked = okf_fts._fts_ranking(self.root, "tunnel", 10,
                                  okf_find_filters.FindFilters(tag="tail"))
        self.assertEqual(ranked, [])

    def test_scope_filter_narrows_to_a_bundle(self):
        okf_fts.build_fts_index(self.root)
        self.assertNotEqual(okf_fts._fts_ranking(self.root, "tunnel", 10, okf_find_filters.FindFilters(scope="b")), [])
        self.assertEqual(okf_fts._fts_ranking(self.root, "tunnel", 10, okf_find_filters.FindFilters(scope="zz")), [])

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
