#!/usr/bin/env python3
"""Throwaway: measure the four retrieval arms against the ground-truth set.

  K  keyword   — today's okf-cli find (substring scoring), run as a subprocess
  A  title     — cosine vs bge-m3+title
  B  titlebody — cosine vs bge-m3+titlebody   (today's concept_text())
  C  chunk     — cosine vs bge-m3+chunk, aggregated max() per concept

Reports Recall@1/5/10, MRR and zero-hit rate per arm, plus the cosine
separation between the true target and the top non-target — the empirical
basis for the absolute floor the backstop currently lacks.
"""
import argparse
import json
import numpy as np
import os
import sqlite3
import struct
import subprocess
import sys
import urllib.request

REPO = "/Users/erik/dev/okf-tools"
CLI = os.path.join(REPO, "cli", "okf-cli.py")
EMBED_URL = "http://localhost:11434/api/embed"


def arms_in(db):
    """Every populated arm, discovered from the model column — so adding a
    backend (voyage) or a unit (chunk) needs no change here. A query must be
    embedded ONCE PER BACKEND: cosines are only comparable within one model's
    own vector space, never across models."""
    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT model, count(*), count(DISTINCT path) FROM concept_emb"
        " GROUP BY model ORDER BY model").fetchall()
    conn.close()
    return rows


def embed(text, model):
    if model == "bge-m3":
        req = urllib.request.Request(
            EMBED_URL,
            data=json.dumps({"model": "bge-m3", "input": text}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))["embeddings"][0]
    if model == "voyage-3-large":
        # input_type="query" is Voyage's asymmetric retrieval mode: documents
        # were embedded as "document", so the query side must declare itself
        # or the comparison silently loses the model's retrieval tuning.
        req = urllib.request.Request(
            "https://api.voyageai.com/v1/embeddings",
            data=json.dumps({"model": "voyage-3-large", "input": [text],
                             "input_type": "query"}).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + os.environ["VOYAGE_API_KEY"]})
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))["data"][0]["embedding"]
    raise ValueError(model)


def load_vectors(db, model):
    """(paths, L2-normalised matrix). Normalising once at load turns every
    later cosine into a single matrix-vector product — pure-Python cosine over
    13k x 1024 floats per arm per query would have dominated the runtime."""
    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT path, dim, vec FROM concept_emb WHERE model = ?", (model,)).fetchall()
    conn.close()
    paths = [r[0] for r in rows]
    mat = np.array([struct.unpack("<{}f".format(d), v) for _p, d, v in rows],
                   dtype=np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return paths, mat / norms


def keyword_ranking(root, query, limit):
    res = subprocess.run([sys.executable, CLI, "--root", root, "find", query,
                          "--limit", str(limit)],
                         capture_output=True, text=True)
    return [ln[6:].strip() for ln in res.stdout.splitlines() if ln.startswith("path: ")]


def vector_ranking(qvec, arm_data, limit):
    """max-pooled per concept path — the aggregation chunking needs, and a
    no-op for the single-vector arms. Returns (top-N list, {path: cosine})."""
    paths, mat = arm_data
    q = np.asarray(qvec, dtype=np.float32)
    q = q / (np.linalg.norm(q) or 1.0)
    sims = mat @ q
    best = {}
    for path, c in zip(paths, sims):
        c = float(c)
        if c > best.get(path, -2.0):
            best[path] = c
    ranked = sorted(best.items(), key=lambda kv: -kv[1])
    return ranked[:limit], best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Users/erik/Obsidian/Knowledge-Catalogue")
    ap.add_argument("--db", default="eval.sqlite")
    ap.add_argument("--queries", nargs="+", required=True)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--out", default="eval_results.json")
    args = ap.parse_args()

    qs = []
    for f in args.queries:
        with open(f) as fh:
            qs += json.load(fh)
    print("queries: {}".format(len(qs)))

    vecs, backend_of = {}, {}
    for arm, nvec, npath in arms_in(args.db):
        vecs[arm] = load_vectors(args.db, arm)
        backend_of[arm] = arm.rsplit("+", 1)[0]
        print("{:<26} {:6d} vectors over {:5d} concepts".format(arm, nvec, npath))
    ARMS = sorted(vecs)

    per_query = []
    for i, q in enumerate(qs, 1):
        target, query = q["target"], q["query"]
        rec = {"query": query, "target": target, "source": q.get("source", "?"),
               "leaked": bool(q.get("leaked")), "arms": {}}
        kw = keyword_ranking(args.root, query, args.limit)
        rec["arms"]["K_keyword"] = {"ranking": kw,
                                    "rank": kw.index(target) + 1 if target in kw else None,
                                    "target_score": None, "top_other_score": None}
        qvecs = {b: embed(query, b) for b in sorted(set(backend_of.values()))}
        for arm in ARMS:
            qvec = qvecs[backend_of[arm]]
            ranked, best = vector_ranking(qvec, vecs[arm], args.limit)
            paths = [p for p, _ in ranked]
            # target cosine even if it is outside the top-limit window
            tcos = best.get(target)
            other = next((c for p, c in ranked if p != target), None)
            rec["arms"][arm] = {
                "ranking": paths,
                "rank": paths.index(target) + 1 if target in paths else None,
                "target_score": tcos, "top_other_score": other}
        per_query.append(rec)
        marks = " ".join("{}={}".format(a[:14], rec["arms"][a]["rank"] or "-")
                         for a in ["K_keyword"] + ARMS)
        print("{:3d}/{} {:<40} {}".format(i, len(qs), query[:40], marks), flush=True)

    arms = ["K_keyword"] + ARMS

    def metrics(rows, arm):
        ranks = [r["arms"][arm]["rank"] for r in rows]
        n = len(ranks) or 1
        return {
            "n": len(ranks),
            "recall@1": sum(1 for r in ranks if r == 1) / n,
            "recall@5": sum(1 for r in ranks if r and r <= 5) / n,
            "recall@10": sum(1 for r in ranks if r and r <= 10) / n,
            "mrr": sum(1.0 / r for r in ranks if r) / n,
            "zero_hit": sum(1 for r in ranks if r is None) / n,
        }

    # Split the set: leaked/real-literal queries are the control group where
    # keyword MUST win; the clean paraphrases are the actual test.
    subsets = {
        "all": per_query,
        "generated_clean": [r for r in per_query
                            if r["source"] == "generated" and not r["leaked"]],
        "generated_leaked": [r for r in per_query
                             if r["source"] == "generated" and r["leaked"]],
        "real": [r for r in per_query if r["source"] == "real"],
    }
    summary = {name: {arm: metrics(rows, arm) for arm in arms}
               for name, rows in subsets.items() if rows}
    with open(args.out, "w") as fh:
        json.dump({"summary": summary, "per_query": per_query}, fh, indent=2,
                  ensure_ascii=False)

    for name in ["all", "real", "generated_clean", "generated_leaked"]:
        if name not in summary:
            continue
        print("\n== {} (n={})".format(name, summary[name][arms[0]]["n"]))
        print("{:<26} {:>6} {:>6} {:>6} {:>6} {:>6}".format(
            "arm", "R@1", "R@5", "R@10", "MRR", "zero"))
        for arm in arms:
            s = summary[name][arm]
            print("{:<26} {:6.3f} {:6.3f} {:6.3f} {:6.3f} {:6.3f}".format(
                arm, s["recall@1"], s["recall@5"], s["recall@10"], s["mrr"],
                s["zero_hit"]))
    print("\nwrote {}".format(args.out))


if __name__ == "__main__":
    main()
