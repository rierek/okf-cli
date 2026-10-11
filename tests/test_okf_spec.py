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


if __name__ == "__main__":
    unittest.main()
