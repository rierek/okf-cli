#!/usr/bin/env python3
"""cli/eval/gate.py — P12 regression gate (Task 12, bean okf-cli-6gq6).

Loads the frozen baseline result (Task 5, cli/eval/results/
baseline-<rev>.json — immutable, never regenerated) and a fresh hybrid
re-measurement (NEW file, baseline immutability), prints a per-metric
and per-scenario delta table, and enforces the WS1 direction:

    FAIL (exit non-zero) if
      - paraphrase zero-hit-rate did not decrease, OR
      - the literal S1 row regressed in rank (any literal S1 recall
        regression shows up as a worse rank for id "s1-literal").

Pure stdlib. The delta/verdict logic is importable and pinned by
cli/test_eval_gate.py against hand-built blobs.
"""

import argparse
import json


def load_result(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)  # json restores Infinity ranks natively


def compute_metric_deltas(baseline, hybrid):
    """{metric: (baseline, hybrid, delta)} across exactly the metrics
    present in the baseline blob (the eight, per runner.py)."""
    deltas = {}
    for name, base_val in baseline["metrics"].items():
        hyb_val = hybrid["metrics"][name]
        deltas[name] = (base_val, hyb_val, hyb_val - base_val)
    return deltas


def compute_scenario_deltas(baseline, hybrid):
    """Per-scenario rows paired by golden row id: rank baseline vs
    hybrid for every row present in both results."""
    hyb_by_id = {r["id"]: r for r in hybrid["per_row"]}
    rows = []
    for base_row in baseline["per_row"]:
        hyb_row = hyb_by_id.get(base_row["id"])
        if hyb_row is None:
            continue
        rows.append({
            "id": base_row["id"],
            "verb": base_row["verb"],
            "class": base_row["class"],
            "rank_baseline": base_row["rank"],
            "rank_hybrid": hyb_row["rank"],
        })
    return rows


def verdict(baseline, hybrid):
    """(ok, reasons). Guards per EARS (bean okf-cli-6gq6):
    paraphrase zero-hit-rate must DECREASE; literal S1 must not regress."""
    reasons = []

    base_zh = baseline["metrics"]["zero_hit_rate_paraphrase"]
    hyb_zh = hybrid["metrics"]["zero_hit_rate_paraphrase"]
    if not hyb_zh < base_zh:
        reasons.append(
            "paraphrase zero-hit-rate did not decrease "
            "(baseline {:.3f} -> hybrid {:.3f})".format(base_zh, hyb_zh))

    hyb_by_id = {r["id"]: r for r in hybrid["per_row"]}
    for base_row in baseline["per_row"]:
        if base_row["class"] != "literal":
            continue
        if not base_row["id"].startswith("s1-"):
            continue
        hyb_row = hyb_by_id.get(base_row["id"])
        if hyb_row is None or hyb_row["rank"] > base_row["rank"]:
            reasons.append(
                "literal S1 recall regressed: {} rank {} -> {}".format(
                    base_row["id"], base_row["rank"],
                    hyb_row["rank"] if hyb_row else "missing"))

    return (not reasons), reasons


def _fmt_rank(rank):
    return "inf" if rank == float("inf") else "{:g}".format(rank)


def print_report(baseline, hybrid):
    print("== per-metric delta (baseline -> hybrid) ==")
    print("{:<26} {:>9} {:>9} {:>9}".format(
        "metric", "baseline", "hybrid", "delta"))
    for name, (b, h, d) in compute_metric_deltas(baseline, hybrid).items():
        print("{:<26} {:>9.3f} {:>9.3f} {:>+9.3f}".format(name, b, h, d))

    print()
    print("== per-scenario delta (rank, baseline -> hybrid) ==")
    print("{:<24} {:<6} {:<11} {:>9} {:>9}".format(
        "id", "verb", "class", "baseline", "hybrid"))
    for row in compute_scenario_deltas(baseline, hybrid):
        print("{:<24} {:<6} {:<11} {:>9} {:>9}".format(
            row["id"], row["verb"], row["class"],
            _fmt_rank(row["rank_baseline"]), _fmt_rank(row["rank_hybrid"])))

    print()
    print("catalogue_rev: baseline={} hybrid={}".format(
        baseline.get("catalogue_rev"), hybrid.get("catalogue_rev")))


def main():
    ap = argparse.ArgumentParser(
        description="P12 regression gate: frozen baseline vs hybrid "
                    "re-measurement (exit non-zero on guard regression).")
    ap.add_argument("--baseline", required=True,
                    help="frozen baseline result json (Task 5)")
    ap.add_argument("--hybrid", required=True,
                    help="fresh hybrid result json (NEW file, Task 12)")
    args = ap.parse_args()

    baseline = load_result(args.baseline)
    hybrid = load_result(args.hybrid)

    print_report(baseline, hybrid)
    ok, reasons = verdict(baseline, hybrid)
    print()
    if ok:
        print("GATE: PASS")
        return 0
    print("GATE: FAIL")
    for reason in reasons:
        print("  - " + reason)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
