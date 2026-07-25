#!/usr/bin/env python3
"""Tests for cli/eval/runner.py — mechanical golden-file eval runner
(Modus A, Task 4 of docs/okf-revision/PLAN.md, bean okf-cli-o7z2).

Two tiers:
  * ParseFindBlocks — pure unit test against a canned find stdout string,
    no subprocess, no catalogue (fast, deterministic).
  * RunnerAgainstRealCatalogue — seeds the real S1-S4 fixtures (D11:
    fixtures live in the real catalogue), runs run() against golden.json,
    tears down in a finally-block so a failed assertion never leaves
    residue.

Run: python3 -m unittest cli.test_eval_runner -v
"""
import importlib.util
import json
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))

_fx_spec = importlib.util.spec_from_file_location(
    "eval_fixtures", os.path.join(_HERE, "eval", "fixtures.py")
)
fixtures = importlib.util.module_from_spec(_fx_spec)
_fx_spec.loader.exec_module(fixtures)

_runner_spec = importlib.util.spec_from_file_location(
    "eval_runner", os.path.join(_HERE, "eval", "runner.py")
)
runner = importlib.util.module_from_spec(_runner_spec)
_runner_spec.loader.exec_module(runner)

CATALOGUE_ROOT = fixtures.DEFAULT_ROOT
GOLDEN_PATH = os.path.join(_HERE, "eval", "golden.json")


class ParseFindBlocksTest(unittest.TestCase):
    """Unit test — no subprocess, no real catalogue."""

    def test_parses_ranked_hits_in_order(self):
        stdout = (
            "------\n"
            "score: 6/6\n"
            "title: First\n"
            "type: Concept\n"
            "path: bundle/first\n"
            "description: d1\n"
            "body-snippet: s1\n"
            "------\n"
            "score: 3/6\n"
            "title: Second\n"
            "type: Concept\n"
            "path: bundle/second\n"
            "description: d2\n"
            "body-snippet: s2\n"
            "------\n"
        )
        hits = runner._parse_find_blocks(stdout)
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0]["rank"], 1)
        self.assertEqual(hits[0]["path"], "bundle/first")
        self.assertEqual(hits[0]["score"], 6)
        self.assertEqual(hits[0]["max_score"], 6)
        self.assertEqual(hits[1]["rank"], 2)
        self.assertEqual(hits[1]["path"], "bundle/second")

    def test_no_matches_output_parses_to_empty_list(self):
        hits = runner._parse_find_blocks("(no matches for: zzz)\n")
        self.assertEqual(hits, [])


class RunnerAgainstRealCatalogueTest(unittest.TestCase):
    """Integration — real catalogue, real subprocess boundary (SC-003)."""

    def setUp(self):
        self.assertTrue(
            os.path.isdir(CATALOGUE_ROOT),
            "real catalogue not found at {} — fixtures target the real "
            "catalogue by design (D11)".format(CATALOGUE_ROOT),
        )
        fixtures.teardown(CATALOGUE_ROOT)  # defensive pre-clean
        fixtures.seed(CATALOGUE_ROOT)
        self.result = runner.run(CATALOGUE_ROOT, GOLDEN_PATH)

    def tearDown(self):
        fixtures.teardown(CATALOGUE_ROOT)

    def _row(self, row_id):
        for r in self.result["per_row"]:
            if r["id"] == row_id:
                return r
        self.fail("row {} missing from per_row".format(row_id))

    def test_runner_scores_literal_s1_top1(self):
        """SC-001 / bean Step 1 — S1 literal row scores rank 1,
        recall_at_1 > 0."""
        row = self._row("s1-literal")
        self.assertEqual(row["rank"], 1)
        self.assertGreater(self.result["metrics"]["recall_at_1"], 0)

    def test_result_blob_has_all_eight_metrics_and_catalogue_rev(self):
        """SC-002."""
        expected_metrics = {
            "recall_at_1", "recall_at_5", "mrr",
            "zero_hit_rate_literal", "zero_hit_rate_paraphrase",
            "mean_score_ratio", "location_correct_rate", "metadata_hit_rate",
        }
        self.assertEqual(set(self.result["metrics"].keys()), expected_metrics)
        self.assertIsNotNone(self.result["catalogue_rev"])
        self.assertTrue(len(self.result["catalogue_rev"]) > 0)
        for row in self.result["per_row"]:
            self.assertIn("rank", row)

    def test_zero_hit_paraphrase_rows_get_rank_inf_never_crash(self):
        """Bean AC4 — zero hits never crash, rank recorded as inf."""
        row = self._row("s1-paraphrase")
        self.assertEqual(row["rank"], float("inf"))
        self.assertGreater(
            self.result["metrics"]["zero_hit_rate_paraphrase"], 0
        )

    def test_s2_location_row_scored_as_expected_miss(self):
        """PLAN.md Task 4 acceptance — list --scope row expected-miss folds
        into location_correct_rate."""
        row = self._row("s2-list-location-miss")
        self.assertTrue(row["correct"])
        self.assertEqual(self.result["metrics"]["location_correct_rate"], 1.0)

    def test_metadata_hit_and_miss_rows_scored_correct(self):
        """Ziel-3 list(type,tag) rows fold into metadata_hit_rate."""
        hit_row = self._row("s1-list-metadata-hit")
        miss_row = self._row("s4-list-metadata-miss")
        self.assertTrue(hit_row["correct"])
        self.assertTrue(miss_row["correct"])
        self.assertEqual(self.result["metrics"]["metadata_hit_rate"], 1.0)

    def test_index_walk_row_present_with_rank_no_dedicated_metric(self):
        """Prelude constraint — index-walk measured via --json only (no
        index.md assertion); per-row rank recorded but not folded into one
        of the eight metrics."""
        row = self._row("s4-index-walk")
        self.assertIn("rank", row)
        self.assertEqual(row["rank"], 1)


class MainCliTest(unittest.TestCase):
    """SC-003 / bean --out surface."""

    def setUp(self):
        fixtures.teardown(CATALOGUE_ROOT)
        fixtures.seed(CATALOGUE_ROOT)

    def tearDown(self):
        fixtures.teardown(CATALOGUE_ROOT)

    def test_main_writes_valid_json_result_file(self):
        out_path = os.path.join(_HERE, "eval", "_test_out.json")
        try:
            rc = runner.main([
                "--root", CATALOGUE_ROOT, "--golden", GOLDEN_PATH,
                "--out", out_path,
            ])
            self.assertEqual(rc, 0)
            with open(out_path, encoding="utf-8") as f:
                blob = json.load(f)
            self.assertIn("metrics", blob)
            self.assertIn("catalogue_rev", blob)
            self.assertIn("per_row", blob)
        finally:
            if os.path.isfile(out_path):
                os.remove(out_path)


if __name__ == "__main__":
    unittest.main()
