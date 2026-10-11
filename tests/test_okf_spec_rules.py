#!/usr/bin/env python3
"""Tests for the Trust, Lifecycle, Format and Attested Computation rules of `check` in bundles
declaring OKF v0.2. unittest.

Run: just test tests.test_okf_spec_rules -v
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

from okf import check as okf_check
from okf import spec as okf_spec
from tests.okf_testkit import DECLARE, SpecCase, run_json

FAMILIES = ("okf/trust/", "okf/lifecycle/", "okf/format/", "okf/computation/")
UTC = datetime.timezone.utc
GOOD_AT = "2026-06-20T22:53:05Z"
PAST = "2000-01-01T00:00:00Z"
FUTURE = "2999-01-01T00:00:00Z"


class RuleCase(SpecCase):
    """One bundle `b` with one concept `b/x.md` per assertion; GROUP names the family under test."""

    GROUP = ""

    def _hits(self, extra, group=None, front=DECLARE, type_="Note"):
        self._bundle(front)
        self._concept(extra, type_=type_)
        return self._group(group or self.GROUP)

    def _one(self, extra, severity="error", group=None, type_="Note"):
        """Exactly one finding of the family, on b/x.md, with `severity`; returns it."""
        hits = self._hits(extra, group, type_=type_)
        self.assertEqual([(f.severity, f.path) for f in hits], [(severity, "b/x.md")], hits)
        return hits[0]

    def _none(self, extra, group=None, type_="Note"):
        self.assertEqual(self._hits(extra, group, type_=type_), [])


class RegistryEntries(unittest.TestCase):
    def test_every_rule_of_the_four_families_is_a_gated_file_rule(self):
        rules = [r for r in okf_check.RULES if r.id.startswith(FAMILIES)]
        for family in FAMILIES:
            self.assertTrue([r for r in rules if r.id.startswith(family)], family)
        for rule in rules:
            self.assertEqual((rule.scope, rule.okf_version), ("file", "0.2"), rule.id)


class TrustRules(RuleCase):
    GROUP = "okf/trust/"

    def test_generated_that_is_not_a_mapping_is_an_error(self):
        for extra in ("generated: text", "generated: [a]", "generated: 5"):
            with self.subTest(extra):
                self._one(extra)

    def test_generated_without_a_non_empty_by_is_an_error(self):
        for body in ("{at: %s}" % GOOD_AT, '{by: "", at: %s}' % GOOD_AT, "{by: , at: %s}" % GOOD_AT,
                     "{by: [], at: %s}" % GOOD_AT, "{}"):
            with self.subTest(body):
                self._one("generated: " + body)

    def test_generated_with_by_passes_with_or_without_at(self):
        self._none("generated: {by: claude/4, at: %s}" % GOOD_AT)
        self._none("generated: {by: 'human:erik'}")

    def test_verified_that_is_neither_mapping_nor_list_of_mappings_is_an_error(self):
        for extra in ("verified: yes", "verified: [a, b]", "verified: 5", "verified: [[x]]"):
            with self.subTest(extra):
                self._one(extra)

    def test_verified_entry_without_by_or_at_is_an_error(self):
        entry = "{by: 'human:erik', at: %s}" % GOOD_AT
        for body in ("[{at: %s}]" % GOOD_AT, "[{by: 'human:erik'}]", "[%s, {by: 'human:erik'}]" % entry,
                     "{by: 'human:erik'}", "{at: %s}" % GOOD_AT, '[{by: "", at: %s}]' % GOOD_AT,
                     "[{by: 'human:erik', at: }]"):
            with self.subTest(body):
                self._one("verified: " + body)

    def test_each_defective_entry_gets_its_own_finding(self):
        hits = self._hits("verified:\n  - {by: 'human:erik'}\n  - {at: %s}" % GOOD_AT)
        self.assertEqual(len(hits), 2)

    def test_bare_verified_mapping_counts_as_a_one_element_list(self):
        bare = "verified: {by: 'human:erik', at: %s}" % GOOD_AT
        listed = "verified: [{by: 'human:erik', at: %s}]" % GOOD_AT
        self._bundle()
        for extra in (bare, listed):
            self._concept(extra)
            self.assertEqual(self._group("okf/"), [], extra)


class LifecycleRules(RuleCase):
    GROUP = "okf/lifecycle/"

    def test_status_outside_the_three_values_is_an_error(self):
        for extra in ("status: active", "status: Draft", "status: obsolete", 'status: ""',
                      "status:", "status: 5", "status: true"):
            with self.subTest(extra):
                self._one(extra)

    def test_the_three_statuses_and_an_absent_status_pass(self):
        for extra in ("status: draft", "status: stable", "status: deprecated", ""):
            with self.subTest(extra):
                self._none(extra)

    def test_passed_stale_after_is_a_warning(self):
        self._one("stale_after: " + PAST, "warning")
        self._one("stale_after: '%s'" % PAST, "warning")

    def test_future_stale_after_passes(self):
        self._none("stale_after: " + FUTURE)

    def test_unparseable_stale_after_is_no_lifecycle_finding(self):
        for value in ("2000-01-01T00:00:00", "2000-01-01", "soon", "'2000-01-01T00:00:00'"):
            with self.subTest(value):
                self._none("stale_after: " + value)

    def test_stale_after_equal_to_now_is_stale_and_one_second_later_is_not(self):
        now = datetime.datetime(2026, 9, 23, 12, 0, 0, tzinfo=UTC)
        with mock.patch.object(okf_spec, "utcnow", return_value=now):
            self._one("stale_after: 2026-09-23T12:00:00Z", "warning")
            self._none("stale_after: 2026-09-23T12:00:01Z")

    def test_stale_after_compares_as_an_instant_across_offsets(self):
        now = datetime.datetime(2026, 9, 22, 23, 0, 0, tzinfo=UTC)
        with mock.patch.object(okf_spec, "utcnow", return_value=now):
            # 00:00+02:00 is 22:00Z, before now; 00:00Z is after it.
            self._one("stale_after: 2026-09-23T00:00:00+02:00", "warning")
            self._none("stale_after: 2026-09-23T00:00:00Z")

    def test_one_instant_serves_every_comparison_of_a_run(self):
        self._bundle()
        self._bundle(bundle="c")
        for rel in ("b/1.md", "b/2.md", "c/3.md"):
            self._concept("stale_after: " + PAST, rel=rel)
        calls = []
        real = okf_spec.utcnow

        def counting():
            calls.append(real())
            return calls[-1]

        with mock.patch.object(okf_spec, "utcnow", counting):
            hits = [f for f in okf_check.run_checks(self.tmp, None) if f.rule.startswith(self.GROUP)]
        self.assertEqual((len(calls), len(hits)), (1, 3))

    def test_the_instant_is_taken_in_utc(self):
        self.assertEqual(okf_spec.utcnow().utcoffset(), datetime.timedelta(0))

    def test_a_passed_stale_after_exits_0_and_4_under_strict(self):
        self._bundle()
        self._concept("stale_after: " + PAST)
        envelope, _, code = run_json(self.tmp, "check", "b")
        self.assertEqual((code, [f["severity"] for f in envelope["data"]["findings"]]), (0, ["warning"]))
        envelope, _, code = run_json(self.tmp, "check", "b", "--strict")
        self.assertEqual((code, [f["severity"] for f in envelope["data"]["findings"]]), (4, ["warning"]))


class FormatRules(RuleCase):
    GROUP = "okf/format/"

    def test_an_actor_that_follows_no_form_is_a_format_error(self):
        self._one("generated: {by: erik, at: %s}" % GOOD_AT)
        self._one("generated: {by: 'human:', at: %s}" % GOOD_AT)
        self._one("verified: [{by: erik, at: %s}]" % GOOD_AT)
        self._one("verified: {by: 'process:', at: %s}" % GOOD_AT)

    def test_a_non_string_actor_is_one_format_finding_not_two(self):
        hits = self._hits("generated: {by: 5, at: %s}" % GOOD_AT, group="okf/")
        self.assertEqual([f.rule.startswith(self.GROUP) for f in hits], [True])

    def test_the_three_actor_forms_pass_for_generated_and_verified(self):
        for actor in ("claude-opus/4.1", "'human:erik'", "'process:nightly'"):
            with self.subTest(actor):
                self._none("generated: {by: %s, at: %s}\nverified: [{by: %s, at: %s}]"
                           % (actor, GOOD_AT, actor, GOOD_AT))

    def test_the_author_of_a_source_is_not_checked(self):
        self._none("sources:\n  - resource: a\n    author: team:ga4-docs", group="okf/")

    # key -> a frontmatter snippet with the value `{v}` in the key under test
    TIMESTAMP_KEYS = {
        "generated.at": "generated: {{by: claude/4, at: {v}}}",
        "verified.at": "verified: [{{by: 'human:erik', at: {v}}}]",
        "verified.at (bare)": "verified: {{by: 'human:erik', at: {v}}}",
        "stale_after": "stale_after: {v}",
        "usage_window.from": "usage_window: {{from: {v}, to: 2026-01-01T00:00:00Z}}",
        "usage_window.to": "usage_window: {{from: 2026-01-01T00:00:00Z, to: {v}}}",
        "sources.usage_window.from": "sources:\n  - resource: a\n    usage_window: {{from: {v}, to: 2026-01-01T00:00:00Z}}",
        "sources.usage_window.to": "sources:\n  - resource: a\n    usage_window: {{from: 2026-01-01T00:00:00Z, to: {v}}}",
        "sources.last_modified": "sources:\n  - resource: a\n    last_modified: {v}",
    }

    def test_every_timestamp_key_needs_an_explicit_offset_quoted_or_not(self):
        bad = ("2026-06-20T22:53:05", "2026-06-20", "yesterday")
        for key, snippet in self.TIMESTAMP_KEYS.items():
            for value in bad:
                for form in ("{}", "'{}'"):
                    text = snippet.format(v=form.format(value))
                    with self.subTest(key=key, text=text):
                        self._one(text)

    def test_every_timestamp_key_accepts_an_offset_quoted_or_not(self):
        for key, snippet in self.TIMESTAMP_KEYS.items():
            for value in (GOOD_AT, "2026-06-20T22:53:05+02:00"):
                for form in ("{}", "'{}'"):
                    text = snippet.format(v=form.format(value))
                    with self.subTest(key=key, text=text):
                        self._none(text)

    def test_a_blank_required_trust_field_is_reported_once_by_trust_only(self):
        for extra in ("generated: {by: , at: %s}" % GOOD_AT, "verified: [{by: 'human:erik', at: }]"):
            with self.subTest(extra):
                hits = self._hits(extra, group="okf/")
                self.assertEqual([f.rule.startswith("okf/trust/") for f in hits], [True])

    def test_a_blank_optional_timestamp_is_a_format_error(self):
        self._one("stale_after:")
        self._one("generated: {by: claude/4, at: }")


class ComputationRules(RuleCase):
    GROUP = "okf/computation/"
    TYPE = "Attested Computation"

    def test_an_attested_computation_without_a_non_empty_runtime_is_an_error(self):
        for extra in ("", 'runtime: ""', "runtime:", "runtime: '  '", "runtime: []", "executor: {resource: x}"):
            with self.subTest(extra):
                self._one(extra, type_=self.TYPE)

    def test_runtime_alone_is_enough(self):
        self._none("runtime: python3.12", type_=self.TYPE)
        self._none("runtime: python3.12\nparameters: []", type_=self.TYPE)

    def test_other_types_need_no_runtime(self):
        self._none("", type_="Note")
        self._none("")


class OnlyDeclaringBundles(RuleCase):
    """AC11 and AC14 of OKFT-q37h."""

    EVERYTHING = ("status: active\nstale_after: " + PAST + "\n"
                  "generated: {by: erik, at: 2026-06-20T22:53:05}\n"
                  "verified: [{by: erik}, plain]\n"
                  "usage_window: {from: 2026-01-01, to: soon}\n"
                  "sources:\n  - resource: a\n    last_modified: yesterday\n")

    def _families(self, front):
        self._bundle(front)
        self._concept(self.EVERYTHING, type_="Attested Computation")
        return {f.rule.rsplit("/", 1)[0] + "/" for f in self._findings() if f.rule.startswith(FAMILIES)}

    def test_a_declaring_bundle_reports_every_family(self):
        self.assertEqual(self._families(DECLARE), set(FAMILIES))

    def test_an_undeclared_bundle_reports_none_of_them(self):
        for front in (None, 'okf_version: "0.1"', "okf_version: 0.2"):
            with self.subTest(front):
                self.assertEqual(self._families(front), set())

    def test_a_concept_without_these_fields_has_no_finding(self):
        self._bundle()
        self._concept("sources:\n  - resource: a")
        self.assertEqual([f for f in self._findings() if f.rule.startswith(FAMILIES)], [])


class CheckJson(RuleCase):
    EXTRA = "status: active\ngenerated: {at: 2026-06-20T22:53:05Z}\nstale_after: 2000-01-01T00:00:00Z"

    def _shape(self):
        envelope, _, code = run_json(self.tmp, "check", "b")
        return code, sorted((f["rule"].rsplit("/", 1)[0], f["severity"])
                            for f in envelope["data"]["findings"] if f["rule"].startswith(FAMILIES))

    def test_declaring_bundle_exits_4_with_two_errors_and_a_warning_across_families(self):
        self._bundle()
        self._concept(self.EXTRA)
        self.assertEqual(self._shape(), (4, [("okf/lifecycle", "error"), ("okf/lifecycle", "warning"),
                                             ("okf/trust", "error")]))

    def test_the_same_bundle_without_the_declaration_is_clean(self):
        self._bundle(None)
        self._concept(self.EXTRA)
        self.assertEqual(self._shape(), (0, []))


if __name__ == "__main__":
    unittest.main()
