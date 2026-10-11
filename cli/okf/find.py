"""find: the lexical arm with its substring fallback, the semantic hand-over and
fusion, hit hydration, zero-hit suggestions, the printed result and the find
parser."""

import argparse
import difflib
import os
import re

from okf import semantic
from okf.output import _add_output, _note
from okf.catalogue import (
    _dequote, all_tags, iter_concepts, list_search_bundles, load_okf_config, read_file,
    resolve_scopes, split_frontmatter,
)
from okf.find_filters import compile_where
from okf.fts import _fts_index_includes_topics, _fts_ranking, tokenize
from okf.parser_support import _add_filters, _sub
from okf.semantic import semantic_ranking


def _format_contrib(contrib):
    """SC-002 — per-hit breakdown text: which field(s) each term hit."""
    parts = []
    for field in ("title", "tags", "body"):
        terms = contrib.get(field) or []
        if terms:
            parts.append("{}=[{}]".format(field, ",".join(terms)))
    return "; ".join(parts) if parts else "(none)"


def _hit_record(rank, hit, breakdown, max_score):
    """One hit as the envelope carries it: the fields cmd_find prints per hit, under
    --breakdown also the arm's own values."""
    record = {"rank": rank, "title": hit["title"], "type": hit["type"]}
    if hit.get("superseded_by"):
        record["superseded_by"] = hit["superseded_by"]
    record.update(path=hit["path"], description=hit["desc"], snippet=hit["snip"],
                  provenance=hit.get("provenance", "lexical"))
    if breakdown:
        record["breakdown"] = (
            {"cosine": hit["cosine"]} if hit.get("provenance") == "semantic" else
            {"score": hit["score"], "max_score": max_score, "contrib": hit.get("contrib")})
    return record


def _hydrate_hit(root, path, terms, score, provenance, cosine=None):
    """Build the hit dict cmd_find prints, reading the concept file itself.
    Only ever called for the <= limit paths that actually rank, which is what
    makes the FTS path cheaper than the full scan. Returns None when the path
    no longer resolves (index or embedding cache newer than the file tree)."""
    ap = os.path.join(root, path + ".md")
    if not os.path.isfile(ap):
        return None
    fm, body = split_frontmatter(read_file(ap))
    hit = {
        "score": score,
        "path": path,
        "title": _dequote(fm.get("title", "")) or path.rsplit("/", 1)[-1],
        "type": fm.get("type", ""),
        "desc": _dequote(fm.get("description", "")),
        "snip": make_snippet(body, terms),
        "provenance": provenance,
    }
    sb = _dequote(fm.get("superseded_by", ""))
    if sb:
        hit["superseded_by"] = sb
    if cosine is not None:
        hit["cosine"] = cosine
    return hit


def _substring_ranking(root, query, terms, limit, filters):
    """The pre-FTS lexical arm, unchanged: substring matching with field
    weights title 3 / tags 2 / body 1 over a full scan. It stays in the tool
    as the degradation target for a missing or unusable index (D15) — its
    scoring, its `contrib` breakdown and its 6*len(terms) scale must remain
    byte-identical, because the frozen eval baseline was recorded against it.

    The expression is enforced twice on purpose, and the two are not redundant:
    resolve_scopes() confines the TRAVERSAL to the active catalogue, or to it
    plus the archive when the expression names `archived` (so a concept the
    archive rule hides is never even read from disk), while matches_loaded()
    re-checks the assembled path against the whole expression. Only the second
    one is a predicate; dropping it would reopen the I01 gap the moment the
    traversal changes shape.

    `indexable_only` tracks `--include-topics`: the default uses the declared
    index corpus while an explicit topic search scans all bundles."""
    hits = []
    for _b, bp in resolve_scopes(
            root, None, filters.include_archive,
            indexable_only=not filters.include_topics):
        # The path prefix is the bundle's position under root (`_archive/<b>` for an
        # archived one), so a hit's path is one `okf-cli read` resolves.
        prefix = os.path.relpath(bp, root).replace(os.sep, "/")
        for cid, ap in iter_concepts(bp):
            text = read_file(ap)
            fm, body = split_frontmatter(text)
            t = fm.get("type", "")
            if not filters.matches_loaded("{}/{}".format(prefix, cid), fm, text):
                continue
            title = fm.get("title", cid)
            tags = fm.get("tags", "")
            hay_title = title.lower()
            hay_tags = tags.lower()
            hay_body = body.lower()
            score = 0
            contrib = {"title": [], "tags": [], "body": []}
            for term in terms:
                if hay_title.count(term):
                    score += 3
                    contrib["title"].append(term)
                if hay_tags.count(term):
                    score += 2
                    contrib["tags"].append(term)
                if hay_body.count(term):
                    score += 1
                    contrib["body"].append(term)
            if score:
                hit = {
                    "score": score, "path": "{}/{}".format(prefix, cid),
                    "title": title, "type": t,
                    "desc": _dequote(fm.get("description", "")),
                    "snip": make_snippet(body, terms), "contrib": contrib,
                    "provenance": "lexical",
                }
                sb = _dequote(fm.get("superseded_by", ""))
                if sb:
                    hit["superseded_by"] = sb
                hits.append(hit)
    hits.sort(key=lambda h: -h["score"])
    return hits[:limit]


def _rank_lexically(root, query, terms, limit, filters, notify=True):
    """(hits, max_score) — the FTS arm when the index is usable, otherwise the
    substring scan (D15). The two arms report on different scales, so the
    scale is returned with the result instead of being recomputed by the
    caller: 0..100 for BM25 (relative to this run's own top hit), and
    6*len(terms) for the substring fallback, which keeps that path
    byte-identical to pre-plan output."""
    ranked = _fts_ranking(root, query, limit, filters, notify=notify)
    if ranked is None:
        return (_substring_ranking(root, query, terms, limit, filters),
                6 * len(terms))
    top = ranked[0][1] if ranked else 1.0
    hits = []
    for path, s in ranked:
        hit = _hydrate_hit(root, path, terms,
                           int(round(100 * s / top)) if top else 0, "lexical")
        if hit is not None:
            hits.append(hit)
    return hits, 100


# Post-review fix (F01, 2026-07-25): the original absolute score/max_score
# ratio gate misclassified legitimate literal top-1 hits as "weak" — this
# repo's OWN golden fixtures have literal min_score_ratio well below any
# sane absolute threshold (S1=0.30, S2=0.25, S4=0.55), because a partial
# multi-term title/tag/body match is a perfectly confident top-1, not a weak
# one; the ratio depends on term count and per-field weighting, not on
# actual retrieval confidence. Replaced with a margin gate: fire the
# backstop on zero hits OR when the keyword top-1 has no clear lead over
# the runner-up (ambiguous ranking) — never on an absolute ratio.
SEMANTIC_MARGIN_RATIO = 0.5  # top1 >= (1 + ratio) * top2, i.e. top1 must
                              # lead the runner-up by at least 1.5x to count
                              # as "confident" enough for the lexical arm to
                              # OWN the ranking (D12). Copied from
                              # eval/hybrid_eval.py:151, NOT calibrated: on
                              # the real catalogue it fires ~1 of 48 queries
                              # (OKFT-8l96 SC-001), so R43 ~ semantic arm
                              # alone. Honest fallback, not a tuning knob.
# SEMANTIC_NOISE_RATIO removed (T08/D12): it was a crutch for the old
# pin+blend rule, forcing the backstop to fire against a noisy substring
# top-1 regardless of margin. Under conditional handover a noisy lexical
# arm simply does not own the ranking (its top-1 has no clear margin, or
# there IS no meaningful runner-up comparison at all when hits are sparse
# noise), so the absolute floor is redundant — R43 measured the rule
# without it. Do not resurrect it as a second, competing gate.


def _keyword_top1_is_confident(hits):
    """True when the lexical arm may OWN the ranking: it has hits and either a
    single one (nothing to be ambiguous against) or a top-1 leading the
    runner-up by the measured margin.

    The comparison is `top1 >= (1 + SEMANTIC_MARGIN_RATIO) * top2`, i.e.
    top1 >= 1.5x top2 — copied from the rule that actually produced R43's
    0.437 (eval/hybrid_eval.py:151). The pre-plan code computed
    `(top1-top2)/top1 >= SEMANTIC_MARGIN_RATIO`, which is top1 >= 2x top2: a
    stricter bar that hands over to the semantic arm LESS often than what was
    measured. Do not "simplify" it back."""
    if not hits:
        return False
    if len(hits) == 1:
        return True
    top1, top2 = hits[0]["score"], hits[1]["score"]
    if top1 <= 0:
        return False
    return top1 >= (1 + SEMANTIC_MARGIN_RATIO) * top2


def _semantic_hit_dicts(root, query, limit, filters):
    """semantic_ranking() results, hydrated into the same hit-dict shape the
    lexical arm produces so fusion and printing treat both uniformly.
    Semantic score is round(100 * cosine) — the same 0..100 scale the FTS arm
    reports, which makes the printed number comparable without implying the
    two are fused by score (they are not; see fuse_conditional)."""
    terms = tokenize(query)
    out = []
    for cosine, path in semantic_ranking(root, query, limit, filters):
        hit = _hydrate_hit(root, path, terms, int(round(100 * cosine)),
                           "semantic", cosine=cosine)
        if hit is not None:
            out.append(hit)
    return out


def fuse_conditional(lexical_hits, semantic_hits, limit):
    """(fused_hits, lexical_owned) — conditional HANDOVER, not blending (D12).

    Measured on the unbiased query set: blending a lexical list that is pure
    noise on paraphrases (zero-hit 1.000) into a working semantic list costs
    more than it adds, whether by score interleaving (MRR 0.029) or by RRF
    (0.201). On literal queries the lexical arm is the better one. So decide
    per query WHICH arm owns the ranking instead of averaging them: worst case
    0.437 across both regimes (R43).

    The owning arm's list comes first in its own order; the other arm is
    appended behind it, never in front. Duplicates keep the owning arm's entry
    (and therefore its provenance), so a concept both arms found is not
    reported twice."""
    lexical_owned = _keyword_top1_is_confident(lexical_hits)
    primary = lexical_hits if lexical_owned else semantic_hits
    secondary = semantic_hits if lexical_owned else lexical_hits
    out, seen = [], set()
    for hit in list(primary) + list(secondary):
        if hit["path"] in seen:
            continue
        seen.add(hit["path"])
        out.append(hit)
    return out[:limit], lexical_owned


def _zero_hit_suggestions(root, query, limit=5):
    """Registered tag slugs closest to the query's terms — the reformulation
    hint a zero hit hands back (Q13). difflib only: no network, no vectors, so
    this works on the fully degraded path too."""
    tags = sorted(all_tags(root))
    if not tags:
        return []
    out = []
    for term in tokenize(query):
        for cand in difflib.get_close_matches(term, tags, n=limit, cutoff=0.7):
            if cand not in out:
                out.append(cand)
    return out[:limit]


def cmd_find(root, args):
    # I01: built ONCE, here, and handed to every arm as a single value. The
    # filters used to travel as loose positional arguments, which is how the
    # semantic arm ended up never receiving them at all (B01). Compiled before
    # anything else, so a malformed --where fails whatever the query is.
    include_topics = getattr(args, "include_topics", False)
    # Only a positive `bundle` declaration narrows the result predicate.
    # A catalogue without that declaration keeps its historic behavior:
    # archived-only bundles remain reachable through `archived` in --where.
    config = load_okf_config(root)
    corpus_bundles = (list_search_bundles(root) if config.get("bundle")
                      and not include_topics else None)
    filters = compile_where(getattr(args, "where", None), include_topics, corpus_bundles)
    if include_topics and _fts_index_includes_topics(root) is False:
        _note("lexical index excludes topic folders — run `okf-cli build-index --include-topics`")
    terms = tokenize(args.query)
    if not terms:
        if getattr(args, "json", False):
            return {"hits": [], "nearest_tags": []}
        print("(empty query)")
        return
    breakdown = getattr(args, "breakdown", False)
    hits, max_score = _rank_lexically(root, args.query, terms, args.limit,
                                      filters)

    # The semantic arm costs a network call, so run it only when it can
    # change the answer: whenever the lexical arm is not confident (it will
    # then OWN the ranking), or when a confident lexical list is too short to
    # fill --limit (it then fills the tail, exactly as measured).
    lexical_owned_provisionally = _keyword_top1_is_confident(hits)

    # T05/Q05 (experimental, off by default): when the unexpanded lexical arm
    # is not confident, widen the query with semantically near registered tags
    # and give the lexical arm a second chance. Deliberately NOT run when the
    # lexical arm is already confident — that query needs no rescue, and the
    # call would be pure cost (same rule the semantic arm follows below).
    if getattr(args, "expand_tags", False) and not lexical_owned_provisionally:
        extra = semantic._expand_query_tags(root, args.query)
        if extra:
            _note("query expanded with tag(s): {}".format(", ".join(extra)))
            terms = terms + [t for t in extra if t not in terms]
            # notify=False: this is the SAME index, looked at a second time
            # within one invocation. Repeating its degradation note here
            # would print it twice with the expansion note in between —
            # PF-4 says exactly one note per degraded arm, per invocation.
            hits, max_score = _rank_lexically(
                root, " ".join(terms), terms, args.limit, filters,
                notify=False)
            lexical_owned_provisionally = _keyword_top1_is_confident(hits)

    semantic_hits = []
    if not lexical_owned_provisionally or len(hits) < args.limit:
        # B01: the SAME filters object the lexical arm got — --where
        # constrains the answer, not one arm of it.
        semantic_hits = _semantic_hit_dicts(root, args.query, args.limit,
                                            filters)

    # R-13: the embedding build stays on the active catalogue by design
    # (cli/embeddings/build_tagvec.py:174) — an unannounced limit is a trap,
    # so tell the searcher when `archived` did not reach the arm
    # that just shaped the answer. Gated on the conjunction (expression names
    # `archived` AND the semantic arm actually contributed hits), not the
    # expression alone, and printed at most once per invocation (PF-4).
    if filters.include_archive and semantic_hits:
        _note("`archived` in --where covers the lexical arm only; "
              "embeddings stay on the active catalogue")

    all_hits, lexical_owned = fuse_conditional(hits, semantic_hits, args.limit)
    if not lexical_owned and semantic_hits:
        _note("semantic arm owns this ranking (lexical top-1 lacked a "
              "clear margin)")

    if getattr(args, "json", False):
        return {"hits": [_hit_record(i, h, breakdown, max_score)
                         for i, h in enumerate(all_hits[: args.limit], start=1)],
                "nearest_tags": [] if all_hits else _zero_hit_suggestions(root, args.query)}
    if not all_hits:
        print("(no matches for: {})".format(args.query))
        near = _zero_hit_suggestions(root, args.query)
        if near:
            print("nearest registered tags: {}".format(", ".join(near)))
            print("try: okf-cli find \"{}\"".format(" ".join(near[:2])))
        return
    for i, h in enumerate(all_hits[: args.limit], start=1):
        print("------")
        # D01 (OKFT-3rb6): `rank` is the ONE comparable scale across a mixed
        # result list — the 1-based position actually delivered. It is
        # comparable by construction (it IS the list order) and claims
        # nothing about the two arms' raw scores being on one scale, which
        # D12 rejects. Those raw values (a/b lexical, cosine X.XX semantic)
        # are informative but not sortable against each other, so they move
        # out of the headline entirely and only reappear under --breakdown.
        print("rank: {}".format(i))
        print("title: {}".format(h["title"]))
        print("type: {}".format(h["type"]))
        # Present only when the concept's frontmatter carries the relation
        # (D01, OKFT-gpcx) — a hit without it stays byte-identical to the
        # pre-existing block shape (this is asserted, not assumed).
        if h.get("superseded_by"):
            print("superseded_by: {}".format(h["superseded_by"]))
        print("path: {}".format(h["path"]))
        print("description: {}".format(h["desc"]))
        print("body-snippet: {}".format(h["snip"]))
        # Every line names its own arm. The banner above says who OWNS the
        # ranking, which is not the same statement — a lexical hit can sit
        # inside a semantic-owned list, and leaving it unmarked made its
        # provenance derivable only from a missing marker (Modus-B B01).
        print("provenance: {}".format(h.get("provenance", "lexical")))
        if breakdown:
            if h.get("provenance") == "semantic":
                print("score: cosine {:.2f}".format(h["cosine"]))
                print("contrib: semantic-only (cosine={:.2f}, no keyword field match)".format(h["cosine"]))
            else:
                print("score: {}/{}".format(h["score"], max_score))
                if "contrib" in h:
                    print("contrib: {}".format(_format_contrib(h["contrib"])))
                else:
                    print("contrib: bm25 (fts5 index; field-level breakdown not "
                          "available)")
    print("------")


def make_snippet(body, terms, width=140):
    low = body.lower()
    pos = -1
    for t in terms:
        i = low.find(t)
        if i != -1 and (pos == -1 or i < pos):
            pos = i
    if pos == -1:
        pos = 0
    start = max(0, pos - width // 3)
    frag = re.sub(r"\s+", " ", body[start:start + width]).strip()
    return ("…" if start else "") + frag + "…"


_FIND_EPILOG = """\
rank / score lines:
  Every hit's headline number is `rank: N` — its 1-based position in the
  delivered list. It is the one scale comparable across a mixed-arm result,
  because it IS the list order, and it claims nothing about the two arms'
  raw scores being on one scale (D12: fuse_conditional hands the ranking to
  whichever arm owns it, it never blends the two by score). Those raw,
  non-comparable values stay out of the default output and show only with
  --breakdown, one `score:` line per hit naming which arm produced it:
    a/100        the FTS5/BM25 lexical arm, relative to this run's own top
                 hit.
    a/(6 * n)    the substring fallback used when no FTS index is available:
                 per query term 3 for a title hit, 2 for a tag hit, 1 for a
                 body hit, capped at one per field per term — so the maximum
                 is 6 * number of terms.
    cosine X.XX  the semantic arm's raw cosine similarity — printed on its
                 own line, not folded into an a/100 fraction, because that
                 shape would invite comparing it against a lexical score
                 (D12, same rule as above).
  `provenance:` names the arm that produced the line. Degradations (index
  absent or stale, embedding backend unavailable) are announced on stderr,
  one note per degraded arm.

filters:
  --where EXPR selects the concepts the answer may hold, whichever arm owns
  the ranking: the lexical, substring and semantic arms all apply it before
  the result is cut to --limit. Without `archived` in the expression,
  archived concepts are hidden; the semantic arm never covers them.
"""


def add_find_parser(sub):
    pf = _sub(sub, "find", "search",
              "hybrid ranked search: lexical FTS5/BM25 arm plus semantic arm",
              formatter_class=argparse.RawDescriptionHelpFormatter,
              epilog=_FIND_EPILOG)
    pf.add_argument("query", help="search terms; quote multi-word queries")
    pf.add_argument("--include-topics", action="store_true", help="widen beyond .okf.toml declared bundle to topic folders")
    pf.add_argument("--limit", type=int, default=10,
                    help="max results to print (default 10)")
    _add_filters(pf)
    pf.add_argument("--breakdown", action="store_true",
                    help="print per-hit contributing field(s)/term(s); "
                         "output is byte-identical to today without this flag")
    pf.add_argument("--expand-tags", action="store_true",
                    help="expand the query with semantically near registered "
                         "tags before lexical scoring; measured against the "
                         "full catalogue and found ineffective for the "
                         "vocabulary-mismatch class it was built for, so it "
                         "stays off by default (Q05/D17)")
    _add_output(pf)


COMMANDS = {"find": (cmd_find, add_find_parser)}
