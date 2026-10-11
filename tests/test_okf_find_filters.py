#!/usr/bin/env python3
"""Tests for cli/okf/find_filters.py — the filters every search arm shares. Stdlib unittest, no deps.

Run: python3 -m unittest tests.test_okf_find_filters -v
"""
import os
import sys
import unittest
from unittest import mock

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli")
if _HERE not in sys.path:  # cli/ holds the okf package
    sys.path.insert(0, _HERE)

from okf import find_filters as okf_find_filters
from okf.errors import OkfError
from okf.find_filters import And, Compare, In, Not, Or, parse_where


class PathInScopeArchiveRule(unittest.TestCase):
    """path_in_scope() directly — the one named, reusable primitive R-08/R-09
    live in (okf-cli-pn72). The FTS arm (FindIncludeArchive in test_okf_find.py) proves it
    end to end against a real build_fts_index() over real `_archive/...`
    fixture files (R-11, okf-cli-fu7o) — this class proves the primitive
    itself is correct standalone, independent of any one caller's traversal
    shape, so a future caller that starts feeding it archived paths
    inherits correct behaviour immediately, not a silently-dead branch."""

    def test_archived_path_excluded_by_default(self):
        f = okf_find_filters.FindFilters()
        self.assertFalse(f.path_in_scope("_archive/bundle-a/hidden"))
        self.assertTrue(f.path_in_scope("bundle-a/active"))

    def test_archived_path_included_when_flagged(self):
        f = okf_find_filters.FindFilters(include_archive=True)
        self.assertTrue(f.path_in_scope("_archive/bundle-a/hidden"))

    def test_scope_compares_against_archive_stripped_path(self):
        f = okf_find_filters.FindFilters(scope="bundle-a", include_archive=True)
        self.assertTrue(f.path_in_scope("_archive/bundle-a/hidden"))
        self.assertFalse(f.path_in_scope("_archive/bundle-b/other-hidden"))


def C(field, op, value):
    return Compare(field, op, value)


class ParseWhereGrammar(unittest.TestCase):
    """OKFT-lm0a — one grammar (D34): and/or/not, parentheses, the seven comparisons and the
    `in` set, parsed into one immutable tree."""

    def test_each_comparison_operator(self):
        for op in ("=", "!=", "<", "<=", ">", ">=", "~"):
            with self.subTest(op=op):
                self.assertEqual(parse_where("n {} 3".format(op)), C("n", op, "3"))

    def test_operators_need_no_spaces(self):
        for text, expected in [("type=runbook", C("type", "=", "runbook")),
                               ("path~a/b", C("path", "~", "a/b")),
                               ("x!=y", C("x", "!=", "y")),
                               ("n>=2", C("n", ">=", "2")),
                               ("n<-5", C("n", "<", "-5"))]:
            with self.subTest(text=text):
                self.assertEqual(parse_where(text), expected)

    def test_in_set_keeps_written_order_and_strips_quotes(self):
        self.assertEqual(parse_where("status in (draft, stable)"),
                         In("status", ("draft", "stable")))
        self.assertEqual(parse_where("status in (b,a, 'c d')"),
                         In("status", ("b", "a", "c d")))
        self.assertEqual(parse_where("status in (only)"), In("status", ("only",)))

    def test_dotted_field_passes_through_as_written(self):
        self.assertEqual(parse_where("generated.by = okf-cli"), C("generated.by", "=", "okf-cli"))
        self.assertEqual(parse_where("a.b.c in (x)"), In("a.b.c", ("x",)))

    def test_bare_values_carry_path_date_and_timestamp_characters(self):
        for value in ("home-lab-wiki/", "2026-10-11", "2026-10-11T10:00:00", "a_b.c", "Übersicht"):
            with self.subTest(value=value):
                self.assertEqual(parse_where("k = " + value), C("k", "=", value))

    def test_quoted_values_lose_their_quotes_and_may_hold_anything_but_the_quote(self):
        for text, value in [("k = 'a b'", "a b"), ('k = "x and y"', "x and y"),
                            ("k = ''", ""), ("k = \"it's\"", "it's"), ("k = 'a,b)'", "a,b)")]:
            with self.subTest(text=text):
                self.assertEqual(parse_where(text), C("k", "=", value))

    def test_keywords_are_lower_case_only_and_a_quoted_keyword_is_a_value(self):
        self.assertEqual(parse_where("k = AND"), C("k", "=", "AND"))
        self.assertEqual(parse_where("k = 'and'"), C("k", "=", "and"))
        self.assertEqual(parse_where("k in ('or', not2)"), In("k", ("or", "not2")))
        with self.assertRaises(OkfError):
            parse_where("a = 1 AND b = 2")

    def test_precedence_or_below_and(self):
        self.assertEqual(parse_where("a = 1 or b = 2 and c = 3"),
                         parse_where("a = 1 or (b = 2 and c = 3)"))
        self.assertNotEqual(parse_where("a = 1 or b = 2 and c = 3"),
                            parse_where("(a = 1 or b = 2) and c = 3"))

    def test_not_binds_tighter_than_and_and_or(self):
        expected = And(Not(C("a", "=", "1")), C("b", "=", "2"))
        self.assertEqual(parse_where("not a = 1 and b = 2"), expected)
        self.assertEqual(parse_where("(not a = 1) and b = 2"), expected)
        self.assertEqual(parse_where("not a = 1 or b = 2"),
                         Or(Not(C("a", "=", "1")), C("b", "=", "2")))
        self.assertEqual(parse_where("not not a = 1"), Not(Not(C("a", "=", "1"))))
        self.assertEqual(parse_where("not a in (x)"), Not(In("a", ("x",))))

    def test_parentheses_group_before_precedence(self):
        self.assertEqual(
            parse_where("(a = 1 or b = 2) and c = 3"),
            And(Or(C("a", "=", "1"), C("b", "=", "2")), C("c", "=", "3")))
        self.assertEqual(parse_where("not (a = 1 and b = 2)"),
                         Not(And(C("a", "=", "1"), C("b", "=", "2"))))

    def test_and_and_or_associate_left(self):
        self.assertEqual(parse_where("a = 1 and b = 2 and c = 3"),
                         And(And(C("a", "=", "1"), C("b", "=", "2")), C("c", "=", "3")))
        self.assertEqual(parse_where("a = 1 or b = 2 or c = 3"),
                         Or(Or(C("a", "=", "1"), C("b", "=", "2")), C("c", "=", "3")))

    def test_d34_example(self):
        tree = parse_where("(type = runbook and tag != tailscale) and status in (draft, stable)")
        self.assertEqual(tree, And(And(C("type", "=", "runbook"), C("tag", "!=", "tailscale")),
                                   In("status", ("draft", "stable"))))

    def test_whitespace_of_any_kind_separates(self):
        self.assertEqual(parse_where("\n a\t=  1 \n and\nb = 2 "),
                         And(C("a", "=", "1"), C("b", "=", "2")))

    def test_node_types_are_immutable_and_distinct(self):
        node = C("a", "=", "1")
        with self.assertRaises(Exception):
            node.value = "2"
        self.assertNotEqual(And(node, node), Or(node, node))
        self.assertNotEqual(Not(node), node)

    def test_parsing_reads_no_file(self):
        with mock.patch("builtins.open", side_effect=AssertionError("parser opened a file")):
            parse_where("(type = x and tag != y) or path ~ 'a b/'")


class ParseWhereErrors(unittest.TestCase):
    """OKFT-lm0a criteria 7 and 8 — every malformed class is invalid_input, never a tree and
    never an internal error, and the message names the 1-based character position and the
    offending token."""

    # (expression, 1-based position, offending token as the message shows it)
    CASES = [
        ("empty", "", 1, "end of expression"),
        ("blank", "   ", 4, "end of expression"),
        ("unbalanced open", "(a = 1", 7, "end of expression"),
        ("unbalanced close", "a = 1)", 6, "')'"),
        ("unbalanced nested", "((a = 1)", 9, "end of expression"),
        ("empty parentheses", "()", 2, "')'"),
        ("operand missing after and", "a = 1 and", 10, "end of expression"),
        ("operand missing before and", "and a = 1", 1, "'and'"),
        ("operand missing after not", "not", 4, "end of expression"),
        ("doubled or", "a = 1 or or b = 2", 10, "'or'"),
        ("value missing at end", "a =", 4, "end of expression"),
        ("value is a bare keyword", "a = and", 5, "'and'"),
        ("value missing before paren", "(a =)", 5, "')'"),
        ("operator missing", "a", 2, "end of expression"),
        ("empty in list", "a in ()", 7, "')'"),
        ("in list unclosed", "a in (x", 8, "end of expression"),
        ("in without list", "a in x", 6, "'x'"),
        ("in list trailing comma", "a in (x,)", 9, "')'"),
        ("in list without comma", "a in (x y)", 9, "'y'"),
        ("unknown operator ==", "a == 1", 3, "'=='"),
        ("unknown operator <>", "a <> 1", 3, "'<>'"),
        ("unknown operator =>", "a => 1", 3, "'=>'"),
        ("lone bang", "a ! 1", 3, "'!'"),
        ("comma outside in", "a = 1, b = 2", 6, "','"),
        ("comma inside parentheses", "(a = 1, b = 2)", 7, "','"),
        ("unterminated single quote", "a = 'x", 5, "quote '"),
        ("unterminated double quote", 'a = "x', 5, 'quote "'),
        ("unterminated quote in list", "a in ('x, y)", 7, "quote '"),
        ("trailing token", "a = 1 b = 2", 7, "'b'"),
        ("trailing value", "a = b c", 7, "'c'"),
        ("quoted keyword is no operator", "a = 1 'and' b = 2", 7, "string 'and'"),
        ("keyword as field", "not = 1", 5, "'='"),
        ("quoted field", "'a' = 1", 1, "string 'a'"),
        ("field with slash", "a/b = 1", 1, "'a/b'"),
        ("field with leading dot", ".a = 1", 1, "'.a'"),
        ("field with trailing dot", "a. = 1", 1, "'a.'"),
        ("stray character", "a = 1 & b = 2", 7, "'&'"),
    ]

    def test_every_malformed_class_is_invalid_input_with_position_and_token(self):
        for name, text, position, token in self.CASES:
            with self.subTest(name):
                with self.assertRaises(OkfError) as caught:
                    parse_where(text)
                self.assertEqual(caught.exception.kind, "invalid_input")
                self.assertIn("at position {}".format(position), caught.exception.message)
                self.assertIn(token, caught.exception.message)

    def test_deeply_nested_input_is_invalid_input_not_a_crash(self):
        with self.assertRaises(OkfError) as caught:
            parse_where("(" * 5000 + "a = 1" + ")" * 5000)
        self.assertEqual(caught.exception.kind, "invalid_input")
