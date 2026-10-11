#!/usr/bin/env python3
"""Tests for `migrate` (cli/okf/migrate.py) and unified_diffs (cli/okf/diffs.py): the migration runs
against a real git repository with pinned identities and dates. unittest.

Run: just test tests.test_okf_migrate -v
"""
import datetime
import os
import re
import subprocess
import sys
import unittest

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli")
if _HERE not in sys.path:  # cli/ holds the okf package
    sys.path.insert(0, _HERE)
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from okf.catalogue import read_frontmatter
from okf.diffs import unified_diffs
from okf.spec import parse_okf_datetime
from tests.okf_testkit import GitCatalogue, needs_git, run_cli, run_json

T1 = "2026-01-01T10:00:00+02:00"  # the body commit
T2 = "2026-02-01T09:00:00-05:00"  # a frontmatter-only commit afterwards
STAMP = "2026-03-03T03:03:03+00:00"  # the deviating `timestamp`


class UnifiedDiffs(unittest.TestCase):
    def test_orders_by_path_headers_a_b_and_omits_equal_texts(self):
        got = unified_diffs([("b/z.md", "x\n", "y\n"), ("b/same.md", "s\n", "s\n"), ("b/a.md", "1\n", "2\n")])
        self.assertEqual([e["path"] for e in got], ["b/a.md", "b/z.md"])
        self.assertTrue(got[0]["diff"].startswith("--- a/b/a.md\n+++ b/b/a.md\n"))
        self.assertTrue(all(e["old_path"] is None for e in got))

    def test_marks_a_missing_final_newline(self):
        (entry,) = unified_diffs([("b/a.md", "x", "y")])
        self.assertIn("-x\n\\ No newline at end of file\n+y\n\\ No newline at end of file\n", entry["diff"])


@needs_git
class Migrate(GitCatalogue):
    def _fixture(self):
        """b/x.md: body commit T1, frontmatter-only commit T2, `timestamp` names a third instant."""
        self._doc("b/x.md", "one\n", "type: Note\ntimestamp: {}\ntags: [a]".format(STAMP))
        self._doc("b/old.md", "kept\n", "type: Note\ntimestamp: {}\ngenerated: {{by: claude/4, at: 2025-01-01T00:00:00Z}}".format(STAMP))
        self._doc("b/free.md", "no stamp\n")
        self._w("b/index.md", "---\ntimestamp: {}\n---\n# B\n".format(STAMP))
        self._commit("body", T1, author="ann@x.org")
        self._doc("b/x.md", "one\n", "type: Note\ntimestamp: {}\ntags: [a, b]".format(STAMP))
        self._commit("front", T2, author="fm@x.org")

    def _generated(self, rel="b/x.md"):
        with open(os.path.join(self.tmp, rel), encoding="utf-8") as f:
            return read_frontmatter(f.read()).data.get("generated")

    def test_preview_writes_nothing_and_shows_one_diff_per_concept(self):
        self._fixture()
        envelope, _err, code = run_json(self.tmp, "migrate")
        self.assertEqual(code, 0)
        files = envelope["data"]["files"]
        self.assertEqual([f["path"] for f in files], ["b/old.md", "b/x.md"])
        diff = files[1]["diff"]
        self.assertIn("-timestamp: " + STAMP, diff)
        self.assertIn("by: human:ann", diff)
        self.assertIn("2026-01-01T10:00:00+02:00", diff)
        self.assertEqual(envelope["data"]["unresolved"], [])
        self.assertEqual(self._git("status", "--short"), "")
        self.assertEqual(self._git("diff", "--stat"), "")

    def test_apply_writes_the_previewed_plan_and_no_timestamp_remains(self):
        self._fixture()
        preview, _e, _c = run_json(self.tmp, "migrate")
        applied, _e, code = run_json(self.tmp, "migrate", "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(applied["data"]["files"], preview["data"]["files"])
        changed = self._git("diff", "--name-only").split()
        self.assertEqual(changed, ["b/old.md", "b/x.md"])
        for entry in applied["data"]["files"]:
            patch = self._git("diff", "--", entry["path"])
            self.assertEqual([l for l in patch.splitlines() if l[:1] in "+-" and l[:3] not in ("+++", "---")],
                             [l for l in entry["diff"].splitlines() if l[:1] in "+-" and l[:3] not in ("+++", "---")])
        out = subprocess.run(["grep", "-rl", "^timestamp:", os.path.join(self.tmp, "b")],
                             capture_output=True, text=True).stdout.split()
        self.assertEqual([os.path.basename(p) for p in out], ["index.md"])  # reserved file untouched

    def test_generated_at_is_the_body_commit_not_the_frontmatter_commit_nor_timestamp(self):
        self._fixture()
        run_json(self.tmp, "migrate", "--apply")
        generated = self._generated()
        at = parse_okf_datetime(generated["at"])
        self.assertEqual(at, datetime.datetime(2026, 1, 1, 8, 0, tzinfo=datetime.timezone.utc))
        self.assertEqual(generated["by"], "human:ann")
        self.assertEqual(at.utcoffset(), datetime.timedelta(hours=2))

    def test_generated_takes_the_key_position_of_timestamp_and_other_bytes_stay(self):
        self._fixture()
        run_json(self.tmp, "migrate", "--apply")
        with open(os.path.join(self.tmp, "b/x.md"), encoding="utf-8") as f:
            text = f.read()
        keys = re.findall(r"^([a-z]+):", text.split("---")[1], re.M)
        self.assertEqual(keys, ["type", "generated", "tags"])
        self.assertTrue(text.endswith("---\none\n"))

    def test_existing_generated_stays_and_only_timestamp_goes(self):
        self._fixture()
        run_json(self.tmp, "migrate", "--apply")
        with open(os.path.join(self.tmp, "b/old.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "---\ntype: Note\ngenerated: {by: claude/4, at: 2025-01-01T00:00:00Z}\n---\nkept\n")

    def test_git_authors_maps_the_email(self):
        self._w(".okf.toml", '[git_authors]\n"ann@x.org" = "human:ann-riedel"\n')
        self._fixture()
        run_json(self.tmp, "migrate", "--apply")
        self.assertEqual(self._generated()["by"], "human:ann-riedel")

    def test_invalid_git_authors_value_exits_2_and_changes_nothing(self):
        self._w(".okf.toml", '[git_authors]\n"ann@x.org" = "ann"\n')
        self._fixture()
        before = self._git("status", "--short")
        envelope, _err, code = run_json(self.tmp, "migrate", "--apply")
        self.assertEqual((code, envelope["error"]["kind"]), (2, "invalid_input"))
        self.assertEqual(self._git("diff", "--stat"), "")
        self.assertEqual(self._git("status", "--short"), before)

    def test_unknown_target_exits_3(self):
        self._fixture()
        envelope, _err, code = run_json(self.tmp, "migrate", "nope", "--apply")
        self.assertEqual((code, envelope["error"]["kind"]), (3, "not_found"))

    def test_untracked_concept_stays_unresolved_with_its_timestamp(self):
        self._doc("b/seed.md")
        self._commit("seed", T1)
        self._doc("b/new.md", "n\n", "type: Note\ntimestamp: {}".format(STAMP))  # never committed
        envelope, _err, code = run_json(self.tmp, "migrate", "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(envelope["data"]["files"], [])
        self.assertEqual([(u["path"], u["field"]) for u in envelope["data"]["unresolved"]], [("b/new.md", "generated")])
        with open(os.path.join(self.tmp, "b/new.md"), encoding="utf-8") as f:
            self.assertIn("timestamp", f.read())

    def test_text_preview_prints_the_diff_and_a_dry_run_hint(self):
        self._fixture()
        out, _err, code = run_cli(self.tmp, "migrate")
        self.assertEqual(code, 0)
        self.assertIn("--- a/b/x.md\n+++ b/b/x.md\n", out)
        self.assertIn("dry-run", out)


@needs_git
class MigrateStatus(GitCatalogue):
    D37 = {"obsolete": "deprecated", "deleted": "deprecated", "archived": "deprecated",
           "accepted": "stable", "active": "stable", "passive": "stable", "stable": "stable",
           "todo": "draft", "planned": "draft", "in-bearbeitung": "draft", "experimental": "draft",
           "draft": "draft", "deprecated": "deprecated"}

    def _fixture(self):
        for old in self.D37:
            self._doc("b/{}.md".format(old), "x\n", "type: Note\nstatus: {}".format(old))
        self._doc("b/unknown.md", "x\n", "type: Note\nstatus: wibble")
        self._doc("b/empty.md", "x\n", "type: Note\nstatus:")
        self._doc("b/none.md", "x\n", "type: Note")
        self._doc("b/tpl.md", "status: <status>\n", "type: Note")
        self._commit("c", T1)

    def _r(self, rel):
        with open(os.path.join(self.tmp, rel), encoding="utf-8") as f:
            return f.read()

    def _status(self, name):
        return read_frontmatter(self._r("b/{}.md".format(name))).data.get("status")

    def test_apply_maps_every_d37_value_and_leaves_the_rest(self):
        self._fixture()
        _env, _e, code = run_json(self.tmp, "migrate", "--apply")
        self.assertEqual(code, 0)
        for old, new in self.D37.items():
            self.assertEqual(self._status(old), new, old)
        self.assertEqual(self._status("unknown"), "wibble")
        self.assertIsNone(self._status("empty"))
        self.assertNotIn("status", read_frontmatter(self._r("b/none.md")).data)
        self.assertIn("status: <status>", self._r("b/tpl.md"))
        self.assertNotIn("\nstatus", self._r("b/obsolete.md").replace("status: deprecated", ""))

    def test_preview_diff_shows_old_and_new_line_and_writes_nothing(self):
        self._fixture()
        env, _e, _c = run_json(self.tmp, "migrate")
        diff = {f["path"]: f["diff"] for f in env["data"]["files"]}["b/accepted.md"]
        self.assertIn("-status: accepted", diff)
        self.assertIn("+status: stable", diff)
        self.assertNotIn("b/draft.md", diff)
        self.assertEqual(self._git("status", "--short"), "")
        paths = [f["path"] for f in env["data"]["files"]]
        self.assertNotIn("b/draft.md", paths)
        self.assertNotIn("b/tpl.md", paths)

    def test_unresolved_lists_unknown_and_empty_values(self):
        self._fixture()
        env, _e, _c = run_json(self.tmp, "migrate")
        got = {u["path"]: u for u in env["data"]["unresolved"]}
        self.assertEqual(sorted(got), ["b/empty.md", "b/unknown.md"])
        self.assertEqual(got["b/unknown.md"]["field"], "status")
        self.assertIn("wibble", got["b/unknown.md"]["reason"])

    def test_status_mapping_plan_is_ordered_with_counts(self):
        self._fixture()
        self._doc("b/active2.md", "x\n", "type: Note\nstatus: active")
        self._commit("c2", T2)
        env, _e, _c = run_json(self.tmp, "migrate")
        sm = env["data"]["status_mapping"]
        self.assertEqual([m["old"] for m in sm], sorted(m["old"] for m in sm))
        by = {m["old"]: m for m in sm}
        self.assertEqual(by["active"], {"old": "active", "new": "stable", "count": 2})
        self.assertEqual(by["wibble"], {"old": "wibble", "new": None, "count": 1})
        out, _e, _c = run_cli(self.tmp, "migrate")
        self.assertIn("active -> stable (2 concept(s))", out)
        self.assertIn("wibble -> (no decision) (1 concept(s))", out)


if __name__ == "__main__":
    unittest.main()
