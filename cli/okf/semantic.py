"""Semantic search arm: the voyage query embedding, cosine ranking over the .tagvec
concept embeddings, query-tag expansion, embedding coverage and the
build-semantic-index command."""

import json
import math
import os
import sqlite3
import struct
import sys
import urllib.request

from okf import catalogue
from okf.catalogue import iter_concepts, list_indexable_bundles
from okf.find_filters import EMB_FILTER_COLUMNS, FindFilters
from okf.parser_support import _sub


# 8c (D04) — semantic arm (renamed from "semantic backstop" in T07/D12: on a
# paraphrase query it OWNS the ranking, it does not just fill gaps). Fires
# only as cmd_find's gate in find.py decides (zero/weak/ambiguous keyword hits),
# reads .tagvec's concept_emb table (title+body scope, cli/embeddings/
# build_tagvec.py) via stdlib sqlite3, and embeds the query with a REMOTE
# voyage-3-large call (Voyage AI HTTP API, D13) — best-effort: any failure
# (cache absent, key missing, backend unreachable) degrades to keyword-only
# with a one-line stderr note, never raises, never blocks the keyword path
# (Global Constraints). bge-m3 is NOT a runtime fallback here (D16).
# D13 — voyage-3-large is the productive semantic model: MRR 0.452 vs 0.150
# for bge-m3 on the unbiased query set, zero-hit 0.167 vs 0.646 (R42). That is
# the difference between usable and not, not a tuning gap. The accepted price
# is a network call and an API key in the request path; D16 makes the
# degradation two-stage (voyage -> lexical only), so bge-m3 is NOT a runtime
# fallback and concept_emb holds voyage rows only.
SEMANTIC_MODEL = "voyage-3-large"
VOYAGE_EMBED_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_EMBED_TIMEOUT = 10


def _tagvec_db_path(root):
    return os.path.join(root, ".tagvec", "tag_vectors.sqlite")


def _load_concept_vectors(db_path, model, filters=None):
    """([(path, [float, ...]), ...], residual) for every concept_emb row of
    `model`, or (None, _) if the cache file/table is absent or has no rows for
    this model (the graceful-skip signal semantic_ranking() acts on).

    concept_emb carries only the path, so of the three filter dimensions this
    query can enforce scope alone — with the SAME predicate the FTS arm uses,
    since concept_emb.path and docs.path share the `<bundle>/<concept>` form.
    Enforcing it in SQL rather than after ranking keeps --limit meaningful: an
    out-of-scope concept never occupies a slot it would then be dropped from
    (B01). The returned `residual` carries type/tag for the caller to apply."""
    filters = filters or FindFilters()
    where, where_params, residual = filters.sql_where(EMB_FILTER_COLUMNS)
    if not os.path.isfile(db_path):
        return None, residual
    scope = filters.scope
    sql = "SELECT path, dim, vec FROM concept_emb WHERE model = ?" + where
    params = [model] + where_params
    try:
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(sql, params).fetchall()
            # "no rows" means two different things once a scope narrows the
            # query, and they must not share a return value: a cache with no
            # embeddings for this model is a DEGRADATION (None -> stderr
            # note), while a populated cache holding nothing inside the
            # requested scope is a correct, complete, empty answer ([] -> no
            # note). Conflating them would print "embeddings absent" at the
            # user every time they scoped to a bundle that simply has none.
            if not rows and scope:
                have_any = conn.execute(
                    "SELECT 1 FROM concept_emb WHERE model = ? LIMIT 1",
                    (model,)).fetchone()
                if have_any:
                    return [], residual
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return None, residual
    if not rows:
        return None, residual
    return ([(path, list(struct.unpack("<{}f".format(dim), vec_blob)))
             for path, dim, vec_blob in rows], residual)


# One CLI invocation answers one query, and both the semantic arm and (when
# enabled) tag expansion embed the SAME string. Cache it so --expand-tags
# costs zero extra network calls rather than doubling them.
_QUERY_VEC_CACHE = {}


def _query_vector(text):
    """Cached _embed_query_voyage(). Raises exactly what it raises, so every
    caller keeps its own degradation behaviour."""
    if text not in _QUERY_VEC_CACHE:
        _QUERY_VEC_CACHE[text] = _embed_query_voyage(text)
    return _QUERY_VEC_CACHE[text]


def _embed_query_voyage(text):
    """Best-effort Voyage embed call for the query string. NETWORK — reached
    only when the semantic arm actually runs (never at import time, never
    unconditionally). `input_type="query"` is the asymmetric query form the
    measurement used (eval/hybrid_eval.py:73-80); documents were embedded with
    input_type="document" by the producer. Any failure propagates so the
    caller degrades gracefully; this function never catches."""
    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key:
        raise RuntimeError("VOYAGE_API_KEY not set")
    req = urllib.request.Request(
        VOYAGE_EMBED_URL,
        data=json.dumps({
            "model": SEMANTIC_MODEL,
            "input": [text],
            "input_type": "query",
        }).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        },
    )
    with urllib.request.urlopen(req, timeout=VOYAGE_EMBED_TIMEOUT) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["data"][0]["embedding"]


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _load_tag_vectors(db_path, model):
    """[(tag, [float, ...]), ...] from the `emb` table, or None when the cache
    or the model's rows are absent — mirrors _load_concept_vectors()."""
    if not os.path.isfile(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT tag, dim, vec FROM emb WHERE model = ?", (model,)
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return None
    if not rows:
        return None
    return [(tag, list(struct.unpack("<{}f".format(dim), blob)))
            for tag, dim, blob in rows]


def _expand_query_tags(root, query, top_k=3, floor=0.6):
    """Registered tag slugs semantically near the query (Q05). Reuses the
    query vector the semantic arm needs anyway, which is what makes Q06 moot:
    a query term that is not a registered tag never needs its own embedding
    call. Returns [] on any degradation — expansion is an enhancement, never a
    precondition. The floor exists because a nearest neighbour is always
    returned otherwise; unlike the concept case (R34, no separable floor),
    tag slugs are short, clean labels where a cutoff is defensible — that is
    exactly what Step 6 measures."""
    vectors = _load_tag_vectors(_tagvec_db_path(root), SEMANTIC_MODEL)
    if not vectors:
        return []
    try:
        qvec = _query_vector(query)
    except Exception:
        return []
    ranked = sorted(((_cosine(qvec, v), tag) for tag, v in vectors),
                    key=lambda x: -x[0])
    return [tag for score, tag in ranked[:top_k] if score >= floor]


def semantic_ranking(root, query, limit, filters):
    """[(cosine, path), ...] best first, or [] with one stderr note on any
    degradation (cache/table absent, no API key, backend unreachable).

    Renamed from semantic_backstop(): under conditional handover this arm is
    no longer a fallback that only fills gaps — on a paraphrase query it OWNS
    the ranking (D12). It also no longer takes exclude_paths, because
    deduplication happens in fusion, after the owner has been decided.

    B01: the filters are not the lexical arm's private business. Whichever arm
    ends up owning the ranking, --scope/--type/--tag describe the ANSWER, so
    they are enforced here too. Scope rides along in the cache query; the
    residual (type/tag, absent from concept_emb) is applied while walking the
    ranked list — lazily, stopping at `limit`, so it costs one frontmatter
    read per candidate actually considered rather than one per embedding."""
    vectors, residual = _load_concept_vectors(
        _tagvec_db_path(root), SEMANTIC_MODEL, filters)
    if vectors is None:
        print("note: semantic arm skipped (.tagvec cache/concept embeddings "
              "absent) — lexical results only", file=sys.stderr)
        return []
    if not vectors:
        return []
    try:
        qvec = _query_vector(query)
    except Exception as exc:
        print("note: semantic arm skipped (embedding backend unavailable: {})"
              " — lexical results only".format(exc), file=sys.stderr)
        return []
    # path is the tiebreaker for equal cosine values (OKFT-rx72): the SQL
    # row order feeding this sort has no ORDER BY of its own, so without a
    # secondary key here two runs could stably-sort equal cosines in
    # whatever order concept_emb happened to return them in.
    ranked = sorted(((_cosine(qvec, vec), path) for path, vec in vectors),
                    key=lambda x: (-x[0], x[1]))
    if not residual:
        return ranked[:limit]
    out = []
    for cosine, path in ranked:
        if len(out) >= limit:
            break
        if residual.matches(root, path):
            out.append((cosine, path))
    return out


def semantic_coverage(root, paths):
    """(embedded, total) for the concepts named in `paths`, or None when the
    catalogue carries no `.tagvec` at all.

    Delegates to plan_concept_delta() — the same content-hash comparison
    (concept_cache_key over title+body) the producer uses to decide what to
    re-embed — rather than running a second, weaker detector next to it. A
    PATH-SET-only comparison used to pass here: a concept whose body changed
    after embedding kept its old row's path, so the gap between "coverage
    thinks it's done" and "the producer still has 40 concepts queued"
    (measured live, 2026-08-10) went unreported. `paths` is intersected with
    the delta rather than trusted verbatim, so a caller passing a subset
    still gets an answer scoped to what it asked about.

    Costs ~2.2s over ~2600 concepts (offline, one read+hash per concept) —
    call sparingly on a hot path; see _semantic_coverage_line()'s `thorough`
    gate for the default-prime case."""
    db = _tagvec_db_path(root)
    if not os.path.isfile(db):
        return None
    try:
        bt = catalogue._load_build_tagvec()
        delta = bt.plan_concept_delta(root, SEMANTIC_MODEL, db)
    except sqlite3.Error:
        return None
    stale = {path for path, _text, _key in delta} & set(paths)
    return len(paths) - len(stale), len(paths)


def cmd_build_semantic_index(root, args):
    """Fill .tagvec/tag_vectors.sqlite's concept_emb table for every concept
    still missing a voyage-3-large embedding (OKFT-wsne) -- the trigger the
    producer (cli/embeddings/build_tagvec.py) never had. Offline half is
    plan_concept_delta(); network half is embed_voyage(), run batch-by-batch
    through embed_resilient() so one bad batch (LL-08) does not throw away
    an already-embedded run.

    With --if-stale, skip the whole call when semantic_coverage()'s PATH-SET
    probe already reports every on-disk concept embedded -- same D02 shape
    as cmd_build_index's --if-stale: skip only when the artefact both
    exists and is current, absent/partial still gets the full run, and
    omitting the flag stays unconditional exactly as before the flag
    existed. The probe is semantic_coverage(), not a row count, because
    concept_emb keeps orphan rows for deleted concepts (OKFT-3520) that
    would let a row-count check report complete while paths are missing.

    Never raises: a missing VOYAGE_API_KEY or an exhausted-retries network
    failure degrades to a stderr `note: ...` (same shape as the existing
    lexical-index degradation notices) and a clean return, because this is
    meant to run unattended from a SessionStart hook, detached, and must
    never surface a traceback into a session transcript. The query path
    (`find`) is untouched by any of this -- it never calls this producer
    itself (D13/D16)."""
    db_path = _tagvec_db_path(root)
    if getattr(args, "if_stale", False):
        bundles = list_indexable_bundles(root)
        paths = ["{}/{}".format(b, cid) for b in bundles
                 for cid, _ap in iter_concepts(os.path.join(root, b))]
        cov = semantic_coverage(root, paths)
        if cov is not None and cov[0] >= cov[1]:
            print("semantic index is current, skipping rebuild -> {}".format(db_path))
            return
    if not os.environ.get("VOYAGE_API_KEY"):
        print("note: semantic index build skipped (VOYAGE_API_KEY not set) "
              "-- run again once it is set, or set it before the next "
              "SessionStart hook run", file=sys.stderr)
        return
    bt = catalogue._load_build_tagvec()
    try:
        delta = bt.plan_concept_delta(root, SEMANTIC_MODEL, db_path)
        written = 0
        incomplete = False
        max_items, max_chars = bt.BATCH_LIMITS[SEMANTIC_MODEL]
        for batch in bt.batches(delta, max_items, max_chars):
            vectors = bt.embed_resilient(
                bt.embed_voyage, [t for _path, t, _key in batch],
                "voyage concepts {}..".format(batch[0][0]))
            if vectors is None:
                incomplete = True
                continue
            rows = [
                (key, path, SEMANTIC_MODEL, bt.MODELS[SEMANTIC_MODEL]["dim"],
                 bt.pack_vec(vec))
                for (path, _text, key), vec in zip(batch, vectors)
            ]
            bt.write_concept_rows(db_path, rows)
            written += len(rows)
        print("embedded {} concept(s) -> {}".format(written, db_path))
        if incomplete:
            print("note: semantic index build incomplete -- {} concept(s) "
                  "left unembedded after retries; rerun to pick up the "
                  "rest".format(len(delta) - written), file=sys.stderr)
    except Exception as exc:
        print("note: semantic index build failed ({}: {}) -- lexical arm "
              "unaffected".format(type(exc).__name__, exc), file=sys.stderr)


def add_build_semantic_index_parser(sub):
    pbs = _sub(sub, "build-semantic-index", "search",
               "fill <root>/.tagvec/tag_vectors.sqlite's concept_emb table "
               "for every concept still missing a voyage-3-large embedding "
               "(NETWORK, requires VOYAGE_API_KEY)")
    pbs.add_argument("--if-stale", action="store_true",
                      help="skip the run when semantic_coverage() already "
                           "reports every on-disk concept embedded "
                           "(default: always fill the delta)")


COMMANDS = {"build-semantic-index": (cmd_build_semantic_index, add_build_semantic_index_parser)}
