#!/usr/bin/env python3
"""Tests for cli/okf/history.py (the body-changing commit lookup) and the drift warning of `check`,
both against real git repositories with pinned identities and dates. unittest.

Run: just test tests.test_okf_history -v
"""
import datetime
import os
import shutil
import subprocess
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
from okf import history as okf_history
from tests.okf_testkit import GitCatalogue, SpecCase, needs_git, run_json

UTC = datetime.timezone.utc
T1 = "2026-01-01T10:00:00+02:00"  # 08:00Z
T2 = "2026-02-01T09:00:00-05:00"  # 14:00Z
T3 = "2026-03-01T00:00:00Z"
T4 = "2026-04-01T00:00:00Z"
T5 = "2026-05-01T00:00:00Z"
GENERATED = "type: Note\ngenerated: {{by: claude/4, at: {at}}}"


class HistoryCase(GitCatalogue):
    """A GitCatalogue with the lookup of cli/okf/history.py at hand."""

    def _lookup(self, rel="b/x.md", root=None, **kw):
        history = okf_history.History(root or self.tmp)
        self.addCleanup(history.close)
        return history.last_body_commit(os.path.join(root or self.tmp, rel), **kw)

    def _email(self, *args, **kw):
        """The author email of the lookup result, None when there is no result."""
        got = self._lookup(*args, **kw)
        return got.email if got is not None else None


@needs_git
class BodyCommitLookup(HistoryCase):
    """AC1-AC5 of OKFT-0l2i."""

    def test_returns_the_committer_instant_and_the_author_email_of_the_last_body_commit(self):
        self._doc(body="one\n")
        self._commit("c1", T1)
        self._doc(body="two\n")
        self._commit("c2", T2, author="eve@x.org", author_when="2026-01-31T00:00:00Z")
        got = self._lookup()
        self.assertEqual(got.email, "eve@x.org")
        self.assertEqual(got.time, datetime.datetime(2026, 2, 1, 14, 0, tzinfo=UTC))
        self.assertIsNotNone(got.time.utcoffset())

    def test_the_commit_that_adds_the_file_counts(self):
        self._doc()
        self._commit("c1", T1, author="ann@x.org")
        got = self._lookup()
        self.assertEqual((got.email, got.time), ("ann@x.org", datetime.datetime(2026, 1, 1, 8, 0, tzinfo=UTC)))

    def test_frontmatter_only_commits_are_skipped(self):
        self._doc(body="one\n")
        self._commit("c1", T1, author="body@x.org")
        self._doc(body="one\n", front="type: Note\ntags: [a]")
        self._commit("c2", T2, author="fm@x.org")
        self._doc(body="one\n", front='type: "Note"\ntags: [a]')  # a re-quoting normalisation
        self._commit("c3", T3, author="fm@x.org")
        self.assertEqual(self._email(), "body@x.org")

    def test_a_pure_rename_is_skipped(self):
        self._doc(body="one\nline2\nline3\nline4\nline5\n")
        self._commit("c1", T1, author="body@x.org")
        os.makedirs(os.path.join(self.tmp, "b", "sub"))
        self._git("mv", "b/x.md", "b/sub/y.md")
        self._commit("c2 rename", T2, author="mover@x.org")
        self.assertEqual(self._email("b/sub/y.md"), "body@x.org")

    def test_a_pure_rename_is_skipped_even_when_the_repository_config_turns_rename_detection_off(self):
        self._git("config", "diff.renames", "false")
        self._doc(body="one\nline2\nline3\nline4\nline5\n")
        self._commit("c1", T1, author="body@x.org")
        os.makedirs(os.path.join(self.tmp, "b", "sub"))
        self._git("mv", "b/x.md", "b/sub/y.md")
        self._commit("c2 rename", T2, author="mover@x.org")
        self.assertEqual(self._email("b/sub/y.md"), "body@x.org")

    def test_a_rename_that_also_changes_the_body_counts(self):
        self._doc(body="one\nline2\nline3\nline4\nline5\nline6\nline7\nline8\n")
        self._commit("c1", T1, author="body@x.org")
        os.makedirs(os.path.join(self.tmp, "b", "sub"))
        self._git("mv", "b/x.md", "b/sub/y.md")
        self._doc("b/sub/y.md", body="one\nline2\nline3\nline4\nline5\nline6\nline7\nEDITED\n")
        self._commit("c2 rename and edit", T2, author="mover@x.org")
        self.assertEqual(self._email("b/sub/y.md"), "mover@x.org")

    def test_a_rename_that_changes_only_the_frontmatter_is_skipped(self):
        self._doc(body="one\nline2\nline3\nline4\nline5\n")
        self._commit("c1", T1, author="body@x.org")
        os.makedirs(os.path.join(self.tmp, "b", "sub"))
        self._git("mv", "b/x.md", "b/sub/y.md")
        self._doc("b/sub/y.md", body="one\nline2\nline3\nline4\nline5\n", front="type: Note\ntags: [a]")
        self._commit("c2", T2, author="mover@x.org")
        self.assertEqual(self._email("b/sub/y.md"), "body@x.org")

    def test_an_untracked_file_has_no_result(self):
        self._doc()
        self._commit("c1", T1)
        self._doc("b/new.md")
        self.assertIsNone(self._lookup("b/new.md"))

    def test_a_repository_without_commits_has_no_result(self):
        self._doc()
        self.assertIsNone(self._lookup())

    def test_a_file_outside_any_repository_has_no_result_and_one_note(self):
        outside = os.path.join(os.path.dirname(self.tmp), "okft-no-repo-{}".format(os.getpid()))
        os.makedirs(os.path.join(outside, "b"))
        self.addCleanup(subprocess.run, ["rm", "-rf", outside])
        with open(os.path.join(outside, "b", "x.md"), "w", encoding="utf-8") as f:
            f.write("---\ntype: Note\n---\nbody\n")
        history = okf_history.History(outside)
        self.addCleanup(history.close)
        ap = os.path.join(outside, "b", "x.md")
        self.assertIsNone(history.last_body_commit(ap))
        self.assertIsNone(history.last_body_commit(ap))
        self.assertEqual(len(history.notes()), 1)
        self.assertIn("git repository", history.notes()[0])

    def test_without_the_git_binary_there_is_no_result_and_one_note(self):
        self._doc()
        self._commit("c1", T1)
        history = okf_history.History(self.tmp)
        self.addCleanup(history.close)
        with mock.patch.dict(os.environ, {"PATH": "/nonexistent"}):
            self.assertIsNone(history.last_body_commit(os.path.join(self.tmp, "b", "x.md")))
        self.assertEqual(len(history.notes()), 1)
        self.assertIn("git binary", history.notes()[0])

    def test_two_scopes_without_git_raise_one_note_not_two(self):
        history = okf_history.History(self.tmp)
        self.addCleanup(history.close)
        with mock.patch.dict(os.environ, {"PATH": "/nonexistent"}):
            history.last_body_commit(os.path.join(self.tmp, "b", "x.md"))
            history.last_body_commit(os.path.join(os.path.dirname(self.tmp), "elsewhere", "y.md"))
        self.assertEqual(len(history.notes()), 1)

    def test_a_path_that_is_reused_after_a_rename_is_not_followed_back_into_the_old_history(self):
        self._doc("b/x.md", body="one\nline2\nline3\nline4\nline5\n")
        self._commit("c1", T1, author="body@x.org")
        self._git("mv", "b/x.md", "b/y.md")
        self._commit("c2 rename", T2, author="mover@x.org")
        self._doc("b/x.md", body="unrelated\n")
        self._commit("c3 new file at the old path", T3, author="other@x.org")
        self.assertEqual(self._email("b/y.md"), "body@x.org")

    def test_a_deletion_is_no_body_change_when_the_walk_passes_it(self):
        self._doc(body="one\n")
        self._commit("c1", T1, author="add@x.org")
        self._git("rm", "-q", "b/x.md")
        self._commit("c2 delete", T2, author="deleter@x.org")
        self._doc(body="one\n", front=GENERATED.format(at="2026-01-01T00:00:00Z"))
        self._commit("c3 re-add", T3, author="readd@x.org")
        self.assertEqual(self._email(), "readd@x.org")
        self.assertEqual(self._email(keep_generated=True), "add@x.org")

    # --- the regeneration variant (D45) ---

    def test_keep_generated_skips_a_commit_that_changes_body_and_generated_at_together(self):
        self._doc(body="one\n", front=GENERATED.format(at="2026-01-01T00:00:00Z"))
        self._commit("c1", T1, author="add@x.org")
        self._doc(body="two\n", front=GENERATED.format(at="2026-01-01T00:00:00Z"))
        self._commit("c2", T2, author="edit@x.org")
        self._doc(body="three\n", front=GENERATED.format(at="2026-02-20T00:00:00Z"))
        self._commit("c3 regenerate", T3, author="regen@x.org")
        self.assertEqual(self._email(), "regen@x.org")
        self.assertEqual(self._email(keep_generated=True), "edit@x.org")

    def test_keep_generated_treats_the_adding_commit_with_generated_at_as_a_regeneration(self):
        self._doc(front=GENERATED.format(at="2026-01-01T00:00:00Z"))
        self._commit("c1", T1)
        self.assertIsNone(self._lookup(keep_generated=True))
        self.assertIsNotNone(self._lookup())

    def test_keep_generated_counts_a_body_change_in_a_file_that_has_no_generated_at(self):
        self._doc(body="one\n")
        self._commit("c1", T1, author="add@x.org")
        self._doc(body="two\n")
        self._commit("c2", T2, author="edit@x.org")
        self.assertEqual(self._email(keep_generated=True), "edit@x.org")

    def test_requoting_generated_at_without_changing_the_instant_is_no_change(self):
        self._doc(body="one\n", front=GENERATED.format(at="2026-01-01T00:00:00Z"))
        self._commit("c1", T1)
        self._doc(body="two\n", front=GENERATED.format(at='"2026-01-01T00:00:00+00:00"'))
        self._commit("c2", T2, author="edit@x.org")
        self.assertEqual(self._email(keep_generated=True), "edit@x.org")

    def test_changing_generated_at_to_the_same_instant_in_another_offset_is_no_change(self):
        self._doc(body="one\n", front=GENERATED.format(at="2026-01-01T00:00:00Z"))
        self._commit("c1", T1)
        self._doc(body="two\n", front=GENERATED.format(at="2026-01-01T02:00:00+02:00"))
        self._commit("c2", T2, author="edit@x.org")
        self.assertEqual(self._email(keep_generated=True), "edit@x.org")

    # --- where it looks ---

    def test_the_repository_is_resolved_from_the_file_so_a_catalogue_below_the_top_works(self):
        os.makedirs(os.path.join(self.tmp, "docs"))
        self._doc("docs/b/x.md", body="one\n")
        self._doc("other/y.md", body="other\n")
        self._commit("c1", T1, author="a@x.org")
        self._doc("docs/b/x.md", body="two\n")
        self._commit("c2", T2, author="b@x.org")
        self.assertEqual(self._email("b/x.md", root=os.path.join(self.tmp, "docs")), "b@x.org")

    def test_a_linked_worktree_resolves_its_own_checkout(self):
        self._doc(body="one\n")
        self._commit("c1", T1, author="a@x.org")
        wt = os.path.join(os.path.dirname(self.tmp), "okft-wt-{}".format(os.getpid()))
        self._git("worktree", "add", "-q", "--detach", wt)
        self.addCleanup(subprocess.run, ["rm", "-rf", wt])
        self._doc("b/x.md", body="two\n")
        self._commit("c2", T2, author="b@x.org")
        self._git("checkout", "-q", "--detach", "main", cwd=wt)
        self.assertEqual(self._email("b/x.md", root=wt), "b@x.org")

    # --- cost ---

    def test_git_processes_do_not_grow_with_the_number_of_concepts_or_commits(self):
        def processes(n_concepts, n_commits):
            self._reset()
            for i in range(n_concepts):
                self._doc("b/c{}.md".format(i), body="v0\n")
            self._commit("add", T1)
            for v in range(1, n_commits):
                for i in range(n_concepts):
                    self._doc("b/c{}.md".format(i), body="v{}\n".format(v))
                self._commit("edit {}".format(v), T2)
            history = okf_history.History(self.tmp)
            calls = self._count_git()
            for i in range(n_concepts):
                self.assertIsNotNone(history.last_body_commit(os.path.join(self.tmp, "b", "c{}.md".format(i))))
            history.close()
            return len(calls)

        small = processes(2, 2)
        big = processes(12, 9)
        self.assertEqual(big, small)

    def test_the_walk_reads_no_version_older_than_the_first_body_changing_commit(self):
        for v in range(8):
            self._doc(body="v{}\n".format(v))
            self._commit("edit {}".format(v), T2)
        reads = []
        real = okf_history._Blobs.text

        def counting(self_, sha):
            reads.append(sha)
            return real(self_, sha)

        with mock.patch.object(okf_history._Blobs, "text", counting):
            self.assertIsNotNone(self._lookup())
        self.assertEqual(len(reads), 2)  # the newest version and its parent, nothing older


@needs_git
class DriftWarning(HistoryCase):
    """AC6-AC12 of OKFT-0l2i: the `okf/trust/` warning of `check`."""

    def _drift(self, target="b"):
        return [f for f in self._findings(target) if f.rule.startswith("okf/trust/") and f.severity == "warning"]

    def _history(self, steps):
        """steps: [(front, body, when)] committed in order to b/x.md."""
        self._bundle()
        for n, (front, body, when) in enumerate(steps):
            self._doc(front=front, body=body)
            self._commit("c{}".format(n), when)

    def test_a_body_commit_after_generated_at_without_a_new_generated_at_warns_and_exits_0(self):
        self._history([("type: Note", "one\n", T1),
                       (GENERATED.format(at="2026-01-15T00:00:00Z"), "one\n", T2),
                       (GENERATED.format(at="2026-01-15T00:00:00Z"), "two\n", T3)])
        hits = self._drift()
        self.assertEqual([(f.severity, f.path) for f in hits], [("warning", "b/x.md")])
        envelope, _, code = run_json(self.tmp, "check", "b")
        self.assertEqual(code, 0)
        self.assertEqual([f["severity"] for f in envelope["data"]["findings"]
                          if f["rule"].startswith("okf/trust/")], ["warning"])

    def test_frontmatter_only_commits_after_generated_at_do_not_warn(self):
        self._history([("type: Note", "one\n", T1),
                       ("type: Note", "two\n", T2),
                       (GENERATED.format(at="2026-02-15T00:00:00Z"), "two\n", T3),
                       (GENERATED.format(at="2026-02-15T00:00:00Z") + "\ntags: [a]", "two\n", T4)])
        self.assertEqual(self._drift(), [])

    def test_a_commit_that_changes_body_and_generated_at_together_does_not_warn(self):
        self._history([("type: Note", "one\n", T1),
                       (GENERATED.format(at="2026-02-20T00:00:00Z"), "two\n", T3)])
        self.assertEqual(self._drift(), [])
        self.assertEqual(self._lookup().time, datetime.datetime(2026, 3, 1, tzinfo=UTC))  # the default lookup still sees it

    def test_a_missing_or_unparseable_generated_at_does_not_warn(self):
        for front in ("type: Note", "type: Note\ngenerated: {by: claude/4}",
                      GENERATED.format(at="2026-01-01T00:00:00"), GENERATED.format(at="soon")):
            with self.subTest(front):
                self._reset()
                self._history([("type: Note", "one\n", T1), (front, "two\n", T3)])
                self.assertEqual(self._drift(), [])

    def test_the_comparison_is_between_instants_not_between_texts(self):
        # 2026-03-01T00:00:00+02:00 is 2026-02-28T22:00Z: a body commit at 23:00Z follows it,
        # although its text sorts before.
        self._history([("type: Note", "one\n", T1),
                       (GENERATED.format(at="2026-03-01T00:00:00+02:00"), "one\n", T2),
                       (GENERATED.format(at="2026-03-01T00:00:00+02:00"), "two\n", "2026-02-28T23:00:00Z")])
        self.assertEqual(len(self._drift()), 1)

    def test_a_body_commit_at_the_same_instant_as_generated_at_does_not_warn(self):
        self._history([("type: Note", "one\n", T1),
                       (GENERATED.format(at="2026-03-01T02:00:00+02:00"), "one\n", T2),
                       (GENERATED.format(at="2026-03-01T02:00:00+02:00"), "two\n", T3)])
        self.assertEqual(self._drift(), [])

    def test_a_pure_rename_after_generated_at_does_not_warn(self):
        self._history([("type: Note", "one\nline2\nline3\nline4\nline5\n", T1),
                       (GENERATED.format(at="2026-02-01T00:00:00Z"), "one\nline2\nline3\nline4\nline5\n", T2)])
        os.makedirs(os.path.join(self.tmp, "b", "sub"))
        self._git("mv", "b/x.md", "b/sub/y.md")
        self._commit("rename", T4)
        self.assertEqual(self._drift(), [])

    def test_an_undeclared_bundle_has_no_drift_finding(self):
        self._bundle(None)
        self._doc(front="type: Note", body="one\n")
        self._commit("c1", T1)
        self._doc(front=GENERATED.format(at="2026-01-15T00:00:00Z"), body="one\n")
        self._commit("c2", T2)
        self._doc(front=GENERATED.format(at="2026-01-15T00:00:00Z"), body="two\n")
        self._commit("c3", T3)
        self.assertEqual(self._drift(), [])

    def test_check_writes_nothing(self):
        self._history([("type: Note", "one\n", T1),
                       (GENERATED.format(at="2026-01-15T00:00:00Z"), "one\n", T2),
                       (GENERATED.format(at="2026-01-15T00:00:00Z"), "two\n", T3)])
        def snapshot():
            files = [os.path.join(d, f) for d, _, names in os.walk(self.tmp)
                     if ".git" not in d.split(os.sep) for f in names]
            contents = {}
            for path in files:
                with open(path, "rb") as handle:
                    contents[path] = handle.read()
            return contents

        before = snapshot()
        self.assertEqual(len(self._drift()), 1)
        run_json(self.tmp, "check")
        after = snapshot()
        self.assertEqual(after, before)
        self.assertEqual(self._git("status", "--short"), "")

    def test_no_git_process_runs_for_concepts_without_a_parseable_generated_at_or_in_other_bundles(self):
        self._history([("type: Note", "one\n", T1), ("type: Note\ngenerated: {by: claude/4}", "two\n", T2)])
        self._doc("b/n.md", front=GENERATED.format(at="2026-01-01T00:00:00"))  # unparseable
        self._bundle(None, bundle="v1")
        self._doc("v1/z.md", front=GENERATED.format(at="2026-01-01T00:00:00Z"))
        self._commit("more", T3)
        calls = self._count_git()
        self._findings(None)
        self.assertEqual(calls, [])

    def test_git_processes_do_not_grow_with_the_number_of_concepts(self):
        def processes(n):
            self._reset()
            self._bundle()
            for i in range(n):
                self._doc("b/c{}.md".format(i), front=GENERATED.format(at="2026-01-15T00:00:00Z"), body="one\n")
            self._commit("add", T1)
            for i in range(n):
                self._doc("b/c{}.md".format(i), front=GENERATED.format(at="2026-01-15T00:00:00Z"), body="two\n")
            self._commit("edit", T3)
            calls = self._count_git()
            self.assertEqual(len(self._drift()), n)
            return len(calls)

        self.assertEqual(processes(10), processes(2))

    def test_without_the_git_binary_there_is_no_finding_and_one_note(self):
        self._history([("type: Note", "one\n", T1),
                       (GENERATED.format(at="2026-01-15T00:00:00Z"), "two\n", T3)])
        with mock.patch.dict(os.environ, {"PATH": "/nonexistent"}), \
                mock.patch.object(okf_check, "_note") as note:
            self.assertEqual(self._drift(), [])
        self.assertEqual(note.call_count, 1)
        self.assertIn("git", note.call_args[0][0])


class NoRepository(SpecCase):
    def test_a_bundle_outside_any_repository_gives_no_finding_and_one_envelope_warning(self):
        self._bundle()
        self._concept("generated: {by: claude/4, at: 2026-01-15T00:00:00Z}")
        envelope, _, code = run_json(self.tmp, "check", "b")
        self.assertEqual(code, 0)
        self.assertEqual([f for f in envelope["data"]["findings"] if f["rule"].startswith("okf/trust/")], [])
        notes = [w for w in envelope["warnings"] if w.startswith("drift check skipped")]
        self.assertEqual(len(notes), 1)
        self.assertIn("git repository", notes[0])


if __name__ == "__main__":
    unittest.main()
