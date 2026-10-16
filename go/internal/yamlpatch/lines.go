package yamlpatch

import (
	"strings"

	"go.yaml.in/yaml/v3"
)

// The line model: a block text is a list of lines that keep their line endings, and a node's Line
// and Column (1-based; the column counts characters) say where it starts. Edits replace or insert
// whole lines, or splice a span inside lines; nothing else of the text is touched.

// splitLines splits s after every "\n"; each line keeps its ending (CRLF stays CRLF).
func splitLines(s string) []string {
	if s == "" {
		return nil
	}
	parts := strings.SplitAfter(s, "\n")
	if parts[len(parts)-1] == "" {
		parts = parts[:len(parts)-1]
	}
	return parts
}

// indentOf counts the leading spaces of a line.
func indentOf(line string) int { return len(line) - len(strings.TrimLeft(line, " ")) }

func isBlank(line string) bool { return strings.Trim(line, " \t\r\n") == "" }

func isComment(line string) bool { return strings.HasPrefix(strings.TrimLeft(line, " \t"), "#") }

// byteCol turns yaml.v3's 1-based column (counted in characters) into a byte offset of the line.
func byteCol(line string, col int) int {
	n := 0
	for i := range line {
		if n == col-1 {
			return i
		}
		n++
	}
	return len(line)
}

// pos is a place in the lines: a line index and a byte offset in it.
type pos struct{ l, c int }

// span is the text from `from` up to, not including, `to`.
type span struct{ from, to pos }

// scanQuoted returns the position just behind the closing quote of the quoted scalar that opens at
// (l, c).
func (p *patcher) scanQuoted(l, c int, single bool) (el, ec int, ok bool) {
	for ln := l; ln < len(p.lines); ln++ {
		line := p.lines[ln]
		j := 0
		if ln == l {
			j = c + 1
		}
		for ; j < len(line); j++ {
			switch ch := line[j]; {
			case single && ch == '\'':
				if j+1 < len(line) && line[j+1] == '\'' {
					j++
					continue
				}
				return ln, j + 1, true
			case !single && ch == '\\':
				j++
			case !single && ch == '"':
				return ln, j + 1, true
			}
		}
	}
	return 0, 0, false
}

// plainEnd returns the position behind the last character of the plain scalar that starts at (l, c).
// Continuation lines of a multi-line scalar run until a comment line, a line indented less than
// minIndent, or limit (the line of the next sibling).
func (p *patcher) plainEnd(l, c, limit, minIndent int) (el, ec int) {
	cut := func(line string, from int) (int, bool) {
		rest := line[from:]
		for i := range len(rest) {
			if rest[i] == '#' && (i == 0 || rest[i-1] == ' ' || rest[i-1] == '\t') {
				return from + len(strings.TrimRight(rest[:i], " \t\r\n")), true
			}
		}
		return from + len(strings.TrimRight(rest, " \t\r\n")), false
	}
	el = l
	ec, comment := cut(p.lines[l], c)
	for i := l + 1; !comment && i < limit; i++ {
		line := p.lines[i]
		if isBlank(line) {
			continue
		}
		if isComment(line) || indentOf(line) < minIndent {
			break
		}
		el = i
		ec, comment = cut(line, indentOf(line))
	}
	return el, ec
}

func isBlockScalar(n *yaml.Node) bool {
	return n.Kind == yaml.ScalarNode && n.Style&(yaml.LiteralStyle|yaml.FoldedStyle) != 0
}

func isQuoted(n *yaml.Node) bool {
	return n.Kind == yaml.ScalarNode && n.Style&(yaml.DoubleQuotedStyle|yaml.SingleQuotedStyle) != 0
}

// blockScalarEnd is the exclusive end of the lines of the block scalar whose header is on the line of
// leaf: the content lines, which are indented more than the header line, and the blank lines between
// them. Trailing blank lines are not counted.
func (p *patcher) blockScalarEnd(leaf *yaml.Node, hi int) int {
	hl := leaf.Line - 1
	minIndent, contentIndent := indentOf(p.lines[hl])+1, -1
	end := hl + 1
	for i := hl + 1; i < hi; i++ {
		line := p.lines[i]
		if isBlank(line) {
			continue
		}
		if contentIndent < 0 {
			if indentOf(line) < minIndent {
				break
			}
			contentIndent = indentOf(line)
		}
		if indentOf(line) < contentIndent {
			break
		}
		end = i + 1
	}
	return end
}

func lastLeaf(n *yaml.Node) *yaml.Node {
	for len(n.Content) > 0 {
		n = n.Content[len(n.Content)-1]
	}
	return n
}

// contentEnd is the exclusive end of the lines that node n, which starts on line lo, really owns inside
// [lo, hi): trailing blank and comment lines belong to what follows and drop out. A `#` line inside a
// block or quoted scalar is text, not a comment.
func (p *patcher) contentEnd(n *yaml.Node, lo, hi int) int {
	leaf := lastLeaf(n)
	if isBlockScalar(leaf) {
		return max(p.blockScalarEnd(leaf, hi), lo+1)
	}
	end := hi
	for end > lo+1 && (isBlank(p.lines[end-1]) || isComment(p.lines[end-1])) {
		end--
	}
	if isQuoted(leaf) {
		if el, _, ok := p.scanQuoted(leaf.Line-1, byteCol(p.lines[leaf.Line-1], leaf.Column), leaf.Style&yaml.SingleQuotedStyle != 0); ok && el+1 > end {
			end = el + 1
		}
	}
	return end
}

// flowList is where the items of a flow list sit, found by scanning the text: the parser gives the
// start of every item, not its end.
type flowList struct {
	open, close pos    // the brackets
	items       []span // one per item, without the whitespace around it
	lastEnd     pos    // behind the last non-space character in front of the closing bracket
	lastChar    byte   // that character
}

// scanFlow scans the flow list node v. A comment inside refuses the edit (R-04). The items found are
// checked against the parser's: the same count, the same starts.
func (p *patcher) scanFlow(v *yaml.Node) (*flowList, error) {
	l, c := v.Line-1, byteCol(p.lines[v.Line-1], v.Column)
	if p.lines[l][c] != '[' {
		return nil, reject("a flow list does not start with a bracket")
	}
	fl := &flowList{open: pos{l, c}, lastEnd: pos{l, c + 1}, lastChar: '['}
	depth, prev := 1, byte('[')
	var start *pos
	c++
	for ; l < len(p.lines); l, c = l+1, 0 {
		line := p.lines[l]
		for c < len(line) {
			ch := line[c]
			if ch == ' ' || ch == '\t' || ch == '\r' || ch == '\n' {
				c++
				continue
			}
			if ch == '#' && (c == 0 || line[c-1] == ' ' || line[c-1] == '\t') {
				return nil, reject("a comment sits inside a flow list")
			}
			if depth == 1 && start == nil && ch != ',' && ch != ']' {
				start = &pos{l, c}
			}
			switch {
			case (ch == '"' || ch == '\'') && strings.IndexByte("[{,:?", prev) >= 0:
				el, ec, ok := p.scanQuoted(l, c, ch == '\'')
				if !ok {
					return nil, reject("a quote in a flow list is not closed")
				}
				l, c = el, ec
				line = p.lines[l]
				fl.lastEnd, fl.lastChar, prev = pos{l, c}, ch, ch
				continue
			case ch == '[' || ch == '{':
				depth++
			case ch == ']' || ch == '}':
				depth--
				if depth == 0 {
					if start != nil {
						fl.items = append(fl.items, span{*start, fl.lastEnd})
					}
					fl.close = pos{l, c}
					if err := fl.verify(p, v); err != nil {
						return nil, err
					}
					return fl, nil
				}
			case ch == ',' && depth == 1:
				if start != nil {
					fl.items = append(fl.items, span{*start, fl.lastEnd})
					start = nil
				}
				c++
				fl.lastEnd, fl.lastChar, prev = pos{l, c}, ch, ch
				continue
			}
			c++
			fl.lastEnd, fl.lastChar, prev = pos{l, c}, ch, ch
		}
	}
	return nil, reject("the closing bracket of a flow list is not found")
}

// verify checks the scan against the parser.
func (fl *flowList) verify(p *patcher, v *yaml.Node) error {
	if len(fl.items) != len(v.Content) {
		return reject("a flow list scan finds %d items where the parser finds %d", len(fl.items), len(v.Content))
	}
	for i, it := range v.Content {
		if fl.items[i].from != (pos{it.Line - 1, byteCol(p.lines[it.Line-1], it.Column)}) {
			return reject("a flow list scan and the parser disagree on item %d", i)
		}
	}
	return nil
}
