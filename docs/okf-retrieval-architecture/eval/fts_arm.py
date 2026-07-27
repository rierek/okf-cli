#!/usr/bin/env python3
"""Throwaway: the lexical arm okf-cli never had.

Builds an sqlite FTS5 index over title/tags/body of the live catalogue and
ranks with BM25 (field weights mirroring today's 3/2/1 substring weights),
so Q02 — "how much do the zero-hits shrink from better KEYWORD retrieval
alone, before any embedding?" — is answered with a number instead of an
opinion. stdlib only, exactly like okf-cli.py itself.
"""
import argparse
import json
import os
import re
import sqlite3
import sys

REPO = "/Users/erik/dev/okf-tools"
sys.path.insert(0, os.path.join(REPO, "cli", "embeddings"))
import build_tagvec as bt  # noqa: E402

# unicode61 folds diacritics (ä/ö/ü, needed for a German catalogue). porter is
# an ENGLISH stemmer — it still helps mixed-language text on the English half
# and is a no-op-ish on German, which is itself part of the finding.
TOKENIZERS = {
    "plain": "unicode61 remove_diacritics 2",
    "porter": "porter unicode61 remove_diacritics 2",
}


def build(db, root, tokenizer):
    okf = bt._load_okf_cli()
    if os.path.exists(db):
        os.remove(db)
    conn = sqlite3.connect(db)
    conn.execute("CREATE VIRTUAL TABLE docs USING fts5("
                 "path UNINDEXED, title, tags, body, tokenize='{}')".format(
                     TOKENIZERS[tokenizer]))
    n = 0
    for path, ap in bt._iter_all_concepts(okf, root):
        raw = okf.read_file(ap)
        fm, body = okf.split_frontmatter(raw)
        title = okf._dequote(fm.get("title", "")) or path.rsplit("/", 1)[-1]
        tags = " ".join(okf.extract_tags(raw))
        conn.execute("INSERT INTO docs(path, title, tags, body) VALUES (?,?,?,?)",
                     (path, title, tags, body))
        n += 1
    conn.commit()
    return conn, n


def search(conn, query, limit, prefix=True):
    """OR over the query terms, each optionally as a prefix match. bm25()
    weights title:3 tags:2 body:1 — the same field ranking today's substring
    scorer uses, so the comparison isolates the retrieval model, not the
    weighting."""
    terms = [t for t in re.split(r"[^\wäöüÄÖÜß]+", query.lower()) if len(t) > 1]
    if not terms:
        return []
    expr = " OR ".join('"{}"{}'.format(t.replace('"', ""), "*" if prefix else "")
                       for t in terms)
    try:
        rows = conn.execute(
            "SELECT path, bm25(docs, 0.0, 3.0, 2.0, 1.0) AS r FROM docs"
            " WHERE docs MATCH ? ORDER BY r LIMIT ?", (expr, limit)).fetchall()
    except sqlite3.OperationalError:
        return []
    return [r[0] for r in rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Users/erik/Obsidian/Knowledge-Catalogue")
    ap.add_argument("--db", default="fts.sqlite")
    ap.add_argument("--queries", nargs="+", required=True)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--out", default="fts_results.json")
    args = ap.parse_args()

    qs = []
    for f in args.queries:
        with open(f) as fh:
            qs += json.load(fh)

    variants = {}
    for tok in ("plain", "porter"):
        for prefix in (False, True):
            name = "L_fts5_{}{}".format(tok, "_prefix" if prefix else "")
            conn, n = build(args.db, args.root, tok)
            ranks = []
            for q in qs:
                hits = search(conn, q["query"], args.limit, prefix)
                ranks.append({
                    "query": q["query"], "target": q["target"],
                    "source": q.get("source", "?"), "leaked": bool(q.get("leaked")),
                    "rank": hits.index(q["target"]) + 1 if q["target"] in hits else None})
            conn.close()
            variants[name] = ranks
            print("built {} over {} docs".format(name, n), flush=True)

    def metrics(rows):
        rk = [r["rank"] for r in rows]
        n = len(rk) or 1
        return {"n": len(rk),
                "recall@1": sum(1 for r in rk if r == 1) / n,
                "recall@5": sum(1 for r in rk if r and r <= 5) / n,
                "recall@10": sum(1 for r in rk if r and r <= 10) / n,
                "mrr": sum(1.0 / r for r in rk if r) / n,
                "zero_hit": sum(1 for r in rk if r is None) / n}

    subsets = {
        "all": lambda r: True,
        "real": lambda r: r["source"] == "real",
        "generated_clean": lambda r: r["source"] == "generated" and not r["leaked"],
        "generated_leaked": lambda r: r["source"] == "generated" and r["leaked"],
    }
    out = {}
    for sub, pred in subsets.items():
        out[sub] = {name: metrics([r for r in rows if pred(r)])
                    for name, rows in variants.items()}
        print("\n== {}".format(sub))
        print("{:<26} {:>6} {:>6} {:>6} {:>6} {:>6}".format(
            "arm", "R@1", "R@5", "R@10", "MRR", "zero"))
        for name in sorted(out[sub]):
            s = out[sub][name]
            print("{:<26} {:6.3f} {:6.3f} {:6.3f} {:6.3f} {:6.3f}".format(
                name, s["recall@1"], s["recall@5"], s["recall@10"], s["mrr"],
                s["zero_hit"]))
    with open(args.out, "w") as fh:
        json.dump({"summary": out, "per_query": variants}, fh, indent=2,
                  ensure_ascii=False)
    print("\nwrote {}".format(args.out))


if __name__ == "__main__":
    main()
