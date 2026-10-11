#!/usr/bin/env python3
"""Tests for cli/okf/spec.py: the actor and datetime parsers, the trust tier and staleness
derivations. unittest.

Run: just test tests.test_okf_spec -v
"""
import datetime
import os
import sys
import unittest

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli")
if _HERE not in sys.path:  # cli/ holds the okf package
    sys.path.insert(0, _HERE)
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from okf import spec as okf_spec
from okf.catalogue import read_frontmatter

UTC = datetime.timezone.utc


def _loaded(yaml_text):
    """The frontmatter mapping of `yaml_text` as the reader loads it (ruamel types included)."""
    return read_frontmatter("---\n{}\n---\nbody\n".format(yaml_text)).data


class ParseActor(unittest.TestCase):
    """`parse_actor(value) -> (kind, text) | None` (OKF §7)."""

    def test_the_three_forms(self):
        table = [("claude-opus/4.1", ("producer", "claude-opus/4.1")),
                 ("gpt/5", ("producer", "gpt/5")),
                 ("human:erik", ("human", "erik")),
                 ("human:erik.riedel", ("human", "erik.riedel")),
                 ("process:nightly-build", ("process", "nightly-build"))]
        for value, want in table:
            with self.subTest(value):
                self.assertEqual(okf_spec.parse_actor(value), want)

    def test_anything_else_is_none(self):
        for value in ("erik", "", " ", "human:", "human: ", "process:", "/4.1", "claude/", " /",
                      " human:erik", "human:erik ", "Human:erik", "human", "team@example.org"):
            with self.subTest(value):
                self.assertIsNone(okf_spec.parse_actor(value))

    def test_non_strings_are_none(self):
        for value in (None, 5, 1.5, True, ["human:erik"], {"by": "human:erik"}):
            with self.subTest(repr(value)):
                self.assertIsNone(okf_spec.parse_actor(value))

    def test_loader_strings_parse_like_plain_ones(self):
        got = okf_spec.parse_actor(_loaded('by: "human:erik"')["by"])
        self.assertEqual(got, ("human", "erik"))
        self.assertIs(type(got[1]), str)


class ParseOkfDatetime(unittest.TestCase):
    """`parse_okf_datetime(value) -> aware datetime | None` (OKF §7): explicit UTC offset or None."""

    def test_strings_with_an_offset_parse_to_aware_instants(self):
        table = [("2026-06-20T22:53:05Z", datetime.datetime(2026, 6, 20, 22, 53, 5, tzinfo=UTC)),
                 ("2026-06-20T22:53:05+00:00", datetime.datetime(2026, 6, 20, 22, 53, 5, tzinfo=UTC)),
                 ("2026-06-21T00:53:05+02:00", datetime.datetime(2026, 6, 20, 22, 53, 5, tzinfo=UTC)),
                 ("2026-06-20T17:53:05-05:00", datetime.datetime(2026, 6, 20, 22, 53, 5, tzinfo=UTC)),
                 ("2026-06-20T22:53:05.250Z", datetime.datetime(2026, 6, 20, 22, 53, 5, 250000, tzinfo=UTC))]
        for text, want in table:
            with self.subTest(text):
                got = okf_spec.parse_okf_datetime(text)
                self.assertIsNotNone(got)
                self.assertIsNotNone(got.utcoffset())
                self.assertEqual(got, want)

    def test_offset_less_date_only_and_garbage_strings_are_none(self):
        for text in ("2026-06-20T22:53:05", "2026-06-20", "2026-06", "yesterday", "", " ",
                     "2026-06-20T22:53:05ZZ", " 2026-06-20T22:53:05Z"):
            with self.subTest(text):
                self.assertIsNone(okf_spec.parse_okf_datetime(text))

    def test_other_types_are_none(self):
        for value in (None, 5, 1.5, True, ["2026-06-20T22:53:05Z"], datetime.date(2026, 6, 20)):
            with self.subTest(repr(value)):
                self.assertIsNone(okf_spec.parse_okf_datetime(value))

    def test_datetime_objects_follow_the_same_rule(self):
        aware = datetime.datetime(2026, 6, 20, 22, 53, 5, tzinfo=UTC)
        self.assertEqual(okf_spec.parse_okf_datetime(aware), aware)
        self.assertIsNone(okf_spec.parse_okf_datetime(datetime.datetime(2026, 6, 20, 22, 53, 5)))

    def test_loader_resolved_values_match_their_quoted_twins(self):
        data = _loaded('plain: 2026-06-20T22:53:05+02:00\nquoted: "2026-06-20T22:53:05+02:00"\n'
                       'naive: 2026-06-20T22:53:05\nnaive_quoted: "2026-06-20T22:53:05"\n'
                       'day: 2026-06-20\nday_quoted: "2026-06-20"')
        parsed = {k: okf_spec.parse_okf_datetime(v) for k, v in data.items()}
        self.assertIsNotNone(parsed["plain"])
        self.assertEqual(parsed["plain"], parsed["quoted"])
        self.assertEqual([parsed[k] for k in ("naive", "naive_quoted", "day", "day_quoted")],
                         [None, None, None, None])

    def test_instants_compare_across_offsets_not_as_text(self):
        plus_two = okf_spec.parse_okf_datetime("2026-09-23T00:00:00+02:00")
        zulu = okf_spec.parse_okf_datetime("2026-09-23T00:00:00Z")
        self.assertLess(plus_two, zulu)


NOW = datetime.datetime(2026, 9, 23, 12, 0, 0, tzinfo=UTC)
AT = "2026-10-01T00:00:00Z"


class TrustTier(unittest.TestCase):
    """`trust_tier(fm)` (OKF §5.3): table over the cases R-14 names, `verified` is the only source."""

    TABLE = [
        ("no verified", "type: Note", "unverified"),
        ("empty list", "verified: []", "unverified"),
        ("entry without by", "verified: [{at: %s}]" % AT, "unverified"),
        ("not a mapping or list", "verified: yes", "unverified"),
        ("list of non-mappings", "verified: [a, b]", "unverified"),
        ("only non-human actors", "verified: [{by: claude/4, at: %s}, {by: 'process:ci', at: %s}]" % (AT, AT),
         "machine-confirmed"),
        ("one non-human actor", "verified: [{by: claude/4, at: %s}]" % AT, "machine-confirmed"),
        ("one human actor", "verified: [{by: 'human:erik', at: %s}]" % AT, "human-reviewed"),
        ("human among others", "verified: [{by: claude/4}, {by: 'human:erik'}, {by: 'process:ci'}]",
         "human-reviewed"),
        ("bare mapping, human", "verified: {by: 'human:erik', at: %s}" % AT, "human-reviewed"),
        ("bare mapping, non-human", "verified: {by: claude/4, at: %s}" % AT, "machine-confirmed"),
        ("by without a prefix is non-human", "verified: [{by: erik, at: %s}]" % AT, "machine-confirmed"),
        ("empty human id is no human", "verified: [{by: 'human:', at: %s}]" % AT, "machine-confirmed"),
        ("prefix is case-sensitive", "verified: [{by: 'Human:erik', at: %s}]" % AT, "machine-confirmed"),
        ("generated and timestamp are no source",
         "timestamp: 2020-01-01T00:00:00Z\ngenerated: {by: 'human:erik', at: %s}" % AT, "unverified"),
    ]

    def test_table(self):
        for label, yaml_text, want in self.TABLE:
            with self.subTest(label):
                self.assertEqual(okf_spec.trust_tier(_loaded(yaml_text)), want)

    def test_a_bare_mapping_gives_the_tier_of_a_one_element_list(self):
        for by in ("'human:erik'", "claude/4", "erik"):
            with self.subTest(by):
                bare = _loaded("verified: {by: %s, at: %s}" % (by, AT))
                listed = _loaded("verified: [{by: %s, at: %s}]" % (by, AT))
                self.assertEqual(okf_spec.trust_tier(bare), okf_spec.trust_tier(listed))

    def test_no_frontmatter_is_unverified(self):
        self.assertEqual(okf_spec.trust_tier(None), "unverified")


class Staleness(unittest.TestCase):
    """`is_stale(fm, now)` (OKF §5.5): `now >= stale_after`, `stale_after` is the only source."""

    def _stale(self, yaml_text, now=NOW):
        return okf_spec.is_stale(_loaded(yaml_text), now)

    def test_before_at_and_after_now(self):
        self.assertTrue(self._stale("stale_after: 2026-09-23T11:59:59Z"))
        self.assertTrue(self._stale("stale_after: 2026-09-23T12:00:00Z"))
        self.assertFalse(self._stale("stale_after: 2026-09-23T12:00:01Z"))

    def test_it_compares_instants_across_offsets(self):
        self.assertTrue(self._stale("stale_after: 2026-09-23T14:00:00+02:00"))   # 12:00Z, equal
        self.assertTrue(self._stale("stale_after: 2026-09-23T13:59:59+02:00"))
        self.assertFalse(self._stale("stale_after: 2026-09-23T14:00:01+02:00"))
        self.assertTrue(self._stale("stale_after: 2026-09-23T00:00:00+02:00"))   # before 00:00Z of that day
        self.assertFalse(self._stale("stale_after: 2026-09-23T00:00:00Z", now=datetime.datetime(
            2026, 9, 22, 23, 0, 0, tzinfo=UTC)))

    def test_a_quoted_value_gives_the_answer_of_the_unquoted_one(self):
        self.assertTrue(self._stale('stale_after: "2026-09-23T11:59:59Z"'))
        self.assertFalse(self._stale('stale_after: "2026-09-23T12:00:01Z"'))

    def test_absent_and_unparseable_values_are_not_stale(self):
        for yaml_text in ("type: Note", "stale_after:", "stale_after: soon", "stale_after: 2000-01-01",
                          "stale_after: 2000-01-01T00:00:00", "stale_after: '2000-01-01T00:00:00'",
                          "stale_after: [2000-01-01T00:00:00Z]"):
            with self.subTest(yaml_text):
                self.assertFalse(self._stale(yaml_text))

    def test_generated_timestamp_and_verified_are_no_fallback(self):
        self.assertFalse(self._stale("timestamp: 2000-01-01T00:00:00Z\ngenerated: {by: x/1, at: 2000-01-01T00:00:00Z}\n"
                                     "verified: {by: x/1, at: 2000-01-01T00:00:00Z}"))

    def test_no_frontmatter_is_not_stale(self):
        self.assertFalse(okf_spec.is_stale(None, NOW))


class TrustFields(unittest.TestCase):
    def test_the_two_keys_of_a_record(self):
        fm = _loaded("verified: {by: 'human:erik', at: %s}\nstale_after: 2000-01-01T00:00:00Z" % AT)
        self.assertEqual(okf_spec.trust_fields(fm, NOW), {"tier": "human-reviewed", "stale": True})
        self.assertEqual(okf_spec.trust_fields(None, NOW), {"tier": "unverified", "stale": False})


if __name__ == "__main__":
    unittest.main()
