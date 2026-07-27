#!/usr/bin/env python3
"""Throwaway: measure the ARCHITECTURE, not just the arms.

okf-cli already has the hybrid shape (keyword primary + semantic backstop on
a weak/zero result, R04). The arms measured so far only tell us how each half
performs alone. This measures the composition, with the lexical half upgraded
to FTS5/BM25:

  H = FTS5(porter+prefix) primary
      -> backstop fires on zero hits OR when top-1 lacks a clear margin
      -> FTS top-1 stays pinned at rank 1 (the invariant okf-cli already has)

Reported next to its own two halves so the composition is judged against
what it is made of, not against nothing.
"""
import argparse
import json
import os
import re
import sqlite3
import struct
import sys
import urllib.request

import numpy as np

REPO = "/Users/erik/dev/okf-tools"
sys.path.insert(0, os.path.join(REPO, "cli", "embeddings"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fts_arm  # noqa: E402

MARGIN = 0.5      # mirrors SEMANTIC_MARGIN_RATIO in cli/okf-cli.py
WORD = re.compile(r"[^\wäöüÄÖÜß]+")


def fts_ranking(conn, query, limit):
    """[(path, positive_score)] — bm25() returns lower-is-better, so it is
    negated into a comparable positive score."""
    terms = [t for t in WORD.split(query.lower()) if len(t) > 1]
    if not terms:
        return []
    expr = " OR ".join('"{}"*'.format(t.replace('"', "")) for t in terms)
    try:
        rows = conn.execute(
            "SELECT path, bm25(docs, 0.0, 3.0, 2.0, 1.0) AS r FROM docs"
            " WHERE docs MATCH ? ORDER BY r LIMIT ?", (expr, limit)).fetchall()
    except sqlite3.OperationalError:
        return []
    return [(p, -r) for p, r in rows]


def load_arm(db, model):
    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT path, dim, vec FROM concept_emb WHERE model = ?",
                        (model,)).fetchall()
    conn.close()
    paths = [r[0] for r in rows]
    mat = np.array([struct.unpack("<{}f".format(d), v) for _p, d, v in rows],
                   dtype=np.float32)
    n = np.linalg.norm(mat, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return paths, mat / n


def embed(text, backend):
    if backend == "bge-m3":
        req = urllib.request.Request(
            "http://localhost:11434/api/embed",
            data=json.dumps({"model": "bge-m3", "input": text}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))["embeddings"][0]
    req = urllib.request.Request(
        "https://api.voyageai.com/v1/embeddings",
        data=json.dumps({"model": "voyage-3-large", "input": [text],
                         "input_type": "query"}).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + os.environ["VOYAGE_API_KEY"]})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))["data"][0]["embedding"]


def sem_ranking(qvec, arm, limit):
    paths, mat = arm
    q = np.asarray(qvec, dtype=np.float32)
    q = q / (np.linalg.norm(q) or 1.0)
    sims = mat @ q
    best = {}
    for p, c in zip(paths, sims):
        c = float(c)
        if c > best.get(p, -2.0):
            best[p] = c
    return sorted(best.items(), key=lambda kv: -kv[1])[:limit]


def fuse(fts, sem, limit):
    """FTS top-1 pinned; backstop only fires when the lexical result is empty
    or ambiguous. Returns (paths, fired)."""
    fired = False
    if not fts:
        fired = True
        return [p for p, _ in sem][:limit], fired
    if len(fts) == 1 or fts[0][1] < (1 + MARGIN) * fts[1][1]:
        fired = True
    if not fired:
        return [p for p, _ in fts][:limit], fired
    seen = {fts[0][0]}
    out = [fts[0][0]]
    rest = []
    top = fts[0][1] or 1.0
    for p, s in fts[1:]:
        rest.append((p, s / top))
    for p, c in sem:
        rest.append((p, c))
    rest.sort(key=lambda x: -x[1])
    for p, _ in rest:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out[:limit], fired


def fuse_rrf(fts, sem, limit, k=60):
    """Reciprocal Rank Fusion: score = sum 1/(k+rank) over both lists.

    The score-interleaving fusion above cannot rescue a lexical miss — a full
    BM25 list normalises to ~0.9 at rank 2 while a good cosine sits at ~0.6,
    so every semantic candidate lands behind every wrong keyword hit. RRF
    compares POSITIONS instead of incomparable score scales, which is exactly
    the mismatch that neutralises the backstop today."""
    scores = {}
    for rank, (p, _s) in enumerate(fts, 1):
        scores[p] = scores.get(p, 0.0) + 1.0 / (k + rank)
    for rank, (p, _c) in enumerate(sem, 1):
        scores[p] = scores.get(p, 0.0) + 1.0 / (k + rank)
    return [p for p, _ in sorted(scores.items(), key=lambda kv: -kv[1])][:limit]


def fuse_conditional(fts, sem, limit):
    """Conditional HANDOVER instead of blending.

    Measured on unbiased paraphrases, blending hurts: mixing a lexical list
    that is pure noise (zero-hit 1.000 there) into a working semantic list
    costs more than it adds, whether by score-interleaving or by RRF. But on
    literal queries the lexical arm is the better one. So: decide WHICH arm
    owns the ranking, per query, instead of averaging them.

    Rule: the lexical arm owns the result only when it is confident — a clear
    margin of top-1 over the runner-up. Otherwise the semantic arm owns it and
    the lexical hits are appended behind, never in front."""
    lex_confident = bool(fts) and (len(fts) == 1 or fts[0][1] >= (1 + MARGIN) * fts[1][1])
    primary = [p for p, _ in (fts if lex_confident else sem)]
    secondary = [p for p, _ in (sem if lex_confident else fts)]
    out, seen = [], set()
    for p in primary + secondary:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out[:limit], lex_confident


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Users/erik/Obsidian/Knowledge-Catalogue")
    ap.add_argument("--db", default="eval.sqlite")
    ap.add_argument("--fts-db", default="fts_hybrid.sqlite")
    ap.add_argument("--queries", nargs="+", required=True)
    ap.add_argument("--models", nargs="+",
                    default=["voyage-3-large+titlebody", "bge-m3+titlebody"])
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--out", default="hybrid_results.json")
    args = ap.parse_args()

    qs = []
    for f in args.queries:
        with open(f) as fh:
            qs += json.load(fh)

    conn, ndocs = fts_arm.build(args.fts_db, args.root, "porter")
    print("FTS5 index over {} docs".format(ndocs))
    arms = {m: load_arm(args.db, m) for m in args.models}
    for m in args.models:
        print("{}: {} vectors".format(m, len(arms[m][0])))

    rows, fired_count = [], {m: 0 for m in args.models}
    for i, q in enumerate(qs, 1):
        target, query = q["target"], q["query"]
        rec = {"query": query, "target": target, "source": q.get("source", "?"),
               "leaked": bool(q.get("leaked")), "arms": {}}
        fts = fts_ranking(conn, query, args.limit)
        fpaths = [p for p, _ in fts]
        rec["arms"]["L_fts5"] = {"rank": fpaths.index(target) + 1
                                 if target in fpaths else None}
        for m in args.models:
            backend = m.rsplit("+", 1)[0]
            qvec = embed(query, backend)
            sem = sem_ranking(qvec, arms[m], args.limit)
            spaths = [p for p, _ in sem]
            rec["arms"]["S_" + m] = {"rank": spaths.index(target) + 1
                                     if target in spaths else None}
            hy, fired = fuse(fts, sem, args.limit)
            fired_count[m] += int(fired)
            rec["arms"]["H_" + m] = {"rank": hy.index(target) + 1
                                     if target in hy else None,
                                     "backstop_fired": fired}
            rrf = fuse_rrf(fts, sem, args.limit)
            rec["arms"]["R_" + m] = {"rank": rrf.index(target) + 1
                                     if target in rrf else None}
            cond, lex_owned = fuse_conditional(fts, sem, args.limit)
            rec["arms"]["C_" + m] = {"rank": cond.index(target) + 1
                                     if target in cond else None,
                                     "lexical_owned": lex_owned}
        rows.append(rec)
        print("{:3d}/{} {:<38} {}".format(
            i, len(qs), query[:38],
            " ".join("{}={}".format(k[:22], v["rank"] or "-")
                     for k, v in rec["arms"].items())), flush=True)
    conn.close()

    def metrics(subset, arm):
        rk = [r["arms"][arm]["rank"] for r in subset]
        n = len(rk) or 1
        return {"n": len(rk),
                "recall@1": sum(1 for r in rk if r == 1) / n,
                "recall@5": sum(1 for r in rk if r and r <= 5) / n,
                "recall@10": sum(1 for r in rk if r and r <= 10) / n,
                "mrr": sum(1.0 / r for r in rk if r) / n,
                "zero_hit": sum(1 for r in rk if r is None) / n}

    subsets = {"all": rows}
    for src in sorted({r["source"] for r in rows}):
        subsets[src] = [r for r in rows if r["source"] == src]
    arm_names = list(rows[0]["arms"])
    summary = {name: {a: metrics(sub, a) for a in arm_names}
               for name, sub in subsets.items() if sub}
    with open(args.out, "w") as fh:
        json.dump({"summary": summary, "per_query": rows,
                   "backstop_fired": fired_count}, fh, indent=2, ensure_ascii=False)

    for name in summary:
        print("\n== {} (n={})".format(name, summary[name][arm_names[0]]["n"]))
        print("{:<30} {:>6} {:>6} {:>6} {:>6} {:>6}".format(
            "arm", "R@1", "R@5", "R@10", "MRR", "zero"))
        for a in arm_names:
            s = summary[name][a]
            print("{:<30} {:6.3f} {:6.3f} {:6.3f} {:6.3f} {:6.3f}".format(
                a, s["recall@1"], s["recall@5"], s["recall@10"], s["mrr"],
                s["zero_hit"]))
    print("\nbackstop fired: {} of {} queries".format(fired_count, len(rows)))
    print("wrote {}".format(args.out))


if __name__ == "__main__":
    main()
