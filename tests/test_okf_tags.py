#!/usr/bin/env python3
"""Tests for cli/okf/tags.py — the tag verbs and the auto-embedding of newly
registered tags. unittest.
Run: just test tests.test_okf_tags -v
"""
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli")
if _HERE not in sys.path:  # cli/ holds the okf package
    sys.path.insert(0, _HERE)

from okf import catalogue as okf_catalogue
from okf import tags as okf_tags


class TmpTree:
    """A temp directory per test, a file writer and a runner for one tag verb that returns its stdout."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _w(self, rel, text):
        ap = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(text)
        return ap

    def _text(self, ap):
        with open(ap, encoding="utf-8") as f:
            return f.read()

    def _verb(self, cmd, apply=True, where=None, **extra):
        args = types.SimpleNamespace(where=where, apply=apply, json=False, **extra)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cmd(self.tmp, args)
        return out.getvalue()


class AutoEmbedOnRegister(unittest.TestCase):
    """cmd_tags --register must auto-embed new tags (bge-m3) so registration
    and embedding coverage never drift apart (PO-review reject 2026-07-25,
    bean okf-cli-3geg: 125/418 tags were unembedded at review time because
    embedding was a fully manual, separate step). Best-effort: an embedding
    failure (e.g. Ollama down) must never block registration itself."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.bt = okf_catalogue._load_build_tagvec()
        self._orig_embed = self.bt.embed_bge_m3

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.bt.embed_bge_m3 = self._orig_embed

    def test_register_command_auto_embeds_without_manual_produce(self):
        import types
        self.bt.embed_bge_m3 = lambda texts: [[0.1, 0.2, 0.3] for _ in texts]
        args = types.SimpleNamespace(register=[["freshly-minted", "a fresh tag"]])
        okf_tags.cmd_tags(self.tmp, args)
        db_path = os.path.join(self.tmp, ".tagvec", "tag_vectors.sqlite")
        delta_after = self.bt.plan_delta({"freshly-minted"}, "bge-m3", db_path)
        self.assertEqual(delta_after, [])

    def test_embedding_failure_never_blocks_registration(self):
        import types
        def _boom(texts):
            raise RuntimeError("connection refused")
        self.bt.embed_bge_m3 = _boom
        args = types.SimpleNamespace(register=[["still-registered", "stays registered"]])
        okf_tags.cmd_tags(self.tmp, args)  # must not raise
        self.assertEqual(okf_catalogue.load_tags(self.tmp), {"still-registered"})


class RemoveTags(TmpTree, unittest.TestCase):
    """remove-tags: strip tags from frontmatter (no merge target), dry-run default,
    empties strip the whole tags field."""

    def test_removing_the_last_tag_removes_the_key_and_nothing_else(self):
        for tags in ("tags:\n  - only\n", "tags: [only]\n"):
            with self.subTest(tags=tags):
                ap = self._w("b/x.md", "---\ntype: Concept\n" + tags + "title: X   # keep\n---\n# X\n")
                self._verb(okf_tags.cmd_remove_tags, tags=["only"])
                self.assertEqual(open(ap, encoding="utf-8").read(),
                                 "---\ntype: Concept\ntitle: X   # keep\n---\n# X\n")

    def test_removes_one_keeps_others(self):
        ap = self._w("b/x.md", "---\ntype: Concept\ntitle: X\ntags:\n  - keep\n  - drop\n---\n# X\n")
        self._verb(okf_tags.cmd_remove_tags, tags=["drop"])
        new = open(ap, encoding="utf-8").read()
        self.assertIn("  - keep", new)
        self.assertNotIn("drop", new)

    def test_dry_run_writes_nothing(self):
        original = "---\ntype: Concept\ntitle: X\ntags:\n  - drop\n---\n# X\n"
        ap = self._w("b/x.md", original)
        self._verb(okf_tags.cmd_remove_tags, apply=False, tags=["drop"])
        self.assertEqual(open(ap, encoding="utf-8").read(), original)

    def test_where_limits_rewrite(self):
        a = self._w("b/x.md", "---\ntype: Concept\ntitle: X\ntags:\n  - drop\n---\n# X\n")
        b = self._w("c/y.md", "---\ntype: Concept\ntitle: Y\ntags:\n  - drop\n---\n# Y\n")
        self._verb(okf_tags.cmd_remove_tags, tags=["drop"], where="path ~ b/")
        self.assertNotIn("drop", open(a, encoding="utf-8").read())
        self.assertIn("drop", open(b, encoding="utf-8").read())  # out of scope, untouched


class TagCommandsReachStagingContent(TmpTree, unittest.TestCase):
    """OKFT-oe8t Review D02: merge-tags/remove-tags/normalize-tags are write
    paths, not the retrieval surface this bean's fix narrowed (index/list/
    find). The prune that dropped "_intake/" from those three commands must
    NOT also drop it here — a tag rename/removal/normalization would then
    silently leave staging content on the old tag, unreported. Behavioural,
    mirroring the reviewer's own reproduction: a bundle with
    `_intake/staged.md` and a regular concept, both carrying the same tag —
    a dry run must name both."""

    def setUp(self):
        super().setUp()
        self._w("b/_intake/staged.md",
                "---\ntype: Concept\ntitle: Staged\ntags:\n  - oldtag\n---\n# Staged\n")
        self._w("b/sub/regular.md",
                "---\ntype: Concept\ntitle: Regular\ntags:\n  - oldtag\n---\n# Regular\n")

    def test_merge_tags_dry_run_reaches_staging(self):
        """Exact reproduction from the review: `merge-tags oldtag --into
        newtag`, no --apply, must name the _intake file, not just the
        regular one."""
        out = self._verb(okf_tags.cmd_merge_tags, apply=False, tags=["oldtag"], into="newtag")
        self.assertIn("b/_intake/staged.md", out)
        self.assertIn("b/sub/regular.md", out)

    def test_remove_tags_dry_run_reaches_staging(self):
        out = self._verb(okf_tags.cmd_remove_tags, apply=False, tags=["oldtag"])
        self.assertIn("b/_intake/staged.md", out)
        self.assertIn("b/sub/regular.md", out)

    def test_normalize_tags_dry_run_reaches_staging(self):
        # normalize-tags only rewrites an *inline* `tags: [...]` field — the
        # block-list fixtures from setUp never trigger it, so this test
        # needs its own inline-form fixture.
        self._w("b/_intake/staged.md",
                "---\ntype: Concept\ntitle: Staged\ntags: [oldtag]\n---\n# Staged\n")
        self._w("b/sub/regular.md",
                "---\ntype: Concept\ntitle: Regular\ntags: [oldtag]\n---\n# Regular\n")
        out = self._verb(okf_tags.cmd_normalize_tags, apply=False)
        self.assertIn("b/_intake/staged.md", out)
        self.assertIn("b/sub/regular.md", out)

class TagVerbsHonourWhere(unittest.TestCase):
    """OKFT-zpom criteria 7 and 8 — the three tag verbs rewrite only what the --where expression
    selects: the archive when the expression names `archived`, staging content like any other."""

    ARCHIVED = "_archive/b/old.md"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        for rel, ctype in (("b/new.md", "Concept"), (self.ARCHIVED, "Concept"),
                           ("b/_intake/staged.md", "Concept"), ("b/other.md", "Pattern")):
            ap = os.path.join(self.tmp, rel)
            os.makedirs(os.path.dirname(ap), exist_ok=True)
            with open(ap, "w", encoding="utf-8") as f:
                f.write("---\ntype: {}\ntitle: T\ntags: [oldtag]\n---\n# T\n".format(ctype))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def files(self, cmd, where, **extra):
        import contextlib
        import io
        import types
        args = types.SimpleNamespace(where=where, apply=False, json=True, **extra)
        with contextlib.redirect_stdout(io.StringIO()):
            return sorted(f["path"] for f in cmd(self.tmp, args)["files"])

    def verbs(self):
        return [("merge-tags", lambda where: self.files(okf_tags.cmd_merge_tags, where,
                                                         tags=["oldtag"], into="newtag")),
                ("remove-tags", lambda where: self.files(okf_tags.cmd_remove_tags, where,
                                                          tags=["oldtag"])),
                ("normalize-tags", lambda where: self.files(okf_tags.cmd_normalize_tags, where))]

    def test_the_archive_is_untouched_unless_the_expression_names_it(self):
        for name, run in self.verbs():
            with self.subTest(verb=name):
                hidden = run("type = Concept")
                self.assertEqual(hidden, ["b/_intake/staged.md", "b/new.md"])
                reached = run("type = Concept and archived in (true, false)")
                self.assertEqual(reached, ["_archive/b/old.md", "b/_intake/staged.md", "b/new.md"])

    def test_no_expression_selects_every_active_concept_staging_included(self):
        for name, run in self.verbs():
            with self.subTest(verb=name):
                self.assertEqual(run(None), ["b/_intake/staged.md", "b/new.md", "b/other.md"])

    def test_the_expression_narrows_by_a_field_the_path_does_not_carry(self):
        for name, run in self.verbs():
            with self.subTest(verb=name):
                self.assertEqual(run("type = Pattern"), ["b/other.md"])


class TagVerbsWriteThroughTheWriter(TmpTree, unittest.TestCase):
    """R-11 — merge-tags, remove-tags and normalize-tags edit the round-trip mapping and render it
    through render_frontmatter: a write changes only the targeted key and keeps every comment,
    quoting style and the body."""

    LONG = "word " * 40 + "end"
    FRONT = ("---\n# header comment\ntype: Note   # kind\ntitle: \"Quoted\"\ndescription: " + LONG +
             "\ntags:\n  - alpha\n  - beta   # keep me\n  - \"gamma delta\"\n"
             "generated: {by: x, at: 2026-10-09T00:00:00Z}\n---\n\nbody `alpha` text\n")

    def test_merge_changes_only_the_tag_line(self):
        ap = self._w("b/x.md", self.FRONT)
        self._verb(okf_tags.cmd_merge_tags, tags=["alpha"], into="omega")
        self.assertEqual(self._text(ap), self.FRONT.replace("  - alpha\n", "  - omega\n"))

    def test_merge_keeps_the_position_and_drops_a_repeated_tag(self):
        ap = self._w("b/x.md", "---\ntype: Note\ntags:\n  - a\n  - b\n  - c\n---\n")
        self._verb(okf_tags.cmd_merge_tags, tags=["a", "c"], into="z")
        self.assertEqual(self._text(ap), "---\ntype: Note\ntags:\n  - z\n  - b\n---\n")

    def test_merge_keeps_a_flow_list_a_flow_list(self):
        ap = self._w("b/x.md", "---\ntype: Note\ntags: [alpha, \"b c\"]\n---\n")
        self._verb(okf_tags.cmd_merge_tags, tags=["alpha"], into="omega")
        self.assertEqual(self._text(ap), "---\ntype: Note\ntags: [omega, \"b c\"]\n---\n")

    def test_without_apply_nothing_is_written_and_the_lines_say_would_rewrite(self):
        ap = self._w("b/x.md", self.FRONT)
        out = self._verb(okf_tags.cmd_merge_tags, apply=False, tags=["alpha"], into="omega")
        self.assertEqual(self._text(ap), self.FRONT)
        self.assertIn("--- a/b/x.md\n+++ b/b/x.md\n", out)
        self.assertIn("merge-tags: 1 file(s) would rewrite, 0 unparseable — alpha -> omega", out)

    def test_remove_drops_the_tag_and_keeps_everything_else(self):
        ap = self._w("b/x.md", self.FRONT)
        self._verb(okf_tags.cmd_remove_tags, tags=["alpha"])
        self.assertEqual(self._text(ap), self.FRONT.replace("  - alpha\n", ""))

    def test_normalize_turns_a_flow_list_into_a_block_list_and_keeps_quotes(self):
        ap = self._w("b/x.md", "---\ntype: Note   # kind\ntags: [alpha, \"b c\"]\ntitle: T\n---\nbody\n")
        self._verb(okf_tags.cmd_normalize_tags)
        self.assertEqual(self._text(ap),
                         "---\ntype: Note   # kind\ntags:\n  - alpha\n  - \"b c\"\ntitle: T\n---\nbody\n")

    def test_normalize_leaves_a_block_list_and_an_empty_list_alone(self):
        a = self._w("b/a.md", "---\ntype: Note\ntags:\n- x\n---\n")
        b = self._w("b/b.md", "---\ntype: Note\ntags: []\n---\n")
        out = self._verb(okf_tags.cmd_normalize_tags)
        self.assertEqual((self._text(a), self._text(b)), ("---\ntype: Note\ntags:\n- x\n---\n",
                                                           "---\ntype: Note\ntags: []\n---\n"))
        self.assertIn("normalize-tags: 0 file(s) rewrote", out)

    def test_a_file_whose_frontmatter_fails_to_parse_is_listed_and_left_unwritten(self):
        bad = "---\ntype: Note\ndescription: a: b\ntags:\n  - alpha\n---\nbody\n"
        for name, cmd, extra in (("merge-tags", okf_tags.cmd_merge_tags, dict(tags=["alpha"], into="omega")),
                                 ("remove-tags", okf_tags.cmd_remove_tags, dict(tags=["alpha"])),
                                 ("normalize-tags", okf_tags.cmd_normalize_tags, {})):
            with self.subTest(verb=name):
                ap = self._w("b/bad.md", bad)
                out = self._verb(cmd, **extra)
                self.assertEqual(self._text(ap), bad)
                self.assertIn("unparseable    b/bad.md  (frontmatter does not parse: mapping values are not "
                              "allowed here (line 3, column 15) — skipped)", out)

    def test_normalize_names_a_file_that_fails_to_parse_in_its_json_data_and_summary(self):
        import types
        self._w("b/bad.md", "---\ntype: Note\ndescription: a: b\n---\n")
        self._w("b/flow.md", "---\ntype: Note\ntags: [a, b]\n---\n")
        data = okf_tags.cmd_normalize_tags(self.tmp, types.SimpleNamespace(where=None, apply=False, json=True))
        self.assertEqual(data["files"][0]["path"], "b/flow.md")
        self.assertEqual((data["applied"], len(data["files"]), data["unparseable"]), (False, 1, ["b/bad.md"]))
        self.assertIn("normalize-tags: 1 file(s) would rewrite, 1 unparseable",
                      self._verb(okf_tags.cmd_normalize_tags, apply=False))

    def test_a_tags_value_that_is_not_a_list_is_listed_and_left_unwritten(self):
        text = "---\ntype: Note\ntags: alpha, beta\n---\nbody\n"
        ap = self._w("b/odd.md", text)
        out = self._verb(okf_tags.cmd_merge_tags, tags=["alpha"], into="omega")
        self.assertEqual(self._text(ap), text)
        self.assertIn("unparseable    b/odd.md  (tags field not in inline/block form — skipped)", out)


class TagVerbDiffPreview(TmpTree, unittest.TestCase):
    """OKFT-guup — the tag verbs preview one unified diff per affected file (text and `data.files`),
    leave the tree alone without --apply and write exactly the planned text with --apply."""

    VERBS = (("merge-tags", okf_tags.cmd_merge_tags, dict(tags=["alpha"], into="omega")),
             ("remove-tags", okf_tags.cmd_remove_tags, dict(tags=["alpha"])),
             ("normalize-tags", okf_tags.cmd_normalize_tags, dict()))
    BLOCK = "---\ntype: Note\ntitle: T\ntags:\n  - alpha\n  - beta\n---\n# T\n" + "line\n" * 20 + "end\n"
    FLOW = "---\ntype: Note\ntags: [alpha, beta]\n---\nbody"  # flow list, no final newline

    def _tree(self):
        for rel, text in (("b/z.md", self.FLOW), ("a/y.md", self.BLOCK), ("a/x.md", self.FLOW),
                          ("a/none.md", "---\ntype: Note\ntags:\n  - beta\n---\n"),
                          ("a/bad.md", "---\ntype: Note\ndescription: a: b\n---\n"),
                          ("a/odd.md", "---\ntype: Note\ntags: alpha, beta\n---\n")):
            self._w(rel, text)

    def _snapshot(self):
        out = {}
        for dp, _dn, fns in os.walk(self.tmp):
            for fn in fns:
                with open(os.path.join(dp, fn), "rb") as f:
                    out[os.path.relpath(os.path.join(dp, fn), self.tmp)] = f.read()
        return out

    def _json(self, cmd, apply=False, **extra):
        args = types.SimpleNamespace(where=None, apply=apply, json=True, **extra)
        return cmd(self.tmp, args)

    def test_preview_leaves_every_byte_alone_and_json_lists_ordered_diffs(self):
        self._tree()
        for name, cmd, extra in self.VERBS:
            with self.subTest(verb=name):
                before = self._snapshot()
                data = self._json(cmd, **extra)
                self.assertEqual(self._snapshot(), before)
                paths = [f["path"] for f in data["files"]]
                self.assertEqual(paths, sorted(paths))
                self.assertTrue(paths)
                for f in data["files"]:
                    self.assertEqual(sorted(f), ["diff", "old_path", "path"])
                    self.assertIsNone(f["old_path"])
                    self.assertTrue(f["diff"].startswith("--- a/{0}\n+++ b/{0}\n".format(f["path"])))
                self.assertNotIn("a/none.md", paths)
                self.assertNotIn("a/bad.md", paths)

    def test_text_mode_prints_the_json_diffs_in_path_order_and_the_summary(self):
        self._tree()
        data = self._json(okf_tags.cmd_merge_tags, tags=["alpha"], into="omega")
        out = self._verb(okf_tags.cmd_merge_tags, apply=False, tags=["alpha"], into="omega")
        self.assertEqual([f["path"] for f in data["files"]], ["a/x.md", "a/y.md", "b/z.md"])
        positions = [out.index(f["diff"]) for f in data["files"]]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("merge-tags: 3 file(s) would rewrite, 2 unparseable", out)

    def test_unparseable_files_are_reported_and_kept_out_of_the_plan(self):
        self._tree()
        data = self._json(okf_tags.cmd_merge_tags, tags=["alpha"], into="omega")
        self.assertEqual(data["unparseable"], ["a/bad.md", "a/odd.md"])
        out = self._verb(okf_tags.cmd_merge_tags, apply=False, tags=["alpha"], into="omega")
        self.assertIn("unparseable    a/odd.md", out)
        self.assertNotIn("+++ b/a/odd.md", out)

    def test_apply_writes_exactly_the_planned_texts(self):
        self._tree()
        for name, cmd, extra in self.VERBS:
            with self.subTest(verb=name):
                self._tree()
                before = self._snapshot()
                plan = self._json(cmd, **extra)["files"]
                applied = self._json(cmd, apply=True, **extra)["files"]
                self.assertEqual(applied, plan)
                after = self._snapshot()
                changed = sorted(k for k in after if after[k] != before[k])
                self.assertEqual(changed, [f["path"] for f in plan])

    def test_a_crlf_file_shows_its_line_end_change_and_an_invalid_utf8_file_is_left_alone(self):
        crlf = self._w("c/crlf.md", "x")
        with open(crlf, "wb") as f:
            f.write(b"---\r\ntype: Note\r\ntags: [alpha]\r\n---\r\nbody\r\n")
        bad = os.path.join(self.tmp, "c/latin.md")
        with open(bad, "wb") as f:
            f.write(b"---\ntype: Note\ntags: [alpha]\n---\ncaf\xe9\n")
        data = self._json(okf_tags.cmd_merge_tags, tags=["alpha"], into="omega")
        self.assertEqual([f["path"] for f in data["files"]], ["c/crlf.md"])
        self.assertEqual(data["unparseable"], ["c/latin.md"])
        self.assertIn("\r", data["files"][0]["diff"])  # the old side is the stored text, CRLF kept
        self._json(okf_tags.cmd_merge_tags, apply=True, tags=["alpha"], into="omega")
        with open(bad, "rb") as f:
            self.assertEqual(f.read(), b"---\ntype: Note\ntags: [alpha]\n---\ncaf\xe9\n")


@unittest.skipUnless(shutil.which("git"), "git not installed")
class TagVerbPreviewEqualsGitDiff(TmpTree, unittest.TestCase):
    """OKFT-guup SC-01 — per file, the preview of a tag verb and the `git diff` after --apply agree on
    the `---`/`+++` headers and every hunk (git's `diff --git`/`index`/mode lines carry hashes and are
    excluded)."""

    def _git(self, *argv):
        env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
                   HOME=self.tmp, GIT_TERMINAL_PROMPT="0")
        res = subprocess.run(["git", "-C", self.tmp, "-c", "init.defaultBranch=main", "-c", "user.name=t",
                              "-c", "user.email=t@e", "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false"]
                             + list(argv), capture_output=True, env=env)
        self.assertEqual(res.returncode, 0, res.stderr)
        return res.stdout.decode()  # bytes first: text mode would fold the CRLF the diff must show

    def _git_diff(self, rel):
        out = self._git("diff", "--no-color", "--no-ext-diff", "--", rel)
        return out[out.index("--- a/"):]

    def test_preview_equals_git_diff_after_apply(self):
        long_desc = "description: " + "word " * 30 + "end\n"
        files = {
            "kc/a.md": "---\ntype: Note\n" + long_desc + "tags:\n  - alpha\n  - beta   # keep\n---\n\n"
                       + "body\n" * 30 + "alpha\n",
            "kc/b.md": "---\ntype: Note\ntags: [alpha, beta]\ngenerated: {by: x}\n---\nno final newline",
            "kc/sub/c.md": "---\ntype: Note\ntags:\n  - beta\n  - alpha\n  - gamma\n---\n",
            "kc/d.md": "---\r\ntype: Note\r\ntags: [alpha]\r\n---\r\nbody\r\n",
        }
        for name, cmd, extra in TagVerbDiffPreview.VERBS:
            with self.subTest(verb=name):
                shutil.rmtree(self.tmp, ignore_errors=True)
                os.makedirs(self.tmp)
                for rel, text in files.items():
                    ap = os.path.join(self.tmp, rel)
                    os.makedirs(os.path.dirname(ap), exist_ok=True)
                    with open(ap, "wb") as f:
                        f.write(text.encode())
                self._git("init", "-q")
                self._git("add", "-A")
                self._git("commit", "-qm", "base")
                run = lambda apply: cmd(self.tmp, types.SimpleNamespace(where=None, apply=apply, json=True, **extra))
                preview = run(False)["files"]
                self.assertEqual(self._git("status", "--porcelain"), "")
                self.assertTrue(preview)
                run(True)
                self.assertEqual(sorted(self._git("diff", "--name-only").split()), [f["path"] for f in preview])
                for f in preview:
                    self.assertEqual(f["diff"], self._git_diff(f["path"]), f["path"])


if __name__ == "__main__":
    unittest.main()
