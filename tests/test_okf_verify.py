#!/usr/bin/env python3
"""Tests for `verify <concept> --by <actor>` (OKFT-iw3e): the three append forms, byte stability
outside `verified`, the refusals and the envelope, against throwaway catalogues. unittest.

Run: just test tests.test_okf_verify -v
"""
import datetime
import os
import re
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
from tests.okf_testkit import SpecCase, run_cli, run_json

BODY = "# X\n\nbody line one\n\n\n  indented  \nlast without newline"
OLD = "{by: claude/4, at: 2026-09-01T00:00:00Z}"


class VerifyCase(SpecCase):
    def _put(self, front, rel="b/x.md", body=BODY):
        self._w(rel, "---\n{}\n---\n{}".format(front, body))

    def _text(self, rel="b/x.md"):
        with open(os.path.join(self.tmp, rel), encoding="utf-8", newline="") as f:
            return f.read()

    def _verify(self, by="human:erik", concept="b/x", *extra):
        envelope, _, code = run_json(self.tmp, "verify", concept, "--by", by, *extra)
        return envelope, code

    def _verified(self, rel="b/x.md"):
        return read_frontmatter(self._text(rel)).data["verified"]

    def _now(self):
        return datetime.datetime.now(datetime.timezone.utc)

    def _assert_entry(self, entry, by, before, after):
        self.assertEqual(set(entry), {"by", "at"})
        self.assertEqual(entry["by"], by)
        at = okf_spec.parse_okf_datetime(entry["at"])
        self.assertIsNotNone(at, entry["at"])
        self.assertEqual(at.utcoffset(), datetime.timedelta(0))
        self.assertTrue(before - datetime.timedelta(seconds=1) <= at <= after, (before, at, after))


class AppendForms(VerifyCase):
    """AC1-AC5."""

    def test_absent_verified_becomes_a_list_with_one_entry(self):
        self._put("type: Note")
        before = self._now()
        envelope, code = self._verify()
        self.assertEqual((code, envelope["ok"]), (0, True))
        entries = self._verified()
        self.assertIsInstance(entries, list)
        self.assertEqual(len(entries), 1)
        self._assert_entry(entries[0], "human:erik", before, self._now())

    def test_a_bare_mapping_becomes_a_list_with_the_old_entry_first(self):
        self._put("type: Note\nverified: " + OLD)
        before = self._now()
        _, code = self._verify("process:ci")
        self.assertEqual(code, 0)
        entries = self._verified()
        self.assertEqual(len(entries), 2)
        self.assertEqual((entries[0]["by"], okf_spec.parse_okf_datetime(entries[0]["at"])),
                         ("claude/4", datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc)))
        self._assert_entry(entries[1], "process:ci", before, self._now())

    def test_a_list_gets_the_new_entry_at_its_end(self):
        self._put("type: Note\nverified:\n  - {by: a/1, at: 2026-08-01T00:00:00Z}\n  - " + OLD)
        _, code = self._verify("human:erik")
        self.assertEqual(code, 0)
        self.assertEqual([e["by"] for e in self._verified()], ["a/1", "claude/4", "human:erik"])

    def test_a_flow_list_and_a_block_list_both_append(self):
        for form in ("verified: [" + OLD + "]", "verified:\n  - " + OLD):
            with self.subTest(form):
                self._put("type: Note\n" + form)
                self.assertEqual(self._verify()[1], 0)
                self.assertEqual([e["by"] for e in self._verified()], ["claude/4", "human:erik"])

    def test_two_calls_leave_a_three_entry_list_in_call_order(self):
        self._put("type: Note\nverified: " + OLD)
        self._verify("human:erik")
        self._verify("process:nightly")
        self.assertEqual([e["by"] for e in self._verified()], ["claude/4", "human:erik", "process:nightly"])

    def test_every_other_key_comment_and_the_body_stay_byte_identical(self):
        front_before = "type: Note  # why\ntitle: \"Quoted: Title\"\ntags: [a, b]\n"
        front_after = "\n# trailing block comment\nz: 'single'\nwidth: 2026-09-23\n"
        self._put(front_before + "verified: " + OLD + front_after.rstrip("\n"))
        before = self._text()
        self.assertEqual(self._verify()[1], 0)
        after = self._text()
        self.assertTrue(after.startswith("---\n" + front_before), after)
        self.assertTrue(after.endswith("# trailing block comment\nz: 'single'\nwidth: 2026-09-23\n---\n" + BODY), after)
        self.assertEqual(after.split("---\n", 2)[2], before.split("---\n", 2)[2])  # the body, byte for byte

    def test_a_file_without_a_verified_key_changes_only_by_the_added_lines(self):
        self._put("type: Note\ntags:\n  - a\n  - b  # keep")
        before = self._text().splitlines(keepends=True)
        self.assertEqual(self._verify()[1], 0)
        after = self._text().splitlines(keepends=True)
        added = [line for line in after if line not in before]
        self.assertEqual(added[0], "verified:\n")
        self.assertEqual(len(added), 3, added)
        self.assertEqual([line for line in after if line in before], before)

    def test_the_written_entry_is_plain_yaml_the_check_accepts(self):
        self._bundle()
        self._put("type: Note")
        self.assertEqual(self._verify("human:erik")[1], 0)
        self.assertEqual(self._verify("claude-opus/4.1")[1], 0)
        self.assertEqual([f for f in self._findings() if f.rule.startswith(("okf/trust/", "okf/format/"))], [])
        self.assertRegex(self._text(), r"\n    at: \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\n")  # unquoted, like the spec

    def test_works_in_a_bundle_without_the_declaration(self):
        self._bundle(None)
        self._put("type: Note")
        self.assertEqual(self._verify()[1], 0)
        self.assertEqual(len(self._verified()), 1)

    def test_a_file_without_a_frontmatter_block_gets_one_holding_only_verified(self):
        self._w("b/x.md", "# X\n\nbody\n")
        self.assertEqual(self._verify()[1], 0)
        text = self._text()
        self.assertTrue(text.startswith("---\nverified:\n  - by: human:erik\n    at: "), text)
        self.assertTrue(text.endswith("---\n# X\n\nbody\n"), text)

    def test_a_path_with_the_md_suffix_resolves_like_read(self):
        self._put("type: Note")
        self.assertEqual(self._verify(concept="b/x.md")[1], 0)
        self.assertEqual(self._verified()[0]["by"], "human:erik")


class Refusals(VerifyCase):
    """AC6-AC9."""

    def _refused(self, code, kind, **kw):
        envelope, got = self._verify(**kw)
        self.assertEqual((got, envelope["ok"], (envelope["error"] or {}).get("kind")), (code, False, kind), envelope)
        return envelope

    def _unchanged_after(self, front, rel="b/x.md", **kw):
        self._put(front, rel)
        before = self._text(rel)
        self._refused(2, "invalid_input", **kw)
        self.assertEqual(self._text(rel), before)

    def test_an_actor_outside_the_convention_exits_2_and_leaves_the_file_alone(self):
        for by in ("erik", "human:", "process:", "/4", "claude/", " human:erik", "human:erik ", ""):
            with self.subTest(by):
                self._unchanged_after("type: Note", by=by)

    def test_a_verified_that_is_no_mapping_and_no_list_of_mappings_exits_2_unchanged(self):
        for form in ("verified: yes", "verified: [a, b]", "verified: [{by: a/1, at: 2026-01-01T00:00:00Z}, x]",
                     "verified: 5", "verified: [[x]]"):
            with self.subTest(form):
                self._unchanged_after("type: Note\n" + form)

    def test_a_reserved_file_exits_2_unchanged(self):
        for rel in ("b/index.md", "b/log.md", "b/readme.md", "b/index-map.md", "b/sub/index.md"):
            with self.subTest(rel):
                self._put("type: Note", rel)
                before = self._text(rel)
                self._refused(2, "invalid_input", concept=rel[:-3])
                self.assertEqual(self._text(rel), before)

    def test_a_bundle_directory_resolves_to_its_index_and_is_refused(self):
        self._bundle()
        before = self._text("b/index.md")
        self._refused(2, "invalid_input", concept="b")
        self.assertEqual(self._text("b/index.md"), before)

    def test_a_missing_concept_exits_3(self):
        self._put("type: Note")
        self._refused(3, "not_found", concept="b/nope")
        self._refused(3, "not_found", concept="nobundle/x")

    def test_frontmatter_that_does_not_parse_exits_2_unchanged(self):
        self._unchanged_after("type: [unclosed")

    def test_the_actor_is_judged_before_the_concept_is_looked_up(self):
        self._refused(2, "invalid_input", by="erik", concept="b/nope")

    def test_a_missing_by_flag_is_a_usage_error_not_a_write(self):
        self._put("type: Note")
        before = self._text()
        _, _, code = run_cli(self.tmp, "verify", "b/x")
        self.assertEqual(code, 2)
        self.assertEqual(self._text(), before)


class Output(VerifyCase):
    """AC10."""

    def test_json_data_carries_the_concept_path_and_the_appended_entry(self):
        self._put("type: Note")
        before = self._now()
        envelope, code = self._verify()
        self.assertEqual((code, envelope["command"], envelope["error"]), (0, "verify", None))
        self.assertEqual(set(envelope["data"]), {"path", "entry"})
        self.assertEqual(envelope["data"]["path"], "b/x")
        self._assert_entry(envelope["data"]["entry"], "human:erik", before, self._now())
        written = self._verified()[0]
        self.assertEqual((written["by"], okf_spec.parse_okf_datetime(written["at"])),
                         ("human:erik", okf_spec.parse_okf_datetime(envelope["data"]["entry"]["at"])))

    def test_the_text_output_names_the_concept_and_the_actor(self):
        self._put("type: Note")
        out, _, code = run_cli(self.tmp, "verify", "b/x", "--by", "human:erik")
        self.assertEqual(code, 0)
        self.assertRegex(out, r"^verified b/x by human:erik at \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\n$")

    def test_the_verb_is_listed_in_the_maintenance_group_of_the_help(self):
        out, _, code = run_cli(self.tmp, "--help")
        self.assertEqual(code, 0)
        groups, current = {}, None
        for line in out.splitlines():
            if re.match(r"^  \w+:$", line):
                current = line.strip(" :")
                groups[current] = []
            elif current and (command := re.match(r"^    (\S+) {2,}\S", line)):
                groups[current].append(command.group(1))
        self.assertIn("verify", groups["maintenance"])
        self.assertEqual([g for g, names in groups.items() if "verify" in names], ["maintenance"])


if __name__ == "__main__":
    unittest.main()
