#!/usr/bin/env python3
"""Tests for cli/okf/wikilinks.py — the `[[…]]` parser, the basename index and
resolver, and the wikilinks command. unittest.
Run: just test tests.test_okf_wikilinks -v
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli")
if _HERE not in sys.path:  # cli/ holds the okf package
    sys.path.insert(0, _HERE)
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from okf import linkscan as okf_linkscan
from okf import wikilinks as okf_wikilinks
from tests.okf_testkit import _cli
from okf.errors import EXIT_CODES


class WikilinkFixtureMixin:
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

    def _r(self, rel):
        with open(os.path.join(self.tmp, rel), encoding="utf-8") as f:
            return f.read()

    def _index(self):
        return okf_wikilinks.build_concept_basename_index(self.tmp)

    def _status(self, source_rel, page):
        return okf_wikilinks.resolve_wikilink(self._index(), source_rel, page)


class WikilinkExtraction(unittest.TestCase):
    """REQ-01 — one record per [[…]] occurrence, with page/alias/suffix/embed
    split out and the region tagged. Pure text parse, no filesystem."""

    def test_shapes(self):
        recs = okf_wikilinks.parse_wikilinks(
            "[[a]] [[a|b]] [[a#h]] [[a#^blk]] ![[a]] [[dir/a]]")
        self.assertEqual([r["page"] for r in recs],
                         ["a", "a", "a", "a", "a", "dir/a"])
        self.assertEqual([r["alias"] for r in recs],
                         [None, "b", None, None, None, None])
        self.assertEqual([r["suffix"] for r in recs],
                         [None, None, "h", "^blk", None, None])
        self.assertEqual([r["embed"] for r in recs],
                         [False, False, False, False, True, False])

    def test_region_is_tagged(self):
        recs = okf_wikilinks.parse_wikilinks(
            '---\ntype: Concept\nrelated:\n  - "[[a]]"\n---\nProse with [[b]].\n')
        self.assertEqual([(r["region"], r["page"]) for r in recs],
                         [("frontmatter", "a"), ("body", "b")])

    def test_code_spans_are_not_links(self):
        recs = okf_wikilinks.parse_wikilinks(
            "```\n[[x]]\n```\n\n~~~\n[[x]]\n~~~\n\nand `[[x]]` inline.\n")
        self.assertEqual(recs, [])

    def test_md_suffix_is_stripped(self):
        self.assertEqual([r["page"] for r in okf_wikilinks.parse_wikilinks("[[a.md]] [[a]]")],
                         ["a", "a"])
        self.assertEqual([r["page"] for r in okf_wikilinks.parse_wikilinks("[[8.3.3]]")],
                         ["8.3.3"])

    def test_unclosed_is_not_a_link(self):
        for text in ("[[a", "[a]]", "[[a\n]]"):
            self.assertEqual(okf_wikilinks.parse_wikilinks(text), [], text)

    def test_raw_excludes_the_embed_marker(self):
        """`raw` is a substitutable link token, so it starts at `[[` — the `!`
        is carried by `embed` instead. The report format depends on it."""
        rec = okf_wikilinks.parse_wikilinks("![[a|Label]]")[0]
        self.assertEqual(rec["raw"], "[[a|Label]]")
        self.assertTrue(rec["embed"])

    def test_in_file_anchor_is_not_a_link(self):
        """`[[#Heading]]` addresses a position in the current file, not another
        concept — a record for it would be reported unresolved forever."""
        self.assertEqual(okf_wikilinks.parse_wikilinks("[[#Heading]] and [[#^blk]]"), [])

    def test_hash_in_an_alias_is_not_a_suffix(self):
        """Obsidian's `#` binds to the page part. `C#` and `bug #42` are
        realistic alias text and must survive as alias, not be split."""
        rec = okf_wikilinks.parse_wikilinks("[[dotnet|C#]]")[0]
        self.assertEqual((rec["page"], rec["alias"], rec["suffix"]), ("dotnet", "C#", None))
        rec = okf_wikilinks.parse_wikilinks("[[issue|bug #42]]")[0]
        self.assertEqual((rec["alias"], rec["suffix"]), ("bug #42", None))

    def test_empty_suffix_is_none_not_empty_string(self):
        self.assertIsNone(okf_wikilinks.parse_wikilinks("[[a#]]")[0]["suffix"])

    def test_page_part_is_stripped(self):
        self.assertEqual(okf_wikilinks.parse_wikilinks("[[ a ]]")[0]["page"], "a")

    def test_comments_are_not_links(self):
        """Obsidian excludes `%%`-commented text from its link index, and an
        HTML comment is never rendered at all."""
        recs = okf_wikilinks.parse_wikilinks(
            "<!-- TODO revisit [[a]] -->\n%% draft: [[b]] %%\nreal [[c]]\n")
        self.assertEqual([r["page"] for r in recs], ["c"])

    def test_indented_code_block_is_not_a_link(self):
        """A 4-space-indented block is a code block that the fence/backtick
        masker does not see. Rewriting inside one corrupts a documentation
        sample, so the wikilink mask has to cover it."""
        recs = okf_wikilinks.parse_wikilinks("Example:\n\n    Use [[a]] in a note.\n\nEnd.\n")
        self.assertEqual(recs, [])

    def test_leading_thematic_rule_does_not_expose_a_fence(self):
        """A body whose first line is `---` opens a head that does not parse as a YAML
        mapping. That region must be masked as body too, or a fenced example inside it
        becomes a rewritable link."""
        recs = okf_wikilinks.parse_wikilinks(
            "---\n\nIntro\n\n```\nexample: [[a]]\n```\n\n---\n\nreal body\n")
        self.assertEqual(recs, [])

    def test_list_continuation_is_not_code(self):
        """Indentation alone is not a code block — the same shape is markdown's
        list-continuation form, and Obsidian indexes links in it."""
        recs = okf_wikilinks.parse_wikilinks("- bullet\n\n    A continuation with [[a]].\n")
        self.assertEqual([r["page"] for r in recs], ["a"])

    def test_comment_regexes_do_not_span_two_comments(self):
        """A greedy comment pattern would swallow everything between the first
        opener and the last closer, hiding every link in between."""
        recs = okf_wikilinks.parse_wikilinks(
            "%% one %%\nlive [[a]]\n%% two %%\n"
            "<!-- three -->\nlive [[b]]\n<!-- four -->\n")
        self.assertEqual([r["page"] for r in recs], ["a", "b"])

    def test_fence_pattern_does_not_span_two_fences(self):
        """A greedy fence pattern reaches from the first opener to the last
        closer and swallows every link in the prose between them."""
        recs = okf_wikilinks.parse_wikilinks(
            "```\nfirst\n```\n\nlive [[a]]\n\n```\nsecond\n```\n")
        self.assertEqual([r["page"] for r in recs], ["a"])

    def test_comment_inside_a_fence_does_not_break_the_fence(self):
        """One alternation matched left to right: whichever construct opens
        first owns the span, so a `%%` inside a fence cannot end it early."""
        self.assertEqual(
            okf_wikilinks.parse_wikilinks("```\n%% x %%\n[[a]]\n```\n"), [])

    def test_frontmatter_indentation_is_structure_not_code(self):
        """The one body rule that must not apply to YAML: a block list under a
        blank line is valid YAML and looks exactly like an indented code block.
        Inline code IS masked here — see test_thematic_rule_region_gets_body_rules
        for why exempting it cost more than it bought."""
        recs = okf_wikilinks.parse_wikilinks(
            '---\ntype: Concept\nrelated:\n\n    - "[[b]]"\n    - "[[c]]"\n---\n# X\n')
        self.assertEqual([(r["region"], r["page"]) for r in recs],
                         [("frontmatter", "b"), ("frontmatter", "c")])

    def test_indented_line_without_a_blank_line_is_not_code(self):
        """A code block needs a blank line to open it. Without that rule every
        continuation line in a wrapped paragraph becomes a dead zone."""
        recs = okf_wikilinks.parse_wikilinks("Some prose\n    continued with [[a]] indented\n")
        self.assertEqual([r["page"] for r in recs], ["a"])

    def test_mask_preserves_length_so_spans_address_the_original(self):
        """The span each record carries is what a rewrite splices on. If the
        mask changed length the offsets would point at the wrong bytes."""
        text = "---\ntype: Concept\n---\n`code` and [[a]] and <!-- c -->\n"
        self.assertEqual(len(okf_linkscan.wikilink_scan_text(text)), len(text))
        a, b = okf_wikilinks.parse_wikilinks(text)[0]["span"]
        self.assertEqual(text[a:b], "[[a]]")

    def test_four_backtick_fence_masks_its_contents(self):
        """A regex pairs backtick runs left to right with no notion of line
        start or fence width, so one prose ``` mention or a 4-backtick fence
        shifted every later pairing by one and left a real code block exposed
        to the rewriter. One live catalogue file carried exactly this shape."""
        self.assertEqual(okf_wikilinks.parse_wikilinks(
            "Use ``` to open a fence.\n\n````\nS = \"[[a]]\"\n````\n"), [])
        self.assertEqual(okf_wikilinks.parse_wikilinks(
            "````\n```\nnested [[a]]\n```\n````\n"), [])

    def test_fence_closing_rules(self):
        """Each closing condition separately: a closer must be at least as wide
        as its opener, must use the same character, and must carry nothing but
        the marker. Any one of them dropped and a fence ends early, exposing
        prose-looking code to the rewriter."""
        # a narrower run does not close a wider fence
        self.assertEqual(okf_wikilinks.parse_wikilinks("````\n```\n[[a]]\n````\n"), [])
        # a tilde run does not close a backtick fence
        self.assertEqual(okf_wikilinks.parse_wikilinks("```\n[[a]]\n~~~\n[[b]]\n```\n"), [])
        # a closer carrying an info string does not close
        self.assertEqual(okf_wikilinks.parse_wikilinks("```\n``` end\n[[a]]\n```\n"), [])
        # a wider run does close a narrower fence
        recs = okf_wikilinks.parse_wikilinks("```\ncode\n````\n\nlive [[a]]\n")
        self.assertEqual([r["page"] for r in recs], ["a"])

    def test_indented_fence_is_recognised(self):
        """Up to three spaces of indent still opens a fence (CommonMark)."""
        self.assertEqual(okf_wikilinks.parse_wikilinks("   ```\n   [[a]]\n   ```\n"), [])

    def test_tab_indented_code_masks(self):
        self.assertEqual(okf_wikilinks.parse_wikilinks("intro\n\n\tcode [[a]] here\n"), [])

    def test_indented_first_line_is_not_code(self):
        """No blank line can precede line 0, so an indented opening line is
        prose (or YAML), never a code block."""
        recs = okf_wikilinks.parse_wikilinks("    [[a]] on the first line\n")
        self.assertEqual([r["page"] for r in recs], ["a"])

    def test_wikilink_pattern_rejects_newlines_and_brackets(self):
        """Load-bearing: a token containing a newline can never be found again
        by a later scan, so a rename must not be able to produce one."""
        self.assertEqual(okf_wikilinks.parse_wikilinks("[[a\nb]]"), [])
        self.assertEqual(okf_wikilinks.parse_wikilinks("[[a[b]]"), [])

    def test_empty_frontmatter_block_is_frontmatter(self):
        recs = okf_wikilinks.parse_wikilinks("---\n---\nBody [[a]]\n")
        self.assertEqual([(r["region"], r["page"]) for r in recs], [("body", "a")])

    def test_a_block_that_fails_to_parse_is_body_text(self):
        """The YAML parse decides, not a first-line heuristic: a plain scalar continued on an
        unindented line is invalid YAML, so its head is body text and the link property in it is
        reported in the body (the loss of sloppy-YAML metadata is the accepted cost of R-11)."""
        recs = okf_wikilinks.parse_wikilinks(
            '---\ndescription: Eine Beschreibung,\n'
            'die hier unindentiert weitergeht\ntags:\n  - x\n'
            'related:\n  - "[[X]]"\n---\nBody [[B]].\n')
        self.assertEqual([(r["region"], r["page"]) for r in recs],
                         [("body", "X"), ("body", "B")])

    def test_indented_first_line_of_a_file_is_not_code(self):
        """An indented run opens a code block only after a blank line. Reading
        the predecessor of line 0 wraps to the LAST line, so a file ending in a
        blank line would open a phantom block on its own first line and drop the
        link — which is why line 0 is excluded outright."""
        recs = okf_wikilinks.parse_wikilinks("    [[A]]\nprose\n\n")
        self.assertEqual([r["page"] for r in recs], ["A"])

    def test_md_suffix_is_stripped_case_insensitively(self):
        self.assertEqual(okf_wikilinks.parse_wikilinks("[[Old.MD]]")[0]["page"], "Old")

    def test_unclosed_fence_runs_to_end_of_file(self):
        """Obsidian renders an unterminated fence as code to EOF, so the
        rewriter must not treat what follows as prose."""
        self.assertEqual(okf_wikilinks.parse_wikilinks("intro\n\n```\ncode [[a]]\n"), [])

    def test_info_string_with_a_backtick_is_not_a_fence(self):
        recs = okf_wikilinks.parse_wikilinks("``` not `a` fence\nstill prose [[a]]\n")
        self.assertEqual([r["page"] for r in recs], ["a"])

    def test_thematic_rule_region_gets_body_rules(self):
        """A head that is not YAML is body text: inline code and indented code
        in it must mask, or the rewriter edits a documentation sample."""
        self.assertEqual(okf_wikilinks.parse_wikilinks(
            "---\n\nWrite `[[a]]` to link.\n\n---\n\nTail.\n"), [])
        self.assertEqual(okf_wikilinks.parse_wikilinks(
            "---\n\nIntro.\n\n    code sample: [[a]]\n\n---\n\nTail.\n"), [])

    def test_yaml_block_with_umlaut_and_colon_keys_is_frontmatter(self):
        """`Übersicht … ISO 9001:2015:` is a real key in this catalogue; an
        ASCII-only key pattern rejected 432 files and pushed their link
        properties into the body region under body masking rules."""
        recs = okf_wikilinks.parse_wikilinks(
            '---\nQualitätsmanagement Grundlagen: "[[a]]"\n'
            'Übersicht dokumentierter Informationen ISO 9001:2015:\n'
            '  - "[[b]]"\n---\n# X\n')
        self.assertEqual([(r["region"], r["page"]) for r in recs],
                         [("frontmatter", "a"), ("frontmatter", "b")])

    def test_nested_dead_zone_does_not_leak_into_raw(self):
        """`raw` is cut from the original text, so a masked span inside the
        brackets cannot put NUL bytes into the record or break `text[span] ==
        raw` — which every rewrite depends on."""
        for text in ("[[a`x`b]]", "[[a<!--c-->b]]", "[[o%%z%%ld]]"):
            recs = okf_wikilinks.parse_wikilinks(text)
            self.assertTrue(recs, text)
            for r in recs:
                self.assertNotIn("\x00", r["raw"], text)
                self.assertEqual(text[r["span"][0]:r["span"][1]], r["raw"], text)

    def test_region_boundary_is_exclusive_at_fm_end(self):
        """The first body byte must be body: an off-by-one here mislabels the
        region and, with the two masks differing, changes what is even seen."""
        text = "---\na: 1\n---[[y]]\n"
        self.assertEqual([r["region"] for r in okf_wikilinks.parse_wikilinks(text)], ["body"])

    def test_inline_code_needs_content(self):
        recs = okf_wikilinks.parse_wikilinks("a `` [[x]] `` b\n")
        self.assertEqual(recs, [])

    def test_nested_list_continuation_is_not_code(self):
        recs = okf_wikilinks.parse_wikilinks("- a\n  - b\n\n      deep [[x]]\n")
        self.assertEqual([r["page"] for r in recs], ["x"])

    def test_second_indented_paragraph_after_a_list_is_not_code(self):
        recs = okf_wikilinks.parse_wikilinks("- item\n\n    cont\n\n    more [[x]]\n")
        self.assertEqual([r["page"] for r in recs], ["x"])

    def test_indented_block_after_two_blank_lines_is_still_list_continuation(self):
        recs = okf_wikilinks.parse_wikilinks("- item\n\n\n    [[x]]\n")
        self.assertEqual([r["page"] for r in recs], ["x"])

    def test_indented_code_span_stops_at_the_last_indented_line(self):
        """A trailing blank line belongs to the prose after the block, not to
        the block. This cannot cost a link: the span already ends before the
        first line that is neither blank nor indented, so the trim only ever
        crosses whitespace — 40 000 fuzzed documents cannot tell the trimmed
        span from the untrimmed one. Kept for the offsets it reports, not for a
        masking difference."""
        recs = okf_wikilinks.parse_wikilinks("intro\n\n    code\n   \n[[x]]\n")
        self.assertEqual([r["page"] for r in recs], ["x"])

    def test_blank_line_inside_an_indented_block_does_not_end_it(self):
        self.assertEqual(okf_wikilinks.parse_wikilinks("intro\n\n    a\n\n    b [[x]]\n"), [])

    def test_fence_in_a_key_like_block_still_means_body(self):
        """A block can open with a real `key:` line and still be body text with
        a fence in it. Only the fence check catches that, and it decides which
        mask the prose AFTER the fence gets."""
        recs = okf_wikilinks.parse_wikilinks(
            "---\ntype: Concept\n```\nf\n```\nSee `[[a]]` here\n---\nTail\n")
        self.assertEqual(recs, [])

    def test_tilde_fence_in_a_key_like_block_still_means_body(self):
        """A tilde fence is as valid as a backtick one in CommonMark. Matching
        only backticks let an unindented `~~~` block sit inside a key-like head
        and the whole thing be judged YAML — frontmatter masking over prose."""
        recs = okf_wikilinks.parse_wikilinks(
            "---\nNote: a line that reads like a key\n~~~\nsample\n~~~\n"
            "and [[X]] here\n---\nBody [[B]].\n")
        self.assertEqual([(r["region"], r["page"]) for r in recs],
                         [("body", "X"), ("body", "B")])

    def test_percent_comment_in_frontmatter_is_masked(self):
        self.assertEqual(okf_wikilinks.parse_wikilinks("---\nx: %%[[a]]%%\n---\n# X\n"), [])

    def test_inline_code_in_frontmatter_is_masked(self):
        """Inline code is masked in BOTH regions. Exempting it in frontmatter
        cost more than it bought: a `---` thematic rule whose first line happens
        to read like `key: value` lands in the YAML branch, and its prose
        backticks then become rewritable. A genuine backticked link property has
        zero occurrences catalogue-wide — under-reported, never corrupted."""
        recs = okf_wikilinks.parse_wikilinks(
            '---\ntype: Concept\nnote: "see `[[X]]` for details"\n---\nBody [[B]].\n')
        self.assertEqual([(r["region"], r["page"]) for r in recs], [("body", "B")])

    def test_a_head_counts_as_frontmatter_only_when_it_parses_as_a_mapping(self):
        for text, head in (
            ("---\ntype: Concept\n---\nbody\n", "---\ntype: Concept\n---"),
            ("---\n---\nbody\n", "---\n---"),
            ("---\ntype: Concept\nnote: |\n  ```\n  [[a]]\n  ```\n---\nbody\n",
             "---\ntype: Concept\nnote: |\n  ```\n  [[a]]\n  ```\n---"),
        ):
            self.assertEqual(okf_linkscan.wikilink_regions(text)[0], ("frontmatter", 0, len(head)), repr(text))
        for text in (
            "no frontmatter at all\n",
            "---\ntype: Concept\nbody never closes\n",
            "---\njust a thematic rule and prose\n---\nbody\n",
            "---\n- a\n- b\n---\nbody\n",
            "---\ntype: [unclosed\n---\nbody\n",
        ):
            self.assertEqual(okf_linkscan.wikilink_regions(text), [
                ("frontmatter", 0, 0), ("body", 0, len(text))], repr(text))


class WikilinkResolve(WikilinkFixtureMixin, unittest.TestCase):
    """REQ-02..REQ-05 — basename resolution, same-bundle tie-break, ambiguity,
    unresolved."""

    def test_unique_basename(self):
        self._w("b/x.md", "---\ntype: Concept\n---\nSee [[y]].\n")
        self._w("other/sub/y.md", "---\ntype: Concept\n---\n# Y\n")
        self.assertEqual(self._status("b/x.md", "y"),
                         ("resolved", ["/other/sub/y.md"]))

    def test_alias_and_suffix_do_not_affect_resolution(self):
        self._w("b/x.md", "---\ntype: Concept\n---\n"
                          "[[y]] [[y|Label]] [[y#Heading]] [[y#^blk]] [[y.md]]\n")
        self._w("other/sub/y.md", "---\ntype: Concept\n---\n# Y\n")
        recs = okf_wikilinks.resolve_wikilink_records(
            self._index(), okf_wikilinks.parse_wikilinks(self._r("b/x.md"), "b/x.md"))
        self.assertEqual([r["candidates"] for r in recs],
                         [["/other/sub/y.md"]] * 5)

    def test_same_bundle_wins(self):
        self._w("a/x.md", "---\ntype: Concept\n---\nSee [[g]].\n")
        self._w("a/g.md", "---\ntype: Concept\n---\n# G\n")
        self._w("b/g.md", "---\ntype: Concept\n---\n# G\n")
        self.assertEqual(self._status("a/x.md", "g"), ("resolved", ["/a/g.md"]))

    def test_tie_break_compares_bundles_case_insensitively(self):
        """D10 — on this filesystem `A/x.md` and `a/x.md` are one file. A
        case-sensitive tie-break made the same link resolve from one spelling
        and go ambiguous from the other."""
        self._w("a/g.md", "---\ntype: Concept\n---\n# G\n")
        self._w("b/g.md", "---\ntype: Concept\n---\n# G\n")
        self.assertEqual(self._status("A/x.md", "g"), ("resolved", ["/a/g.md"]))

    def test_case_folding_matches_obsidian_not_unicode_casefold(self):
        """Obsidian folds with JavaScript `toLowerCase()`, which leaves ß alone.
        `casefold()` maps ß to ss, so it would resolve `[[STRASSE]]` here and
        leave the link broken in the app — and on a case-sensitive checkout it
        would collapse `Straße.md` and `Strasse.md` into one shadowing key."""
        self._w("a/Straße.md", "---\ntype: Concept\n---\n# S\n")
        self.assertEqual(self._status("a/x.md", "straße"),
                         ("resolved", ["/a/Straße.md"]))
        self.assertEqual(self._status("a/x.md", "STRASSE"), ("unresolved", []))

    def test_path_form_tail_is_compared_case_insensitively(self):
        self._w("b/sub/name.md", "---\ntype: Concept\n---\n# N\n")
        self.assertEqual(self._status("b/x.md", "Sub/Name"),
                         ("resolved", ["/b/sub/name.md"]))
        # …and with the casing on the DISK side, which a one-sided casefold
        # of the query alone would still get wrong.
        self._w("c/Sub/Name.md", "---\ntype: Concept\n---\n# N\n")
        self.assertEqual(self._status("c/x.md", "sub/name"),
                         ("resolved", ["/c/Sub/Name.md"]))

    def test_reserved_file_participates_as_a_source(self):
        """D04 — reserved files are not link TARGETS but they do carry links,
        and the reporting surface must list them."""
        self._w("a/index.md", "# A\n\nIntro.\n\nSee [[y]].\n")
        self._w("a/y.md", "---\ntype: Concept\n---\n# Y\n")
        links = okf_wikilinks.scan_wikilinks(self.tmp, "a")
        self.assertEqual([(l["source"], l["status"]) for l in links],
                         [("a/index.md", "resolved")])

    def test_candidate_order_is_deterministic(self):
        """An unsorted candidate list makes an ambiguous report differ between
        runs on the same tree, and AC-04.1 rests on the order."""
        for b in ("d", "a", "c", "b"):
            self._w("{}/g.md".format(b), "---\ntype: Concept\n---\n# G\n")
        status, cands = self._status("z/x.md", "g")
        self.assertEqual((status, cands),
                         ("ambiguous", ["/a/g.md", "/b/g.md", "/c/g.md", "/d/g.md"]))

    def test_ambiguous_across_foreign_bundles(self):
        self._w("c/x.md", "---\ntype: Concept\n---\nSee [[g]].\n")
        self._w("a/g.md", "---\ntype: Concept\n---\n# G\n")
        self._w("b/g.md", "---\ntype: Concept\n---\n# G\n")
        self.assertEqual(self._status("c/x.md", "g"),
                         ("ambiguous", ["/a/g.md", "/b/g.md"]))

    def test_ambiguous_within_one_bundle(self):
        """The tie-break is bundle-level, not directory-level: two candidates in
        the linking file's own bundle stay ambiguous."""
        self._w("a/x.md", "---\ntype: Concept\n---\nSee [[g]].\n")
        self._w("a/g.md", "---\ntype: Concept\n---\n# G\n")
        self._w("a/sub/g.md", "---\ntype: Concept\n---\n# G\n")
        self.assertEqual(self._status("a/x.md", "g"),
                         ("ambiguous", ["/a/g.md", "/a/sub/g.md"]))

    def test_missing_target(self):
        self._w("a/x.md", "---\ntype: Concept\n---\nSee [[ghost]].\n")
        self.assertEqual(self._status("a/x.md", "ghost"), ("unresolved", []))

    def test_path_form_target_uses_last_segment(self):
        self._w("a/x.md", "---\ntype: Concept\n---\n[[800 Bank/Claude Code Skills]]\n")
        page = okf_wikilinks.parse_wikilinks(self._r("a/x.md"))[0]["page"]
        self.assertEqual(page, "800 Bank/Claude Code Skills")
        self.assertEqual(self._status("a/x.md", page), ("unresolved", []))

    def test_non_concept_target_is_unresolved(self):
        """No extension-based exclusion exists (D05 retired): a clause number and
        an image name are looked up like any other page part and reported."""
        self._w("a/x.md", "---\ntype: Concept\n---\n[[8.3.3]] and [[diagram.png]]\n")
        recs = okf_wikilinks.resolve_wikilink_records(
            self._index(), okf_wikilinks.parse_wikilinks(self._r("a/x.md"), "a/x.md"))
        self.assertEqual([r["page"] for r in recs], ["8.3.3", "diagram.png"])
        self.assertEqual([r["status"] for r in recs], ["unresolved", "unresolved"])

    def test_resolution_is_case_insensitive(self):
        """The store's filesystem is case-insensitive and Obsidian resolves
        accordingly: `[[YAML]]` opens `yaml.md`. A case-sensitive table calls
        96 live catalogue links dead and lets rename orphan them unannounced."""
        self._w("a/yaml.md", "---\ntype: Concept\n---\n# YAML\n")
        self._w("a/GLOSSARY.md", "---\ntype: Concept\n---\n# Glossary\n")
        self._w("a/x.md", "---\ntype: Concept\n---\nSee [[YAML]] and [[glossary]].\n")
        # Both directions: an uppercase link onto a lowercase file, and a
        # lowercase link onto an uppercase file. Casefolding only the lookup
        # side passes the first and fails the second.
        self.assertEqual(self._status("a/x.md", "YAML"), ("resolved", ["/a/yaml.md"]))
        self.assertEqual(self._status("a/x.md", "glossary"), ("resolved", ["/a/GLOSSARY.md"]))

    def test_path_form_target_is_honoured_when_it_matches(self):
        """An author who spelled the directory out meant it. Answering with the
        candidate that spelling excludes is worse than answering unresolved."""
        self._w("a/old.md", "---\ntype: Concept\n---\n# A\n")
        self._w("z/deep/old.md", "---\ntype: Concept\n---\n# Z\n")
        self._w("z/x.md", "---\ntype: Concept\n---\nSee [[a/old]].\n")
        self.assertEqual(self._status("z/x.md", "a/old"), ("resolved", ["/a/old.md"]))
        self.assertEqual(self._status("a/src.md", "z/deep/old"),
                         ("resolved", ["/z/deep/old.md"]))

    def test_path_form_that_matches_nothing_is_unresolved(self):
        """No fallback to the bare basename: falling back answered with the very
        candidate the spelled-out path excludes. With `a/_plan/old.md` unindexed
        as staging, `[[_plan/old]]` used to resolve to `a/old.md` — a different
        file — and rename then rewrote it."""
        self._w("a/y.md", "---\ntype: Concept\n---\n# Y\n")
        self.assertEqual(self._status("a/x.md", "gone/y"), ("unresolved", []))
        self._w("a/old.md", "---\ntype: Concept\n---\n# Old\n")
        self._w("a/_plan/old.md", "---\ntype: Concept\n---\n# Draft\n")
        self.assertEqual(self._status("c/x.md", "_plan/old"), ("unresolved", []))

    def test_reserved_file_is_not_a_resolution_target(self):
        """`index.md` is bundle furniture, not a concept — every bundle has one,
        so `[[index]]` could never address a unique file."""
        self._w("a/index.md", "# A\n\nIntro.\n")
        self.assertEqual(self._status("a/x.md", "index"), ("unresolved", []))

    def test_staging_concept_is_not_a_resolution_target(self):
        """No reporting or check surface scans `_`-prefixed staging, so a draft
        there must not be able to satisfy a link either — otherwise a link
        resolves against a file nothing ever audits."""
        self._w("a/_inbox/draft.md", "---\ntype: Concept\n---\n# Draft\n")
        self.assertEqual(self._status("a/x.md", "draft"), ("unresolved", []))

    def test_symlinked_bundle_concepts_are_resolvable_targets(self):
        """os.walk does not descend into a symlinked SUBdirectory, so the index
        walks per bundle — five catalogue bundles are symlinks and a root-level
        walk would make every concept in them unresolvable."""
        import tempfile
        ext = tempfile.mkdtemp()
        try:
            with open(os.path.join(ext, "mounted.md"), "w", encoding="utf-8") as f:
                f.write("---\ntype: Concept\n---\n# Mounted\n")
            os.symlink(ext, os.path.join(self.tmp, "ext-bundle"))
            self._w("a/x.md", "---\ntype: Concept\n---\nSee [[mounted]].\n")
            self.assertEqual(self._status("a/x.md", "mounted"),
                             ("resolved", ["/ext-bundle/mounted.md"]))
        finally:
            import shutil
            shutil.rmtree(ext, ignore_errors=True)

    def test_nfd_filename_matches_nfc_link(self):
        """OKFT-gm5k: APFS delivers filenames in NFD, but users type links
        in NFC. build_concept_basename_index normalizes filenames; resolve_wikilink
        normalizes link text. Both must use the same order (NFC + lowercase) to
        match bidirectionally."""
        import unicodedata
        # Create a concept with an umlaut filename in NFD (APFS form).
        name_nfd = unicodedata.normalize('NFD', 'Größe')  # ö = o + combining diacritic
        self._w(f"a/{name_nfd}.md", "---\ntype: Concept\n---\n# Größe\n")
        # Type the same word in NFC (user input) and check it resolves.
        name_nfc = unicodedata.normalize('NFC', 'Größe')  # ö = single precomposed char
        self.assertEqual(self._status("a/x.md", name_nfc),
                         ("resolved", [f"/a/{name_nfd}.md"]))

    def test_nfc_filename_matches_nfd_link(self):
        """Reverse of above: file created with NFC normalization (e.g., from
        editor or git), link queried with NFD (rare but possible on clipboard
        paste). Both forms must resolve to the same concept."""
        import unicodedata
        name_nfc = unicodedata.normalize('NFC', 'Größe')
        self._w(f"a/{name_nfc}.md", "---\ntype: Concept\n---\n# Größe\n")
        name_nfd = unicodedata.normalize('NFD', 'Größe')
        self.assertEqual(self._status("a/x.md", name_nfd),
                         ("resolved", [f"/a/{name_nfc}.md"]))

    def test_case_folding_does_not_use_casefold_preserving_d06(self):
        """D06 regression test: casefold() would map ß → ss, causing [[STRASSE]]
        to resolve to Straße.md. JavaScript toLowerCase() (which Obsidian uses)
        leaves ß alone. Our _normalize_key() matches that, using .lower() not
        casefold()."""
        self._w("a/Straße.md", "---\ntype: Concept\n---\n# S\n")
        # Uppercase german eszett does not exist in lowercase form; [[STRASSE]]
        # should not resolve.
        self.assertEqual(self._status("a/x.md", "STRASSE"),
                         ("unresolved", []))
        # But [[straße]] should resolve just fine.
        self.assertEqual(self._status("a/x.md", "straße"),
                         ("resolved", ["/a/Straße.md"]))


class WikilinkArchiveResolution(WikilinkFixtureMixin, unittest.TestCase):
    """R-05/R-06 (docs/okf-archive-lifecycle/SPEC.md) — build_concept_basename_index
    picks up _archive/<bundle>/** as a resolution target, active candidates
    take precedence over archived ones, and existing ambiguity among active
    candidates is unaffected by the archive being resolvable at all."""

    # -- A05/AC1/AC3: archive as a resolution target ---------------------
    def test_archived_concept_is_a_resolution_target(self):
        """A link into a concept that only exists under _archive/ must not go
        unresolved the moment archiving moves the file there."""
        self._w("_archive/a/old.md", "---\ntype: Concept\n---\n# Old\n")
        self.assertEqual(self._status("b/x.md", "old"),
                         ("resolved", ["/_archive/a/old.md"]))

    def test_archived_candidate_used_only_when_no_active_one_exists(self):
        """AC3 — with no active candidate, resolution falls back to the
        archived candidate(s)."""
        self._w("_archive/z/old.md", "---\ntype: Concept\n---\n# Archived Old\n")
        self.assertEqual(self._status("b/x.md", "old"),
                         ("resolved", ["/_archive/z/old.md"]))

    def test_two_archived_candidates_with_no_active_are_ambiguous(self):
        """Symmetric to AC4 in the archived tier: no active candidate at all
        and two archived ones of the same basename stay ambiguous rather than
        one being picked arbitrarily."""
        self._w("_archive/a/g.md", "---\ntype: Concept\n---\n# G\n")
        self._w("_archive/b/g.md", "---\ntype: Concept\n---\n# G\n")
        self.assertEqual(self._status("c/x.md", "g"),
                         ("ambiguous", ["/_archive/a/g.md", "/_archive/b/g.md"]))

    # -- T01/AC2 (okf-cli-yixf): existing-but-empty _archive/ -------------
    def test_existing_but_empty_archive_directory_does_not_crash_or_contribute(self):
        """AC2 — _archive/ can exist while holding no bundle at all (e.g. a
        hand-created directory, or a race with an external mkdir):
        list_bundles(archive_root) then returns [], the
        `if os.path.isdir(archive_root):` branch (cli/okf-cli.py:3436) is
        taken, and its loop body never runs. Geometry only: build must not
        crash, and resolution of an unrelated active concept must be
        unaffected — a bogus empty _archive/ must not itself become a
        candidate or otherwise perturb the index.

        Not a precedence-sensitive test: with zero archived candidates for
        any basename here, _apply_archive_precedence's active/archived
        filter is a no-op regardless of whether it runs at all — mutating or
        removing it cannot change this test's outcome. See this leaf's
        closing report (okf-cli-yixf) for that reading, flagged rather than
        silently claimed as SC-03 coverage."""
        os.makedirs(os.path.join(self.tmp, "_archive"))
        self._w("a/old.md", "---\ntype: Concept\n---\n# Old\n")
        idx = self._index()
        self.assertEqual(idx.get("old"), ["/a/old.md"])
        self.assertEqual(self._status("b/x.md", "old"), ("resolved", ["/a/old.md"]))

    # -- A06/AC2/SC-02: precedence — active wins over archived ------------
    def test_active_candidate_wins_over_an_archived_one_of_the_same_name(self):
        """SC-02/SC-03 — with an active AND an archived concept sharing a
        basename, the link resolves to the active one rather than reporting
        ambiguity. This is also the guard-reversal test named by SC-03:
        removing the active-before-archived precedence from
        build_concept_basename_index turns this assertion red."""
        self._w("a/old.md", "---\ntype: Concept\n---\n# Active Old\n")
        self._w("_archive/z/old.md", "---\ntype: Concept\n---\n# Archived Old\n")
        self.assertEqual(self._status("b/x.md", "old"),
                         ("resolved", ["/a/old.md"]))

    # -- A07/AC4/SC-04 (Gate-B finding F01): active ambiguity unchanged ---
    def test_two_active_candidates_stay_ambiguous_even_with_an_archived_third(self):
        """SC-04 — two active concepts sharing a basename still report
        ambiguous once archive resolution is in place; a same-named archived
        concept must not silently join the candidate set or defuse the
        ambiguity."""
        self._w("a/g.md", "---\ntype: Concept\n---\n# G\n")
        self._w("b/g.md", "---\ntype: Concept\n---\n# G\n")
        self._w("_archive/z/g.md", "---\ntype: Concept\n---\n# Archived G\n")
        self.assertEqual(self._status("c/x.md", "g"),
                         ("ambiguous", ["/a/g.md", "/b/g.md"]))


class WikilinkCommand(WikilinkFixtureMixin, unittest.TestCase):
    """REQ-06..REQ-09 — the `wikilinks` reporting command."""

    def setUp(self):
        super().setUp()
        self._w("a/index.md", "# A\n\nBundle entry with an intro paragraph.\n")
        self._w("a/y.md", "---\ntype: Concept\n---\n# Y\n")
        self._w("a/x.md", '---\ntype: Concept\nrelated:\n  - "[[ghost]]"\n---\n'
                          "Good [[y]] and bad [[nowhere]].\n")
        self._w("b/z.md", "---\ntype: Concept\n---\nAlso [[y]].\n")

    def test_report_line_shape(self):
        out = _cli(self.tmp, "wikilinks")
        self.assertEqual(out.returncode, 0, out.stderr)
        lines = [l for l in out.stdout.splitlines() if not l.startswith("wikilinks:")]
        self.assertEqual(len(lines), 4)
        for line in lines:
            self.assertRegex(
                line,
                r"^(resolved|ambiguous|unresolved)\s+(body|frontmatter)\s+\S+\s+\[\[.*\]\]")

    def test_summary_line_shape(self):
        out = _cli(self.tmp, "wikilinks")
        self.assertRegex(out.stdout.splitlines()[-1],
                         r"^wikilinks: \d+ link\(s\), \d+ resolved, \d+ ambiguous, "
                         r"\d+ unresolved$")

    def test_exit_code_is_zero_with_findings(self):
        """The report is a report, not a gate — `check` is where a wikilink can
        fail a run, and only for an opted-in bundle."""
        out = _cli(self.tmp, "wikilinks")
        self.assertIn("unresolved", out.stdout)
        self.assertEqual(out.returncode, 0)

    def test_unresolved_filter_keeps_summary_totals(self):
        out = _cli(self.tmp, "wikilinks", "--unresolved")
        lines = [l for l in out.stdout.splitlines() if not l.startswith("wikilinks:")]
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(l.startswith("unresolved") for l in lines), lines)
        self.assertIn("wikilinks: 4 link(s), 2 resolved, 0 ambiguous, 2 unresolved",
                      out.stdout)

    def test_json_is_parseable(self):
        out = _cli(self.tmp, "wikilinks", "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        json.loads(out.stdout)

    def test_json_shape(self):
        data = json.loads(_cli(self.tmp, "wikilinks", "--json").stdout)["data"]
        keys = {"source", "region", "raw", "page", "alias", "suffix", "embed",
                "status", "candidates"}
        for link in data["links"]:
            self.assertTrue(keys.issubset(link), sorted(keys - set(link)))
        total = sum(sum(c.values()) for c in data["by_bundle"].values())
        self.assertEqual(total, len(data["links"]))
        self.assertEqual(sorted(data["by_bundle"]), ["a", "b"])

    def test_target_argument_scopes_the_scan(self):
        scoped = json.loads(_cli(self.tmp, "wikilinks", "a", "--json").stdout)["data"]
        whole = json.loads(_cli(self.tmp, "wikilinks", "--json").stdout)["data"]
        self.assertEqual(sorted(scoped["by_bundle"]), ["a"])
        self.assertGreater(len(whole["links"]), len(scoped["links"]))

    def test_missing_target_exits_one(self):
        out = _cli(self.tmp, "wikilinks", "nosuchbundle")
        self.assertEqual(out.returncode, EXIT_CODES["not_found"])
        self.assertIn("nosuchbundle", out.stderr)

    def test_by_bundle_never_contradicts_the_link_list(self):
        """Under --unresolved the two must still agree; a by_bundle computed
        over the unfiltered set would report counts the caller cannot see."""
        data = json.loads(_cli(self.tmp, "wikilinks", "--unresolved", "--json").stdout)["data"]
        self.assertTrue(data["filtered"])
        self.assertEqual(sum(sum(c.values()) for c in data["by_bundle"].values()),
                         len(data["links"]))
        self.assertEqual(data["totals"],
                         {"resolved": 2, "ambiguous": 0, "unresolved": 2})

    def test_embed_is_visible_in_the_report(self):
        """`raw` drops the `!`, so without a marker an embed and a plain link
        print identically."""
        self._w("a/e.md", "---\ntype: Concept\n---\n![[y]]\n")
        out = _cli(self.tmp, "wikilinks", "a")
        self.assertIn("(embed)", out.stdout)

    def test_target_must_name_a_bundle(self):
        """`..` walked out of the catalogue and `_plan` scanned a staging
        directory the reporting surface is defined to exclude."""
        self._w("_plan/note.md", "---\ntype: Concept\n---\nSee [[ghost]].\n")
        self._w("a/_plan/note.md", "---\ntype: Concept\n---\nSee [[ghost]].\n")
        self._w("a/assets/note.md", "---\ntype: Concept\n---\nSee [[ghost]].\n")
        # iter_all_md prunes these names from `dirnames`, never from the
        # directory it is handed, so a target naming one scans it regardless.
        for bad, kind in (("..", "invalid_input"), (".", "invalid_input"),
                          ("./", "invalid_input"), ("_plan", "invalid_input"),
                          ("a/_plan", "invalid_input"), ("a/assets", "invalid_input"),
                          ("a/nosuchsubdir", "not_found"), ("nosuchbundle", "not_found")):
            out = _cli(self.tmp, "wikilinks", bad)
            self.assertEqual(out.returncode, EXIT_CODES[kind], bad)
            self.assertRegex(out.stderr, r"not a (directory|scannable bundle path)", bad)
            self.assertIn(bad, out.stderr, bad)


class BundleKeyDoesNotNarrowResolution(unittest.TestCase):
    """Acceptance guard (OKFT-n8xz, test 5) — the resolution call sites keep
    seeing the WIDE bundle set even when `.okf.toml` declares a narrower
    `bundle` key: a wikilink to a concept outside the declared bundle must
    stay resolvable. Narrowing the index/search corpus must not narrow
    resolution, or the exact defect
    okf-tools-okf/archive-lifecycle/active-beats-archived-in-wikilink-resolution
    describes for archiving recurs here for scaffolding."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "declared-bundle"))
        os.makedirs(os.path.join(self.tmp, "other-scaffolding"))
        with open(os.path.join(self.tmp, ".okf.toml"), "w", encoding="utf-8") as f:
            f.write('bundle = "declared-bundle"\n')
        with open(os.path.join(self.tmp, "declared-bundle", "source.md"),
                  "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: Source\n---\n"
                    "See [[outside]].\n")
        with open(os.path.join(self.tmp, "other-scaffolding", "outside.md"),
                  "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: Outside\n---\nbody\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_wikilink_to_a_concept_outside_the_declared_bundle_resolves(self):
        index = okf_wikilinks.build_concept_basename_index(self.tmp)
        status, candidates = okf_wikilinks.resolve_wikilink(
            index, "declared-bundle/source.md", "outside")
        self.assertEqual(status, "resolved")
        self.assertEqual(candidates, ["/other-scaffolding/outside.md"])


class WikilinkSourceOutsideDeclaredBundle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "declared-bundle"))
        os.makedirs(os.path.join(self.tmp, "topic-folder"))
        with open(os.path.join(self.tmp, ".okf.toml"), "w", encoding="utf-8") as f:
            f.write('bundle = "declared-bundle"\n')
        with open(os.path.join(self.tmp, "topic-folder", "source.md"),
                  "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: Source\n---\nSee [[target]].\n")
        with open(os.path.join(self.tmp, "declared-bundle", "target.md"),
                  "w", encoding="utf-8") as f:
            f.write("---\ntype: Concept\ntitle: Target\n---\nbody\n")

    def test_wikilink_from_outside_the_declared_bundle_resolves(self):
        index = okf_wikilinks.build_concept_basename_index(self.tmp)
        with open(os.path.join(self.tmp, "topic-folder", "source.md"),
                  encoding="utf-8") as f:
            records = okf_wikilinks.resolve_wikilink_records(
                index, okf_wikilinks.parse_wikilinks(f.read(), "topic-folder/source.md"))
        self.assertEqual(records[0]["status"], "resolved")
        self.assertEqual(records[0]["candidates"], ["/declared-bundle/target.md"])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
