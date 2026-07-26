#!/usr/bin/env python3
"""Re-measure the SHIPPED okf-cli find against the unbiased query set.

Unlike hybrid_eval.py (which re-implements the arms to compare fusion rules),
this runs the real CLI as a subprocess, so the number it prints is the number
users get. Metric shape matches eval_v2.json so it can be read next to R42.

Usage:
    python3 docs/okf-retrieval-architecture/eval/remeasure.py \\
        --root ~/Obsidian/Knowledge-Catalogue \\
        --queries queries_v2.json queries_real.json \\
        --out shipped_v2.json
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
CLI = os.path.join(REPO, "cli", "okf-cli.py")


def ranked_paths(root, query, limit):
    """Ordered result paths of one `okf-cli find`, plus its wall time."""
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable, CLI, "--root", root, "find", query,
         "--limit", str(limit)],
        capture_output=True, text=True)
    elapsed = time.time() - t0
    paths = [line[len("path: "):] for line in proc.stdout.splitlines()
             if line.startswith("path: ")]
    return paths, elapsed


def measure(root, rows, limit):
    """The query files use the keys "query", "target", "source" — verified in
    queries_v2.json and queries_real.json. `target` is the concept path."""
    ranks, times = [], []
    for row in rows:
        paths, elapsed = ranked_paths(root, row["query"], limit)
        times.append(elapsed)
        target = row["target"]
        ranks.append(paths.index(target) + 1 if target in paths else None)
    n = len(ranks) or 1
    hit = [r for r in ranks if r is not None]
    return {
        "n": len(ranks),
        "recall@1": sum(1 for r in hit if r == 1) / n,
        "recall@5": sum(1 for r in hit if r <= 5) / n,
        "recall@10": sum(1 for r in hit if r <= 10) / n,
        "mrr": sum(1.0 / r for r in hit) / n,
        "zero_hit": (len(ranks) - len(hit)) / n,
        "latency_p50": sorted(times)[len(times) // 2] if times else 0.0,
        "latency_max": max(times) if times else 0.0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--queries", nargs="+", required=True)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    root = os.path.abspath(os.path.expanduser(args.root))
    result = {}
    combined = []
    for qf in args.queries:
        path = qf if os.path.isabs(qf) else os.path.join(HERE, qf)
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)
        result[os.path.basename(path)] = measure(root, rows, args.limit)
        combined.extend(rows)
    result["combined"] = measure(root, combined, args.limit)

    print(json.dumps(result, indent=2))
    if args.out:
        out = args.out if os.path.isabs(args.out) else os.path.join(HERE, args.out)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
