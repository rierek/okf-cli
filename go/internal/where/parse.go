// Package where is the --where filter language (Python okf.find_filters): the parser into a syntax
// tree, the validator, the predicate, the SQL push-down and FindFilters, the one value every
// search arm and every tag verb filters with.
package where

import (
	"strings"
	"unicode"

	"nas/volume1/data/git/okf-tools/go/internal/okferr"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// Syntax tree of one expression. The parser knows no field names.
type node any

type (
	andNode     struct{ left, right node }
	orNode      struct{ left, right node }
	notNode     struct{ operand node }
	compareNode struct{ field, op, value string }
	inNode      struct {
		field  string
		values []string
	}
)

const (
	operatorChars = "!<>=~" // never part of a bare word, so `x!=y` and `path~a/b` need no spaces
	wordChars     = "-_./:" // besides letters and digits: paths, dates and timestamps need no quotes
)

// frameLimit is Python's recursion limit made visible: the Python parser raised RecursionError
// once its call stack held this many frames, and that was the "nested too deeply" error. The Go
// parser counts the frames the Python parser held (one per parse function, one more for the
// helper it calls) so the same expressions are refused. The value is measured: `okf list --where`
// takes 247 nested parentheses or 989 `not` in a row, and refuses one more.
const frameLimit = 995

type tokenKind string

const (
	tokWord   tokenKind = "word"
	tokStr    tokenKind = "str"
	tokOp     tokenKind = "op"
	tokLParen tokenKind = "("
	tokRParen tokenKind = ")"
	tokComma  tokenKind = ","
	tokEnd    tokenKind = "end"
)

type token struct {
	kind tokenKind
	text string // a str token without its quotes
	pos  int    // 0-based offset of the token start, in characters (Python code points)
	src  string // the token as written
}

func fail(problem string, position int) error {
	return okferr.Newf(okferr.InvalidInput, "--where: %s at position %d", problem, position+1)
}

func errTooDeep() error {
	return okferr.New(okferr.InvalidInput, "--where: expression is nested too deeply")
}

// isAlnum is str.isalnum for one character: a letter or a character with a numeric value.
func isAlnum(r rune) bool { return unicode.IsLetter(r) || unicode.IsNumber(r) }

func tokenize(text string) ([]token, error) {
	rs := []rune(text)
	n := len(rs)
	var tokens []token
	for i := 0; i < n; {
		c := rs[i]
		switch {
		case pytext.IsSpace(c):
			i++
		case c == '(' || c == ')' || c == ',':
			tokens = append(tokens, token{tokenKind(string(c)), string(c), i, string(c)})
			i++
		case c == '\'' || c == '"':
			j := i + 1 // no escapes: a value holding both quote kinds is not expressible
			for j < n && rs[j] != c {
				j++
			}
			if j >= n {
				return nil, fail("unterminated quote "+string(c), i)
			}
			tokens = append(tokens, token{tokStr, string(rs[i+1 : j]), i, string(rs[i : j+1])})
			i = j + 1
		case strings.ContainsRune(operatorChars, c):
			j := i
			for j < n && strings.ContainsRune(operatorChars, rs[j]) {
				j++
			}
			op := string(rs[i:j])
			if !isOperator(op) {
				return nil, fail("unknown operator '"+op+"'", i)
			}
			tokens = append(tokens, token{tokOp, op, i, op})
			i = j
		case isAlnum(c) || strings.ContainsRune(wordChars, c):
			j := i
			for j < n && (isAlnum(rs[j]) || strings.ContainsRune(wordChars, rs[j])) {
				j++
			}
			tokens = append(tokens, token{tokWord, string(rs[i:j]), i, string(rs[i:j])})
			i = j
		default:
			return nil, fail("unexpected character '"+string(c)+"'", i)
		}
	}
	return append(tokens, token{tokEnd, "", n, ""}), nil
}

func isOperator(s string) bool {
	switch s {
	case "=", "!=", "<", "<=", ">", ">=", "~":
		return true
	}
	return false
}

// isReserved is the keyword test: lower case only; a value of that name needs quotes.
func isReserved(s string) bool {
	switch s {
	case "and", "or", "not", "in":
		return true
	}
	return false
}

// isFieldChar is a character of a key part: `[A-Za-z0-9_-]`.
func isFieldChar(r rune) bool {
	return r >= 'a' && r <= 'z' || r >= 'A' && r <= 'Z' || r >= '0' && r <= '9' || r == '_' || r == '-'
}

// isFieldName is `[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+)*`: frontmatter keys, dotted for nested ones.
func isFieldName(s string) bool {
	for _, part := range strings.Split(s, ".") {
		if part == "" || strings.IndexFunc(part, func(r rune) bool { return !isFieldChar(r) }) >= 0 {
			return false
		}
	}
	return true
}

// expected is the syntax error "expected <what>, found <token>". depth is the frame depth of the
// parse function that raises it; the Python helpers it called held three more frames.
func expected(what string, t token, depth int) error {
	if depth+3 >= frameLimit {
		return errTooDeep()
	}
	found := "'" + t.src + "'"
	switch t.kind {
	case tokEnd:
		found = "end of expression"
	case tokStr:
		found = "string " + t.src
	}
	return fail("expected "+what+", found "+found, t.pos)
}

type parser struct{ tokens []token }

func (p *parser) isKeyword(i int, word string) bool {
	t := p.tokens[i]
	return t.kind == tokWord && t.text == word
}

func (p *parser) isValue(i int) bool {
	t := p.tokens[i]
	return t.kind == tokStr || (t.kind == tokWord && !isReserved(t.text))
}

// Each parse function takes the index of the next token and its own frame depth, and returns the
// node and the index after it.

func (p *parser) or(i, depth int) (node, int, error) {
	if depth+1 >= frameLimit {
		return nil, 0, errTooDeep()
	}
	n, i, err := p.and(i, depth+1)
	for err == nil && p.isKeyword(i, "or") {
		var right node
		right, i, err = p.and(i+1, depth+1)
		n = orNode{n, right}
	}
	return n, i, err
}

func (p *parser) and(i, depth int) (node, int, error) {
	if depth+1 >= frameLimit {
		return nil, 0, errTooDeep()
	}
	n, i, err := p.not(i, depth+1)
	for err == nil && p.isKeyword(i, "and") {
		var right node
		right, i, err = p.not(i+1, depth+1)
		n = andNode{n, right}
	}
	return n, i, err
}

func (p *parser) not(i, depth int) (node, int, error) {
	if depth+1 >= frameLimit {
		return nil, 0, errTooDeep()
	}
	if p.isKeyword(i, "not") {
		operand, i, err := p.not(i+1, depth+1)
		return notNode{operand}, i, err
	}
	return p.atom(i, depth+1)
}

func (p *parser) atom(i, depth int) (node, int, error) {
	if depth+1 >= frameLimit {
		return nil, 0, errTooDeep()
	}
	t := p.tokens[i]
	if t.kind == tokLParen {
		n, i, err := p.or(i+1, depth+1)
		if err != nil {
			return nil, 0, err
		}
		if p.tokens[i].kind != tokRParen {
			return nil, 0, expected("')'", p.tokens[i], depth)
		}
		return n, i + 1, nil
	}
	if t.kind != tokWord || isReserved(t.text) || !isFieldName(t.text) {
		return nil, 0, expected("a field name or '('", t, depth)
	}
	after := p.tokens[i+1]
	if p.isKeyword(i+1, "in") {
		return p.in(t.text, i+2, depth+1)
	}
	if after.kind != tokOp {
		return nil, 0, expected("an operator or 'in'", after, depth)
	}
	if !p.isValue(i + 2) {
		return nil, 0, expected("a value", p.tokens[i+2], depth)
	}
	return compareNode{t.text, after.text, p.tokens[i+2].text}, i + 3, nil
}

func (p *parser) in(field string, i, depth int) (node, int, error) {
	if depth+1 >= frameLimit {
		return nil, 0, errTooDeep()
	}
	if p.tokens[i].kind != tokLParen {
		return nil, 0, expected("'(' after 'in'", p.tokens[i], depth)
	}
	var values []string
	i++
	for {
		if !p.isValue(i) {
			return nil, 0, expected("a value", p.tokens[i], depth)
		}
		values = append(values, p.tokens[i].text)
		i++
		if p.tokens[i].kind == tokRParen {
			return inNode{field, values}, i + 1, nil
		}
		if p.tokens[i].kind != tokComma {
			return nil, 0, expected("',' or ')'", p.tokens[i], depth)
		}
		i++
	}
}

// parseWhere is Python parse_where: the syntax tree of one expression, or invalid_input naming
// the 1-based character position and the offending token. Pure: no file, index or network.
//
//	expr  := and ('or' and)*      and   := not ('and' not)*      not := 'not' not | atom
//	atom  := '(' expr ')' | field OP value | field 'in' '(' value (',' value)* ')'
//
// A field is a frontmatter key, dotted for nested keys. A value is a bare word (letters, digits
// and - _ . / :) or a quoted string.
func parseWhere(text string) (node, error) {
	tokens, err := tokenize(text)
	if err != nil {
		return nil, err
	}
	p := parser{tokens}
	tree, i, err := p.or(0, 1)
	if err != nil {
		return nil, err
	}
	if tokens[i].kind != tokEnd {
		return nil, expected("'and', 'or' or end of expression", tokens[i], 0)
	}
	return tree, nil
}
