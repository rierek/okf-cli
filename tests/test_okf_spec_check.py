#!/usr/bin/env python3
"""Tests for the OKF v0.2 rules of `check` (cli/okf/spec.py, cli/okf/spec_check.py): the bundle
gate, Provenance, Trust, Lifecycle, Format and Attested Computation. unittest.

Run: just test tests.test_okf_spec_check -v
"""
import os
import shutil
import sys
import tempfile
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
from tests.okf_testkit import run_json

DECLARE = 'okf_version: "0.2"'


class SpecCase(unittest.TestCase):
    """A throwaway catalogue with one bundle `b`. `_bundle` writes its root index.md."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _w(self, rel, text):
        ap = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(text)

    def _bundle(self, front: "str | None" = DECLARE, bundle="b"):
        """The bundle-root index.md; `front` is its frontmatter text, None for no block."""
        head = "" if front is None else "---\n{}\n---\n".format(front)
        self._w(bundle + "/index.md", head + "# B\n\nA bundle for the v0.2 rule tests.\n")

    def _concept(self, extra="", rel="b/x.md", type_="Note"):
        self._w(rel, "---\ntype: {}\n{}\n---\n# X\n\nbody\n".format(type_, extra))

    def _findings(self, target: "str | None" = "b"):
        return okf_check.run_checks(self.tmp, target)

    def _group(self, prefix, target: "str | None" = "b"):
        return [f for f in self._findings(target) if f.rule.startswith(prefix)]


def _gated_rule(scope="file"):
    check = ((lambda ctx: ["boom"]) if scope == "file"
             else (lambda b: [(b["bundle"], "boom")]))
    return okf_check.Rule("okf/test/gated", "warning", scope, check, okf_version="0.2")


def _ungated_rule():
    return okf_check.Rule("kc/test/ungated", "warning", "file",
                          lambda ctx: [] if ctx["is_reserved"] else ["boom"])


class DeclaredOkfVersion(SpecCase):
    """`declared_okf_version(bundle_root)`: the YAML string `"0.2"` or None."""

    def _declared(self):
        return okf_spec.declared_okf_version(os.path.join(self.tmp, "b"))

    def test_quoted_string_declares(self):
        self._bundle()
        self.assertEqual(self._declared(), "0.2")

    def test_single_quoted_string_declares(self):
        self._bundle("okf_version: '0.2'")
        self.assertEqual(self._declared(), "0.2")

    def test_unquoted_float_does_not_declare(self):
        # Deliberate (OKFT-gtsu risk decision): `0.2` loads as a float, so the bundle stays ungated.
        self._bundle("okf_version: 0.2")
        self.assertIsNone(self._declared())

    def test_any_other_string_is_returned_as_is(self):
        for value in ("0.1", "0.3", "0.2.0"):
            with self.subTest(value=value):
                self._bundle('okf_version: "{}"'.format(value))
                self.assertEqual(self._declared(), value)

    def test_a_value_that_is_not_a_string_is_none(self):
        for value in ('[ "0.2" ]', "2", "null", "true"):
            with self.subTest(value=value):
                self._bundle("okf_version: " + value)
                self.assertIsNone(self._declared())

    def test_absent_key_no_frontmatter_and_no_index_do_not_declare(self):
        self._bundle("title: other")
        self.assertIsNone(self._declared())
        self._bundle(None)
        self.assertIsNone(self._declared())
        os.remove(os.path.join(self.tmp, "b", "index.md"))
        self.assertIsNone(self._declared())

    def test_unparseable_frontmatter_does_not_declare(self):
        self._w("b/index.md", "---\nokf_version: [unclosed\n---\n# B\n")
        self.assertIsNone(self._declared())


class BundleGate(SpecCase):
    """AC1-AC3, AC8 of OKFT-gtsu: the registry field `okf_version` and how `run_checks` honours it."""

    def _run_with(self, *rules, target: "str | None" = "b"):
        with mock.patch.object(okf_check, "RULES", list(rules)):
            return [(f.rule, f.path) for f in okf_check.run_checks(self.tmp, target)]

    def test_declaring_bundle_runs_gated_file_entry_on_each_concept(self):
        self._bundle()
        self._concept(rel="b/x.md")
        self._concept(rel="b/sub/y.md")
        got = self._run_with(_gated_rule())
        self.assertEqual(sorted(got), [("okf/test/gated", "b/sub/y.md"),
                                       ("okf/test/gated", "b/x.md")])

    def test_declaring_bundle_runs_gated_bundle_entry(self):
        self._bundle()
        self._concept()
        self.assertEqual(self._run_with(_gated_rule("bundle")), [("okf/test/gated", "b")])

    def test_gated_entries_do_not_run_on_reserved_files(self):
        self._bundle()
        for name in ("log.md", "readme.md", "index-map.md", "sub/index.md"):
            self._w("b/" + name, "# R\n")
        self.assertEqual(self._run_with(_gated_rule()), [])

    def test_undeclared_variants_run_no_gated_entry(self):
        variants = {"no index": "<absent>", "no frontmatter": None, "no key": "title: t",
                    "other value": 'okf_version: "0.1"', "unquoted": "okf_version: 0.2"}
        for label, front in variants.items():
            with self.subTest(label):
                shutil.rmtree(os.path.join(self.tmp, "b"), ignore_errors=True)
                self._concept()
                if front != "<absent>":
                    self._bundle(front)
                self.assertEqual(self._run_with(_gated_rule(), _gated_rule("bundle")), [])

    def test_ungated_entry_runs_in_every_bundle(self):
        self._concept()
        self._bundle(None)
        self.assertEqual(self._run_with(_ungated_rule()), [("kc/test/ungated", "b/x.md")])
        self._bundle()
        self.assertEqual(self._run_with(_ungated_rule()), [("kc/test/ungated", "b/x.md")])

    def test_bundles_gate_independently_in_one_run(self):
        self._bundle(bundle="v2")
        self._concept(rel="v2/x.md")
        self._bundle(None, bundle="v1")
        self._concept(rel="v1/x.md")
        self.assertEqual(self._run_with(_gated_rule(), target=None), [("okf/test/gated", "v2/x.md")])

    def test_scoped_run_reads_the_bundle_root_index(self):
        self._bundle()
        self._concept(rel="b/sub/x.md")
        self._w("b/sub/index.md", "# S\n")  # a sub-index without the declaration changes nothing
        self.assertEqual(self._run_with(_gated_rule(), target="b/sub"),
                         [("okf/test/gated", "b/sub/x.md")])

    def test_scoped_run_ignores_a_declaration_in_a_sub_index(self):
        self._bundle(None)
        self._concept(rel="b/sub/x.md")
        self._w("b/sub/index.md", '---\n{}\n---\n# S\n'.format(DECLARE))
        self.assertEqual(self._run_with(_gated_rule(), target="b/sub"), [])

    def test_gate_reads_each_bundle_index_once_per_run(self):
        self._bundle()
        self._bundle(bundle="c")
        for i in range(3):
            self._concept(rel="b/x{}.md".format(i))
            self._concept(rel="c/x{}.md".format(i))
        real, reads = okf_spec.read_file, []

        def counting(ap):
            reads.append(ap)
            return real(ap)

        with mock.patch.object(okf_spec, "read_file", counting):
            self._run_with(_gated_rule(), target=None)
        self.assertEqual(sorted(os.path.relpath(p, self.tmp) for p in reads),
                         [os.path.join("b", "index.md"), os.path.join("c", "index.md")])


class ProvenanceRules(SpecCase):
    """AC4-AC7, AC9-AC11 of OKFT-gtsu."""

    GROUP = "okf/provenance/"

    def _rules(self):
        return [r for r in okf_check.RULES if r.id.startswith(self.GROUP)]

    def _assert_one_error(self, extra, **kw):
        self._bundle(**kw)
        self._concept(extra)
        hits = self._group(self.GROUP)
        self.assertEqual([(f.severity, f.path) for f in hits], [("error", "b/x.md")], hits)
        self.assertIn(hits[0].rule, [r.id for r in self._rules()])

    def test_registry_holds_gated_error_rules_of_the_family(self):
        self.assertGreaterEqual(len(self._rules()), 3)
        for rule in self._rules():
            self.assertEqual((rule.severity, rule.scope, rule.okf_version), ("error", "file", "0.2"),
                             rule.id)

    def test_sources_not_a_list_is_an_error(self):
        for extra in ("sources: just-text", "sources: {resource: a}", "sources:", "sources: 5"):
            with self.subTest(extra):
                self._assert_one_error(extra)

    def test_sources_entry_that_is_not_a_mapping_is_an_error(self):
        self._assert_one_error("sources:\n  - plain text")

    def test_sources_entry_without_resource_is_an_error(self):
        self._assert_one_error("sources:\n  - id: s1")

    def test_sources_entry_with_empty_resource_is_an_error(self):
        for value in ('""', "null", "'  '"):
            with self.subTest(value):
                self._assert_one_error("sources:\n  - resource: " + value)

    def test_each_bad_entry_gets_its_own_finding(self):
        self._bundle()
        self._concept("sources:\n  - resource: ok\n  - id: s2\n  - id: s3")
        self.assertEqual(len(self._group(self.GROUP)), 2)

    def test_valid_sources_pass(self):
        self._bundle()
        self._concept("sources:\n  - resource: https://example.org/a\n    id: s1\n"
                      "  - resource: /b/c.md")
        self.assertEqual(self._group(self.GROUP), [])

    def test_shared_usage_window_that_is_not_a_mapping_is_an_error(self):
        for extra in ("usage_window: last-year", "usage_window: from 2026-01-01 to 2026-02-01",
                      "usage_window: [from, to]"):
            with self.subTest(extra):
                self._assert_one_error(extra)

    def test_shared_usage_window_without_to_is_an_error(self):
        self._assert_one_error("usage_window:\n  from: 2026-01-01T00:00:00Z")

    def test_shared_usage_window_without_from_is_an_error(self):
        self._assert_one_error("usage_window:\n  to: 2026-01-01T00:00:00Z")

    def test_per_entry_usage_window_without_to_is_an_error(self):
        self._assert_one_error("sources:\n  - resource: a\n    usage_window:\n"
                               "      from: 2026-01-01T00:00:00Z")

    def test_per_entry_usage_window_not_a_mapping_is_an_error(self):
        for window in ("[x]", "[from, to]", "from 2026-01-01 to 2026-02-01"):
            with self.subTest(window):
                self._assert_one_error("sources:\n  - resource: a\n    usage_window: " + window)

    def test_valid_usage_windows_pass(self):
        self._bundle()
        self._concept("usage_window: {from: 2026-01-01T00:00:00Z, to: 2026-02-01T00:00:00Z}\n"
                      "sources:\n  - resource: a\n    usage_window:\n"
                      "      from: 2026-01-01T00:00:00Z\n      to: 2026-02-01T00:00:00Z")
        self.assertEqual(self._group(self.GROUP), [])

    def test_concept_without_provenance_fields_passes(self):
        self._bundle()
        self._concept()
        self.assertEqual(self._group(self.GROUP), [])

    def test_reserved_files_are_not_checked(self):
        self._bundle()
        for name in ("log.md", "readme.md", "index-map.md", "sub/index.md"):
            self._w("b/" + name, "---\nsources: 5\nusage_window: x\n---\n# R\n")
        self.assertEqual(self._group(self.GROUP), [])

    def test_bundle_index_with_only_okf_version_is_clean(self):
        self._bundle()
        self._concept()
        self.assertEqual(self._findings(), [])

    def test_undeclared_bundle_with_every_violation_reports_no_provenance_finding(self):
        for front in (None, 'okf_version: "0.1"', "okf_version: 0.2"):
            with self.subTest(front):
                self._bundle(front)
                self._concept("sources:\n  - id: s1\n  - plain\nusage_window: nope")
                self._concept("sources: text", rel="b/y.md")
                self.assertEqual(self._group(self.GROUP), [])

    def test_check_json_exits_4_with_one_provenance_error_and_none_without_the_declaration(self):
        self._bundle()
        self._concept("sources:\n  - id: s1")
        envelope, _, code = run_json(self.tmp, "check", "b")
        self.assertEqual(code, 4)
        hits = [f for f in envelope["data"]["findings"] if f["rule"].startswith(self.GROUP)]
        self.assertEqual([f["severity"] for f in hits], ["error"])
        self._bundle(None)
        envelope, _, code = run_json(self.tmp, "check", "b")
        self.assertEqual(code, 0)
        self.assertEqual([f for f in envelope["data"]["findings"]
                          if f["rule"].startswith(self.GROUP)], [])


if __name__ == "__main__":
    unittest.main()
