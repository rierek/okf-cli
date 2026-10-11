#!/usr/bin/env python3
"""Tests for the `--where` fields of OKF v0.2: the pseudo-fields `tier` and `stale`, the dotted keys
through `verified` and `sources`, the `status` default and the instant comparisons (OKFT-g30y). unittest.

Run: just test tests.test_okf_where_spec -v
"""
import builtins
import collections
import contextlib
import datetime
import io
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
from okf.catalogue import read_frontmatter
from okf.errors import OkfError
from okf.find_filters import compile_where
from okf.parser import COMMAND_DISPATCH, build_parser
from okf.parser_support import subcommand_parsers
from tests.okf_testkit import GitCatalogue, run_json

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 9, 23, 12, 0, 0, tzinfo=UTC)
HUMAN_AT = "2026-10-01T00:00:00Z"

CONCEPTS = {
    "b/human": "verified: {by: 'human:erik', at: %s}\nstale_after: 2000-01-01T00:00:00Z\n"
               "generated: {by: claude/4, at: 2026-06-20T22:53:05Z}" % HUMAN_AT,
    "b/listed": "verified:\n  - {by: claude/4, at: 2026-09-01T00:00:00Z}\n"
                "  - {by: 'human:erik', at: '2026-10-05T00:00:00+02:00'}",
    "b/machine": "verified: [{by: claude/4, at: 2026-09-01T00:00:00Z}]\nstale_after: 2999-01-01T00:00:00Z",
    "b/plain": "title: Plain",
    "b/draft": "status: draft\nusage_window: {from: 2026-01-01T00:00:00Z, to: 2026-02-01T00:00:00Z}",
    "b/old": "status: deprecated\nstale_after: 2026-09-23T00:00:00+02:00",
    "b/sources": "sources:\n  - {resource: 'https://a.example/x', id: s1, last_modified: 2026-01-01T00:00:00Z,\n"
                 "     usage_window: {from: 2026-03-01T00:00:00Z, to: 2026-04-01T00:00:00Z}}\n"
                 "  - {resource: /b/other.md, id: s2, last_modified: '2026-05-01T00:00:00+02:00'}",
    "b/odd": "stale_after: soon\nverified: {by: 'human:erik'}",
}
FRONTMATTER = {path: read_frontmatter("---\n{}\n---\nbody\n".format(text)).data for path, text in CONCEPTS.items()}


def select(expression, now=NOW):
    """The concepts of CONCEPTS the expression selects, with the clock fixed at `now`."""
    with mock.patch.object(okf_spec, "utcnow", return_value=now):
        filters = compile_where(expression)
    return {path for path, fm in FRONTMATTER.items() if filters.matches_loaded(path, fm)}


def invalid(case, expression):
    with case.assertRaises(OkfError, msg=expression) as caught:
        compile_where(expression)
    case.assertEqual(caught.exception.kind, "invalid_input", expression)


class TierAndStale(unittest.TestCase):
    """AC1-AC4 of OKFT-g30y."""

    def test_tier_selects_exactly_the_concepts_of_that_tier(self):
        self.assertEqual(select("tier = human-reviewed"), {"b/human", "b/listed", "b/odd"})
        self.assertEqual(select("tier = machine-confirmed"), {"b/machine"})
        self.assertEqual(select("tier = unverified"), set(CONCEPTS) - {"b/human", "b/listed", "b/machine", "b/odd"})

    def test_tier_agrees_with_the_derivation_for_every_concept(self):
        for tier in ("unverified", "machine-confirmed", "human-reviewed"):
            with self.subTest(tier):
                want = {p for p, fm in FRONTMATTER.items() if okf_spec.trust_tier(fm) == tier}
                self.assertEqual(select("tier = " + tier), want)

    def test_not_equal_and_in_follow_from_equality(self):
        self.assertEqual(select("tier != unverified"), {"b/human", "b/listed", "b/machine", "b/odd"})
        self.assertEqual(select("tier in (machine-confirmed, human-reviewed)"),
                         {"b/human", "b/listed", "b/machine", "b/odd"})

    def test_stale_selects_exactly_the_concepts_whose_stale_after_has_passed(self):
        self.assertEqual(select("stale = true"), {"b/human", "b/old"})
        self.assertEqual(select("stale = false"), set(CONCEPTS) - {"b/human", "b/old"})
        self.assertEqual(select("stale != true"), set(CONCEPTS) - {"b/human", "b/old"})

    def test_stale_follows_the_clock_of_the_expression(self):
        edge = datetime.datetime(2026, 9, 22, 22, 0, 0, tzinfo=UTC)  # b/old's stale_after, exactly
        self.assertIn("b/old", select("stale = true", now=edge))
        self.assertNotIn("b/old", select("stale = true", now=edge - datetime.timedelta(seconds=1)))

    def test_one_clock_reading_serves_the_whole_expression(self):
        with mock.patch.object(okf_spec, "utcnow", return_value=NOW) as clock:
            filters = compile_where("stale = true or stale = false or tier = unverified")
            for path, fm in FRONTMATTER.items():
                filters.matches_loaded(path, fm)
        self.assertEqual(clock.call_count, 1)

    def test_values_outside_the_vocabulary_are_invalid_input(self):
        for expression in ("tier = human-reviwed", "tier = Human-Reviewed", "tier != reviewed",
                           "tier in (unverified, machine)", "tier = ''", "stale = yes", "stale = 1",
                           "stale = True", "stale != maybe", "stale in (true, maybe)"):
            with self.subTest(expression):
                invalid(self, expression)

    def test_operators_without_meaning_for_a_pseudo_field_are_invalid_input(self):
        for expression in ("tier ~ human", "tier < unverified", "tier >= unverified", "stale ~ true",
                           "stale > false"):
            with self.subTest(expression):
                invalid(self, expression)


class DottedKeysAndStatus(unittest.TestCase):
    """AC5-AC7 of OKFT-g30y."""

    def test_verified_by_matches_a_bare_mapping_and_a_list_alike(self):
        self.assertEqual(select("verified.by = human:erik"), {"b/human", "b/listed", "b/odd"})
        self.assertEqual(select("verified.by = claude/4"), {"b/listed", "b/machine"})

    def test_verified_at_matches_a_bare_mapping_and_a_list_alike(self):
        self.assertEqual(select("verified.at = 2026-10-01T00:00:00Z"), {"b/human"})
        self.assertEqual(select("verified.at >= 2026-10-01T00:00:00Z"), {"b/human", "b/listed"})

    def test_a_dotted_key_through_a_list_matches_when_any_element_does(self):
        self.assertEqual(select("verified.at > 2026-10-01T00:00:00Z"), {"b/listed"})   # element 2
        self.assertEqual(select("verified.at < 2026-09-02T00:00:00Z"), {"b/listed", "b/machine"})  # element 1
        self.assertEqual(select("sources.id = s2"), {"b/sources"})
        self.assertEqual(select("sources.resource = /b/other.md"), {"b/sources"})
        self.assertEqual(select("sources.resource = https://a.example/x"), {"b/sources"})

    def test_list_operators_follow_the_semantics_of_tag(self):
        self.assertEqual(select("sources.id in (s2, zz)"), {"b/sources"})
        self.assertEqual(select("sources.resource ~ example"), {"b/sources"})
        self.assertEqual(select("sources.resource ~ other"), {"b/sources"})
        self.assertEqual(select("sources.id != s1"), set(CONCEPTS) - {"b/sources"})  # the negation of =
        self.assertEqual(select("verified.by != claude/4"), set(CONCEPTS) - {"b/listed", "b/machine"})

    def test_an_absent_key_matches_nothing_but_not_equal(self):
        self.assertEqual(select("sources.resource = nothing"), set())
        self.assertEqual(select("sources.id != nothing"), set(CONCEPTS))

    def test_an_absent_status_is_stable(self):
        self.assertEqual(select("status = stable"), set(CONCEPTS) - {"b/draft", "b/old"})
        self.assertEqual(select("status != stable"), {"b/draft", "b/old"})
        self.assertEqual(select("status = draft"), {"b/draft"})
        self.assertEqual(select("status in (draft, deprecated)"), {"b/draft", "b/old"})

    def test_an_explicit_status_is_unchanged(self):
        fm = read_frontmatter("---\nstatus: stable\n---\n").data
        self.assertTrue(compile_where("status = stable").matches_loaded("b/x", fm))
        fm = read_frontmatter("---\nstatus: active\n---\n").data
        self.assertTrue(compile_where("status = active").matches_loaded("b/x", fm))
        self.assertFalse(compile_where("status = stable").matches_loaded("b/x", fm))


class InstantComparison(unittest.TestCase):
    """AC8 and AC9 of OKFT-g30y: timestamps compare as instants."""

    def test_stale_after_compares_across_offsets_with_all_six_operators(self):
        # b/old: 2026-09-23T00:00:00+02:00 is 2026-09-22T22:00:00Z
        table = [("=", "'2026-09-22T22:00:00Z'", True), ("=", "'2026-09-23T00:00:00Z'", False),
                 ("!=", "'2026-09-22T22:00:00Z'", False), ("!=", "'2026-09-23T00:00:00Z'", True),
                 ("<", "2026-09-23T00:00:00Z", True), ("<", "2026-09-22T22:00:00Z", False),
                 ("<=", "2026-09-22T22:00:00Z", True), ("<=", "2026-09-22T21:59:59Z", False),
                 (">", "2026-09-22T21:59:59Z", True), (">", "2026-09-22T22:00:00Z", False),
                 (">=", "2026-09-22T22:00:00Z", True), (">=", "2026-09-22T22:00:01Z", False)]
        for op, literal, want in table:
            with self.subTest(op=op, literal=literal):
                self.assertEqual("b/old" in select("stale_after {} {}".format(op, literal)), want)

    def test_the_offset_in_the_literal_counts(self):
        # 00:00+02:00 is before 00:00Z of the same day, whatever the text order says
        self.assertIn("b/old", select("stale_after < '2026-09-23T00:00:00Z'"))
        self.assertNotIn("b/old", select("stale_after > '2026-09-23T00:00:00Z'"))
        self.assertIn("b/old", select("stale_after = '2026-09-23T00:00:00+02:00'"))
        self.assertIn("b/old", select("stale_after = '2026-09-22T17:00:00-05:00'"))

    def test_every_timestamp_field_compares_as_an_instant(self):
        table = [("generated.at", "= 2026-06-20T22:53:05Z", "b/human"),
                 ("generated.at", "< 2026-06-20T22:53:06Z", "b/human"),
                 ("verified.at", "= 2026-10-01T00:00:00Z", "b/human"),
                 ("usage_window.from", "= '2026-01-01T02:00:00+02:00'", "b/draft"),
                 ("usage_window.to", "< 2026-02-02T00:00:00Z", "b/draft"),
                 ("sources.last_modified", "= '2026-05-01T00:00:00+02:00'", "b/sources"),
                 ("sources.last_modified", "= '2026-04-30T22:00:00Z'", "b/sources"),
                 ("sources.last_modified", "= 2026-01-01T00:00:00Z", "b/sources"),
                 ("sources.usage_window.from", "= '2026-03-01T01:00:00+01:00'", "b/sources"),
                 ("sources.usage_window.to", "= '2026-04-01T02:00:00+02:00'", "b/sources")]
        for field, tail, path in table:
            with self.subTest(field=field, tail=tail):
                self.assertIn(path, select("{} {}".format(field, tail)))

    def test_in_matches_an_instant_with_any_literal_not_just_the_first(self):
        # b/old: 2026-09-23T00:00:00+02:00 is 2026-09-22T22:00:00Z
        self.assertEqual(select("stale_after in (2000-01-01T00:00:00Z, '2026-09-22T22:00:00Z')"), {"b/human", "b/old"})
        self.assertEqual(select("stale_after in ('2026-09-22T23:00:00+01:00', 2000-01-01T00:00:00Z)"), {"b/human", "b/old"})
        self.assertEqual(select("stale_after in (2001-01-01T00:00:00Z, 2002-01-01T00:00:00Z)"), set())

    def test_quoted_and_unquoted_stored_values_answer_alike(self):
        # b/listed holds an unquoted Z instant and a quoted +02:00 one
        self.assertEqual(select("verified.at = '2026-10-04T22:00:00Z'"), {"b/listed"})
        self.assertEqual(select("verified.at = 2026-09-01T00:00:00Z"), {"b/listed", "b/machine"})

    def test_a_stored_value_that_is_no_instant_matches_no_comparison_but_not_equal(self):
        # b/odd: stale_after: soon
        for op in ("=", "<", "<=", ">", ">="):
            with self.subTest(op):
                self.assertNotIn("b/odd", select("stale_after {} 2026-09-23T00:00:00Z".format(op)))
        self.assertIn("b/odd", select("stale_after != 2026-09-23T00:00:00Z"))

    def test_a_literal_that_is_no_instant_with_an_offset_is_invalid_input(self):
        for literal in ("2026-09-23", "2026-09-23T00:00:00", "soon", "'2026-09-23 00:00'", "5", "''"):
            for field in ("stale_after", "generated.at", "verified.at", "usage_window.from",
                          "usage_window.to", "sources.last_modified"):
                with self.subTest(field=field, literal=literal):
                    invalid(self, "{} < {}".format(field, literal))
        invalid(self, "stale_after in (2026-09-23T00:00:00Z, soon)")
        invalid(self, "stale_after != 2026-09-23")

    def test_a_substring_match_on_a_timestamp_is_invalid_input(self):
        invalid(self, "generated.at ~ 2026")
        invalid(self, "stale_after ~ 2026-09-23T00:00:00Z")

    def test_other_dotted_keys_keep_their_text_comparison(self):
        fm = read_frontmatter("---\nowner: {name: erik}\ncount: 12\n---\n").data
        self.assertTrue(compile_where("owner.name = erik").matches_loaded("b/x", fm))
        self.assertTrue(compile_where("count > 9").matches_loaded("b/x", fm))


class OneFilterPath(unittest.TestCase):
    """AC10 and AC11: the fields enter through `--where` and nowhere else."""

    def test_no_command_has_a_tier_or_stale_flag(self):
        for name, parser in subcommand_parsers(build_parser()).items():
            flags = {flag for action in parser._actions for flag in action.option_strings}
            self.assertFalse(flags & {"--tier", "--stale"}, name)

    def test_the_where_help_of_every_filter_command_names_the_new_fields(self):
        for name in ("find", "list", "recent"):
            where = next(a for a in subcommand_parsers(build_parser())[name]._actions
                         if "--where" in a.option_strings)
            for phrase in ("tier (unverified, machine-confirmed or human-reviewed)", "stale (true or false)",
                           "status (an absent status is stable)", "verified.by", "sources.resource",
                           "compare as instants"):
                with self.subTest(command=name, phrase=phrase):
                    self.assertIn(phrase, where.help)


class EndToEnd(GitCatalogue):
    """SC-01 to SC-03 through the commands, on a catalogue that is a git repository."""

    def setUp(self):
        super().setUp()
        self._bundle()
        for path, front in CONCEPTS.items():
            self._w(path + ".md", "---\ntype: Note\n{}\n---\n# T\n\nneedle in the body\n".format(front))
        self._commit("add", "2026-01-01T00:00:00Z")

    def _paths(self, *argv):
        envelope, _, code = run_json(self.tmp, *argv)
        self.assertEqual(code, 0, envelope["error"])
        data = envelope["data"]
        records = data["hits"] if isinstance(data, dict) else data
        return {r["path"] for r in records}

    def test_list_by_tier_and_by_staleness(self):
        self.assertEqual(self._paths("list", "--where", "tier = human-reviewed"),
                         {"b/human", "b/listed", "b/odd"})
        self.assertEqual(self._paths("list", "--where", "stale = true"), {"b/human", "b/old"})

    def test_list_by_verifier_finds_the_bare_and_the_listed_form(self):
        self.assertEqual(self._paths("list", "--where", "verified.by = human:erik"),
                         {"b/human", "b/listed", "b/odd"})

    def test_a_typo_in_a_tier_exits_2_with_invalid_input_for_every_filter_command(self):
        for argv in (("list",), ("find", "needle"), ("recent",)):
            with self.subTest(argv):
                envelope, _, code = run_json(self.tmp, *argv, "--where", "tier = human-reviwed")
                self.assertEqual((code, envelope["error"]["kind"]), (2, "invalid_input"))

    def test_find_and_recent_filter_by_tier_and_staleness(self):
        for arm in ("full scan", "index"):
            if arm == "index":
                okf_fts.build_fts_index(self.tmp)
            with self.subTest(arm):
                self.assertEqual(self._paths("find", "needle", "--where", "tier = machine-confirmed"),
                                 {"b/machine"})
                self.assertEqual(self._paths("find", "needle", "--where", "stale = true"), {"b/human", "b/old"})
        self.assertEqual(self._paths("recent", "--where", "tier = machine-confirmed"), {"b/machine"})
        self.assertEqual(self._paths("recent", "--where", "stale = true"), {"b/human", "b/old"})

    def test_a_filter_on_the_new_fields_reads_each_file_once(self):
        # no index here: the full scan is the arm whose one read feeds predicate and record alike
        for argv in (("list", "--where", "tier = human-reviewed and stale = true"),
                     ("find", "needle", "--where", "tier = human-reviewed"),
                     ("recent", "--where", "stale = false")):
            with self.subTest(argv):
                real, seen = builtins.open, collections.Counter()

                def spy(file, *a, **k):
                    if isinstance(file, str) and file.startswith(self.tmp) and file.endswith(".md"):
                        seen[file] += 1
                    return real(file, *a, **k)

                args = build_parser().parse_args(["--root", self.tmp, *argv, "--json"])
                with mock.patch("builtins.open", spy), contextlib.redirect_stderr(io.StringIO()):
                    COMMAND_DISPATCH[args.cmd](self.tmp, args)
                self.assertTrue(seen)
                self.assertEqual(max(seen.values()), 1, dict(seen))

    def test_a_list_call_reads_the_clock_once_for_filter_and_records(self):
        args = build_parser().parse_args(["--root", self.tmp, "list", "--where", "stale = true", "--json"])
        with mock.patch.object(okf_spec, "utcnow", return_value=NOW) as clock:
            records = COMMAND_DISPATCH["list"](self.tmp, args)
        self.assertEqual((clock.call_count, {r["path"] for r in records}), (1, {"b/human", "b/old"}))

    def test_find_reads_the_clock_once_through_the_index_arm_and_the_full_scan_arm(self):
        for arm in ("full scan", "index"):
            if arm == "index":
                okf_fts.build_fts_index(self.tmp)
            args = build_parser().parse_args(["--root", self.tmp, "find", "needle", "--where",
                                              "stale = true", "--json"])
            with self.subTest(arm), mock.patch.object(okf_spec, "utcnow", return_value=NOW) as clock, \
                    contextlib.redirect_stderr(io.StringIO()):
                data = COMMAND_DISPATCH["find"](self.tmp, args)
            self.assertEqual((clock.call_count, {h["path"] for h in data["hits"]}), (1, {"b/human", "b/old"}))


if __name__ == "__main__":
    unittest.main()
