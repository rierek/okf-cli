#!/usr/bin/env python3
"""Tests for cli/eval/runner.py — mechanical golden-file eval runner
(Modus A, Task 4 of docs/okf-revision/PLAN.md, bean okf-cli-o7z2).

Three tiers:
  * ParseFindBlocks — pure unit test against a canned find stdout string,
    no subprocess, no catalogue (fast, deterministic).
  * AggregateMetricsPureUnitTest (F01, Prelude 2026-07-25, bean
    okf-cli-5qmn) — pins the exact aggregation formula for all eight
    metrics against a hand-built per_row list. No subprocess, no
    catalogue, no golden.json — protects the numbers Task 5 is about to
    freeze from a silent formula regression.
  * Fixture-Tests (PickBundles, GoldenBundleConsistency,
    FixtureSpecGoldenAlignment) — isolierte tmpdirs, kein Live-Catalogue.

Run: python3 -m unittest cli.test_eval_runner -v
"""
import importlib.util
import json
import os
import shutil
import tempfile
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

    def test_parses_a_semantic_hits_cosine_score_line(self):
        """A semantic hit's score line is `score: cosine X.XX`, not the
        lexical arm's a/b fraction (okf-cli.py cmd_find) — the parser must
        recognize it rather than crash on int('cosine 0.40', base=10)."""
        stdout = (
            "------\n"
            "score: cosine 0.40\n"
            "title: Only\n"
            "type: Concept\n"
            "path: bundle/only\n"
            "description: d\n"
            "body-snippet: s\n"
            "provenance: semantic\n"
            "------\n"
        )
        hits = runner._parse_find_blocks(stdout)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["path"], "bundle/only")
        self.assertAlmostEqual(hits[0]["cosine"], 0.40)
        self.assertIsNone(hits[0]["score"])
        self.assertIsNone(hits[0]["max_score"])


class AggregateMetricsPureUnitTest(unittest.TestCase):
    """F01 (Prelude 2026-07-25, bean okf-cli-5qmn) — pins the exact
    aggregation formula for all eight metrics against a hand-built
    per_row list. No subprocess, no catalogue, no golden.json: this must
    keep passing even if the real catalogue or golden fixtures change."""

    # Splits are deliberately ASYMMETRIC (2/1, never 1/1): with a 50/50
    # split, inverting a predicate (rank == 1 -> rank != 1, correct ->
    # not correct, zero-hit -> non-zero-hit) yields the same mean and the
    # mutation passes undetected (LL-04, P12 prelude from P5 review).
    PER_ROW = [
        # find/literal (n=3, 2x rank-1 / 1x rank-4) -> recall_at_1,
        # recall_at_5, mrr, zero_hit_rate_literal, mean_score_ratio
        {"id": "lit-top1", "verb": "find", "class": "literal",
         "expect": "hit", "rank": 1, "score_ratio": 1.0, "correct": True},
        {"id": "lit-top1b", "verb": "find", "class": "literal",
         "expect": "hit", "rank": 1, "score_ratio": 0.55, "correct": True},
        {"id": "lit-rank4", "verb": "find", "class": "literal",
         "expect": "hit", "rank": 4, "score_ratio": 0.25, "correct": True},
        # find/paraphrase (n=3, 2x zero-hit / 1x rank-2)
        # -> zero_hit_rate_paraphrase
        {"id": "para-hit", "verb": "find", "class": "paraphrase",
         "expect": "miss", "rank": 2, "score_ratio": 0.5,
         "correct": False},
        {"id": "para-zero", "verb": "find", "class": "paraphrase",
         "expect": "miss", "rank": float("inf"), "score_ratio": 0.0,
         "correct": True},
        {"id": "para-zero-b", "verb": "find", "class": "paraphrase",
         "expect": "miss", "rank": float("inf"), "score_ratio": 0.0,
         "correct": True},
        # list/location (n=3, 2x correct / 1x wrong)
        # -> location_correct_rate
        {"id": "loc-correct", "verb": "list", "class": "location",
         "expect": "miss", "rank": float("inf"), "score_ratio": None,
         "correct": True},
        {"id": "loc-correct-b", "verb": "list", "class": "location",
         "expect": "miss", "rank": float("inf"), "score_ratio": None,
         "correct": True},
        {"id": "loc-wrong", "verb": "list", "class": "location",
         "expect": "miss", "rank": 1, "score_ratio": None,
         "correct": False},
        # list/metadata (n=3) -> metadata_hit_rate
        {"id": "meta-hit", "verb": "list", "class": "metadata",
         "expect": "hit", "rank": 1, "score_ratio": None,
         "correct": True},
        {"id": "meta-miss-correct", "verb": "list", "class": "metadata",
         "expect": "miss", "rank": float("inf"), "score_ratio": None,
         "correct": True},
        {"id": "meta-wrong", "verb": "list", "class": "metadata",
         "expect": "hit", "rank": float("inf"), "score_ratio": None,
         "correct": False},
        # index-walk row — present in per_row like every real golden
        # query, but must NOT be folded into any of the eight metrics
        # and must not crash aggregation.
        {"id": "idx-walk", "verb": "index", "class": "index-walk",
         "expect": "hit", "rank": 1, "score_ratio": None,
         "correct": True},
    ]

    def test_all_eight_metrics_match_hand_computed_values(self):
        metrics = runner.aggregate_metrics(self.PER_ROW)
        self.assertEqual(
            set(metrics.keys()),
            {
                "recall_at_1", "recall_at_5", "mrr",
                "zero_hit_rate_literal", "zero_hit_rate_paraphrase",
                "mean_score_ratio", "location_correct_rate",
                "metadata_hit_rate",
            },
        )
        self.assertEqual(metrics["recall_at_1"], 2.0 / 3.0)
        self.assertEqual(metrics["recall_at_5"], 1.0)
        self.assertEqual(metrics["mrr"], 0.75)
        self.assertEqual(metrics["zero_hit_rate_literal"], 0.0)
        self.assertEqual(metrics["zero_hit_rate_paraphrase"], 2.0 / 3.0)
        self.assertAlmostEqual(metrics["mean_score_ratio"], 0.6)
        self.assertEqual(metrics["location_correct_rate"], 2.0 / 3.0)
        self.assertEqual(metrics["metadata_hit_rate"], 2.0 / 3.0)


class PickBundlesTest(unittest.TestCase):
    """OKFT-sgkn AC-01/AC-02/AC-03/AC-06 — `_pick_bundles` pins the fixture
    bundle pair explicitly instead of deriving it from `list_bundles()`
    alphabetical order. Isolated tmpdir, no live catalogue, no subprocess."""

    def _make_root(self, names):
        root = tempfile.mkdtemp(prefix="okfeval-pickbundles-")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        for name in names:
            os.makedirs(os.path.join(root, name))
        return root

    def test_pins_correct_and_wrong_bundle_by_name(self):
        root = self._make_root([fixtures.CORRECT_BUNDLE, fixtures.WRONG_BUNDLE])
        self.assertEqual(
            fixtures._pick_bundles(root),
            (fixtures.CORRECT_BUNDLE, fixtures.WRONG_BUNDLE),
        )

    def test_ignores_alphabetically_earlier_bundle(self):
        # AC-03/AC-06: an extra bundle sorting before the pinned pair must
        # not shift the resolved pair — the historical defect (OKFT-sgkn)
        # was exactly this: "aca-okf" sorting before "agent-memory" bumped
        # S1 into the wrong bundle. "aaa-earlier-than-both" sorts before
        # both pinned names, so a sort-order-derived pick would return it
        # instead of at least one of them.
        root = self._make_root(
            ["aaa-earlier-than-both", fixtures.CORRECT_BUNDLE, fixtures.WRONG_BUNDLE]
        )
        self.assertEqual(
            fixtures._pick_bundles(root),
            (fixtures.CORRECT_BUNDLE, fixtures.WRONG_BUNDLE),
        )

    def test_raises_when_pinned_bundle_missing(self):
        # AC-02: only the correct bundle present, wrong bundle absent —
        # must fail loudly, never silently fall back to sort order.
        root = self._make_root([fixtures.CORRECT_BUNDLE])
        with self.assertRaises(RuntimeError):
            fixtures._pick_bundles(root)

    def test_raises_when_pinned_bundle_is_symlink(self):
        root = self._make_root([fixtures.CORRECT_BUNDLE])
        real_wrong = tempfile.mkdtemp(prefix="okfeval-wrong-target-")
        self.addCleanup(shutil.rmtree, real_wrong, ignore_errors=True)
        os.symlink(real_wrong, os.path.join(root, fixtures.WRONG_BUNDLE))
        with self.assertRaises(RuntimeError):
            fixtures._pick_bundles(root)


class GoldenBundleConsistencyTest(unittest.TestCase):
    """OKFT-sgkn AC-07 / D-sgkn-02 — golden.json's bundle-name literals
    (expected_path prefix, and the s4-index-walk row's query.bundle) are
    the second literal source the D-sgkn-02 interpretation leaves in
    place; this guard checks the FILE against fixtures.py's pinned
    constants (not the production function against the same constants it
    reads from — that would be tautological) so a one-sided drift between
    the two fails loudly instead of silently. Reads golden.json as data —
    no catalogue, no subprocess."""

    @staticmethod
    def _expected_bundle_for(row_id):
        # S2 is the deliberately-misplaced fixture (correct_bundle=False
        # in fixtures.py); every other scenario (S1/S3/S4) lives in the
        # correct bundle.
        return fixtures.WRONG_BUNDLE if row_id.startswith("s2") else fixtures.CORRECT_BUNDLE

    def test_golden_bundle_literals_match_fixtures_pin(self):
        with open(GOLDEN_PATH, encoding="utf-8") as f:
            golden = json.load(f)
        mismatches = []
        for row in golden:
            want = self._expected_bundle_for(row["id"])
            path_bundle = row["expected_path"].split("/", 1)[0]
            if path_bundle != want:
                mismatches.append((row["id"], "expected_path", path_bundle, want))
            query = row.get("query")
            if isinstance(query, dict) and "bundle" in query:
                if query["bundle"] != want:
                    mismatches.append((row["id"], "query.bundle", query["bundle"], want))
            # scope always names CORRECT_BUNDLE, also on S2 rows (location probe)
            if isinstance(query, dict) and "scope" in query:
                if query["scope"] != fixtures.CORRECT_BUNDLE:
                    mismatches.append((row["id"], "query.scope", query["scope"], fixtures.CORRECT_BUNDLE))
        self.assertEqual(
            mismatches, [],
            "golden.json bundle literal(s) diverge from fixtures.py pin "
            "(row id, field, got, want): {}".format(mismatches),
        )


class FixtureSpecGoldenAlignmentTest(unittest.TestCase):
    """OKFT-fivs — GoldenBundleConsistencyTest above only catches literal
    (golden.json) vs constant (fixtures.CORRECT_BUNDLE/WRONG_BUNDLE) drift;
    it never asks `_fixture_spec` where it actually PLACES each scenario.
    Changing S2's `format(wrong, ...)` to `format(correct, ...)` in
    `_fixture_spec` moves S2 into CORRECT_BUNDLE for real while leaving both
    shared constants and golden.json untouched — the guard above stays
    green. This test derives the real per-scenario placement from
    `_fixture_spec` itself and compares it against golden.json's
    expectation for the same scenario id directly, so that drift fails
    here too. Isolated tmpdir, no live catalogue, no subprocess."""

    def _make_root(self):
        root = tempfile.mkdtemp(prefix="okfeval-specgolden-")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        os.makedirs(os.path.join(root, fixtures.CORRECT_BUNDLE))
        os.makedirs(os.path.join(root, fixtures.WRONG_BUNDLE))
        return root

    def test_fixture_spec_placement_matches_golden_expectations(self):
        root = self._make_root()
        placements = {
            fx.sz.lower(): fx.rel_path.split("/", 1)[0]
            for fx in fixtures._fixture_spec(root)
        }
        with open(GOLDEN_PATH, encoding="utf-8") as f:
            golden = json.load(f)
        mismatches = []
        for row in golden:
            sz = row["id"].split("-", 1)[0]
            placed_bundle = placements[sz]
            path_bundle = row["expected_path"].split("/", 1)[0]
            if path_bundle != placed_bundle:
                mismatches.append((row["id"], "expected_path", path_bundle, placed_bundle))
            query = row.get("query")
            if isinstance(query, dict) and "bundle" in query:
                if query["bundle"] != placed_bundle:
                    mismatches.append((row["id"], "query.bundle", query["bundle"], placed_bundle))
        self.assertEqual(
            mismatches, [],
            "golden.json bundle literal(s) diverge from _fixture_spec's "
            "actual placement (row id, field, got, want): {}".format(mismatches),
        )


if __name__ == "__main__":
    unittest.main()
