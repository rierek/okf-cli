"""Tests for cli/eval/gate.py — P12 regression gate (bean okf-cli-6gq6).

Pure unit tests against hand-built result blobs (no catalogue, no
subprocess except the CLI exit-code tests on temp files). Pins:
  - per-metric delta computation across all eight metrics
  - per-scenario delta rows (S1-S4 x literal/paraphrase)
  - verdict: FAIL if paraphrase zero-hit-rate did not decrease OR any
    literal S1 recall regressed (EARS, bean okf-cli-6gq6)
  - CLI exit codes: 0 on PASS, non-zero on FAIL
"""

import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
GATE_PATH = os.path.join(_HERE, "eval", "gate.py")

_spec = importlib.util.spec_from_file_location("gate", GATE_PATH)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def _blob(zero_para, s1_rank, extra_rows=None):
    """Minimal result blob in the runner.py output shape."""
    per_row = [
        {"id": "s1-literal", "verb": "find", "class": "literal",
         "expect": "hit", "rank": s1_rank, "score_ratio": 0.417,
         "correct": True},
        {"id": "s1-paraphrase", "verb": "find", "class": "paraphrase",
         "expect": "miss",
         "rank": float("inf") if zero_para >= 1.0 else 3,
         "score_ratio": 0.0, "correct": True},
    ] + (extra_rows or [])
    return {
        "catalogue_rev": "testrev",
        "metrics": {
            "recall_at_1": 0.75, "recall_at_5": 1.0, "mrr": 0.8125,
            "zero_hit_rate_literal": 0.0,
            "zero_hit_rate_paraphrase": zero_para,
            "mean_score_ratio": 0.396,
            "location_correct_rate": 1.0, "metadata_hit_rate": 1.0,
        },
        "per_row": per_row,
    }


class ComputeDeltaTest(unittest.TestCase):
    def test_per_metric_delta_covers_all_eight(self):
        base = _blob(zero_para=1.0, s1_rank=1)
        hyb = _blob(zero_para=0.25, s1_rank=1)
        hyb["metrics"]["mrr"] = 0.9
        deltas = gate.compute_metric_deltas(base, hyb)
        self.assertEqual(
            set(deltas.keys()), set(base["metrics"].keys()),
            "delta table must cover exactly the eight metrics")
        b, h, d = deltas["zero_hit_rate_paraphrase"]
        self.assertEqual((b, h), (1.0, 0.25))
        self.assertAlmostEqual(d, -0.75)
        self.assertAlmostEqual(deltas["mrr"][2], 0.9 - 0.8125)

    def test_per_scenario_delta_pairs_rows_by_id(self):
        base = _blob(zero_para=1.0, s1_rank=1)
        hyb = _blob(zero_para=0.0, s1_rank=1)
        hyb["per_row"][1]["rank"] = 3  # paraphrase rescued to rank 3
        rows = gate.compute_scenario_deltas(base, hyb)
        by_id = {r["id"]: r for r in rows}
        self.assertIn("s1-literal", by_id)
        self.assertIn("s1-paraphrase", by_id)
        self.assertEqual(by_id["s1-literal"]["rank_baseline"], 1)
        self.assertEqual(by_id["s1-literal"]["rank_hybrid"], 1)
        self.assertEqual(by_id["s1-paraphrase"]["rank_baseline"],
                         float("inf"))
        self.assertEqual(by_id["s1-paraphrase"]["rank_hybrid"], 3)


class VerdictTest(unittest.TestCase):
    def test_pass_when_paraphrase_down_and_s1_stable(self):
        ok, reasons = gate.verdict(_blob(1.0, 1), _blob(0.25, 1))
        self.assertTrue(ok, reasons)
        self.assertEqual(reasons, [])

    def test_fail_when_paraphrase_zero_hit_not_decreased(self):
        ok, reasons = gate.verdict(_blob(1.0, 1), _blob(1.0, 1))
        self.assertFalse(ok)
        self.assertTrue(any("paraphrase" in r for r in reasons), reasons)

    def test_fail_when_s1_literal_rank_regressed(self):
        ok, reasons = gate.verdict(_blob(1.0, 1), _blob(0.0, 2))
        self.assertFalse(ok)
        self.assertTrue(any("s1-literal" in r for r in reasons), reasons)

    def test_fail_reports_both_guards_together(self):
        ok, reasons = gate.verdict(_blob(1.0, 1), _blob(1.0, 4))
        self.assertFalse(ok)
        self.assertEqual(len(reasons), 2, reasons)


class GateCliTest(unittest.TestCase):
    """CLI boundary: exit 0 on PASS, non-zero on FAIL, delta table on
    stdout. inf ranks survive the JSON round-trip via the runner's own
    convention (json.dump writes Infinity, json.load reads it back)."""

    def _write(self, blob):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(blob, f)
        self.addCleanup(os.unlink, path)
        return path

    def _run(self, base_blob, hyb_blob):
        return subprocess.run(
            [sys.executable, GATE_PATH,
             "--baseline", self._write(base_blob),
             "--hybrid", self._write(hyb_blob)],
            capture_output=True, text=True)

    def test_exit_zero_and_table_on_pass(self):
        proc = self._run(_blob(1.0, 1), _blob(0.25, 1))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("zero_hit_rate_paraphrase", proc.stdout)
        self.assertIn("s1-literal", proc.stdout)
        self.assertIn("GATE: PASS", proc.stdout)

    def test_exit_nonzero_on_fail(self):
        proc = self._run(_blob(1.0, 1), _blob(1.0, 2))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("GATE: FAIL", proc.stdout)


if __name__ == "__main__":
    unittest.main()
