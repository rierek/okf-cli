#!/usr/bin/env python3
"""Measure the top-1 cosine distribution of queries WITHOUT a target.

R34 rejected an absolute cosine floor on evidence gathered exclusively from
queries that HAVE a target in the catalogue. This measures the opposite
population, so that the two distributions can be compared and the cost of
every candidate threshold read off data instead of picked.

Ships no threshold and touches no production code (bean okf-cli-a4as).

Two mechanisms are scored against the SAME numbers, because their cost
functions differ:

  (a) suppressing floor  — a candidate below the floor is not a hit at all.
      A false trigger costs a RESULT.
  (b) confidence bar     — results are kept, a suggestion line is added when
      the best candidate sits below the bar. A false trigger costs one noisy
      LINE.

Per LL-14 the run counts its own invocations, so that a null result can be
distinguished from a mechanism that never ran.

Usage:
    python3 docs/okf-retrieval-architecture/eval/measure_negative.py \\
        --root ~/Obsidian/Knowledge-Catalogue \\
        --out negative_v1.json
"""
import argparse
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
CLI = os.path.join(REPO, "cli", "okf-cli.py")

FLOOR_LO, FLOOR_HI, FLOOR_STEP = 0.30, 0.65, 0.01

# Counters exist so a null result can be told apart from a mechanism that
# never ran (LL-14). Every one of these is asserted before any conclusion is
# printed.
COUNTS = {
    "queries_embedded": 0,
    "embed_cache_hits": 0,
    "concept_vectors_loaded": 0,
    "cosine_comparisons": 0,
    "floors_evaluated": 0,
}


def load_cli():
    """Import cli/okf-cli.py under a legal module name (the file has a dash)."""
    spec = importlib.util.spec_from_file_location("okf_cli", CLI)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def query_vectors(cli, queries, cache_path):
    """Embed every query once, persisted across runs — the API calls are the
    only part of this measurement that costs money, and the measurement is
    meant to be repeatable freely."""
    cache = {}
    if cache_path and os.path.isfile(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            cache = json.load(f)
    for q in queries:
        if q in cache:
            COUNTS["embed_cache_hits"] += 1
            continue
        cache[q] = cli._query_vector(q)
        COUNTS["queries_embedded"] += 1
    if cache_path:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    return cache


def top_scores(cli, concepts, qvec, target=None):
    """(top1_cosine, target_cosine, target_rank) for one query.

    target_cosine/target_rank are None when no target is given. Rank is
    1-based over the whole catalogue, not over a result window — the point is
    where the target sits in the raw semantic ordering.
    """
    scored = []
    for path, vec in concepts:
        scored.append((cli._cosine(qvec, vec), path))
        COUNTS["cosine_comparisons"] += 1
    scored.sort(reverse=True)
    top1 = scored[0][0] if scored else 0.0
    if target is None:
        return top1, None, None
    for rank, (score, path) in enumerate(scored, 1):
        if path == target:
            return top1, score, rank
    return top1, None, None


def pct(values, p):
    if not values:
        return None
    s = sorted(values)
    i = min(int(round(p / 100.0 * (len(s) - 1))), len(s) - 1)
    return s[i]


def distribution(label, values):
    return {
        "label": label,
        "n": len(values),
        "min": min(values) if values else None,
        "p05": pct(values, 5),
        "p25": pct(values, 25),
        "median": pct(values, 50),
        "p75": pct(values, 75),
        "p95": pct(values, 95),
        "max": max(values) if values else None,
    }


def tradeoff(neg_top1, pos_top1, pos_target_cos):
    """One row per candidate threshold, both mechanisms scored on it.

    suppressed        — negatives the mechanism catches (the benefit, shared)
    targets_lost      — mechanism (a): positives whose target drops below the
                        floor and stops being a hit
    noisy_lines       — mechanism (b): positives that would get a suggestion
                        line although the query is legitimate
    """
    rows = []
    f = FLOOR_LO
    while f <= FLOOR_HI + 1e-9:
        floor = round(f, 2)
        rows.append({
            "floor": floor,
            "suppressed": sum(1 for c in neg_top1 if c < floor),
            "suppressed_pct": round(
                sum(1 for c in neg_top1 if c < floor) / len(neg_top1), 4)
            if neg_top1 else None,
            "targets_lost": sum(1 for c in pos_target_cos
                                if c is not None and c < floor),
            "targets_missing_before": sum(1 for c in pos_target_cos
                                          if c is None),
            "noisy_lines": sum(1 for c in pos_top1 if c < floor),
        })
        COUNTS["floors_evaluated"] += 1
        f += FLOOR_STEP
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--positives", nargs="+",
                    default=["queries_v2.json", "queries_real.json"])
    ap.add_argument("--negatives", default="queries_negative.json")
    ap.add_argument("--vec-cache", default="_qvec_cache.json",
                    help="persisted query embeddings; delete to re-embed")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    root = os.path.abspath(os.path.expanduser(args.root))
    cli = load_cli()

    def resolve(p):
        return p if os.path.isabs(p) else os.path.join(HERE, p)

    positives = []
    for qf in args.positives:
        with open(resolve(qf), encoding="utf-8") as f:
            positives.extend(json.load(f))
    with open(resolve(args.negatives), encoding="utf-8") as f:
        negatives = json.load(f)

    concepts, _ = cli._load_concept_vectors(
        cli._tagvec_db_path(root), cli.SEMANTIC_MODEL)
    if not concepts:
        print("concept_emb is empty or absent — nothing to measure",
              file=sys.stderr)
        return 2
    COUNTS["concept_vectors_loaded"] = len(concepts)

    cache = query_vectors(
        cli, [r["query"] for r in positives + negatives],
        resolve(args.vec_cache))

    pos_rows = []
    for row in positives:
        top1, tgt, rank = top_scores(cli, concepts, cache[row["query"]],
                                     row["target"])
        pos_rows.append({"query": row["query"], "target": row["target"],
                         "top1_cosine": top1, "target_cosine": tgt,
                         "target_rank": rank})

    neg_rows = []
    for row in negatives:
        top1, _, _ = top_scores(cli, concepts, cache[row["query"]])
        neg_rows.append({"query": row["query"], "class": row.get("class"),
                         "top1_cosine": top1})

    neg_top1 = [r["top1_cosine"] for r in neg_rows]
    pos_top1 = [r["top1_cosine"] for r in pos_rows]
    pos_target = [r["target_cosine"] for r in pos_rows]

    rows_tradeoff = tradeoff(neg_top1, pos_top1, pos_target)

    # LL-14: prove the mechanism ran. A zero here means the numbers below are
    # meaningless, not that the effect is absent. Every counter is raised
    # before this point — the assertions come last on purpose.
    assert COUNTS["concept_vectors_loaded"] > 0, "no concept vectors loaded"
    assert COUNTS["cosine_comparisons"] > 0, "no cosine comparison performed"
    assert COUNTS["floors_evaluated"] > 0, "no floor evaluated"

    result = {
        "counts": COUNTS,
        "n_positive": len(pos_rows),
        "n_negative": len(neg_rows),
        "distributions": {
            "negative_top1": distribution("negative top-1", neg_top1),
            "negative_top1_hard": distribution(
                "hard negatives top-1",
                [r["top1_cosine"] for r in neg_rows
                 if r["class"] == "hard_negative"]),
            "negative_top1_nonsense": distribution(
                "nonsense top-1",
                [r["top1_cosine"] for r in neg_rows
                 if r["class"] == "nonsense"]),
            "positive_top1": distribution("positive top-1", pos_top1),
            "positive_target": distribution(
                "positive target", [c for c in pos_target if c is not None]),
        },
        "tradeoff": rows_tradeoff,
        "rows_negative": neg_rows,
        "rows_positive": pos_rows,
    }

    print(json.dumps(result["counts"], indent=2))
    print(json.dumps(result["distributions"], indent=2))
    if args.out:
        with open(resolve(args.out), "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print("wrote " + resolve(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
