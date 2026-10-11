#!/usr/bin/env python3
"""Tests for `tier` and `stale` in the `--json` records of list, find, recent, index <bundle> and
read (OKFT-0hte), against a throwaway catalogue that is a git repository (recent needs one). unittest.

Run: just test tests.test_okf_trust_output -v
"""
import datetime
import os
import sys
import unittest
from unittest import mock

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli")
if _HERE not in sys.path:  # cli/ holds the okf package
    sys.path.insert(0, _HERE)
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from okf import fts as okf_fts
from okf import spec as okf_spec
from tests.okf_testkit import GitCatalogue, call_command, count_md_reads, run_cli, run_json

UTC = datetime.timezone.utc
HUMAN = ("title: Human\nverified: {by: 'human:erik', at: 2026-10-01T00:00:00Z}\n"
         "stale_after: 2000-01-01T00:00:00Z")
MACHINE = ("title: Machine\nverified: [{by: claude/4, at: 2026-10-01T00:00:00Z}]\n"
           "stale_after: 2999-01-01T00:00:00Z")
PLAIN = "title: Plain"
# path -> (tier, stale); v1 is a bundle without the v0.2 declaration, its concept reads the same
EXPECTED = {"b/human": ("human-reviewed", True), "b/machine": ("machine-confirmed", False),
            "b/plain": ("unverified", False), "v1/legacy": ("human-reviewed", True)}
FIXED_NOW = datetime.datetime(2026, 9, 23, 12, 0, 0, tzinfo=UTC)


class TrustOutputCase(GitCatalogue):
    def setUp(self):
        super().setUp()
        self._bundle()
        self._bundle(None, bundle="v1")
        for rel, front in (("b/human.md", HUMAN), ("b/machine.md", MACHINE), ("b/plain.md", PLAIN),
                           ("v1/legacy.md", HUMAN)):
            self._w(rel, "---\ntype: Note\n{}\n---\n# T\n\nneedle in the body\n".format(front))
        self._commit("add", "2026-01-01T00:00:00Z")

    def _derived(self, records, key):
        return {r[key]: (r.get("tier"), r.get("stale")) for r in records}


class JsonRecords(TrustOutputCase):
    """AC7 and AC8: every per-concept record of `data` carries `tier` and `stale`, in every bundle."""

    def test_list(self):
        envelope, _, code = run_json(self.tmp, "list", "--where", "type = Note")
        self.assertEqual(code, 0)
        self.assertEqual(self._derived(envelope["data"], "path"), EXPECTED)
        for record in envelope["data"]:
            self.assertEqual(set(record), {"title", "type", "path", "description", "tier", "stale"})
            self.assertIsInstance(record.get("stale"), bool)

    def test_find_through_the_full_scan_and_through_the_index(self):
        envelope, _, _ = run_json(self.tmp, "find", "needle")
        self.assertTrue([w for w in envelope["warnings"] if "build-index" in w], envelope["warnings"])
        self.assertEqual(self._derived(envelope["data"]["hits"], "path"), EXPECTED)
        okf_fts.build_fts_index(self.tmp)
        envelope, _, _ = run_json(self.tmp, "find", "needle")
        self.assertEqual([w for w in envelope["warnings"] if "build-index" in w], [])
        self.assertEqual(self._derived(envelope["data"]["hits"], "path"), EXPECTED)
        for record in envelope["data"]["hits"]:
            self.assertEqual(set(record), {"rank", "title", "type", "path", "description", "snippet",
                                           "provenance", "tier", "stale"})

    def test_recent(self):
        envelope, _, _ = run_json(self.tmp, "recent")
        self.assertEqual(self._derived(envelope["data"], "path"), EXPECTED)
        for record in envelope["data"]:
            self.assertEqual(set(record), {"created", "created_ts", "title", "type", "path",
                                           "description", "tier", "stale"})

    def test_recent_with_a_filter_reads_the_same_values(self):
        envelope, _, _ = run_json(self.tmp, "recent", "--where", "type = Note")
        self.assertEqual(self._derived(envelope["data"], "path"), EXPECTED)

    def test_index_of_a_bundle(self):
        envelope, _, _ = run_json(self.tmp, "index", "b")
        records = envelope["data"]["concepts"]
        self.assertEqual(self._derived(records, "id"), {k[2:]: v for k, v in EXPECTED.items() if k[0] == "b"})
        for record in records:
            self.assertEqual(set(record), {"id", "title", "type", "description", "tier", "stale"})
        envelope, _, _ = run_json(self.tmp, "index", "v1")
        self.assertEqual(self._derived(envelope["data"]["concepts"], "id"), {"legacy": EXPECTED["v1/legacy"]})

    def test_read(self):
        for path, (tier, stale) in EXPECTED.items():
            with self.subTest(path):
                envelope, _, _ = run_json(self.tmp, "read", path)
                self.assertEqual(set(envelope["data"]), {"path", "text", "tier", "stale"})
                self.assertEqual((envelope["data"].get("tier"), envelope["data"].get("stale")), (tier, stale))

    def test_read_with_a_narrowing_flag_derives_from_the_whole_frontmatter(self):
        envelope, _, _ = run_json(self.tmp, "read", "b/human", "--body-only")
        self.assertEqual((envelope["data"].get("tier"), envelope["data"].get("stale")), EXPECTED["b/human"])


class TextOutputUnchanged(TrustOutputCase):
    """AC9: no command's text output names the new keys."""

    def test_no_text_output_carries_tier_or_stale(self):
        for argv in (("list", "--where", "type = Note"), ("find", "needle"), ("recent",), ("index", "b")):
            with self.subTest(argv):
                out, _, code = run_cli(self.tmp, *argv)
                self.assertEqual(code, 0)
                self.assertNotIn("tier", out)
                self.assertNotIn("stale", out)

    def test_list_text_is_the_four_lines_per_concept_only(self):
        out, _, _ = run_cli(self.tmp, "list", "--where", "path = b/plain")
        self.assertEqual(out, "------\ntitle: Plain\ntype: Note\npath: b/plain\ndescription: \n"
                              "------\nlist: 1 concept(s)\n")

    def test_read_prints_the_file_as_before(self):
        out, _, _ = run_cli(self.tmp, "read", "b/human")
        with open(os.path.join(self.tmp, "b", "human.md"), encoding="utf-8") as f:
            self.assertEqual(out, f.read() + "\n")


class OneInstantPerCall(TrustOutputCase):
    """One `now` per call, taken in UTC, serves every record of it."""

    COMMANDS = {"list": ("list", "--where", "type = Note"), "find": ("find", "needle"), "recent": ("recent",),
                "index": ("index", "b"), "read": ("read", "b/human")}

    def test_every_command_asks_the_clock_once(self):
        okf_fts.build_fts_index(self.tmp)
        for name, argv in self.COMMANDS.items():
            with self.subTest(name), mock.patch.object(okf_spec, "utcnow", return_value=FIXED_NOW) as clock:
                call_command(self.tmp, *argv)
                self.assertEqual(clock.call_count, 1)

    def test_the_instant_of_the_call_decides_staleness_at_the_boundary(self):
        self._w("b/edge.md", "---\ntype: Note\nstale_after: 2026-09-23T12:00:00Z\n---\n# T\n\nneedle\n")
        self._commit("edge", "2026-01-02T00:00:00Z")
        before = FIXED_NOW - datetime.timedelta(seconds=1)
        for now, want in ((before, False), (FIXED_NOW, True)):
            with self.subTest(now=now), mock.patch.object(okf_spec, "utcnow", return_value=now):
                got = {r["path"]: r.get("stale") for r in call_command(self.tmp, "list", "--where", "path ~ b/edge")}
                self.assertEqual(got, {"b/edge": want})
                self.assertEqual(call_command(self.tmp, "read", "b/edge").get("stale"), want)


class NoSecondRead(TrustOutputCase):
    """Deriving the keys reads no concept file a second time."""

    def test_each_concept_file_is_read_at_most_once_per_call(self):
        okf_fts.build_fts_index(self.tmp)
        for argv in (("list", "--where", "type = Note"), ("find", "needle"), ("recent",),
                     ("recent", "--where", "type = Note"), ("index", "b"), ("read", "b/human")):
            with self.subTest(argv):
                seen = count_md_reads(self.tmp, *argv)
                self.assertTrue(seen)
                self.assertEqual(max(seen.values()), 1, dict(seen))

    def test_the_full_scan_arm_of_find_reads_each_file_once_too(self):
        seen = count_md_reads(self.tmp, "find", "needle")
        self.assertEqual((len(seen), max(seen.values())), (4, 1))


if __name__ == "__main__":
    unittest.main()
