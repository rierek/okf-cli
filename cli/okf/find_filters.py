"""The --scope/--type/--tag/--include-archive filters as one value, FindFilters,
shared by every search arm, and the column maps naming which dimensions each
search table filters natively."""

import os

from okf.catalogue import extract_tags, read_file, split_frontmatter


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

    __slots__ = ("scope", "type", "tag", "include_archive", "include_topics", "corpus_bundles")

    _ARCHIVE_PREFIX = "_archive/"
    # Escaped once here rather than re-derived at each of the two LIKE call
    # sites (review B01 round 3, okf-cli-pn72): the constant's own leading
    # `_` is exactly as much a wildcard inside a bound LIKE pattern as a
    # user's scope value is, and two independent `_like_escape(...)` call
    # sites is how the first fix already missed one of them.
    _ARCHIVE_PREFIX_ESC = _like_escape(_ARCHIVE_PREFIX)

    def __init__(self, scope=None, type=None, tag=None, include_archive=False, include_topics=False, corpus_bundles=None):
        # Normalize "" to None once, here: cmd_find reads these off argparse
        # and the MCP layer passes empty strings for "unset".
        self.scope = (scope or "").rstrip("/") or None
        self.type = type or None
        self.tag = tag or None
        self.include_archive = bool(include_archive)
        self.include_topics = bool(include_topics)
        self.corpus_bundles = tuple(corpus_bundles or ())

    def __bool__(self):
        # Deliberately NOT include_archive: this reports whether scope/type/
        # tag hold a restriction, which is what sql_where()'s residual
        # assertions and callers reason about. include_archive's own default
        # (False) is a restriction too, but path_in_scope() enforces it
        # unconditionally in matches()/matches_loaded() regardless of this
        # value, so nothing needs it folded in here.
        return bool(self.scope or self.type or self.tag)

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
        if self.corpus_bundles and "scope" in columns:
            col = columns["scope"]
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
        if self.scope and "scope" in columns:
            col = columns["scope"]
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
        if not self.include_archive and "scope" in columns:
            # R-08's default exclusion, on the same column scope uses — only
            # a table carrying `path` can tell an archived concept from an
            # active one. ESCAPE is not optional (R-10): `_` is a LIKE
            # single-char wildcard, so an unescaped pattern would also
            # exclude a bundle literally named "xarchive".
            sql += " AND {} NOT LIKE '{}%' ESCAPE '\\'".format(
                columns["scope"], self._ARCHIVE_PREFIX_ESC)
        residual = FindFilters(
            scope=None if "scope" in covered else self.scope,
            type=None if "type" in covered else self.type,
            tag=None if "tag" in covered else self.tag,
            include_archive=self.include_archive,
            include_topics=self.include_topics, corpus_bundles=self.corpus_bundles,
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
        return True

    def matches(self, root, path):
        """Same predicate, reading the concept file when needed. Checks scope
        first so a filtered-out path costs no disk read. A path that no longer
        resolves fails — _hydrate_hit drops it anyway.

        No `if not self: return True` shortcut here (there used to be one):
        include_archive's default is itself a restriction, so even an
        otherwise "empty" FindFilters() must still run path_in_scope()."""
        if not self.path_in_scope(path):
            return False
        if not (self.type or self.tag):
            return True
        ap = os.path.join(root, path + ".md")
        if not os.path.isfile(ap):
            return False
        text = read_file(ap)
        fm, _body = split_frontmatter(text)
        return self.matches_loaded(path, fm, text)


# Column maps naming which dimensions each table can filter natively. The FTS
# `docs` table carries all three; the embedding cache carries only the path,
# which is why semantic_ranking gets a non-empty residual to apply itself.
FTS_FILTER_COLUMNS = {"scope": "path", "type": "ctype", "tag": "tags"}
EMB_FILTER_COLUMNS = {"scope": "path"}
