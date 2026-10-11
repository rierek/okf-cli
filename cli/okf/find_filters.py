"""The --where filter language: the parser into a syntax tree, the compiler into one value,
FindFilters, shared by every search arm, and the column maps naming which fields each search
table filters natively."""

import functools
import operator
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import NamedTuple

from okf import spec
from okf.catalogue import read_file, read_frontmatter, scalar_text, tags_of
from okf.errors import OkfError


# --- the --where expression: syntax tree and parser (D34) ---------------------------------


@dataclass(frozen=True, slots=True)
class And:
    left: "Node"
    right: "Node"


@dataclass(frozen=True, slots=True)
class Or:
    left: "Node"
    right: "Node"


@dataclass(frozen=True, slots=True)
class Not:
    operand: "Node"


@dataclass(frozen=True, slots=True)
class Compare:
    field: str
    op: str
    value: str


@dataclass(frozen=True, slots=True)
class In:
    field: str
    values: tuple[str, ...]


Node = And | Or | Not | Compare | In

_KEYWORDS = frozenset(("and", "or", "not", "in"))  # lower case only; a value of that name needs quotes
_OPERATORS = frozenset(("=", "!=", "<", "<=", ">", ">=", "~"))
_OPERATOR_CHARS = "!<>=~"  # never part of a bare word, so `x!=y` and `path~a/b` need no spaces
_WORD_CHARS = "-_./:"  # besides letters and digits: paths, dates and timestamps need no quotes
_FIELD_RE = re.compile(r"[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+)*$")  # frontmatter keys, dotted for nested


def _fail(problem, position):
    raise OkfError("invalid_input", "--where: {} at position {}".format(problem, position + 1))


class _Token(NamedTuple):
    kind: str  # word, str, op, (, ), comma or end
    text: str  # a str token without its quotes
    pos: int  # 0-based offset of the token start
    src: str  # the token as written


def _tokenize(text):
    tokens, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c in "(),":
            tokens.append(_Token(c, c, i, c))
            i += 1
        elif c in "'\"":
            j = text.find(c, i + 1)  # no escapes: a value holding both quote kinds is not expressible
            if j < 0:
                _fail("unterminated quote {}".format(c), i)
            tokens.append(_Token("str", text[i + 1:j], i, text[i:j + 1]))
            i = j + 1
        elif c in _OPERATOR_CHARS:
            j = i
            while j < n and text[j] in _OPERATOR_CHARS:
                j += 1
            if text[i:j] not in _OPERATORS:
                _fail("unknown operator '{}'".format(text[i:j]), i)
            tokens.append(_Token("op", text[i:j], i, text[i:j]))
            i = j
        elif c.isalnum() or c in _WORD_CHARS:
            j = i
            while j < n and (text[j].isalnum() or text[j] in _WORD_CHARS):
                j += 1
            tokens.append(_Token("word", text[i:j], i, text[i:j]))
            i = j
        else:
            _fail("unexpected character '{}'".format(c), i)
    tokens.append(_Token("end", "", n, ""))
    return tokens


def _expected(what, token):
    found = ("end of expression" if token.kind == "end" else
             "string " + token.src if token.kind == "str" else "'{}'".format(token.src))
    _fail("expected {}, found {}".format(what, found), token.pos)


def _is_keyword(token, word):
    return token.kind == "word" and token.text == word


def _is_value(token):
    return token.kind == "str" or (token.kind == "word" and token.text not in _KEYWORDS)


def _parse_or(tokens, i):
    node, i = _parse_and(tokens, i)
    while _is_keyword(tokens[i], "or"):
        right, i = _parse_and(tokens, i + 1)
        node = Or(node, right)
    return node, i


def _parse_and(tokens, i):
    node, i = _parse_not(tokens, i)
    while _is_keyword(tokens[i], "and"):
        right, i = _parse_not(tokens, i + 1)
        node = And(node, right)
    return node, i


def _parse_not(tokens, i):
    if _is_keyword(tokens[i], "not"):
        operand, i = _parse_not(tokens, i + 1)
        return Not(operand), i
    return _parse_atom(tokens, i)


def _parse_atom(tokens, i):
    token = tokens[i]
    if token.kind == "(":
        node, i = _parse_or(tokens, i + 1)
        if tokens[i].kind != ")":
            _expected("')'", tokens[i])
        return node, i + 1
    if token.kind != "word" or token.text in _KEYWORDS or not _FIELD_RE.match(token.text):
        _expected("a field name or '('", token)
    field, after = token.text, tokens[i + 1]
    if _is_keyword(after, "in"):
        return _parse_in(field, tokens, i + 2)
    if after.kind != "op":
        _expected("an operator or 'in'", after)
    if not _is_value(tokens[i + 2]):
        _expected("a value", tokens[i + 2])
    return Compare(field, after.text, tokens[i + 2].text), i + 3


def _parse_in(field, tokens, i):
    if tokens[i].kind != "(":
        _expected("'(' after 'in'", tokens[i])
    values, i = [], i + 1
    while True:
        if not _is_value(tokens[i]):
            _expected("a value", tokens[i])
        values.append(tokens[i].text)
        i += 1
        if tokens[i].kind == ")":
            return In(field, tuple(values)), i + 1
        if tokens[i].kind != ",":
            _expected("',' or ')'", tokens[i])
        i += 1


def parse_where(text):
    """The syntax tree of one `--where` expression (D34), or OkfError("invalid_input") naming
    the 1-based character position and the offending token. Pure: no file, index or network.

    expr  := and ('or' and)*      and   := not ('and' not)*      not := 'not' not | atom
    atom  := '(' expr ')' | field OP value | field 'in' '(' value (',' value)* ')'

    A field is a frontmatter key, dotted for nested keys. A value is a bare word (letters,
    digits and - _ . / :) or a quoted string. The parser knows no field names."""
    try:
        tokens = _tokenize(text)
        tree, i = _parse_or(tokens, 0)
        if tokens[i].kind != "end":
            _expected("'and', 'or' or end of expression", tokens[i])
    except RecursionError:
        raise OkfError("invalid_input", "--where: expression is nested too deeply") from None
    return tree


def _mentions(node, field):
    """True when the expression tree references `field`; None is the empty expression."""
    if node is None:
        return False
    if isinstance(node, (And, Or)):
        return _mentions(node.left, field) or _mentions(node.right, field)
    if isinstance(node, Not):
        return _mentions(node.operand, field)
    return node.field == field


# --- the predicate: field registry, evaluation, validation and SQL push-down ---------------

_NUMBER = re.compile(r"-?\d+(\.\d+)?$")  # ponytail: no exponent or leading +, such values order as strings
_ORDERING = frozenset(("<", "<=", ">", ">="))


def _ordered(op):
    def compare(value, wanted):
        if _NUMBER.match(value) and _NUMBER.match(wanted):
            value, wanted = float(value), float(wanted)
        return op(value, wanted)
    return compare


_COMPARE = {"=": operator.eq, "~": lambda value, wanted: wanted in value, "<": _ordered(operator.lt),
            "<=": _ordered(operator.le), ">": _ordered(operator.gt), ">=": _ordered(operator.ge)}

# The one field registry: field name -> resolver(path, load, now), the list of values the concept
# holds for the field. load() returns the frontmatter mapping (or None) and reads the file only
# when called; `now` is the one instant of the call. A name not listed here is a frontmatter key,
# dotted for nested mappings and through lists of mappings.
TIERS = ("unverified", "machine-confirmed", "human-reviewed")
FIELDS = {
    "path": lambda path, load, now: [path],
    "archived": lambda path, load, now: ["true" if path.startswith(FindFilters._ARCHIVE_PREFIX) else "false"],
    "tag": lambda path, load, now: tags_of(load()),
    "tier": lambda path, load, now: [spec.trust_tier(load())],
    "stale": lambda path, load, now: ["true" if spec.is_stale(load(), now) else "false"],
    "status": lambda path, load, now: [scalar_text(v) for v in _leaves("status", load)] or ["stable"],
}
# The timestamp-valued OKF v0.2 keys. They compare as instants, never as text.
INSTANT_FIELDS = frozenset((
    "generated.at", "verified.at", "stale_after", "usage_window.from", "usage_window.to",
    "sources.last_modified", "sources.usage_window.from", "sources.usage_window.to"))
_INSTANT_COMPARE = {"=": operator.eq, "<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge}


def _leaves(field, load):
    """What a dotted key reaches in the frontmatter: a mapping is entered by key, a list through
    each of its elements, so `verified.by` reads a bare mapping and a list alike. A list at the end
    of the path gives its items, a mapping there nothing."""
    def walk(value, parts):
        if isinstance(value, list):
            return [leaf for item in value for leaf in walk(item, parts)]
        if not parts:
            return [] if isinstance(value, Mapping) else [value]
        if isinstance(value, Mapping) and parts[0] in value:
            return walk(value[parts[0]], parts[1:])
        return []  # absent
    return walk(load(), field.split("."))


def _values(field, path, load, now):
    resolve = FIELDS.get(field)
    if resolve:
        return resolve(path, load, now)
    return [scalar_text(v) for v in _leaves(field, load)]


def _evaluate(node, path, load, now):
    if isinstance(node, And):
        return _evaluate(node.left, path, load, now) and _evaluate(node.right, path, load, now)
    if isinstance(node, Or):
        return _evaluate(node.left, path, load, now) or _evaluate(node.right, path, load, now)
    if isinstance(node, Not):
        return not _evaluate(node.operand, path, load, now)
    if node.field in INSTANT_FIELDS:  # values that are no instant hold nothing to compare
        values = [t for t in map(spec.parse_okf_datetime, _leaves(node.field, load)) if t is not None]
        wanted = [spec.parse_okf_datetime(v) for v in (node.values if isinstance(node, In) else (node.value,))]
        if isinstance(node, In):
            return any(v in wanted for v in values)
        if node.op == "!=":
            return not any(v == wanted[0] for v in values)
        return any(_INSTANT_COMPARE[node.op](v, wanted[0]) for v in values)
    values = _values(node.field, path, load, now)
    if isinstance(node, In):
        return any(v in node.values for v in values)
    if node.op == "!=":
        return not any(v == node.value for v in values)  # an absent key satisfies !=
    return any(_COMPARE[node.op](v, node.value) for v in values)


def _validate(node):
    """Semantic misuse of a field is invalid_input, like a syntax error."""
    if isinstance(node, (And, Or)):
        _validate(node.left)
        _validate(node.right)
    elif isinstance(node, Not):
        _validate(node.operand)
    else:
        op, values = ("in", node.values) if isinstance(node, In) else (node.op, (node.value,))
        if node.field == "archived" and (op in _ORDERING or op == "~"
                                         or any(v not in ("true", "false") for v in values)):
            raise OkfError("invalid_input", "--where: archived takes = != or in, with true or false")
        if node.field == "tag" and op in _ORDERING:
            raise OkfError("invalid_input", "--where: tag takes no ordering operator, got {}".format(op))
        if node.field in ("tier", "stale"):
            allowed = TIERS if node.field == "tier" else ("true", "false")
            if op in _ORDERING or op == "~" or any(v not in allowed for v in values):
                raise OkfError("invalid_input", "--where: {} takes = != or in, with {}".format(
                    node.field, " or ".join(allowed)))
        if node.field in INSTANT_FIELDS and (op == "~" or any(spec.parse_okf_datetime(v) is None for v in values)):
            raise OkfError("invalid_input", "--where: {} compares instants: = != < <= > >= or in, with an "
                           "ISO 8601 datetime and an explicit offset, e.g. 2026-09-23T00:00:00Z "
                           "(quote a value that holds +)".format(node.field))


def _conjuncts(node):
    return _conjuncts(node.left) + _conjuncts(node.right) if isinstance(node, And) else [node]


def _push(node, columns):
    """(sql, params) that select what the Python predicate selects for `node`, or None when part of
    it cannot be pushed exactly. Column names come from `columns` (code), every value is bound.
    The columns are NOT NULL, so SQL needs no three-valued logic: an absent key is ''. What cannot
    be told apart from '' stays in Python: empty values, ordering, and tag values holding
    whitespace (the tags column is a space-joined list). ponytail: a stored tag that itself holds
    whitespace is ambiguous in that column; `tag = x` then also selects "x y"."""
    if isinstance(node, (And, Or)):
        left, right = _push(node.left, columns), _push(node.right, columns)
        if left is None or right is None:
            return None
        return "({} {} {})".format(left[0], "AND" if isinstance(node, And) else "OR", right[0]), left[1] + right[1]
    if isinstance(node, Not):
        inner = _push(node.operand, columns)
        return None if inner is None else ("NOT " + inner[0], inner[1])
    op, values = ("=", list(node.values)) if isinstance(node, In) else (node.op, [node.value])
    column, tag = columns.get(node.field), node.field == "tag"
    if (column is None or op in _ORDERING or not all(values)
            or (tag and any(v.split() != [v] for v in values))):
        return None
    if op == "~":
        one = "instr({}, ?) > 0"
    elif tag:
        one = "instr(' ' || {} || ' ', ' ' || ? || ' ') > 0"
    else:
        one = "{} = ?"
    sql = "(" + " OR ".join([one.format(column)] * len(values)) + ")"
    return ("NOT " + sql if op == "!=" else sql), values


def _like_escape(value):
    """Escape a value for safe use inside a SQL LIKE pattern bound with `ESCAPE char(92)`: `\\`,
    `%` and `_` are the three characters LIKE gives special meaning to (backslash because it is
    about to become the escape character itself); every one of them is a literal, user-controlled
    byte that must survive verbatim, or a bundle name collides with a similarly-named foreign
    bundle (I01/B01, again, one level down: inside a single arm's own pattern rather than between
    arms). Backslash MUST be escaped first, or escaping `%`/`_` afterwards would double-escape the
    backslashes those two steps just introduced."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class FindFilters:
    """The `--where` expression as ONE value, with the predicate defined once. Build it with
    compile_where().

    I01, the architectural finding behind B01: the filters used to be implemented three times —
    SQL in the FTS arm, a Python scan in the substring arm, nothing at all in the semantic arm —
    and travelled as loose arguments through five signatures. Nothing made an arm apply them, so
    the semantic arm silently answered unfiltered and a scoped query returned concepts from other
    bundles entirely. The filters describe the ANSWER, not one arm of it: whichever arm ends up
    owning the ranking (fuse_conditional decides per query), the same predicate holds.

    Two rules sit beside the expression, not in it:
      archive   a path under `_archive/` is no match unless the expression names `archived`
                (R-08); the expression then decides alone and include_archive is true, so every
                traversal reaches the archive
      corpus    with corpus_bundles set, a path outside those bundles is no match; an archived
                path compares without its `_archive/` prefix (R-09)
    include_topics only tells the lexical arms which corpus to read.

    Arms consume the value one of two ways, and both hand back what they did NOT cover so that
    skipping a conjunct is visible instead of silent: sql_where() for arms that filter in the
    database, matches()/matches_loaded() for arms that walk the file tree."""

    __slots__ = ("tree", "include_archive", "include_topics", "corpus_bundles", "now")

    _ARCHIVE_PREFIX = "_archive/"
    # Escaped once here rather than re-derived at each LIKE call site (review B01 round 3,
    # okf-cli-pn72): the constant's own leading `_` is exactly as much a wildcard inside a bound
    # LIKE pattern as a user's value is.
    _ARCHIVE_PREFIX_ESC = _like_escape(_ARCHIVE_PREFIX)

    def __init__(self, tree=None, include_topics=False, corpus_bundles=(), now=None):
        self.tree = tree  # the syntax tree of --where, None without one
        self.include_archive = _mentions(tree, "archived")
        self.include_topics = bool(include_topics)
        self.corpus_bundles = tuple(corpus_bundles or ())
        self.now = now or spec.utcnow()  # the one instant of the call, for `stale` and the records

    def __bool__(self):
        # Whether an expression restricts the result. Not the archive default or the corpus
        # rule: path_visible() enforces those in matches()/matches_loaded() unconditionally.
        return self.tree is not None

    def __repr__(self):
        return "FindFilters(tree={!r}, include_archive={!r})".format(self.tree, self.include_archive)

    def sql_where(self, columns):
        """(sql_fragment, params, residual) for a table that natively carries the fields named in
        `columns` ({field: column_name}); the fragment starts with ` AND`.

        `residual` is a FindFilters holding exactly the top-level `and` conjuncts this SQL did NOT
        cover — the caller must run it through matches()/matches_loaded() or it drops them. That
        return value IS the contract: a table lacking a column no longer means the filter quietly
        disappears. It is falsy when everything was pushed.

        Column names come from caller literals, never from user input, so formatting them into the
        SQL is safe; every VALUE is bound."""
        sql, params, rest = "", [], []
        path = columns.get("path")
        if self.corpus_bundles and path:
            branches = []
            for b in self.corpus_bundles:
                archived = self._ARCHIVE_PREFIX + b
                branches += ["{} = ?".format(path), "{} LIKE ? ESCAPE char(92)".format(path)] * 2
                params += [b, _like_escape(b) + "/%", archived, _like_escape(archived) + "/%"]
            sql += " AND (" + " OR ".join(branches) + ")"
        for conjunct in (_conjuncts(self.tree) if self.tree is not None else ()):
            pushed = _push(conjunct, columns)
            if pushed is None:
                rest.append(conjunct)
            else:
                sql += " AND " + pushed[0]
                params.extend(pushed[1])
        if not self.include_archive and path:
            # R-08's default exclusion — only a table carrying `path` can tell an archived
            # concept from an active one. ESCAPE is not optional (R-10): `_` is a LIKE
            # single-char wildcard, so an unescaped pattern would also exclude a bundle
            # literally named "xarchive".
            sql += " AND {} NOT LIKE ? ESCAPE char(92)".format(path)
            params.append(self._ARCHIVE_PREFIX_ESC + "%")
        residual = FindFilters(functools.reduce(And, rest) if rest else None,
                               self.include_topics, self.corpus_bundles, self.now)
        return sql, params, residual

    def path_visible(self, path):
        """R-08/R-09 live here, next to the expression, because they are the same predicate: a
        path under `_archive/` is invisible unless the expression names `archived`, and with a
        corpus a path outside it is invisible. This is the one named, reusable spot: any caller
        that walks paths in Python (not SQL) gets both rules by calling this, not by re-deriving
        them."""
        archived = path.startswith(self._ARCHIVE_PREFIX)
        if archived and not self.include_archive:
            return False
        if self.corpus_bundles:
            compared = path[len(self._ARCHIVE_PREFIX):] if archived else path
            return any(compared == b or compared.startswith(b + "/") for b in self.corpus_bundles)
        return True

    def matches_loaded(self, path, fm):
        """Full predicate for a concept whose frontmatter the caller already read."""
        return self.path_visible(path) and (
            self.tree is None or _evaluate(self.tree, path, lambda: fm, self.now))

    def matches(self, root, path):
        """Same predicate, reading the concept file only when the expression needs a field beyond
        the path, and then once. Checks the path rules first so a filtered-out path costs no disk
        read. A path that no longer resolves fails — _hydrate_hit drops it anyway.

        No `if not self: return True` shortcut here (there used to be one): the archive default is
        itself a restriction, so even an empty FindFilters() must still run path_visible()."""
        if not self.path_visible(path):
            return False
        if self.tree is None:
            return True

        @functools.cache
        def load():
            return read_frontmatter(read_file(os.path.join(root, path + ".md"))).data  # raises when the file is gone

        try:
            return _evaluate(self.tree, path, load, self.now)
        except FileNotFoundError:
            return False


def compile_where(text, include_topics=False, corpus_bundles=()):
    """The filter value of one `--where` expression, or of none (`text` None: only the archive
    default and the corpus rule apply). Raises OkfError("invalid_input") for a syntax error and
    for semantic misuse of a field."""
    tree = None if text is None else parse_where(text)
    if tree is not None:
        _validate(tree)
    return FindFilters(tree, include_topics, corpus_bundles)


# Column maps naming which fields each table can filter natively. The FTS `docs` table carries all
# three; the embedding cache carries only the path, which is why semantic_ranking gets a non-empty
# residual to apply itself.
FTS_FILTER_COLUMNS = {"path": "path", "type": "ctype", "tag": "tags"}
EMB_FILTER_COLUMNS = {"path": "path"}
