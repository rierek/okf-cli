#!/usr/bin/env python3
"""Tests for cli/okf/tags.py — the tag verbs and the auto-embedding of newly
registered tags. unittest.
Run: just test tests.test_okf_tags -v
"""
import contextlib
import io
import os
import shutil
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
            return sorted(cmd(self.tmp, args)["files"])

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
        self.assertIn("would rewrite  b/x.md", out)
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
        self.assertEqual(data, {"applied": False, "files": ["b/flow.md"], "unparseable": ["b/bad.md"]})
        self.assertIn("normalize-tags: 1 file(s) would rewrite, 1 unparseable",
                      self._verb(okf_tags.cmd_normalize_tags, apply=False))

    def test_a_tags_value_that_is_not_a_list_is_listed_and_left_unwritten(self):
        text = "---\ntype: Note\ntags: alpha, beta\n---\nbody\n"
        ap = self._w("b/odd.md", text)
        out = self._verb(okf_tags.cmd_merge_tags, tags=["alpha"], into="omega")
        self.assertEqual(self._text(ap), text)
        self.assertIn("unparseable    b/odd.md  (tags field not in inline/block form — skipped)", out)


if __name__ == "__main__":
    unittest.main()
