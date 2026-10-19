package where

import (
	"slices"
	"strings"

	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// Column maps naming which fields each table can filter natively. The FTS `docs` table carries all
// three; the embedding cache carries only the path, which is why a semantic ranking gets a
// non-empty residual to apply itself.
var (
	// FTSFilterColumns maps the fields of the FTS `docs` table to its columns.
	FTSFilterColumns = map[string]string{"path": "path", "type": "ctype", "tag": "tags"}
	// EMBFilterColumns maps the fields of the embedding cache to its columns.
	EMBFilterColumns = map[string]string{"path": "path"}
)

// conjuncts are the operands of the top-level `and` chain of a tree.
func conjuncts(n node) []node {
	if a, ok := n.(andNode); ok {
		return append(conjuncts(a.left), conjuncts(a.right)...)
	}
	return []node{n}
}

// push is the (sql, params) that select what the predicate selects for n, or ok false when part of
// it cannot be pushed exactly. Column names come from columns (code), every value is bound. The
// columns are NOT NULL, so SQL needs no three-valued logic: an absent key is the empty string.
// What cannot be told apart from the empty string stays in Go: empty values, ordering, and tag
// values holding whitespace (the tags column is a space-joined list). A stored tag that itself
// holds whitespace is ambiguous in that column; `tag = x` then also selects "x y".
func push(n node, columns map[string]string) (string, []string, bool) {
	switch n := n.(type) {
	case andNode:
		return pushPair(n.left, n.right, "AND", columns)
	case orNode:
		return pushPair(n.left, n.right, "OR", columns)
	case notNode:
		inner, params, ok := push(n.operand, columns)
		if !ok {
			return "", nil, false
		}
		return "NOT " + inner, params, true
	case compareNode:
		return pushLeaf(n.field, n.op, []string{n.value}, columns)
	case inNode:
		return pushLeaf(n.field, "=", n.values, columns)
	}
	panic("where: unknown expression node")
}

func pushPair(left, right node, joiner string, columns map[string]string) (string, []string, bool) {
	l, leftParams, leftOK := push(left, columns)
	r, rightParams, rightOK := push(right, columns)
	if !leftOK || !rightOK {
		return "", nil, false
	}
	return "(" + l + " " + joiner + " " + r + ")", slices.Concat(leftParams, rightParams), true
}

func pushLeaf(field, op string, values []string, columns map[string]string) (string, []string, bool) {
	column, found := columns[field]
	tag := field == "tag"
	if !found || op == "<" || op == "<=" || op == ">" || op == ">=" || slices.Contains(values, "") ||
		(tag && slices.ContainsFunc(values, hasSpace)) {
		return "", nil, false
	}
	one := column + " = ?"
	switch {
	case op == "~":
		one = "instr(" + column + ", ?) > 0"
	case tag:
		one = "instr(' ' || " + column + " || ' ', ' ' || ? || ' ') > 0"
	}
	terms := make([]string, len(values))
	for i := range terms {
		terms[i] = one
	}
	sql := "(" + strings.Join(terms, " OR ") + ")"
	if op == "!=" {
		sql = "NOT " + sql
	}
	return sql, slices.Clone(values), true
}

// hasSpace reports whether v holds a character Python's str.split() splits at.
func hasSpace(v string) bool { return strings.IndexFunc(v, pytext.IsSpace) >= 0 }

var likeEscaper = strings.NewReplacer(`\`, `\\`, `%`, `\%`, `_`, `\_`)

// likeEscape escapes a value for use inside a SQL LIKE pattern bound with `ESCAPE char(92)`: `\`,
// `%` and `_` are the three characters LIKE gives special meaning to (the backslash because it is
// about to become the escape character itself). Each is a literal byte that must survive verbatim,
// or a bundle name collides with a similarly-named foreign bundle.
func likeEscape(value string) string { return likeEscaper.Replace(value) }

// SQLWhere is Python sql_where: (sql, params, residual) for a table that natively carries the
// fields named in columns ({field: column name}); the fragment starts with ` AND` and is empty when
// nothing applies. Every param is text, bound in order; params is nil when none is bound.
//
// residual is a FindFilters holding exactly the top-level `and` conjuncts this SQL did NOT cover:
// the caller must run it through Matches or MatchesLoaded or it drops them. Its HasExpression is
// false when everything was pushed. Column names come from caller literals, never from user
// input, so formatting them into the SQL is safe; every value is bound.
func (f *FindFilters) SQLWhere(columns map[string]string) (sql string, params []string, residual *FindFilters) {
	path := columns["path"]
	if len(f.corpusBundles) > 0 && path != "" {
		branches := make([]string, 0, 4*len(f.corpusBundles))
		for _, b := range f.corpusBundles {
			archived := archivePrefix + b
			branches = append(branches, path+" = ?", path+" LIKE ? ESCAPE char(92)", path+" = ?", path+" LIKE ? ESCAPE char(92)")
			params = append(params, b, likeEscape(b)+"/%", archived, likeEscape(archived)+"/%")
		}
		sql += " AND (" + strings.Join(branches, " OR ") + ")"
	}
	var rest node
	if f.tree != nil {
		for _, conjunct := range conjuncts(f.tree) {
			pushed, pushedParams, ok := push(conjunct, columns)
			switch {
			case !ok && rest == nil:
				rest = conjunct
			case !ok:
				rest = andNode{rest, conjunct}
			default:
				sql += " AND " + pushed
				params = append(params, pushedParams...)
			}
		}
	}
	if !f.includeArchive && path != "" {
		// The default exclusion of the archive: only a table carrying `path` can tell an archived
		// concept from an active one. ESCAPE is not optional: `_` is a LIKE single-character
		// wildcard, so an unescaped pattern would also exclude a bundle named "xarchive".
		sql += " AND " + path + " NOT LIKE ? ESCAPE char(92)"
		params = append(params, likeEscape(archivePrefix)+"%")
	}
	return sql, params, newFindFilters(rest, f.includeTopics, f.corpusBundles, f.now)
}
