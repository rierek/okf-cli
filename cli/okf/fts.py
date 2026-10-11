"""Lexical search index: the FTS5 schema, building and staleness check of
<root>/.fts/fts.sqlite, the BM25 ranking over it, query tokenization and the
build-index command."""

import os
import re
import sqlite3
from okf.catalogue import (
    _dequote, extract_tags, iter_concepts, list_search_bundles, read_file, split_frontmatter,
)
from okf.find_filters import FTS_FILTER_COLUMNS
from okf.output import _add_output, _note
from okf.parser_support import _sub


def tokenize(s):
    """Lowercased word tokens. `\\w` is Unicode-aware in Python 3, so umlauts
    and ß stay inside their token (B01); `_` is kept as a separator, matching
    the previous behaviour for identifiers like build_tagvec."""
    return [t for t in re.split(r"[\W_]+", s.lower(), flags=re.UNICODE) if t]


# ── Lexical index (D14/D15) ──────────────────────────────────────────────
# FTS5 + BM25 is the lexical arm of the measured target architecture
# (DESIGN.md). The index is a PERSISTENT but OPTIONAL artefact: when it is
# absent or unusable, find falls back to the substring scan with one stderr
# note — never a hard fail (D15). Field weights title 3 / tags 2 / body 1 are
# the same ratios the substring scorer used, so the comparison isolates the
# retrieval model, not the weighting (eval/fts_arm.py:52-55).
#
# Query-side tokenization vs. index-side tokenization (I01, T04 review
# 2026-07-26): two layers apply in sequence, deliberately, not by accident.
#   1. Python tokenize() (word-splitting, lowercasing, underscore as a
#      separator) decides QUERY TERM BOUNDARIES before a term is quoted into
#      an FTS5 MATCH expression (Task 6: `'"{}"*'.format(t)`).
#   2. SQLite's own configured tokenizer (porter unicode61 remove_diacritics
#      2) is applied a SECOND time by FTS5 itself, both to the indexed
#      title/tags/body text at build time AND to each quoted term inside a
#      MATCH expression at query time — so diacritic-folding/stemming stays
#      symmetric on both sides even though Python's tokenize() alone does
#      not fold (ä stays ä at that layer).
# Verified empirically, not inferred: a query for the raw string "café"
# (unfolded) run as `docs MATCH '"café"*'` DOES match an indexed document
# containing "cafe"/"café_menü", and an unfolded `'"qualitätsmanagement"*'`
# DOES match the porter-stemmed indexed token, because FTS5 tokenizes quoted
# MATCH terms with the table's own tokenizer before comparing. Underscore
# splitting is likewise consistent between the two layers: unicode61 itself
# splits "build_tagvec" into "build"/"tagvec" (checked via fts5vocab), the
# same split tokenize() already performs — so there is no parity gap on
# that dimension either. Net effect: the FTS5 arm never needs Python-level
# folding: SQLite closes that gap on every MATCH.
# ───────────────────────────────────────────────────────────────────────
FTS_DIRNAME = ".fts"
FTS_FILENAME = "fts.sqlite"
# unicode61 folds diacritics (a German catalogue needs ä/ö/ü to match a/o/u);
# porter stems English morphology. Measured best variant: porter + prefix
# (R32).
FTS_TOKENIZER = "porter unicode61 remove_diacritics 2"
FTS_SCHEMA = (
    "CREATE VIRTUAL TABLE docs USING fts5("
    "path UNINDEXED, ctype UNINDEXED, title, tags, body, tokenize='{}')"
).format(FTS_TOKENIZER)
FTS_META_SCHEMA = "CREATE TABLE IF NOT EXISTS fts_meta(k TEXT PRIMARY KEY, v TEXT)"
# bm25() weight per column, in declaration order: path, ctype, title, tags, body.
FTS_BM25_WEIGHTS = "0.0, 0.0, 3.0, 2.0, 1.0"

def _fts_db_path(root):
    return os.path.join(root, FTS_DIRNAME, FTS_FILENAME)


def build_fts_index(root, db_path=None, include_topics=False):
    """(Re)build the FTS5 lexical index from the catalogue. Returns
    (n_concepts, db_path) where n_concepts is active + archived combined.
    Local I/O only — no network, stdlib sqlite3. Builds into a .tmp sibling
    and os.replace()s it, so an interrupted build never leaves a
    half-written index in place of a working one.

    Also indexes `_archive/<bundle>/<cid>` at that exact path (R-11) —
    without it `--include-archive` is a decoration, since FTS is the
    default retrieval arm and no predicate can surface a concept the index
    never saw. Active and archived counts are recorded separately in
    fts_meta (see _fts_index_stale) rather than summed, because a summed
    counter stays constant across an archive move — `git mv` preserves the
    file's mtime, so neither signal alone would catch the move."""
    db_path = db_path or _fts_db_path(root)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    tmp = db_path + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    conn = sqlite3.connect(tmp)
    n_active = 0
    n_archived = 0
    newest = 0.0
    try:
        conn.execute(FTS_SCHEMA)
        conn.execute(FTS_META_SCHEMA)

        def _index_bundle(b, bp, path_prefix):
            nonlocal newest
            count = 0
            for cid, ap in iter_concepts(bp):
                raw = read_file(ap)
                fm, body = split_frontmatter(raw)
                title = _dequote(fm.get("title", "")) or cid
                conn.execute(
                    "INSERT INTO docs(path, ctype, title, tags, body)"
                    " VALUES (?, ?, ?, ?, ?)",
                    ("{}{}/{}".format(path_prefix, b, cid), _dequote(fm.get("type", "")),
                     title, " ".join(extract_tags(raw)), body))
                count += 1
                mt = os.path.getmtime(ap)
                if mt > newest:
                    newest = mt
            return count

        for b in list_search_bundles(root, include_topics):
            n_active += _index_bundle(b, os.path.join(root, b), "")

        archive_root = os.path.join(root, "_archive")
        if os.path.isdir(archive_root):
            for b in list_search_bundles(archive_root, include_topics, root):
                n_archived += _index_bundle(
                    b, os.path.join(archive_root, b), "_archive/")

        conn.executemany(
            "INSERT OR REPLACE INTO fts_meta(k, v) VALUES (?, ?)",
            [("n_concepts", str(n_active)), ("n_archived", str(n_archived)),
             ("newest_mtime", repr(newest)),
             ("includes_topics", "1" if include_topics else "0")])
        conn.commit()
    finally:
        conn.close()
    os.replace(tmp, db_path)
    return n_active + n_archived, db_path


def _fts_index_stale(root, conn, include_topics=False, check_corpus=True):
    """True when the catalogue gained/lost concepts (active OR archived) or
    any concept file is newer than the newest one seen at build time.
    stat()-only — it never reads a concept body, which is exactly what
    makes it cheaper than the full scan it replaces. An unreadable/missing
    meta table counts as stale — this also covers an index built before
    R-11 landed, whose fts_meta has no 'n_archived' key: the KeyError below
    is caught the same way a missing table already is, so an old index is
    reported stale (clean rebuild) rather than crashing this check.

    Active and archived are compared as two separate counters, not their
    sum (R-11/AC2-AC3). A summed counter would stay constant across an
    archive move: `git mv` preserves the file's mtime, so the move would
    be invisible to both signals at once and the index would keep serving
    the concept under its stale, active path."""
    try:
        meta = dict(conn.execute("SELECT k, v FROM fts_meta").fetchall())
        n_active_idx = int(meta["n_concepts"])
        n_archived_idx = int(meta["n_archived"])
        newest_idx = float(meta["newest_mtime"])
        stored_topics = meta.get("includes_topics", "0") == "1"
        if check_corpus and stored_topics != include_topics:
            return True
    except (sqlite3.DatabaseError, KeyError, ValueError, TypeError):
        return True
    # A query against a broad index is current for its stored broad corpus;
    # the query predicate hides topic rows for the default narrow view.
    count_topics = include_topics if check_corpus else stored_topics
    n_active = 0
    n_archived = 0
    newest = 0.0
    for b in list_search_bundles(root, count_topics):
        for _cid, ap in iter_concepts(os.path.join(root, b)):
            n_active += 1
            mt = os.path.getmtime(ap)
            if mt > newest:
                newest = mt
    archive_root = os.path.join(root, "_archive")
    if os.path.isdir(archive_root):
        for b in list_search_bundles(archive_root, count_topics, root):
            for _cid, ap in iter_concepts(os.path.join(archive_root, b)):
                n_archived += 1
                mt = os.path.getmtime(ap)
                if mt > newest:
                    newest = mt
    return (n_active != n_active_idx or n_archived != n_archived_idx
            or newest > newest_idx)


def cmd_build_index(root, args):
    """(Re)build the FTS index, or — with --if-stale — skip when it is
    already current. Skips only when the artefact both exists and passes
    _fts_index_stale()'s stat()-only check; absent or stale still gets the
    full rebuild path (D02). Without the flag this is unconditional, exactly
    as before the flag existed — a caller that omits --if-stale must see
    byte-identical behaviour to the pre-flag CLI."""
    if getattr(args, "if_stale", False):
        db_path = _fts_db_path(root)
        if os.path.isfile(db_path):
            conn = sqlite3.connect(db_path)
            try:
                stale = _fts_index_stale(root, conn, getattr(args, "include_topics", False))
            finally:
                conn.close()
            if not stale:
                if getattr(args, "json", False):
                    return {"applied": False, "concepts": None, "path": db_path}
                print("index is current, skipping rebuild -> {}".format(db_path))
                return
    n, db = build_fts_index(root, include_topics=getattr(args, "include_topics", False))
    if getattr(args, "json", False):
        return {"applied": True, "concepts": n, "path": db}
    print("indexed {} concept(s) -> {}".format(n, db))


def _fts_ranking(root, query, limit, filters, notify=True):
    """[(path, positive_score), ...] best first, or None when the index is
    unusable (absent or corrupt) — None is the caller's signal to degrade to
    the substring scan (D15). bm25() is lower-is-better, so it is negated.
    Filters run inside SQL against the UNINDEXED ctype/path columns and the
    indexed tags column, so filtering never re-reads a concept file.

    `notify` exists because a degradation note describes the INVOCATION, not
    the call: --expand-tags reruns this arm over the widened term set within
    the same `find`, and an unconditional print would emit the same note
    twice (PF-4 violation — exactly one note per degraded arm). The rescue
    rerun passes notify=False; it is a second look at the same index and has
    nothing new to report."""
    db = _fts_db_path(root)
    if not os.path.isfile(db):
        # D15 requires a note for EVERY degradation, absent included — the
        # semantic arm does the same for its missing cache. Silent degradation
        # is the failure mode where "running fine" and "running on the weaker
        # arm" look identical from the outside. It goes to stderr, so stdout
        # stays byte-identical to the pre-plan output.
        if notify:
            _note("lexical index absent — falling back to substring "
                  "scan; run `okf-cli build-index` for BM25 ranking")
        return None
    terms = tokenize(query)
    if not terms:
        return []
    expr = " OR ".join('"{}"*'.format(t.replace('"', "")) for t in terms)
    sql = ("SELECT path, bm25(docs, {}) AS r FROM docs WHERE docs MATCH ?"
           .format(FTS_BM25_WEIGHTS))
    params = [expr]
    # `docs` carries all three dimensions, so the residual is empty and there
    # is nothing left for this arm to enforce in Python.
    where, where_params, residual = filters.sql_where(FTS_FILTER_COLUMNS)
    sql += where
    params.extend(where_params)
    assert not residual, "docs table covers every filter dimension"
    sql += " ORDER BY r, path LIMIT ?"  # path is the tiebreaker for equal
    # bm25 scores (OKFT-rx72): the FTS5 doc-insertion order that would
    # otherwise decide ties comes from os.walk() at build-index time, which
    # is not a contract SQLite is bound to preserve run over run — an
    # explicit secondary key makes tied ranks reproducible instead of
    # accidental.
    params.append(limit)
    try:
        conn = sqlite3.connect(db)
        try:
            # Run the real query FIRST. A corrupt file raises DatabaseError
            # here (garbage bytes still open() fine — sqlite3 does not
            # validate the format until the first read), caught below by the
            # single except. _fts_index_stale() has its own except branch
            # that SWALLOWS DatabaseError and reports "stale" (T05 AC7,
            # locked by FtsIndexStaleDegrades) — calling it before the query
            # would print a second, misleading "stale" note ahead of the
            # "unusable" one for the exact same corrupt file (caught by
            # adversarial testing, not in the original plan). Checking
            # staleness only after a successful query keeps the corrupt path
            # at exactly one stderr note without changing what
            # _fts_index_stale() itself reports when called directly.
            rows = conn.execute(sql, params).fetchall()
            topic_corpus_missing = (
                filters.include_topics and _fts_index_includes_topics(root) is False)
            if (notify and not topic_corpus_missing
                    and _fts_index_stale(
                        root, conn, filters.include_topics, check_corpus=False)):
                _note("lexical index is stale (catalogue changed since "
                      "build) — run `okf-cli build-index`")
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        if notify:
            _note("lexical index unusable — falling back to substring scan")
        return None
    return [(p, -r) for p, r in rows]


def _fts_index_includes_topics(root):
    db = _fts_db_path(root)
    if not os.path.isfile(db):
        return None
    try:
        conn = sqlite3.connect(db)
        try:
            row = conn.execute("SELECT v FROM fts_meta WHERE k = 'includes_topics'").fetchone()
        finally:
            conn.close()
        return bool(row and row[0] == "1")
    except sqlite3.DatabaseError:
        return None


def add_build_index_parser(sub):
    pbi = _sub(sub, "build-index", "search",
               "(re)build the FTS5 lexical search index at "
               "<root>/.fts/fts.sqlite (local only, no network)")
    pbi.add_argument("--include-topics", action="store_true", help="widen beyond .okf.toml declared bundle to topic folders")
    pbi.add_argument("--if-stale", action="store_true",
                      help="skip the rebuild when the existing index is "
                           "already current (default: always rebuild)")
    _add_output(pbi)


COMMANDS = {"build-index": (cmd_build_index, add_build_index_parser)}
