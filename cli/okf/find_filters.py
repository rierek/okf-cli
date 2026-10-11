"""The --scope/--type/--tag/--include-archive filters as one value, FindFilters,
shared by every search arm, and the column maps naming which dimensions each
search table filters natively."""

import functools
import operator
import os
import re
from dataclasses import dataclass
from typing import NamedTuple

from okf.catalogue import _dequote, extract_tags, read_file, split_frontmatter
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

# The one field registry: field name -> resolver(path, load), the list of values the concept holds
# for the field. load() returns (frontmatter dict, text) and reads the file only when called. A
# name not listed here is a frontmatter key, dotted for nested mappings. tier, stale and the v0.2
# keys register here later.
FIELDS = {
    "path": lambda path, load: [path],
    "archived": lambda path, load: ["true" if path.startswith(FindFilters._ARCHIVE_PREFIX) else "false"],
    "tag": lambda path, load: extract_tags(load()[1]),
}


def _values(field, path, load):
    resolve = FIELDS.get(field)
    if resolve:
        return resolve(path, load)
    value = load()[0]
    for part in field.split("."):
        if not isinstance(value, dict) or part not in value:
            return []  # absent
        value = value[part]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [] if isinstance(value, dict) else [_dequote(str(value))]


def _evaluate(node, path, load):
    if isinstance(node, And):
        return _evaluate(node.left, path, load) and _evaluate(node.right, path, load)
    if isinstance(node, Or):
        return _evaluate(node.left, path, load) or _evaluate(node.right, path, load)
    if isinstance(node, Not):
        return not _evaluate(node.operand, path, load)
    values = _values(node.field, path, load)
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
    """Escape a value for safe use inside a SQL LIKE pattern bound with
    `ESCAPE '\\'`. `\\`, `%` and `_` are the three characters LIKE gives
    special meaning to (backslash because it is about to become the escape
    character itself); every one of them is a literal, user-controlled byte
    that must survive verbatim, or a scope value collides with a
    similarly-named foreign bundle (I01/B01, again, one level down: inside a
    single arm's own pattern rather than between arms). Backslash MUST be
    escaped first, or escaping `%`/`_` afterwards would double-escape the
    backslashes those two steps just introduced."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class FindFilters:
    """--scope/--type/--tag/--include-archive as ONE value, with the
    predicate defined once.

    I01, the architectural finding behind B01: the same three filters used to
    be implemented three times — SQL in the FTS arm, a Python scan in the
    substring arm, nothing at all in the semantic arm — and travelled as three
    loose positional arguments through five signatures. Nothing made an arm
    apply them, so the semantic arm silently answered unfiltered and a scoped
    query returned concepts from other bundles entirely. R-08 adds a fourth
    dimension deliberately INTO this object rather than beside it, on pain of
    repeating exactly that finding.

    The filters describe the ANSWER, not one arm of it. Whichever arm ends up
    owning the ranking (fuse_conditional decides per query), the same
    predicate holds:

      scope            path is the scope itself or lives beneath it
      type             exact equality on the concept's frontmatter `type`
      tag              WHOLE-tag membership — "tail" must never hit "tailscale"
      include_archive  a path under `_archive/` is no match unless set (R-08);
                        while it IS set, scope compares against the path with
                        its leading `_archive/` segment stripped, so a scoped
                        query reaches the archived concepts of that same
                        bundle and no other (R-09)

    Arms consume it one of two ways, and both hand back what they did NOT
    cover so that skipping a dimension is visible instead of silent:
    sql_where() for arms that filter in the database, matches()/matches_loaded()
    for arms that walk the file tree."""

    __slots__ = ("scope", "type", "tag", "tree", "include_archive", "include_topics", "corpus_bundles")

    _ARCHIVE_PREFIX = "_archive/"
    # Escaped once here rather than re-derived at each of the two LIKE call
    # sites (review B01 round 3, okf-cli-pn72): the constant's own leading
    # `_` is exactly as much a wildcard inside a bound LIKE pattern as a
    # user's scope value is, and two independent `_like_escape(...)` call
    # sites is how the first fix already missed one of them.
    _ARCHIVE_PREFIX_ESC = _like_escape(_ARCHIVE_PREFIX)

    def __init__(self, scope=None, type=None, tag=None, include_archive=False, include_topics=False,
                 corpus_bundles=None, tree=None):
        # Normalize "" to None once, here: cmd_find reads these off argparse
        # and the MCP layer passes empty strings for "unset".
        self.scope = (scope or "").rstrip("/") or None
        self.type = type or None
        self.tag = tag or None
        self.tree = tree  # the --where expression, None without one
        self.include_archive = bool(include_archive) or _mentions(tree, "archived")
        self.include_topics = bool(include_topics)
        self.corpus_bundles = tuple(corpus_bundles or ())

    def __bool__(self):
        # Deliberately NOT include_archive: this reports whether scope/type/
        # tag hold a restriction, which is what sql_where()'s residual
        # assertions and callers reason about. include_archive's own default
        # (False) is a restriction too, but path_in_scope() enforces it
        # unconditionally in matches()/matches_loaded() regardless of this
        # value, so nothing needs it folded in here.
        return bool(self.scope or self.type or self.tag or self.tree is not None)

    def __repr__(self):
        return "FindFilters(scope={!r}, type={!r}, tag={!r}, include_archive={!r})".format(
            self.scope, self.type, self.tag, self.include_archive)

    def sql_where(self, columns):
        """(sql_fragment, params, residual) for a table that natively carries
        the dimensions named in `columns` ({dimension: column_name}).

        `residual` is a FindFilters holding exactly the dimensions this SQL did
        NOT cover — the caller must run it through matches()/matches_loaded()
        or it drops them. That return value IS the contract: a table lacking a
        column no longer means the filter quietly disappears.

        Column names come from caller literals, never from user input, so
        formatting them into the SQL is safe; every VALUE is still bound."""
        sql, params = "", []
        covered = set()
        if self.corpus_bundles and "path" in columns:
            col = columns["path"]
            branches = []
            for b in self.corpus_bundles:
                esc_bundle = _like_escape(b)
                archived = self._ARCHIVE_PREFIX + b
                branches.extend([
                    "{} = ?".format(col),
                    "{} LIKE ? ESCAPE char(92)".format(col),
                    "{} = ?".format(col),
                    "{} LIKE ? ESCAPE char(92)".format(col),
                ])
                params.extend([
                    b, esc_bundle + "/%",
                    archived, _like_escape(archived) + "/%",
                ])
            sql += " AND (" + " OR ".join(branches) + ")"
            covered.add("corpus")
        if self.scope and "path" in columns:
            col = columns["path"]
            # R-09: an archived concept of this scope lives at
            # `_archive/<scope>[/...]`, not `<scope>[/...]` — match both
            # forms here; visibility of the archived form is decided below,
            # by the include_archive predicate, not by this OR-chain.
            #
            # Every LIKE branch binds an ESCAPED copy of the scope value
            # (review B01, okf-cli-pn72): scope is user-controlled, and an
            # unescaped `_`/`%` in it is a LIKE wildcard, not a literal — a
            # scope of "my_bundle" would otherwise also match a foreign
            # bundle "myXbundle". The `=` branches stay on the raw value;
            # exact equality never interprets wildcards.
            esc_scope = _like_escape(self.scope)
            sql += (" AND ({0} = ? OR {0} LIKE ? ESCAPE '\\'"
                    " OR {0} = ? OR {0} LIKE ? ESCAPE '\\')".format(col))
            params.extend([
                self.scope, esc_scope + "/%",
                self._ARCHIVE_PREFIX + self.scope,
                self._ARCHIVE_PREFIX_ESC + esc_scope + "/%",
            ])
            covered.add("scope")
        if self.type and "type" in columns:
            sql += " AND {} = ?".format(columns["type"])
            params.append(self.type)
            covered.add("type")
        if self.tag and "tag" in columns:
            # whole-tag match: the column is a space-joined slug list, so pad
            # both sides rather than substring-matching.
            sql += " AND instr(' ' || {} || ' ', ' ' || ? || ' ') > 0".format(
                columns["tag"])
            params.append(self.tag)
            covered.add("tag")
        rest = []
        for conjunct in (_conjuncts(self.tree) if self.tree is not None else ()):
            pushed = _push(conjunct, columns)
            if pushed is None:
                rest.append(conjunct)
            else:
                sql += " AND " + pushed[0]
                params.extend(pushed[1])
        if not self.include_archive and "path" in columns:
            # R-08's default exclusion, on the path column — only a table carrying `path`
            # can tell an archived concept from an active one. ESCAPE is not optional
            # (R-10): `_` is a LIKE single-char wildcard, so an unescaped pattern would
            # also exclude a bundle literally named "xarchive".
            sql += " AND {} NOT LIKE ? ESCAPE char(92)".format(columns["path"])
            params.append(self._ARCHIVE_PREFIX_ESC + "%")
        residual = FindFilters(
            scope=None if "scope" in covered else self.scope,
            type=None if "type" in covered else self.type,
            tag=None if "tag" in covered else self.tag,
            include_archive=self.include_archive,
            include_topics=self.include_topics, corpus_bundles=self.corpus_bundles,
            tree=functools.reduce(And, rest) if rest else None,
        )
        return sql, params, residual

    def path_in_scope(self, path):
        """R-08/R-09 live here, next to scope, because they are the same
        predicate: a path under `_archive/` is invisible unless
        include_archive is set, and once it IS set, scope is compared
        against the path with that leading segment stripped — so
        `--scope <bundle> --include-archive` reaches the archived concepts
        of exactly that bundle, never another's. This is the one named,
        reusable spot: any future caller that walks paths in Python (not
        SQL) gets both rules by calling this, not by re-deriving them."""
        archived = path.startswith(self._ARCHIVE_PREFIX)
        compared = path[len(self._ARCHIVE_PREFIX):] if archived else path
        if (self.corpus_bundles
                and not any(compared == b or compared.startswith(b + "/")
                            for b in self.corpus_bundles)):
            return False
        if archived and not self.include_archive:
            return False
        if not self.scope:
            return True
        return compared == self.scope or compared.startswith(self.scope + "/")

    def matches_loaded(self, path, fm, text):
        """Full predicate for a concept whose file the caller already read.
        Covers all three dimensions — an arm that has the text in hand has no
        reason to check only some of them."""
        if not self.path_in_scope(path):
            return False
        if self.type and fm.get("type", "") != self.type:
            return False
        if self.tag and self.tag not in extract_tags(text):
            return False
        return self.tree is None or _evaluate(self.tree, path, lambda: (fm, text))

    def matches(self, root, path):
        """Same predicate, reading the concept file when needed. Checks scope
        first so a filtered-out path costs no disk read. A path that no longer
        resolves fails — _hydrate_hit drops it anyway.

        No `if not self: return True` shortcut here (there used to be one):
        include_archive's default is itself a restriction, so even an
        otherwise "empty" FindFilters() must still run path_in_scope()."""
        if not self.path_in_scope(path):
            return False
        if self.tree is not None:
            return self._tree_matches(root, path)
        if not (self.type or self.tag):
            return True
        ap = os.path.join(root, path + ".md")
        if not os.path.isfile(ap):
            return False
        text = read_file(ap)
        fm, _body = split_frontmatter(text)
        return self.matches_loaded(path, fm, text)

    def _tree_matches(self, root, path):
        loaded = []

        def load():
            if not loaded:
                ap = os.path.join(root, path + ".md")
                if not os.path.isfile(ap):
                    raise FileNotFoundError(ap)
                text = read_file(ap)
                loaded.append((split_frontmatter(text)[0], text))
            return loaded[0]

        try:
            return _evaluate(self.tree, path, load)
        except FileNotFoundError:
            return False  # a path that no longer resolves fails: _hydrate_hit drops it anyway


def compile_where(text, include_topics=False, corpus_bundles=()):
    """The filter value of one `--where` expression, or of none (`text` None: only the default
    archive exclusion and the corpus rule apply). Raises OkfError("invalid_input") for a syntax
    error and for semantic misuse of a field."""
    tree = None if text is None else parse_where(text)
    if tree is not None:
        _validate(tree)
    return FindFilters(include_topics=include_topics, corpus_bundles=corpus_bundles, tree=tree)


# Column maps naming which dimensions each table can filter natively. The FTS
# `docs` table carries all three; the embedding cache carries only the path,
# which is why semantic_ranking gets a non-empty residual to apply itself.
FTS_FILTER_COLUMNS = {"path": "path", "type": "ctype", "tag": "tags"}
EMB_FILTER_COLUMNS = {"path": "path"}
