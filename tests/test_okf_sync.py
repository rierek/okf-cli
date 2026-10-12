#!/usr/bin/env python3
"""Tests for cli/okf/sync.py — canon and sync block parsing, classification and
the sync-insert, sync-status and sync-update commands. unittest.
Run: just test tests.test_okf_sync -v
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import unittest

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli")
if _HERE not in sys.path:  # cli/ holds the okf package
    sys.path.insert(0, _HERE)
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from okf import catalogue as okf_catalogue
from okf import diffs as okf_diffs
from okf import sync as okf_sync
from okf.errors import EXIT_CODES
from tests.okf_testkit import SyncFixtureMixin


class SyncBlockParse(unittest.TestCase):
    """The marker set is parsed structurally, and a hand-broken one is
    reported as malformed instead of disappearing from every surface."""

    def _block(self, block_id="b1", source="/a/owner.md", payload="text\n"):
        return okf_sync.render_sync_block(block_id, source, payload)

    def test_well_formed_block_yields_span_covering_the_whole_block(self):
        blk = self._block()
        body = "pre\n\n" + blk + "\n\npost\n"
        recs = okf_sync.parse_sync_blocks(body)
        self.assertEqual(len(recs), 1)
        r = recs[0]
        self.assertFalse(r["malformed"])
        self.assertEqual((r["id"], r["source"]), ("b1", "/a/owner.md"))
        self.assertEqual(r["hash"], okf_sync.sync_hash("text\n"))
        self.assertEqual(body[r["span"][0]:r["span"][1]], blk)

    def test_two_blocks_in_one_body_stay_separate(self):
        body = (self._block("b1", payload="one\n") + "\n\ntext\n\n"
                + self._block("b2", payload="two\n"))
        recs = okf_sync.parse_sync_blocks(body)
        self.assertEqual([r["id"] for r in recs], ["b1", "b2"])
        self.assertEqual([r["payload"].strip() for r in recs], ["one", "two"])
        self.assertEqual([r["malformed"] for r in recs], [False, False])

    def test_reordered_attributes_are_malformed(self):
        body = ("<!-- okf:sync source=/a/owner.md id=b1 hash=0123456789ab -->\n"
                "> [!quote] x\n" + okf_catalogue.SYNC_BODY + "\ntext\n" + okf_catalogue.SYNC_END)
        recs = okf_sync.parse_sync_blocks(body)
        self.assertEqual(len(recs), 1)
        self.assertTrue(recs[0]["malformed"])

    def test_missing_body_marker_is_malformed(self):
        body = self._block().replace(okf_catalogue.SYNC_BODY + "\n", "")
        recs = okf_sync.parse_sync_blocks(body)
        self.assertEqual(len(recs), 1)
        self.assertTrue(recs[0]["malformed"])
        self.assertEqual(recs[0]["id"], "b1")

    def test_missing_end_marker_does_not_eat_the_next_block(self):
        body = (self._block("b1").replace(okf_catalogue.SYNC_END, "") + "\n"
                + self._block("b2"))
        recs = okf_sync.parse_sync_blocks(body)
        self.assertEqual([r["id"] for r in recs], ["b1", "b2"])
        self.assertEqual([r["malformed"] for r in recs], [True, False])

    def test_canon_block_without_close_marker_has_no_payload(self):
        body = "<!-- okf:canon id=x -->\ntext\n"
        self.assertEqual(okf_sync.parse_canon_blocks(body)[0]["payload"], None)


class SyncClassify(unittest.TestCase):
    """All six statuses of the recorded-hash / canon / local-copy triangle."""

    OWNER = "owner text\n"

    def _rec(self, payload=None, source="/a/owner.md"):
        return {"id": "b1", "source": source, "hash": okf_sync.sync_hash(self.OWNER),
                "payload": self.OWNER if payload is None else payload,
                "span": (0, 1), "malformed": False}

    def _canon(self, payload=None):
        return {("a/owner.md", "b1"): self.OWNER if payload is None else payload}

    def test_synced(self):
        self.assertEqual(
            okf_sync.classify_sync_block(self._rec(), self._canon()), "synced")

    def test_source_changed(self):
        self.assertEqual(
            okf_sync.classify_sync_block(self._rec(), self._canon("neu\n")),
            "source-changed")

    def test_consumer_modified(self):
        self.assertEqual(
            okf_sync.classify_sync_block(self._rec(payload="lokal\n"), self._canon()),
            "consumer-modified")

    def test_both_changed(self):
        self.assertEqual(
            okf_sync.classify_sync_block(self._rec(payload="lokal\n"),
                                         self._canon("neu\n")),
            "both-changed")

    def test_source_missing(self):
        self.assertEqual(okf_sync.classify_sync_block(self._rec(), {}),
                         "source-missing")

    def test_malformed_record_and_non_absolute_source(self):
        rec = self._rec()
        rec["malformed"] = True
        self.assertEqual(okf_sync.classify_sync_block(rec, self._canon()), "malformed")
        self.assertEqual(
            okf_sync.classify_sync_block(self._rec(source="a/owner.md"),
                                         self._canon()),
            "malformed")


class SyncInsertCommand(SyncFixtureMixin, unittest.TestCase):
    """sync-insert materialises a canon block, dry-run by default, and refuses
    a second copy of the same id."""

    def test_dry_run_writes_nothing(self):
        before = self._r("kc-proj/setup.md")
        out, code = self._insert(apply=False)
        self.assertEqual(code, 0)
        self.assertIn("would insert", out)
        self.assertEqual(self._r("kc-proj/setup.md"), before)

    def test_apply_records_the_owner_payload_hash(self):
        _, code = self._insert()
        self.assertEqual(code, 0)
        body = okf_catalogue.read_frontmatter(self._r("kc-proj/setup.md")).body
        rec = okf_sync.parse_sync_blocks(body)[0]
        self.assertEqual(rec["source"], "/kc-gov/ownership.md")
        self.assertEqual(rec["hash"], okf_sync.sync_hash(self.OWNER_PAYLOAD))
        self.assertEqual(rec["payload"].strip(), self.OWNER_PAYLOAD.strip())
        self.assertIn("> [!quote] Synchronisiert aus", self._r("kc-proj/setup.md"))

    def test_second_insert_of_the_same_block_refuses_and_changes_nothing(self):
        self._insert()
        before = self._r("kc-proj/setup.md")
        _, code = self._insert()
        self.assertEqual(code, EXIT_CODES["invalid_input"])
        self.assertEqual(self._r("kc-proj/setup.md"), before)

    def test_unknown_block_id_exits_one(self):
        _, code = self._insert(block_id="nope")
        self.assertEqual(code, EXIT_CODES["not_found"])
        self.assertNotIn("okf:sync", self._r("kc-proj/setup.md"))


class SyncUpdateCommand(SyncFixtureMixin, unittest.TestCase):
    """sync-update re-materialises what the owner changed, and refuses to
    discard a locally modified copy without --force."""

    def setUp(self):
        super().setUp()
        self._insert()

    def _retype_owner(self, new_payload):
        self._w("kc-gov/ownership.md",
                self._r("kc-gov/ownership.md").replace(
                    self.OWNER_PAYLOAD, new_payload))

    def _retype_consumer(self, new_payload):
        self._w("kc-proj/setup.md",
                self._r("kc-proj/setup.md").replace(
                    self.OWNER_PAYLOAD, new_payload))

    def test_source_changed_is_rewritten_to_the_owner_payload(self):
        self._retype_owner("Neuer Kanon.\n")
        out, code = self._update()
        self.assertEqual(code, 0)
        self.assertIn("updated", out)
        self.assertEqual(self._payload_of("kc-proj/setup.md").strip(),
                         "Neuer Kanon.")
        self.assertEqual(self._status()[1], 0)

    def test_dry_run_reports_without_writing(self):
        self._retype_owner("Neuer Kanon.\n")
        before = self._r("kc-proj/setup.md")
        out, code = self._update(apply=False)
        self.assertEqual(code, 0)
        self.assertIn("would update", out)
        self.assertEqual(self._r("kc-proj/setup.md"), before)

    def test_consumer_modified_is_refused_and_the_file_is_untouched(self):
        self._retype_consumer("Lokal umgeschrieben.\n")
        before = self._r("kc-proj/setup.md")
        out, code = self._update()
        self.assertEqual(code, EXIT_CODES["drift"])
        self.assertIn("refused", out)
        self.assertEqual(self._r("kc-proj/setup.md"), before)

    def test_force_overwrites_a_modified_consumer_copy(self):
        self._retype_consumer("Lokal umgeschrieben.\n")
        _, code = self._update(force=True)
        self.assertEqual(code, 0)
        self.assertEqual(self._payload_of("kc-proj/setup.md").strip(),
                         self.OWNER_PAYLOAD.strip())

    def test_source_missing_is_never_written_and_exits_one(self):
        os.remove(os.path.join(self.tmp, "kc-gov/ownership.md"))
        before = self._r("kc-proj/setup.md")
        out, code = self._update(force=True)
        self.assertEqual(code, EXIT_CODES["drift"])
        self.assertIn("source-missing", out)
        self.assertEqual(self._r("kc-proj/setup.md"), before)

    def test_source_filter_narrows_the_scan(self):
        self._retype_owner("Neuer Kanon.\n")
        before = self._r("kc-proj/setup.md")
        _, code = self._update(source="/kc-gov/anderes.md")
        self.assertEqual(code, 0)
        self.assertEqual(self._r("kc-proj/setup.md"), before)


class SyncOwnerInStagingDir(SyncFixtureMixin, unittest.TestCase):
    """A canon owner living in a "_"-prefixed staging dir (_inbox, _archive,
    ...) must stay resolvable by the canon index: iter_all_md prunes those
    dirs by default for read-path scans, but an archived/staged owner is
    still a legitimate source for sync-insert/-status/-update. Regression
    for the bug where such an owner was invisible to build_canon_block_index
    and every consumer misreported source-missing."""

    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.tmp, "kc-gov/_archive"), exist_ok=True)
        os.rename(os.path.join(self.tmp, "kc-gov/ownership.md"),
                  os.path.join(self.tmp, "kc-gov/_archive/ownership.md"))
        self._insert(concept="kc-gov/_archive/ownership")

    def test_status_reports_synced_not_source_missing(self):
        data, code = self._status()
        self.assertEqual(code, 0)
        self.assertEqual([b["status"] for b in data["blocks"]], ["synced"])

    def test_update_after_owner_change_reaches_the_staged_owner(self):
        self._w("kc-gov/_archive/ownership.md",
                self._r("kc-gov/_archive/ownership.md")
                .replace(self.OWNER_PAYLOAD, "Neuer Kanon.\n"))
        out, code = self._update()
        self.assertEqual(code, 0)
        self.assertIn("updated", out)
        self.assertEqual(self._payload_of("kc-proj/setup.md").strip(),
                         "Neuer Kanon.")


class SyncVerbDiffPreview(SyncFixtureMixin, unittest.TestCase):
    """OKFT-9xan — sync-insert and sync-update preview one unified diff per consumer file (text and
    `data.files`), keep the dry run byte-identical and write exactly the previewed texts on --apply."""

    def _json(self, fn, **kw):
        base = dict(consumer="kc-proj/setup", concept="kc-gov/ownership", block_id="ownership-rule",
                    target=None, source=None, block=None, force=False, apply=False, json=True)
        base.update(kw)
        try:
            return fn(self.tmp, argparse.Namespace(**base))
        except okf_sync.OkfError as e:
            return e.result

    def _consumer2(self):
        self._w("kc-proj/other.md", "---\ntype: Runbook\ndescription: d\n---\n\n# Other\n")
        self._insert(consumer="kc-proj/other")

    def test_insert_preview_is_one_diff_and_writes_nothing(self):
        before = self._r("kc-proj/setup.md")
        data = self._json(okf_sync.cmd_sync_insert)
        self.assertEqual([f["path"] for f in data["files"]], ["kc-proj/setup.md"])
        self.assertIsNone(data["files"][0]["old_path"])
        self.assertEqual(self._r("kc-proj/setup.md"), before)
        out, _ = self._insert(apply=False)
        self.assertEqual(out.split("would insert")[0], data["files"][0]["diff"])
        self.assertTrue(out.startswith("--- a/kc-proj/setup.md\n+++ b/kc-proj/setup.md\n"))

    def test_insert_apply_writes_the_previewed_text(self):
        data = self._json(okf_sync.cmd_sync_insert)
        self._insert()
        new = self._r("kc-proj/setup.md")
        self.assertIn("okf:sync", new)
        self.assertEqual(data["files"], okf_diffs.unified_diffs([("kc-proj/setup.md", self._base, new)]))

    def test_update_preview_orders_files_by_path_and_skips_refused_blocks(self):
        self._insert()
        self._consumer2()
        self._w("kc-gov/ownership.md", self._r("kc-gov/ownership.md").replace(self.OWNER_PAYLOAD, "Neu.\n"))
        self._w("kc-proj/setup.md", self._r("kc-proj/setup.md").replace(self.OWNER_PAYLOAD, "Lokal.\n"))
        snap = {r: self._r(r) for r in ("kc-proj/setup.md", "kc-proj/other.md")}
        data = self._json(okf_sync.cmd_sync_update)
        self.assertEqual([f["path"] for f in data["files"]], ["kc-proj/other.md"])
        self.assertEqual(len(data["refused"]), 1)
        self.assertEqual({r: self._r(r) for r in snap}, snap)
        _, code = self._update(apply=True)
        self.assertEqual(code, EXIT_CODES["drift"])
        self.assertEqual(self._r("kc-proj/setup.md"), snap["kc-proj/setup.md"])
        self.assertEqual(okf_diffs.unified_diffs([("kc-proj/other.md", snap["kc-proj/other.md"],
                                                   self._r("kc-proj/other.md"))]), data["files"])

    def setUp(self):
        super().setUp()
        self._base = self._r("kc-proj/setup.md")


@unittest.skipUnless(shutil.which("git"), "git not installed")
class SyncVerbPreviewEqualsGitDiff(SyncFixtureMixin, unittest.TestCase):
    """OKFT-9xan R-21 — per file, the preview of a sync verb and the `git diff` after --apply agree on
    the `---`/`+++` headers and every hunk (git's `diff --git`/`index`/mode lines are excluded)."""

    def _git(self, *argv):
        env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
                   HOME=self.tmp, GIT_TERMINAL_PROMPT="0")
        res = subprocess.run(["git", "-C", self.tmp, "-c", "init.defaultBranch=main", "-c", "user.name=t",
                              "-c", "user.email=t@e", "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false"]
                             + list(argv), capture_output=True, env=env)
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout.decode()

    def _git_diff(self, rel):
        out = self._git("diff", "--no-color", "--no-ext-diff", "--", rel)
        out = out[out.index("--- a/"):]
        return re.sub(r"(?m)^(@@ [^@]* @@).*$", r"\1", out)  # git appends a function-context hint

    def _check(self, fn, **kw):
        base = dict(target=None, source=None, block=None, force=False, json=True)
        base.update(kw)
        run = lambda apply: fn(self.tmp, argparse.Namespace(apply=apply, **base))
        self._git("init", "-q")
        self._git("add", "-A")
        self._git("commit", "-qm", "base")
        preview = run(False)["files"]
        self.assertEqual(self._git("status", "--porcelain"), "")
        self.assertTrue(preview)
        run(True)
        self.assertEqual(sorted(self._git("diff", "--name-only").split()), [f["path"] for f in preview])
        for f in preview:
            self.assertEqual(f["diff"], self._git_diff(f["path"]), f["path"])

    def test_sync_insert(self):
        self._check(okf_sync.cmd_sync_insert, consumer="kc-proj/setup", concept="kc-gov/ownership",
                    block_id="ownership-rule")

    def test_sync_update(self):
        for name in ("a", "b"):
            self._w("kc-proj/{}.md".format(name), "---\ntype: Runbook\ndescription: d\n---\n\nx\n")
            self._insert(consumer="kc-proj/" + name)
        self._w("kc-gov/ownership.md", self._r("kc-gov/ownership.md").replace(self.OWNER_PAYLOAD, "Neu.\n"))
        self._check(okf_sync.cmd_sync_update)


if __name__ == "__main__":
    unittest.main()
