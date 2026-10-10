#!/usr/bin/env python3
"""Tests for cli/okf/tags.py — the tag verbs and the auto-embedding of newly
registered tags. Stdlib unittest, no deps.

Run: python3 -m unittest test_okf_tags -v
"""
import os
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:  # cli/ holds the okf package; a repo-root run lacks it
    sys.path.insert(0, _HERE)

from okf import catalogue as okf_catalogue
from okf import tags as okf_tags


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


class RemoveTags(unittest.TestCase):
    """remove-tags: strip tags from frontmatter (no merge target), dry-run default,
    empties strip the whole tags field."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _w(self, rel, text):
        ap = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(text)
        return ap

    def _run(self, tags, scope=None, apply=True):
        import types
        import contextlib
        import io
        args = types.SimpleNamespace(tags=tags, scope=scope, apply=apply)
        with contextlib.redirect_stdout(io.StringIO()):
            okf_tags.cmd_remove_tags(self.tmp, args)

    def test_field_removal_block_form(self):
        text = "---\ntype: Concept\ntitle: X\ntags:\n  - a\n  - b\n---\n# X\n"
        out = okf_tags.remove_tags_field(text)
        self.assertNotIn("tags:", out)
        self.assertIn("title: X", out)
        self.assertIn("# X", out)

    def test_field_removal_inline_form(self):
        text = "---\ntype: Concept\ntags: [a, b]\ntitle: X\n---\n# X\n"
        out = okf_tags.remove_tags_field(text)
        self.assertNotIn("tags:", out)
        self.assertNotIn("[a, b]", out)
        self.assertIn("title: X", out)

    def test_field_removal_no_tags_returns_none(self):
        self.assertIsNone(okf_tags.remove_tags_field("---\ntype: Concept\ntitle: X\n---\n# X\n"))

    def test_removes_one_keeps_others(self):
        ap = self._w("b/x.md", "---\ntype: Concept\ntitle: X\ntags:\n  - keep\n  - drop\n---\n# X\n")
        self._run(["drop"])
        new = open(ap, encoding="utf-8").read()
        self.assertIn("  - keep", new)
        self.assertNotIn("drop", new)

    def test_emptying_strips_tags_field(self):
        ap = self._w("b/x.md", "---\ntype: Concept\ntitle: X\ntags:\n  - only\n---\n# X\n")
        self._run(["only"])
        new = open(ap, encoding="utf-8").read()
        self.assertNotIn("tags:", new)
        self.assertIn("title: X", new)

    def test_dry_run_writes_nothing(self):
        original = "---\ntype: Concept\ntitle: X\ntags:\n  - drop\n---\n# X\n"
        ap = self._w("b/x.md", original)
        self._run(["drop"], apply=False)
        self.assertEqual(open(ap, encoding="utf-8").read(), original)

    def test_scope_limits_rewrite(self):
        a = self._w("b/x.md", "---\ntype: Concept\ntitle: X\ntags:\n  - drop\n---\n# X\n")
        b = self._w("c/y.md", "---\ntype: Concept\ntitle: Y\ntags:\n  - drop\n---\n# Y\n")
        self._run(["drop"], scope="b")
        self.assertNotIn("drop", open(a, encoding="utf-8").read())
        self.assertIn("drop", open(b, encoding="utf-8").read())  # out of scope, untouched


class TagCommandsReachStagingContent(unittest.TestCase):
    """OKFT-oe8t Review D02: merge-tags/remove-tags/normalize-tags are write
    paths, not the retrieval surface this bean's fix narrowed (index/list/
    find). The prune that dropped "_intake/" from those three commands must
    NOT also drop it here — a tag rename/removal/normalization would then
    silently leave staging content on the old tag, unreported. Behavioural,
    mirroring the reviewer's own reproduction: a bundle with
    `_intake/staged.md` and a regular concept, both carrying the same tag —
    a dry run must name both."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._w("b/_intake/staged.md",
                "---\ntype: Concept\ntitle: Staged\ntags:\n  - oldtag\n---\n# Staged\n")
        self._w("b/sub/regular.md",
                "---\ntype: Concept\ntitle: Regular\ntags:\n  - oldtag\n---\n# Regular\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _w(self, rel, text):
        ap = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(text)

    def _run(self, cmd, **extra):
        import types
        import contextlib
        import io
        kwargs = {"scope": None, "apply": False}
        kwargs.update(extra)
        args = types.SimpleNamespace(**kwargs)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cmd(self.tmp, args)
        return buf.getvalue()

    def test_merge_tags_dry_run_reaches_staging(self):
        """Exact reproduction from the review: `merge-tags oldtag --into
        newtag`, no --apply, must name the _intake file, not just the
        regular one."""
        out = self._run(okf_tags.cmd_merge_tags, tags=["oldtag"], into="newtag")
        self.assertIn("b/_intake/staged.md", out)
        self.assertIn("b/sub/regular.md", out)

    def test_remove_tags_dry_run_reaches_staging(self):
        out = self._run(okf_tags.cmd_remove_tags, tags=["oldtag"])
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
        out = self._run(okf_tags.cmd_normalize_tags)
        self.assertIn("b/_intake/staged.md", out)
        self.assertIn("b/sub/regular.md", out)


if __name__ == "__main__":
    unittest.main()
