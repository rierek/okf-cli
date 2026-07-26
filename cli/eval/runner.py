#!/usr/bin/env python3
"""cli/eval/runner.py — mechanical golden-file eval runner (Modus A, Task 4
of docs/okf-revision/PLAN.md, bean okf-cli-o7z2).

Deterministic: invokes `find`/`list`/`index` against okf-cli.py via
subprocess (real process boundary — the same one the MCP wrapper
(mcp/okf_mcp.py) uses, so this runner doubles as a smoke test of that
path — PLAN.md Task 4 interface). For every cli/eval/golden.json row it
locates the expected concept in the verb's output, records a per-row
rank, then aggregates into the eight metrics EVAL-DESIGN.md + PLAN.md
Task 4 require:

    recall_at_1, recall_at_5, mrr                 — find rows, class=literal
    zero_hit_rate_literal, zero_hit_rate_paraphrase, mean_score_ratio
                                                    — find rows, split by class
    location_correct_rate                         — list rows, class=location (S2)
    metadata_hit_rate                              — list rows, class=metadata (Ziel-3)

index-walk rows (verb=index) still get a per-row rank like every other
golden query, but are NOT folded into an aggregate metric: the eight
metrics above are the exhaustive set the bean's EARS acceptance names,
and (per the 2026-07-25 P3-review prelude) index-walk correctness is
measured only via the `--json` surface, not via an index.md assertion —
there is no ninth "index_hit_rate" metric to fold it into.

Fixtures are TRANSIENT (cli/eval/fixtures.py) — callers seed() before a
run and teardown() after; this module does not seed/teardown itself so
callers (tests, Task 5's baseline freeze) control the window explicitly.

Usage:
    python3 runner.py --root <catalogue> --golden golden.json [--out results/x.json]
"""
import argparse
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
CLI_PATH = os.path.join(_HERE, "..", "okf-cli.py")

# Generous — a golden row's true rank must not be truncated by okf-cli's
# find default of --limit 10 (S3 alone expects rank 4, real-catalogue noise
# could push further).
FIND_LIMIT = 50


def _run_cli(root, argv):
    """Invoke okf-cli.py via subprocess (real process boundary — SC-003).
    Returns stdout text; raises on nonzero exit."""
    proc = subprocess.run(
        ["python3", CLI_PATH, "--root", root] + argv,
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "okf-cli.py {} failed (exit {}): {}".format(
                argv, proc.returncode, proc.stderr.strip()
            )
        )
    return proc.stdout


def _parse_find_blocks(stdout):
    """Parse the `------`-delimited find output (okf-cli.py:592-600) into an
    ordered list of {rank, path, score, max_score} — rank is the 1-based
    output position (= keyword rank, since find already sorts by -score)."""
    hits = []
    current = {}
    for line in stdout.splitlines():
        if line == "------":
            if current:
                hits.append(current)
                current = {}
            continue
        if line.startswith("score: "):
            achieved, _, mx = line[len("score: "):].partition("/")
            current["score"] = int(achieved)
            current["max_score"] = int(mx) if mx else 0
        elif line.startswith("path: "):
            current["path"] = line[len("path: "):]
    for i, h in enumerate(hits, start=1):
        h["rank"] = i
    return hits


def _score_find_row(root, row):
    out = _run_cli(root, ["find", row["query"], "--limit", str(FIND_LIMIT)])
    hits = _parse_find_blocks(out)
    for h in hits:
        if h["path"] == row["expected_path"]:
            ratio = (h["score"] / h["max_score"]) if h["max_score"] else 0.0
            return {"rank": h["rank"], "score_ratio": ratio}
    return {"rank": float("inf"), "score_ratio": 0.0}


def _score_list_row(root, row):
    q = row["query"]
    argv = ["list", "--json"]
    if q.get("type"):
        argv += ["--type", q["type"]]
    if q.get("tag"):
        argv += ["--tag", q["tag"]]
    if q.get("scope"):
        argv += ["--scope", q["scope"]]
    out = _run_cli(root, argv)
    entries = json.loads(out) if out.strip() else []
    hit = any(e.get("path") == row["expected_path"] for e in entries)
    return {"rank": 1 if hit else float("inf"), "score_ratio": None}


def _score_index_row(root, row):
    bundle = row["query"]["bundle"]
    out = _run_cli(root, ["index", bundle, "--json"])
    data = json.loads(out) if out.strip() else {}
    concepts = data.get("concepts", [])
    hit = any(
        "{}/{}".format(bundle, c.get("id")) == row["expected_path"]
        for c in concepts
    )
    return {"rank": 1 if hit else float("inf"), "score_ratio": None}


_SCORERS = {
    "find": _score_find_row,
    "list": _score_list_row,
    "index": _score_index_row,
}


def _mean(values):
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def _catalogue_rev(root):
    try:
        proc = subprocess.run(
            ["git", "-C", root, "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except FileNotFoundError:
        pass
    return None


def aggregate_metrics(per_row):
    """Pure aggregation of the eight metrics from a per_row list — no
    catalogue, golden.json, or subprocess involved. Extracted out of
    run() (F01, Prelude 2026-07-25, bean okf-cli-5qmn) so the exact
    formula can be pinned by a unit test against a hand-built per_row
    fixture, independent of the real catalogue/golden.json."""
    by_class = {}
    for r in per_row:
        by_class.setdefault((r["verb"], r["class"]), []).append(r)

    literal = by_class.get(("find", "literal"), [])
    paraphrase = by_class.get(("find", "paraphrase"), [])
    location = by_class.get(("list", "location"), [])
    metadata = by_class.get(("list", "metadata"), [])

    def is_zero_hit(r):
        return r["rank"] == float("inf")

    return {
        "recall_at_1": _mean(1.0 if r["rank"] == 1 else 0.0 for r in literal),
        "recall_at_5": _mean(1.0 if r["rank"] <= 5 else 0.0 for r in literal),
        "mrr": _mean(
            (1.0 / r["rank"]) if r["rank"] != float("inf") else 0.0
            for r in literal
        ),
        "zero_hit_rate_literal": _mean(
            1.0 if is_zero_hit(r) else 0.0 for r in literal
        ),
        "zero_hit_rate_paraphrase": _mean(
            1.0 if is_zero_hit(r) else 0.0 for r in paraphrase
        ),
        "mean_score_ratio": _mean(r["score_ratio"] for r in literal),
        "location_correct_rate": _mean(
            1.0 if r["correct"] else 0.0 for r in location
        ),
        "metadata_hit_rate": _mean(
            1.0 if r["correct"] else 0.0 for r in metadata
        ),
    }


def run(catalogue_root, golden_path):
    """Score every golden.json row against catalogue_root, aggregate the
    eight metrics (bean okf-cli-o7z2 AC1/SC-002). Returns the result blob:
    {catalogue_rev, per_row:[...], metrics:{...}}."""
    root = os.path.abspath(os.path.expanduser(catalogue_root))
    # The lexical arm is index-backed since D14; without a build here the
    # runner would score the substring fallback and report it as the shipped
    # behaviour. Local, no network, ~ms on a fixture catalogue.
    subprocess.run(
        ["python3", CLI_PATH, "--root", root, "build-index"],
        check=True, capture_output=True, text=True)
    with open(golden_path, encoding="utf-8") as f:
        golden = json.load(f)

    per_row = []
    for row in golden:
        outcome = _SCORERS[row["verb"]](root, row)
        actual_hit = outcome["rank"] != float("inf")
        expected_hit = row["expect"] == "hit"
        per_row.append({
            "id": row["id"],
            "verb": row["verb"],
            "class": row["class"],
            "expect": row["expect"],
            "rank": outcome["rank"],
            "score_ratio": outcome["score_ratio"],
            "correct": actual_hit == expected_hit,
        })

    return {
        "catalogue_rev": _catalogue_rev(root),
        "per_row": per_row,
        "metrics": aggregate_metrics(per_row),
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", required=True, help="catalogue root")
    p.add_argument("--golden", required=True, help="path to golden.json")
    p.add_argument("--out", help="write the machine-readable result blob here")
    args = p.parse_args(argv)

    result = run(args.root, args.golden)

    print("{:<26} {}".format("metric", "value"))
    print("-" * 34)
    for k, v in result["metrics"].items():
        print("{:<26} {:.3f}".format(k, v))
    print("-" * 34)
    print("catalogue_rev: {}".format(result["catalogue_rev"]))

    if args.out:
        out_dir = os.path.dirname(os.path.abspath(args.out))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print("wrote {}".format(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
