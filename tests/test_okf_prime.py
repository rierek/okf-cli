#!/usr/bin/env python3
"""Tests for cli/okf/prime.py — the prime command: onboarding guide, live catalogue
state and bundle listing. Stdlib unittest, no deps.

Run: python3 -m unittest tests.test_okf_prime -v
"""
import os
import sys
import unittest

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli")
if _HERE not in sys.path:  # cli/ holds the okf package
    sys.path.insert(0, _HERE)

from okf import catalogue as okf_catalogue
from okf import fts as okf_fts
from okf import parser as okf_parser
from okf import parser_support as okf_parser_support
from okf import prime as okf_prime
from okf import semantic as okf_semantic


class CmdPrimeBundleListing(unittest.TestCase):
    """T-okf-cli-dwcq, revised by okf-cli-3hjr — the three listing depths.

    dwcq made the compact name+count line the DEFAULT, because prime was then
    carrying a 69-line CLAUDE.md on top of it and the total was unreadable. With
    the guide rewritten and sized, the catalogue TOC an agent actually navigates
    by (`index`: description + concepts + directories) is the default again, and
    dwcq's listing survives as `--compact`. --full is unchanged."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        ap = os.path.join(self.tmp, "b", "one.md")
        os.makedirs(os.path.join(self.tmp, "b", "sub"))
        with open(ap, "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: One\ntags:\n  - t\n---\n# One\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _prime(self, full=False, compact=False):
        import io, contextlib, types
        args = types.SimpleNamespace(full=full, compact=compact)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf_prime.cmd_prime(self.tmp, args)
        return buf.getvalue()

    def test_default_runs_the_index_listing(self):
        out = self._prime()
        self.assertIn("description:", out)
        self.assertIn("concepts: 1", out)
        self.assertIn("directories:", out)
        self.assertNotIn("types:", out)      # that depth is --full

    def test_compact_keeps_the_dwcq_one_liner(self):
        out = self._prime(compact=True)
        self.assertIn("b (1 concepts)", out)
        self.assertNotIn("description:", out)
        self.assertNotIn("directories:", out)

    def test_full_adds_types_and_tags(self):
        out = self._prime(full=True)
        self.assertIn("description:", out)
        self.assertIn("types: Concept", out)
        self.assertIn("tags: t", out)


class CmdPrimeOnboardingGuide(unittest.TestCase):
    """okf-cli-3hjr — prime carries its own onboarding guide. Until now it
    printed <root>/CLAUDE.md; that file was removed from the catalogue on
    2026-07-28 (claude-ablation-1, D14/D15), which left prime emitting
    `(missing: CLAUDE.md)` plus a bundle list. The guide now lives in the CLI,
    and its command overview is generated from the same _sub() registry that
    builds the parser, so it cannot drift from the commands it describes."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        ap = os.path.join(self.tmp, "b", "one.md")
        os.makedirs(os.path.dirname(ap))
        with open(ap, "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: One\n---\n# One\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _prime(self, full=False, compact=False, check_semantic=False):
        import io, contextlib, types
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf_prime.cmd_prime(self.tmp, types.SimpleNamespace(
                full=full, compact=compact, check_semantic=check_semantic))
        return buf.getvalue()

    def test_guide_renders_without_claude_md(self):
        """The regression the ablation exposed: no CLAUDE.md, no guide."""
        out = self._prime()
        self.assertNotIn("missing: CLAUDE.md", out)
        self.assertIn("OKF Knowledge Catalogue", out)

    def test_claude_md_is_not_read_at_all(self):
        """Not merely tolerated when absent — no longer a source. A catalogue
        that still carries one must not have it injected into every prime."""
        with open(os.path.join(self.tmp, "CLAUDE.md"), "w", encoding="utf-8") as f:
            f.write("# Guide\nSENTINEL-FROM-CLAUDE-MD\n")
        self.assertNotIn("SENTINEL-FROM-CLAUDE-MD", self._prime())

    def test_overview_covers_every_registered_command(self):
        """The anti-drift guard. A hand-written command list would pass today
        and rot on the next `_sub()` registration; this fails the moment a
        command exists that prime does not name."""
        out = self._prime()
        registered = set(okf_parser_support.subcommand_parsers(okf_parser.build_parser()))
        missing = sorted(n for n in registered if n not in out)
        self.assertEqual(missing, [])

    def test_overview_is_generated_not_transcribed(self):
        """Counter-mutation to the test above: assert the rendering comes from
        the registry, by pinning a summary that only the registry holds."""
        out = self._prime()
        summary = okf_parser.build_parser()
        parsers = okf_parser_support.subcommand_parsers(summary)
        self.assertIn(parsers["find"].description.split(":")[0], out)

    def test_retrieval_path_is_ordered_and_named(self):
        out = self._prime()
        for step in ("find", "index", "toc", "read"):
            self.assertIn(step, out)
        self.assertIn("progressive disclosure", out.lower())

    def test_write_path_names_the_skill_and_the_gate(self):
        out = self._prime()
        self.assertIn("ce-okf", out)
        self.assertIn("check", out)

    def test_state_reports_absent_index_and_open_tag_vocabulary(self):
        out = self._prime()
        self.assertIn("build-index", out)
        self.assertRegex(out, r"(?i)fts index:\s*absent")
        self.assertRegex(out, r"(?i)tag vocabulary:\s*open")

    def test_state_reports_present_index_and_closed_tag_vocabulary(self):
        okf_fts.build_fts_index(self.tmp)
        with open(os.path.join(self.tmp, "TAGS.md"), "w", encoding="utf-8") as f:
            f.write("| tag | description |\n| --- | --- |\n| `x` | y |\n")
        out = self._prime()
        self.assertRegex(out, r"(?i)fts index:\s*present")
        self.assertRegex(out, r"(?i)tag vocabulary:\s*closed")

    def _make_tagvec(self, paths):
        """A .tagvec carrying one CURRENT-content vector per given path.
        The key is computed with the production concept_cache_key() (via
        split_frontmatter/read_file/concept_text(), the same functions
        plan_concept_delta() uses per concept) so 'covered' here means
        exactly what it means to the real detector, not a stand-in key."""
        bt = okf_catalogue._load_build_tagvec()
        db = okf_semantic._tagvec_db_path(self.tmp)
        rows = []
        for p in paths:
            b, cid = p.split("/", 1)
            ap = os.path.join(self.tmp, b, cid + ".md")
            fm, body = okf_catalogue.split_frontmatter(okf_catalogue.read_file(ap))
            title = okf_catalogue._dequote(fm.get("title", "")) or cid
            text = bt.concept_text(title, body)
            key = bt.concept_cache_key(okf_semantic.SEMANTIC_MODEL, p, text)
            rows.append((key, p, okf_semantic.SEMANTIC_MODEL, 2, bt.pack_vec([1.0, 0.0])))
        bt.write_concept_rows(db, rows)

    def test_state_reports_absent_semantic_index(self):
        """Modus-B: the semantic arm degraded silently for 4.4 % of the live
        catalogue because nothing ever said how much of it was embedded. An
        onboarding agent has to learn that the same way it learns about .fts."""
        out = self._prime()
        self.assertRegex(out, r"(?i)semantic index:\s*absent")

    def test_state_reports_an_incomplete_semantic_index(self):
        """The failure mode that actually occurred: an index that is PRESENT
        and silently partial. Two concepts, one vector. --check-semantic runs
        the exact (content-hash) count; see the two gating tests below for the
        cheap default."""
        ap = os.path.join(self.tmp, "b", "two.md")
        with open(ap, "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: Two\n---\n# Two\n")
        self._make_tagvec(["b/one"])
        out = self._prime(check_semantic=True)
        self.assertRegex(out, r"(?i)semantic index:.*1 of 2")
        self.assertIn("build_tagvec", out)

    def test_state_reports_a_complete_semantic_index(self):
        """Counter-mutation: a covered catalogue must NOT be reported as
        partial, or the notice degenerates into noise nobody reads."""
        self._make_tagvec(["b/one"])
        out = self._prime(check_semantic=True)
        self.assertRegex(out, r"(?i)semantic index:\s*complete")
        self.assertNotIn("build_tagvec", out)

    def test_default_prime_skips_the_expensive_content_check(self):
        """B: the content-hash pass reads and hashes every concept body
        (~2.2s over 2590 concepts on the live catalogue) -- too slow for a
        call that runs on every session start. Bare `prime` must not run it;
        it reports presence only, honestly, rather than an unchecked count."""
        self._make_tagvec(["b/one"])
        out = self._prime()
        self.assertRegex(out, r"(?i)semantic index:\s*present")
        self.assertNotRegex(out, r"(?i)semantic index:\s*(complete|partial)")

    def test_check_semantic_flag_runs_the_exact_content_check(self):
        self._make_tagvec(["b/one"])
        out = self._prime(check_semantic=True)
        self.assertRegex(out, r"(?i)semantic index:\s*complete")

    def test_check_semantic_flag_is_documented(self):
        ap = okf_parser.build_parser()
        parsers = okf_parser_support.subcommand_parsers(ap)
        actions = okf_parser_support.parser_actions(parsers["prime"])
        flag = next((a for a in actions if a.dest == "check_semantic"), None)
        self.assertIsNotNone(flag, "prime has no --check-semantic option")
        self.assertTrue((flag.help or "").strip())

    def test_guide_is_catalogue_agnostic(self):
        """The old CLAUDE.md hardcoded one operator's catalogue path into every
        example. The CLI ships to any catalogue; it speaks of --root."""
        out = self._prime()
        self.assertNotIn("Obsidian/Knowledge-Catalogue", out)
        self.assertIn("--root", out)

    def test_root_docs_are_pointed_at_only_when_present(self):
        self.assertNotIn("SPEC.md", self._prime())
        with open(os.path.join(self.tmp, "SPEC.md"), "w", encoding="utf-8") as f:
            f.write("# spec\n")
        self.assertIn("SPEC.md", self._prime())

    def test_bundle_toc_survives_the_guide(self):
        out = self._prime()
        self.assertIn("bundle: b", out)

    def test_find_help_is_inlined(self):
        """`find` is the entry point an agent reaches for first, and its filters
        and score scales are not guessable. prime carries its --help verbatim so
        the first search does not cost a second round trip."""
        out = self._prime()
        find_help = okf_parser_support.subcommand_parsers(okf_parser.build_parser())["find"].format_help()
        self.assertIn(find_help.strip(), out)

    def test_find_help_is_rendered_not_paraphrased(self):
        """Counter-mutation: pin option strings that only argparse emits, so a
        hand-written summary of `find` cannot pass this pair of tests."""
        out = self._prime()
        for flag in ("--breakdown", "--expand-tags", "--scope"):
            self.assertIn(flag, out)
        self.assertIn("score lines:", out)

    def test_bundle_names_are_the_next_call_verbatim(self):
        """Point 4 of the 2026-08-05 brief: every name prime lists must be the
        exact argument of the next call, not a label the agent has to assemble.
        Asserted by resolving each listed name through the production resolver
        rather than by re-deriving the path here."""
        with open(os.path.join(self.tmp, "b", "index.md"), "w", encoding="utf-8") as f:
            f.write("# B\n")
        out = self._prime()
        self.assertIn("toc <bundle>", out)
        for b in okf_catalogue.list_bundles(self.tmp):
            self.assertIn("bundle: {}".format(b), out)
            self.assertTrue(os.path.isfile(okf_catalogue.resolve_concept(self.tmp, b)))


class CmdPrimeCompactGuide(unittest.TestCase):
    """`prime --compact` is what a session-start recipe pulls, and there the
    guide competes for context with the SSTD, the roadmap and the git log. The
    measurement that opened this (2026-08-05): prime was 13199 of 27391
    characters of `just -g start`. --compact drops what is one call away
    (`find --help`) or irrelevant before the first read (the tag-editing
    ceremony), and keeps what is not guessable: every command name, every find
    flag, the two score scales, the live catalogue state, the bundle list.

    The default and --full renderings are untouched; the guards for those live
    in CmdPrimeOnboardingGuide and must stay green alongside these."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        ap = os.path.join(self.tmp, "b", "one.md")
        os.makedirs(os.path.dirname(ap))
        with open(ap, "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: One\n---\n# One\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _prime(self, full=False, compact=False):
        import io, contextlib, types
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            okf_prime.cmd_prime(self.tmp, types.SimpleNamespace(full=full, compact=compact))
        return buf.getvalue()

    def test_compact_is_shorter_than_the_default_guide(self):
        """Both renderings list one bundle here, so the difference is guide
        prose alone — the thing this change is about."""
        self.assertLess(len(self._prime(compact=True)), len(self._prime()))

    def test_compact_drops_the_verbatim_find_help(self):
        find_help = okf_parser_support.subcommand_parsers(okf_parser.build_parser())["find"].format_help()
        self.assertNotIn(find_help.strip(), self._prime(compact=True))

    def test_compact_still_names_every_find_flag(self):
        """The anti-drift guard for the shortened find block: the flag list is
        rendered from the parser, not transcribed, so a flag registered
        tomorrow cannot go missing here. Derived from the production parser
        rather than a literal list, or this test would rot with the text."""
        out = self._prime(compact=True)
        parser = okf_parser_support.subcommand_parsers(okf_parser.build_parser())["find"]
        flags = [o for a in parser._actions for o in a.option_strings
                 if o.startswith("--") and o != "--help"]
        self.assertTrue(flags)
        self.assertEqual(sorted(f for f in flags if f not in out), [])

    def test_compact_keeps_the_two_score_scales_apart(self):
        """`score: a/b` names a scale, not a confidence. An agent that reads
        a/100 and a/(6 * n) as one scale misreads every degraded run — this is
        the one fact from find's help that is not recoverable by trying."""
        out = self._prime(compact=True)
        self.assertIn("a/100", out)
        self.assertIn("6 * n", out)

    def test_compact_points_at_the_full_help(self):
        self.assertIn("find --help", self._prime(compact=True))

    def test_compact_names_every_registered_command(self):
        out = self._prime(compact=True)
        registered = set(okf_parser_support.subcommand_parsers(okf_parser.build_parser()))
        self.assertEqual(sorted(n for n in registered if n not in out), [])

    def test_compact_command_directory_is_one_line_per_command(self):
        """Where the directory's characters went: wrapping at 96 columns put a
        21-space continuation indent under most descriptions. Nothing is
        dropped, the wrapping is — asserted by matching each command's whole
        registered description against its single line."""
        lines = self._prime(compact=True).splitlines()
        parsers = okf_parser_support.subcommand_parsers(okf_parser.build_parser())
        for name, parser in parsers.items():
            head = "    {:<16} ".format(name)
            own = [l for l in lines if l.startswith(head)]
            self.assertEqual(len(own), 1, name)
            self.assertEqual(own[0][len(head):], parser.description)

    def test_compact_keeps_the_write_gate(self):
        out = self._prime(compact=True)
        self.assertIn("ce-okf", out)
        self.assertIn("check", out)

    def test_compact_keeps_the_live_state_and_the_bundles(self):
        out = self._prime(compact=True)
        self.assertRegex(out, r"(?i)fts index:")
        self.assertRegex(out, r"(?i)tag vocabulary:")
        for b in okf_catalogue.list_bundles(self.tmp):
            self.assertIn("{} (1 concepts)".format(b), out)

    def test_compact_keeps_the_retrieval_ladder(self):
        out = self._prime(compact=True)
        for step in ("find", "index", "toc", "read", "refs"):
            self.assertIn(step, out)
        self.assertIn("progressive disclosure", out.lower())

    def test_default_keeps_the_root_contract(self):
        """Counter-mutation to the intro trim: --compact may assume its caller
        passes --root (a recipe or the MCP server always does), the default
        rendering may not — it is what a human reads first."""
        self.assertIn("--root", self._prime())


if __name__ == "__main__":
    unittest.main()
