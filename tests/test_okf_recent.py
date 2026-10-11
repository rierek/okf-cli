#!/usr/bin/env python3
"""Tests for cli/okf/recent.py — the add-event parser, repository grouping,
ranking, rendering and the recent command. Stdlib unittest, no deps.

Run: python3 -m unittest tests.test_okf_recent -v
"""
import datetime
import json
import os
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli")
if _HERE not in sys.path:  # cli/ holds the okf package
    sys.path.insert(0, _HERE)

from okf import catalogue as okf_catalogue
from okf import recent as okf_recent
from okf.errors import OkfError


class RecentAddEventParse(unittest.TestCase):
    """T1 — parse the `--format=@%at --name-only` stanza stream into
    {repo_rel_path: unix_ts}. Pure: synthetic stdout, no git."""

    def test_stanza_yields_path_to_timestamp(self):
        out = "@1754419680\n\na/one.md\na/two.md\n"
        self.assertEqual(okf_recent.parse_add_events(out),
                         {"a/one.md": 1754419680, "a/two.md": 1754419680})

    def test_multiple_stanzas_all_parsed(self):
        out = "@200\n\nb/new.md\n\n@100\n\na/old.md\n"
        self.assertEqual(okf_recent.parse_add_events(out),
                         {"b/new.md": 200, "a/old.md": 100})

    def test_re_added_path_reports_latest_add(self):
        """D11 — git emits newest-first, so the first sighting wins. A path
        deleted and re-added dates from the re-add, not the original."""
        out = "@900\n\nx.md\n\n@100\n\nx.md\n"
        self.assertEqual(okf_recent.parse_add_events(out), {"x.md": 900})

    def test_blank_and_noise_lines_ignored(self):
        out = "\n@50\n\n\na/one.md\n\n\n"
        self.assertEqual(okf_recent.parse_add_events(out), {"a/one.md": 50})

    def test_empty_output_is_empty_dict(self):
        self.assertEqual(okf_recent.parse_add_events(""), {})

    def test_path_beginning_with_at_is_not_a_timestamp(self):
        """`@notes/x.md` is a path, not a stanza header — only `@<digits>` is."""
        out = "@70\n\n@notes/x.md\n"
        self.assertEqual(okf_recent.parse_add_events(out), {"@notes/x.md": 70})

    def test_paths_before_any_timestamp_are_dropped(self):
        self.assertEqual(okf_recent.parse_add_events("orphan.md\n@10\n\nk.md\n"),
                         {"k.md": 10})


class RecentConceptGitKey(unittest.TestCase):
    """T2 — the repo-relative path git prints for one concept, composed from
    the bundle prefix and the concept id (D08)."""

    def test_key_is_prefix_plus_concept_id(self):
        self.assertEqual(okf_recent.concept_git_key("docs/x-okf", "a/b"),
                         "docs/x-okf/a/b.md")

    def test_empty_prefix_yields_bare_path(self):
        self.assertEqual(okf_recent.concept_git_key("", "agent-memory/note"),
                         "agent-memory/note.md")

    def test_nested_concept_id_keeps_slashes(self):
        self.assertEqual(okf_recent.concept_git_key("p", "a/b/c/d"), "p/a/b/c/d.md")

    def test_key_never_contains_dotdot(self):
        """D08 regression guard. Composing the key with os.path.relpath against
        a symlinked bundle produced `../../Obsidian/...`, which git never
        prints — measured 78/78 misses. The key is built, never derived."""
        for prefix in ("", "docs/x-okf", "deep/nested/prefix"):
            key = okf_recent.concept_git_key(prefix, "sub/concept")
            self.assertNotIn("..", key, prefix)
            self.assertFalse(key.startswith("/"), prefix)


class RecentRepoGrouping(unittest.TestCase):
    """T3 — collapse scopes onto one entry per owning repo, so each repo is
    walked by exactly one git process however many bundles it owns."""

    def test_bundles_sharing_a_toplevel_collapse_to_one_entry(self):
        got = okf_recent.group_scopes_by_repo([
            ("a-okf", "/r", "docs/a-okf"),
            ("b-okf", "/r", "docs/b-okf"),
        ])
        self.assertEqual(got, [("/r", [("a-okf", "docs/a-okf"),
                                       ("b-okf", "docs/b-okf")])])

    def test_distinct_repos_stay_separate(self):
        got = okf_recent.group_scopes_by_repo([
            ("a", "/r1", "a"), ("b", "/r2", "docs/b"),
        ])
        self.assertEqual([repo for repo, _ in got], ["/r1", "/r2"])

    def test_order_is_first_seen(self):
        got = okf_recent.group_scopes_by_repo([
            ("a", "/r2", "a"), ("b", "/r1", "b"), ("c", "/r2", "c"),
        ])
        self.assertEqual([repo for repo, _ in got], ["/r2", "/r1"])
        self.assertEqual(got[0][1], [("a", "a"), ("c", "c")])

    def test_scopes_without_a_repo_are_dropped(self):
        got = okf_recent.group_scopes_by_repo([("a", None, "a"), ("b", "/r", "b")])
        self.assertEqual(got, [("/r", [("b", "b")])])


class RecentRanking(unittest.TestCase):
    """T4 — order [(path, ts_or_None)] newest-first and truncate."""

    def test_newest_first(self):
        got = okf_recent.rank_recent([("old", 100), ("new", 300), ("mid", 200)], 10)
        self.assertEqual([p for p, _ in got], ["new", "mid", "old"])

    def test_limit_truncates_after_sorting(self):
        got = okf_recent.rank_recent([("old", 100), ("new", 300), ("mid", 200)], 2)
        self.assertEqual([p for p, _ in got], ["new", "mid"])

    def test_equal_timestamps_tie_break_by_path(self):
        """One commit adding 40 concepts is the common case — 31 distinct
        add-days over 2966 adds. Ties must be reproducible."""
        got = okf_recent.rank_recent([("z", 100), ("a", 100), ("m", 100)], 10)
        self.assertEqual([p for p, _ in got], ["a", "m", "z"])

    def test_undated_sort_after_every_dated(self):
        """D09 — an untracked file is not evidence of recency."""
        got = okf_recent.rank_recent([("fresh", None), ("ancient", 1)], 10)
        self.assertEqual([p for p, _ in got], ["ancient", "fresh"])

    def test_undated_tie_break_by_path(self):
        got = okf_recent.rank_recent([("z", None), ("a", None)], 10)
        self.assertEqual([p for p, _ in got], ["a", "z"])

    def test_zero_or_negative_limit_returns_empty(self):
        self.assertEqual(okf_recent.rank_recent([("a", 1)], 0), [])
        self.assertEqual(okf_recent.rank_recent([("a", 1)], -3), [])


class RecentRendering(unittest.TestCase):
    """T5 — the one-line-per-concept output contract. `tz` is injected so the
    runner's timezone cannot flake the assertions."""

    UTC = datetime.timezone.utc

    def test_format_created_renders_minute_precision(self):
        # 2026-08-05T18:48:03Z
        self.assertEqual(okf_recent.format_created(1785955683, tz=self.UTC),
                         "2026-08-05 18:48")

    def test_format_created_placeholder_holds_the_column(self):
        placeholder = okf_recent.format_created(None, tz=self.UTC)
        self.assertEqual(placeholder.strip(), "(uncommitted)")
        self.assertEqual(len(placeholder), len("2026-08-05 18:48"))

    def test_line_matches_the_output_contract(self):
        lines = okf_recent.render_recent_lines(
            [(1785955683, "LessonLearned", "agent-memory/beans-store")],
            tz=self.UTC)
        self.assertEqual(
            lines, ["2026-08-05 18:48  LessonLearned  agent-memory/beans-store"])

    def test_type_column_pads_to_widest_in_result_set(self):
        lines = okf_recent.render_recent_lines([
            (1785955683, "LessonLearned", "a/one"),
            (1785955683, "Runbook", "b/two"),
        ], tz=self.UTC)
        self.assertTrue(lines[1].endswith("Runbook        b/two"), lines[1])
        col = [ln.index(ln.split("  ")[-1]) for ln in lines]
        self.assertEqual(col[0], col[1])

    def test_uncommitted_row_keeps_columns_aligned(self):
        lines = okf_recent.render_recent_lines([
            (1785955683, "Runbook", "a/one"),
            (None, "Runbook", "b/two"),
        ], tz=self.UTC)
        self.assertEqual(lines[0].index("Runbook"), lines[1].index("Runbook"))

    def test_empty_rows_render_nothing(self):
        self.assertEqual(okf_recent.render_recent_lines([], tz=self.UTC), [])


class RecentFixtureMixin:
    """Catalogue on disk, git replaced at the seam. `_git_toplevel` and
    `_git_add_events` are the command's entire git surface (T9 pins those two
    against a real repo); everything above them is exercised here without one."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.events = {}          # repo -> stdout string
        self.toplevels = {}       # realpath -> (top, reason)
        self._real_toplevel = okf_catalogue._git_toplevel
        self._real_events = okf_recent._git_add_events
        okf_catalogue._git_toplevel = self._fake_toplevel
        okf_recent._git_add_events = self._fake_events

    def tearDown(self):
        okf_catalogue._git_toplevel = self._real_toplevel
        okf_recent._git_add_events = self._real_events
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fake_toplevel(self, path):
        """Anything not registered in self.toplevels belongs to the catalogue
        repo — the common case, so tests only declare the exceptions."""
        return self.toplevels.get(os.path.realpath(path),
                                  (os.path.realpath(self.tmp), None))

    def _fake_events(self, repo, prefixes):
        got = self.events.get(repo)
        return (got, None) if got is not None else (None, "no-repo")

    def _concept(self, rel, ctype="Runbook", title=None, tags=()):
        ap = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        tagblock = "".join("  - {}\n".format(t) for t in tags)
        with open(ap, "w", encoding="utf-8") as f:
            f.write("---\ntype: {}\ntitle: {}\ndescription: d\n{}---\n# x\n".format(
                ctype, title or os.path.basename(rel)[:-3],
                "tags:\n" + tagblock if tags else ""))
        return ap

    def _run(self, **kw):
        import contextlib
        import io
        import types
        args = types.SimpleNamespace(limit=10, scope=None, type=None,
                                     tag=None, json=False)
        for k, v in kw.items():
            setattr(args, k, v)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            okf_recent.cmd_recent(self.tmp, args)
        return out.getvalue(), err.getvalue()


class RecentCommand(RecentFixtureMixin, unittest.TestCase):
    """T6 — enumeration, join, filtering and output, git stubbed at the seam."""

    def _stub_catalogue_events(self, mapping):
        """{catalogue-relative .md path: unix_ts} → one stanza per timestamp."""
        stanzas = []
        for path, ts in sorted(mapping.items(), key=lambda kv: -kv[1]):
            stanzas.append("@{}\n\n{}\n".format(ts, path))
        self.events[os.path.realpath(self.tmp)] = "\n".join(stanzas)

    def test_lists_newest_first_with_dates(self):
        self._concept("a/old.md")
        self._concept("a/new.md")
        self._stub_catalogue_events({"a/old.md": 1785000000,
                                     "a/new.md": 1785955683})
        out, _ = self._run()
        lines = out.splitlines()
        self.assertIn("a/new", lines[0])
        self.assertIn("a/old", lines[1])
        self.assertNotIn(".md", lines[0])

    def test_trailer_names_shown_and_total(self):
        for i in range(3):
            self._concept("a/c{}.md".format(i))
        self._stub_catalogue_events({"a/c{}.md".format(i): 1785000000 + i
                                     for i in range(3)})
        out, _ = self._run(limit=2)
        self.assertEqual(out.splitlines()[-1], "recent: 2 of 3 concept(s)")

    def test_reserved_and_assets_are_not_concepts(self):
        self._concept("a/real.md")
        for rel in ("a/index.md", "a/log.md", "a/assets/x.md"):
            self._concept(rel)
        self._stub_catalogue_events({"a/real.md": 1785000000})
        out, _ = self._run()
        self.assertIn("recent: 1 of 1 concept(s)", out)

    def test_untracked_concept_listed_undated_at_the_end(self):
        self._concept("a/tracked.md")
        self._concept("a/scratch.md")
        self._stub_catalogue_events({"a/tracked.md": 1785000000})
        out, err = self._run()
        lines = out.splitlines()
        self.assertIn("a/tracked", lines[0])
        self.assertIn("a/scratch", lines[1])
        self.assertIn("(uncommitted)", lines[1])
        self.assertIn("1 concept(s) have no commit that added them", err)

    def test_type_filter_applies(self):
        self._concept("a/one.md", ctype="Runbook")
        self._concept("a/two.md", ctype="Decision")
        self._stub_catalogue_events({"a/one.md": 1, "a/two.md": 2})
        out, _ = self._run(type="Decision")
        self.assertIn("recent: 1 of 1 concept(s)", out)
        self.assertIn("a/two", out)

    def test_tag_filter_applies(self):
        self._concept("a/one.md", tags=("alpha",))
        self._concept("a/two.md", tags=("beta",))
        self._stub_catalogue_events({"a/one.md": 1, "a/two.md": 2})
        out, _ = self._run(tag="alpha")
        self.assertIn("recent: 1 of 1 concept(s)", out)
        self.assertIn("a/one", out)

    def test_scope_narrows_to_one_bundle(self):
        self._concept("a/one.md")
        self._concept("b/two.md")
        self._stub_catalogue_events({"a/one.md": 1, "b/two.md": 2})
        out, _ = self._run(scope="a")
        self.assertIn("recent: 1 of 1 concept(s)", out)
        self.assertIn("a/one", out)

    def test_no_matches_on_empty_catalogue(self):
        os.makedirs(os.path.join(self.tmp, "a"))
        self._stub_catalogue_events({})
        out, _ = self._run()
        self.assertEqual(out, "(no matches)\n")

    def test_json_carries_created_and_created_ts(self):
        self._concept("a/one.md")
        self._stub_catalogue_events({"a/one.md": 1785955683})
        out, _ = self._run(json=True)
        data = json.loads(out)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["created_ts"], 1785955683)
        self.assertEqual(data[0]["path"], "a/one")
        self.assertTrue(data[0]["created"].startswith("2026-08-"))
        for key in ("title", "type", "description"):
            self.assertIn(key, data[0])

    def test_json_undated_concept_has_null_dates(self):
        self._concept("a/one.md")
        self._stub_catalogue_events({})
        out, _ = self._run(json=True)
        data = json.loads(out)
        self.assertIsNone(data[0]["created"])
        self.assertIsNone(data[0]["created_ts"])

    def test_json_empty_result_is_empty_array(self):
        os.makedirs(os.path.join(self.tmp, "a"))
        self._stub_catalogue_events({})
        out, _ = self._run(json=True)
        self.assertEqual(json.loads(out), [])

    def test_symlinked_bundle_resolves_against_its_own_repo(self):
        """D08 end to end — the foreign repo answers for its own concepts, and
        the key that finds them is composed, never derived from relpath."""
        foreign = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, foreign, True)
        bdir = os.path.join(foreign, "docs", "x-okf")
        os.makedirs(bdir)
        with open(os.path.join(bdir, "far.md"), "w", encoding="utf-8") as f:
            f.write("---\ntype: Runbook\ntitle: Far\ndescription: d\n---\n# x\n")
        os.symlink(bdir, os.path.join(self.tmp, "x-okf"))
        self.toplevels[os.path.realpath(bdir)] = (os.path.realpath(foreign), None)
        self.events[os.path.realpath(foreign)] = "@1785955683\n\ndocs/x-okf/far.md\n"
        self._stub_catalogue_events({})
        out, _ = self._run()
        self.assertIn("2026-08-", out.splitlines()[0])
        self.assertIn("x-okf/far", out.splitlines()[0])
        self.assertNotIn("(uncommitted)", out)


class RecentDegradationNotes(RecentFixtureMixin, unittest.TestCase):
    """T7 — degrade while something usable is left, fail when nothing is (D10).
    stdout stays byte-identical whether or not notes were emitted."""

    def test_missing_git_binary_is_a_hard_error(self):
        self.toplevels[os.path.realpath(self.tmp)] = (None, "no-git")
        self._concept("a/one.md")
        with self.assertRaises(OkfError) as cm:
            self._run()
        self.assertEqual((cm.exception.kind, cm.exception.message[:7]), ("internal", "recent:"))

    def test_non_repo_root_is_a_hard_error(self):
        self.toplevels[os.path.realpath(self.tmp)] = (None, "no-repo")
        self._concept("a/one.md")
        with self.assertRaises(OkfError) as cm:
            self._run()
        self.assertEqual((cm.exception.kind, cm.exception.message[:7]), ("invalid_input", "recent:"))

    def test_unreachable_foreign_repo_names_the_bundle_and_lists_undated(self):
        foreign = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, foreign, True)
        bdir = os.path.join(foreign, "docs", "x-okf")
        os.makedirs(bdir)
        with open(os.path.join(bdir, "far.md"), "w", encoding="utf-8") as f:
            f.write("---\ntype: Runbook\ntitle: Far\ndescription: d\n---\n# x\n")
        os.symlink(bdir, os.path.join(self.tmp, "x-okf"))
        self.toplevels[os.path.realpath(bdir)] = (None, "no-repo")
        self.events[os.path.realpath(self.tmp)] = ""
        out, err = self._run()
        self.assertIn("bundle `x-okf` resolves outside any git repository", err)
        self.assertIn("(uncommitted)", out)
        self.assertIn("recent: 1 of 1 concept(s)", out)

    def test_broken_symlink_scope_notes_and_lists_nothing(self):
        os.symlink(os.path.join(self.tmp, "gone"), os.path.join(self.tmp, "dead"))
        self.events[os.path.realpath(self.tmp)] = ""
        out, err = self._run(scope="dead")
        self.assertIn("scope `dead` is a broken symlink", err)
        self.assertEqual(out, "(no matches)\n")

    def test_undated_note_is_aggregated_not_per_concept(self):
        for i in range(3):
            self._concept("a/c{}.md".format(i))
        self.events[os.path.realpath(self.tmp)] = ""
        _, err = self._run()
        self.assertEqual(err.count("note:"), 1)
        self.assertIn("3 concept(s) have no commit", err)

    def test_undated_note_suppressed_when_the_repo_itself_failed(self):
        """A repo whose log could not be read already explains its own
        undated concepts — a second aggregate note would double-report."""
        self._concept("a/one.md")
        self.events.clear()   # _fake_events returns (None, "no-repo")
        _, err = self._run()
        self.assertNotIn("have no commit that added them", err)
        self.assertEqual(err.count("note:"), 1)

    def test_stdout_is_identical_with_and_without_notes(self):
        self._concept("a/one.md")
        self.events[os.path.realpath(self.tmp)] = "@1785955683\n\na/one.md\n"
        clean_out, clean_err = self._run()
        self._concept("a/two.md")
        noisy_out, noisy_err = self._run()
        self.assertEqual(clean_err, "")
        self.assertIn("note:", noisy_err)
        self.assertEqual(clean_out.splitlines()[0], noisy_out.splitlines()[0])


@unittest.skipUnless(shutil.which("git"), "git not installed")
class RecentAgainstRealGit(unittest.TestCase):
    """T9 — the only test in this repo that creates a git repository, and the
    only one that can fail when the contract with the git binary breaks.

    Every assertion in T1-T7 stands against a synthetic string that this repo
    itself authored. Nothing pins that string to git's actual output: drop
    `--no-renames` from the argv, or let git change the stanza grammar, and
    T1-T7 stay green while `okf-cli recent` quietly reports everything
    undated. The contract here is with an external binary, so it is observed,
    not imagined."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _env(self, when):
        env = dict(os.environ)
        env.update({
            "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
            "HOME": self.tmp, "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e",
            "GIT_AUTHOR_DATE": "@{} +0000".format(when),
            "GIT_COMMITTER_DATE": "@{} +0000".format(when),
        })
        return env

    def _git(self, repo, *argv, when=1785000000):
        import subprocess
        base = ["git", "-C", repo, "-c", "init.defaultBranch=main",
                "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
                "-c", "user.name=t", "-c", "user.email=t@e"]
        res = subprocess.run(base + list(argv), capture_output=True, text=True,
                             env=self._env(when))
        self.assertEqual(res.returncode, 0, res.stderr)
        return res

    def _repo(self, name):
        repo = os.path.join(self.tmp, name)
        os.makedirs(repo)
        self._git(repo, "init", "-q")
        return repo

    def _write(self, repo, rel, text="---\ntype: Runbook\n---\n# x\n"):
        ap = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(ap), exist_ok=True)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(text)
        return ap

    def test_add_events_round_trip_through_real_git(self):
        repo = self._repo("cat")
        self._write(repo, "a/one.md")
        self._git(repo, "add", "-A", when=1785000000)
        self._git(repo, "commit", "-qm", "first", when=1785000000)
        self._write(repo, "a/two.md")
        self._git(repo, "add", "-A", when=1785900000)
        self._git(repo, "commit", "-qm", "second", when=1785900000)

        stdout, why = okf_recent._git_add_events(repo, [])
        self.assertIsNone(why, why)
        events = okf_recent.parse_add_events(stdout)
        self.assertEqual(events.get("a/one.md"), 1785000000)
        self.assertEqual(events.get("a/two.md"), 1785900000)

    def test_git_mv_keeps_the_concept_datable(self):
        """D07 guard. git's default rename detection classifies a `git mv` as
        R, which --diff-filter=A drops — and `okf-cli rename` performs exactly
        that move (_git_mv). Removing --no-renames from _git_add_events must
        turn this red; measured on the real catalogue it costs 4 concepts."""
        repo = self._repo("cat")
        self._write(repo, "a/before.md")
        self._git(repo, "add", "-A", when=1785000000)
        self._git(repo, "commit", "-qm", "add", when=1785000000)
        self._git(repo, "mv", "a/before.md", "a/after.md", when=1785900000)
        self._git(repo, "commit", "-qm", "rename", when=1785900000)

        events = okf_recent.parse_add_events(okf_recent._git_add_events(repo, [])[0])
        self.assertIn("a/after.md", events)
        self.assertEqual(events["a/after.md"], 1785900000)

    def test_symlinked_bundle_dates_resolve_against_the_foreign_repo(self):
        """D08 guard. The catalogue tracks a symlinked bundle as ONE entry of
        mode 120000, so its own history knows a single add — the day the link
        was made. The dates live in the foreign repo, and the key that finds
        them is composed from prefix + concept id. Deriving it with
        os.path.relpath against the symlink yields `../../…`, which git never
        prints: measured 78 of 78 concepts undated."""
        catalogue = self._repo("cat")
        foreign = self._repo("proj")
        self._write(foreign, "docs/x-okf/far.md")
        self._git(foreign, "add", "-A", when=1785900000)
        self._git(foreign, "commit", "-qm", "add", when=1785900000)
        bundle_target = os.path.join(foreign, "docs", "x-okf")
        os.symlink(bundle_target, os.path.join(catalogue, "x-okf"))
        self._git(catalogue, "add", "-A", when=1785000000)
        self._git(catalogue, "commit", "-qm", "link", when=1785000000)

        top, why = okf_catalogue._git_toplevel(os.path.join(catalogue, "x-okf"))
        self.assertIsNone(why, why)
        self.assertEqual(os.path.realpath(top), os.path.realpath(foreign))

        prefix = os.path.relpath(os.path.realpath(bundle_target),
                                 os.path.realpath(top)).replace(os.sep, "/")
        events = okf_recent.parse_add_events(okf_recent._git_add_events(top, [prefix])[0])
        self.assertEqual(events.get(okf_recent.concept_git_key(prefix, "far")),
                         1785900000)

    def test_catalogue_repo_knows_only_the_symlink_itself(self):
        """The other half of D08: proves the foreign lookup is necessary, not
        decorative. Asking the catalogue repo about the bundle returns the
        link's own add date and no concept inside it."""
        catalogue = self._repo("cat")
        foreign = self._repo("proj")
        self._write(foreign, "docs/x-okf/far.md")
        self._git(foreign, "add", "-A", when=1785900000)
        self._git(foreign, "commit", "-qm", "add", when=1785900000)
        os.symlink(os.path.join(foreign, "docs", "x-okf"),
                   os.path.join(catalogue, "x-okf"))
        self._git(catalogue, "add", "-A", when=1785000000)
        self._git(catalogue, "commit", "-qm", "link", when=1785000000)

        events = okf_recent.parse_add_events(okf_recent._git_add_events(catalogue, [])[0])
        self.assertEqual(events, {"x-okf": 1785000000})

    def test_non_repo_directory_reports_no_repo(self):
        plain = os.path.join(self.tmp, "plain")
        os.makedirs(plain)
        top, why = okf_catalogue._git_toplevel(plain)
        self.assertIsNone(top)
        self.assertEqual(why, "no-repo")


if __name__ == "__main__":
    unittest.main()
