#!/usr/bin/env python3
"""Tests for cli/okf/find_filters.py — the filters every search arm shares. Stdlib unittest, no deps.

Run: python3 -m unittest tests.test_okf_find_filters -v
"""
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "cli")
if _HERE not in sys.path:  # cli/ holds the okf package
    sys.path.insert(0, _HERE)

from okf import find_filters as okf_find_filters
from okf.catalogue import iter_concepts, resolve_scopes, split_frontmatter
from okf.errors import OkfError
from okf.find_filters import (
    EMB_FILTER_COLUMNS, FTS_FILTER_COLUMNS, And, Compare, Compare as C, In, Not, Or,
    compile_where, parse_where,
)
from okf.fts import build_fts_index


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


def concept(path, front=(), tags=None):
    """(path, frontmatter dict, text) of a concept whose frontmatter the production reader parses."""
    lines = ["---"] + ["{}: {}".format(k, v) for k, v in front]
    if tags is not None:
        lines.append("tags: [{}]".format(", ".join(tags)))
    text = "\n".join(lines + ["---", "# body", ""])
    return path, split_frontmatter(text)[0], text


# path -> concept; sets below name concepts by their path
CONCEPTS = dict((c[0], c) for c in [
    concept("b/one", [("type", "Runbook"), ("status", "draft"), ("n", "10"), ("date", "2026-10-11"),
                      ("title", '"Quoted Title"')], ["alpha", "Shared"]),
    concept("b/two", [("type", "Concept"), ("status", "stable"), ("n", "9"), ("date", "2026-09-30")],
            ["beta"]),
    concept("c/three", [("type", "Runbook")], ["alpha", "c++"]),
    concept("c/four"),
    concept("my_bundle/x", [("type", "Runbook")]),
    concept("myXbundle/y", [("type", "Runbook")]),
    concept("_archive/b/old", [("type", "Runbook")], ["alpha"]),
])
ACTIVE = {"b/one", "b/two", "c/three", "c/four", "my_bundle/x", "myXbundle/y"}


class CompileWhereSemantics(unittest.TestCase):
    """OKFT-vc94 — what each field and operator selects, evaluated by the one predicate
    (`matches_loaded`). Rows are (expression, selected concepts); every row pairs concepts
    that must be in with concepts that must be out."""

    ROWS = [
        # type: exact, case-sensitive, an absent key satisfies !=
        ("type = Runbook", {"b/one", "c/three", "my_bundle/x", "myXbundle/y"}),
        ("type = runbook", set()),
        ("type != Runbook", {"b/two", "c/four"}),
        ("type ~ unb", {"b/one", "c/three", "my_bundle/x", "myXbundle/y"}),
        ("type ~ UNB", set()),
        ("type in (Concept, Pattern)", {"b/two"}),
        # tag: whole tag, case-sensitive, list semantics
        ("tag = alpha", {"b/one", "c/three"}),
        ("tag = alph", set()),
        ("tag = shared", set()),
        ("tag = Shared", {"b/one"}),
        ("tag != alpha", {"b/two", "c/four", "my_bundle/x", "myXbundle/y"}),
        ("tag ~ lph", {"b/one", "c/three"}),
        ("tag ~ 'c+'", {"c/three"}),
        ("tag in (beta, 'c++')", {"b/two", "c/three"}),
        # path and archive visibility
        ("path ~ b/", {"b/one", "b/two"}),
        ("path ~ my_bundle/", {"my_bundle/x"}),
        ("path = c/four", {"c/four"}),
        ("path != c/four", ACTIVE - {"c/four"}),
        ("path ~ old", set()),
        ("archived = true", {"_archive/b/old"}),
        ("archived = false", ACTIVE),
        ("archived != true", ACTIVE),
        ("archived in (true, false)", ACTIVE | {"_archive/b/old"}),
        ("path ~ b/ and archived in (true, false)", {"b/one", "b/two", "_archive/b/old"}),
        ("type = Runbook and archived = true", {"_archive/b/old"}),
        ("not archived = true", ACTIVE),
        # ordering: numeric when both sides are numbers, string order otherwise
        ("n > 9", {"b/one"}),
        ("n >= 9", {"b/one", "b/two"}),
        ("n < 10", {"b/two"}),
        ("n <= 10", {"b/one", "b/two"}),
        ("n > abc", set()),
        ("date >= 2026-10-01", {"b/one"}),
        ("date < 2026-10-01", {"b/two"}),
        # any other key is a frontmatter key; absent never equals, always satisfies !=
        ("status = draft", {"b/one"}),
        ("status != draft", ACTIVE - {"b/one"}),
        ("not status = draft", ACTIVE - {"b/one"}),
        ("status = stable or status = draft", {"b/one", "b/two"}),
        ("title = 'Quoted Title'", {"b/one"}),
        ("generated.by = okf", set()),
        # composition
        ("type = Runbook and tag = alpha", {"b/one", "c/three"}),
        ("type = Concept or tag = beta", {"b/two"}),
        ("not (type = Runbook or tag = beta)", {"c/four"}),
        ("(type = Runbook and tag != alpha) or path = c/four", {"my_bundle/x", "myXbundle/y", "c/four"}),
    ]

    def test_rows(self):
        for expression, expected in self.ROWS:
            with self.subTest(expression):
                filters = compile_where(expression)
                selected = {p for p, fm, text in CONCEPTS.values() if filters.matches_loaded(p, fm, text)}
                self.assertEqual(selected, expected)

    def test_dotted_key_walks_nested_mappings(self):
        nested = {"generated": {"by": "okf", "model": {"name": "m1"}}, "type": "X"}
        for expression, expected in [("generated.by = okf", True), ("generated.by = nope", False),
                                     ("generated.model.name = m1", True), ("generated.by != okf", False),
                                     ("generated.missing != okf", True), ("generated = okf", False),
                                     ("generated.by.deeper = okf", False),
                                     ("generated ~ by", False)]:
            with self.subTest(expression):
                self.assertEqual(compile_where(expression).matches_loaded("b/n", nested, ""), expected)

    def test_a_list_valued_key_is_membership_any_and_any_contains(self):
        fm = {"aliases": ["ax", "by"]}
        for expression, expected in [("aliases = ax", True), ("aliases = a", False),
                                     ("aliases in (zz, by)", True), ("aliases in (zz)", False),
                                     ("aliases ~ y", True), ("aliases ~ q", False),
                                     ("aliases != ax", False), ("aliases != q", True)]:
            with self.subTest(expression):
                self.assertEqual(compile_where(expression).matches_loaded("b/n", fm, ""), expected)

    def test_misuse_is_invalid_input(self):
        for expression in ("archived = yes", "archived = True", "archived < true", "archived >= false",
                           "archived ~ tr", "archived in (true, maybe)", "tag < a", "tag <= a",
                           "tag > a", "tag >= a", "not tag > a", "type = x and archived = 1"):
            with self.subTest(expression):
                with self.assertRaises(OkfError) as caught:
                    compile_where(expression)
                self.assertEqual(caught.exception.kind, "invalid_input")

    def test_a_syntax_error_is_invalid_input(self):
        with self.assertRaises(OkfError) as caught:
            compile_where("type =")
        self.assertEqual(caught.exception.kind, "invalid_input")

    def test_archive_is_hidden_unless_the_expression_names_it(self):
        # (expression, include_archive, does the archived concept b/old match)
        for expression, include_archive, archived_matches in [
                (None, False, False), ("type = Runbook", False, False), ("path ~ old", False, False),
                ("archived = true", True, True), ("not archived = true", True, False),
                ("type = x or archived in (true, false)", True, True)]:
            with self.subTest(expression):
                filters = compile_where(expression)
                p, fm, text = CONCEPTS["_archive/b/old"]
                self.assertEqual(filters.include_archive, include_archive)
                self.assertEqual(filters.matches_loaded(p, fm, text), archived_matches)

    def test_bool_means_an_expression_restricts(self):
        self.assertFalse(compile_where(None))
        self.assertFalse(compile_where(None, corpus_bundles=("b",)))
        self.assertTrue(compile_where("type = x"))
        self.assertTrue(compile_where("archived = true"))

    def test_corpus_bundles_and_topics_keep_their_meaning(self):
        filters = compile_where("type = Runbook", include_topics=True, corpus_bundles=("b", "c"))
        self.assertTrue(filters.include_topics)
        for path, expected in [("b/one", True), ("c/three", True), ("my_bundle/x", False),
                               ("myXbundle/y", False), ("_archive/b/old", False)]:
            with self.subTest(path):
                _p, fm, text = CONCEPTS[path]
                self.assertEqual(filters.matches_loaded(path, fm, text), expected)
        archived = compile_where("archived = true", corpus_bundles=("b",))
        self.assertTrue(archived.matches_loaded("_archive/b/old", {}, ""))
        self.assertFalse(archived.matches_loaded("_archive/c/old", {}, ""))

    def test_matches_reads_the_file_only_for_a_non_path_field_and_only_once(self):
        with mock.patch.object(okf_find_filters, "read_file", wraps=okf_find_filters.read_file) as read:
            root = tempfile.mkdtemp()
            try:
                os.makedirs(os.path.join(root, "b"))
                with open(os.path.join(root, "b", "x.md"), "w", encoding="utf-8") as f:
                    f.write("---\ntype: Runbook\ntags: [alpha]\n---\n# x\n")
                self.assertTrue(compile_where("path ~ b/ and archived = false").matches(root, "b/x"))
                self.assertTrue(compile_where("path ~ b/ and archived = false").matches(root, "b/missing"))
                self.assertEqual(read.call_count, 0)
                self.assertTrue(compile_where("type = Runbook and tag = alpha").matches(root, "b/x"))
                self.assertEqual(read.call_count, 1)
                self.assertFalse(compile_where("type = Runbook").matches(root, "b/missing"))
                self.assertFalse(compile_where("path ~ x/ or path ~ y/ or type = Runbook").matches(root, "b/missing"))
            finally:
                shutil.rmtree(root, ignore_errors=True)


class SqlWherePushDown(unittest.TestCase):
    """OKFT-vc94 — `sql_where` pushes the indexed top-level conjuncts into SQL with every value
    bound and hands back exactly the rest as the residual filter value."""

    def split(self, expression, columns=FTS_FILTER_COLUMNS, **kw):
        return compile_where(expression, **kw).sql_where(columns)

    def test_indexed_conjuncts_leave_an_empty_residual(self):
        sql, params, residual = self.split("type = Runbook and tag = alpha")
        self.assertFalse(residual)
        self.assertEqual({"Runbook", "alpha"} - set(params), set())
        for value in ("Runbook", "alpha"):
            self.assertNotIn(value, sql)

    def test_an_unindexed_conjunct_stays_in_the_residual_and_only_it(self):
        sql, params, residual = self.split("status = draft")
        self.assertEqual(residual.tree, parse_where("status = draft"))
        self.assertNotIn("draft", params)
        _sql, params, residual = self.split("type = Runbook and status = draft and tag = alpha")
        self.assertEqual(residual.tree, parse_where("status = draft"))
        self.assertIn("Runbook", params)
        _sql, _params, residual = self.split("status = draft and n > 3 and type = Runbook")
        self.assertEqual(residual.tree, parse_where("status = draft and n > 3"))

    def test_a_conjunct_is_pushed_whole_or_not_at_all(self):
        _sql, params, residual = self.split("type = A or tag = b")
        self.assertFalse(residual)
        self.assertEqual({"A", "b"} - set(params), set())
        _sql, params, residual = self.split("type = A or status = b")
        self.assertEqual(residual.tree, parse_where("type = A or status = b"))
        self.assertNotIn("A", params)
        _sql, _params, residual = self.split("not (type = A or status = b) and tag = x")
        self.assertEqual(residual.tree, parse_where("not (type = A or status = b)"))

    def test_values_the_index_cannot_compare_exactly_stay_in_the_residual(self):
        # the tags column is a space-joined list and an empty value is not an absent one
        for expression in ("tag = 'a b'", "tag ~ 'a b'", "tag = ''", "type = ''", "type ~ ''",
                           "path in (x, '')", "type < Runbook", "tag in (a, 'b c')"):
            with self.subTest(expression):
                sql, params, residual = self.split(expression)
                self.assertEqual(residual.tree, parse_where(expression))
                self.assertNotIn("instr", sql)

    def test_a_field_the_column_map_lacks_stays_in_the_residual(self):
        _sql, params, residual = self.split("path ~ b/ and type = Runbook", EMB_FILTER_COLUMNS)
        self.assertEqual(residual.tree, parse_where("type = Runbook"))
        self.assertIn("b/", params)

    def test_archived_is_decided_by_the_residual_and_the_default_by_sql(self):
        sql, params, residual = self.split("archived = true")
        self.assertEqual(residual.tree, parse_where("archived = true"))
        self.assertTrue(residual.include_archive)
        self.assertEqual(sql, "")
        sql, params, residual = self.split("type = Runbook")
        self.assertIn("_archive", " ".join(str(p) for p in params))
        self.assertFalse(residual.include_archive)

    def test_the_residual_keeps_topics_and_the_corpus(self):
        _sql, _params, residual = self.split("status = draft", include_topics=True,
                                             corpus_bundles=("b",))
        self.assertTrue(residual.include_topics)
        self.assertEqual(residual.corpus_bundles, ("b",))
        self.assertFalse(residual.matches_loaded("c/x", {"status": "draft"}, ""))

    def test_a_value_is_bound_never_formatted_into_the_sql(self):
        hostile = "x');DROP/**/TABLE/**/docs;--"  # no whitespace: pushed for tag too
        for expression in ("type = \"{}\"".format(hostile), "tag in (\"{}\")".format(hostile),
                           "path ~ \"{}\"".format(hostile)):
            with self.subTest(expression):
                sql, params, residual = self.split(expression)
                self.assertNotIn("DROP", sql)
                self.assertIn(hostile, params)
                conn = sqlite3.connect(":memory:")
                conn.execute("CREATE TABLE docs(path TEXT, ctype TEXT, tags TEXT)")
                conn.execute("INSERT INTO docs VALUES ('b/x', 'T', 'a b')")
                self.assertEqual(conn.execute("SELECT path FROM docs WHERE 1=1" + sql, params).fetchall(), [])
                self.assertEqual(conn.execute("SELECT count(*) FROM docs").fetchone(), (1,))

    def test_corpus_bundles_are_pushed_with_their_archived_form_and_literal_metacharacters(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE docs(path TEXT, ctype TEXT, tags TEXT)")
        conn.executemany("INSERT INTO docs VALUES (?, '', '')",
                         [("b_c/x",), ("bXc/x",), ("_archive/b_c/y",), ("_archive/bXc/y",), ("b_c",)])
        sql, params, _residual = self.split("archived in (true, false)", corpus_bundles=("b_c",))
        rows = conn.execute("SELECT path FROM docs WHERE 1=1" + sql, params).fetchall()
        self.assertEqual(sorted(p for (p,) in rows), ["_archive/b_c/y", "b_c", "b_c/x"])


class PushDownEquivalence(unittest.TestCase):
    """OKFT-vc94 — the B01/I01 guard: SQL fragment plus residual selects exactly what the Python
    predicate alone selects, for both column maps, on files the real index builder reads."""

    FILES = [
        ("b/one.md", "type: Runbook\nstatus: draft\nn: 10", ["alpha", "shared"]),
        ("b/two.md", 'type: "Runbook"', ["Alpha"]),
        ("b/three.md", "type: Concept", ["c++", "a.b", "x-y"]),
        ("b/four.md", "title: no type, no tags", None),
        ("my_bundle/x.md", "type: run_book", ["100%"]),
        ("myXbundle/y.md", "type: runXbook", ["x_y"]),
        ("pct%bundle/z.md", "type: Runbook", ["alpha"]),
        ("xarchive/z.md", "type: Runbook", ["alpha"]),  # `_` is a LIKE wildcard: not an archive
        ("_archive/b/old.md", "type: Runbook", ["alpha"]),
        ("_archive/my_bundle/old.md", "type: run_book", ["100%"]),
    ]
    EXPRESSIONS = [
        "type = Runbook", "type != Runbook", "type = runbook", "type ~ unb", "type ~ n_b", "type ~ 'n%b'",
        "type in (Runbook, Concept)", "type in (run_book, 'run%book')", "type = run_book",
        "tag = alpha", "tag = Alpha", "tag != alpha", "tag ~ lph", "tag ~ 'c+'", "tag in (alpha, 'c++')",
        "tag = a.b", "tag ~ '100%'", "tag = '100%'", "tag = x_y", "tag ~ x_", "tag ~ 'x%y'", "tag = 'a b'",
        "tag ~ 'a b'", "tag in (a, 'b c')",
        "path ~ b/", "path ~ my_b", "path ~ 'my%b'", "path ~ 'pct%b'", "path ~ _archive/", "path = b/one",
        "path != b/one", "path in (b/one, c/zz)", "path ~ /one",
        "type = Runbook and tag = alpha", "type = Runbook or tag = alpha", "not type = Runbook",
        "not (type = Runbook or tag = alpha)", "(type = Runbook and tag != alpha) or path ~ my_b",
        "type = Runbook and status = draft", "status = draft or type = Runbook", "tag = alpha and n > 3",
        "n >= 10 and type = Runbook", "not status = draft", "title = 'no type, no tags'",
        "archived = true", "archived = false", "archived in (true, false)",
        "path ~ b/ and archived in (true, false)", "type = Runbook and archived = true",
        "tag = alpha and archived != false", "type = run_book and archived in (true, false)",
        "path ~ my_b and archived = true", "type > Concept", "type <= Runbook", "path <= c/four",
        "type = ''", "type != ''", "type ~ ''", "tag ~ ''", "path ~ ''", "type ~ UNB",
        "tag = alph", "tag = x", "tag in (alph, bet)", "path ~ xarchive/", "path ~ _archive/b/",
    ]

    def setUp(self):
        self.root = tempfile.mkdtemp()
        for rel, front, tags in self.FILES:
            ap = os.path.join(self.root, rel)
            os.makedirs(os.path.dirname(ap), exist_ok=True)
            with open(ap, "w", encoding="utf-8") as f:
                f.write("---\n{}\n{}---\n# t\n\nbody\n".format(
                    front, "" if tags is None else "tags: [{}]\n".format(", ".join(tags))))
        build_fts_index(self.root)
        self.universe = sorted(
            os.path.relpath(ap, self.root)[:-3]
            for _b, bp in resolve_scopes(self.root, None, include_archive=True)
            for _cid, ap in iter_concepts(bp))
        self.conn = sqlite3.connect(os.path.join(self.root, ".fts", "fts.sqlite"))
        self.conn.execute("CREATE TEMP TABLE concept_emb(path TEXT)")
        self.conn.executemany("INSERT INTO concept_emb VALUES (?)", [(p,) for p in self.universe])

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def through_sql(self, filters, table, columns):
        sql, params, residual = filters.sql_where(columns)
        rows = self.conn.execute("SELECT path FROM {} WHERE 1=1{}".format(table, sql), params).fetchall()
        return {p for (p,) in rows if not residual or residual.matches(self.root, p)}

    def test_every_expression_selects_the_same_set_through_sql_and_in_python(self):
        selected_somewhere = set()
        for expression in self.EXPRESSIONS:
            filters = compile_where(expression)
            expected = {p for p in self.universe if filters.matches(self.root, p)}
            selected_somewhere |= expected
            for table, columns in (("docs", FTS_FILTER_COLUMNS), ("concept_emb", EMB_FILTER_COLUMNS)):
                with self.subTest(expression=expression, table=table):
                    self.assertEqual(self.through_sql(filters, table, columns), expected)
        self.assertEqual(selected_somewhere, set(self.universe))
