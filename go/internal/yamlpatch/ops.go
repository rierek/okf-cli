package yamlpatch

import (
	"regexp"
	"slices"
	"strings"
	"unicode/utf8"

	"go.yaml.in/yaml/v3"
)

// dashRe is the lead of a block list item: indentation, dash, the spaces behind it.
var dashRe = regexp.MustCompile(`^( *)(-)( +)`)

func keyDatum(key string) *datum { return &datum{kind: yaml.ScalarNode, tag: "!!str", text: key} }

func seqDatum(items ...*datum) *datum {
	return &datum{kind: yaml.SequenceNode, tag: "!!seq", kids: items}
}

// ---- new keys and values

func (p *patcher) newKey(key string, v Value) error {
	if err := p.ensurePairs(); err != nil {
		return err
	}
	if p.find(key) != nil {
		return reject("the key %q is already in the frontmatter", key)
	}
	p.appendLines(p.withEOL(pairLines(len(p.indent), key, v)))
	p.want.kids = append(p.want.kids, keyDatum(key), datumOf(v))
	return nil
}

func (p *patcher) setValue(key string, v Value) error {
	if err := p.ensurePairs(); err != nil {
		return err
	}
	if p.find(key) == nil {
		return p.newKey(key, v)
	}
	pr, i, err := p.target(key)
	if err != nil {
		return err
	}
	switch v.(type) {
	case strValue, plainValue:
	default:
		return reject("a set-value edit of %q takes a string or a typed scalar", key)
	}
	n := pr.val
	if n.Kind != yaml.ScalarNode {
		return reject("the value of %q is a list or a mapping; a set-value edit takes a scalar", key)
	}
	if isBlockScalar(n) {
		err = p.setBlockScalar(pr, v)
	} else {
		err = p.setScalar(n, v, ctxValue, pr.next, indentOf(p.lines[pr.line])+1)
	}
	if err != nil {
		return err
	}
	p.want.kids[i+1] = datumOf(v)
	return nil
}

// restyle is the text of a new scalar written in the style of the old one: plain stays plain when the
// new text reads back as the same string, single quotes stay single when they can carry it, double
// quotes stay double; whatever the old style cannot carry follows the quoting rule.
func restyle(old *yaml.Node, v Value, ctx scalarCtx) string {
	x, ok := v.(strValue)
	if !ok {
		return v.(plainValue).s
	}
	switch {
	case old.Style&yaml.DoubleQuotedStyle != 0:
		return dquote(x.s)
	case old.Style&yaml.SingleQuotedStyle != 0:
		if singleOK(x.s) {
			return "'" + strings.ReplaceAll(x.s, "'", "''") + "'"
		}
		return dquote(x.s)
	}
	return quoteScalar(x.s, ctx)
}

// setScalar replaces the plain or quoted scalar n in place; the text before it, behind it and the
// trailing comment of its line stay. limit is the line of the next sibling, minIndent the least indentation of
// a continuation line of a multi-line plain scalar.
func (p *patcher) setScalar(n *yaml.Node, v Value, ctx scalarCtx, limit, minIndent int) error {
	l0 := n.Line - 1
	c0 := byteCol(p.lines[l0], n.Column)
	text := restyle(n, v, ctx)
	el, ec := l0, c0
	switch {
	case isQuoted(n):
		var ok bool
		if el, ec, ok = p.scanQuoted(l0, c0, n.Style&yaml.SingleQuotedStyle != 0); !ok {
			return reject("the end of a quoted scalar is not found")
		}
	case n.Style == 0 && n.Value == "" && n.ShortTag() == "!!null":
		text = " " + text // an empty value: the node sits right behind the colon
	default:
		el, ec = p.plainEnd(l0, c0, limit, minIndent)
	}
	p.splice(l0, c0, el, ec, text)
	return nil
}

// blockOK reports whether a literal or folded scalar `|-` can carry s as one content line.
func blockOK(s string) bool {
	return s != "" && singleOK(s) && s[0] != ' ' && s[0] != '\t'
}

// setBlockScalar replaces the literal or folded scalar of pr: the new text becomes the one content
// line of `|-` (or `>-`) when that style can carry it, else the key line carries it in the quoting rule's
// style. The header's trailing comment stays.
func (p *patcher) setBlockScalar(pr *pair, v Value) error {
	n := pr.val
	l0 := n.Line - 1
	c0 := byteCol(p.lines[l0], n.Column)
	header := p.lines[l0][c0:]
	rest := strings.TrimLeft(header[1:], "-+0123456789") // behind the indicators: spaces, comment, ending
	end := p.blockScalarEnd(n, pr.next)
	head := p.lines[l0][:c0]
	if x, ok := v.(strValue); ok && blockOK(x.s) {
		ci := indentOf(p.lines[l0]) + 2
		for i := l0 + 1; i < end; i++ {
			if !isBlank(p.lines[i]) {
				ci = indentOf(p.lines[i])
				break
			}
		}
		p.replaceLines(l0, end, head+header[:1]+"-"+rest, pad(ci)+x.s+p.eol)
		return nil
	}
	p.replaceLines(l0, end, head+restyle(n, v, ctxValue)+rest)
	return nil
}

// ---- append item

func (p *patcher) appendItem(key string, v Value) error {
	switch v.(type) {
	case strValue, plainValue, mapValue:
	default:
		return reject("a list item is a string, a typed scalar or a mapping")
	}
	if err := p.ensurePairs(); err != nil {
		return err
	}
	if p.find(key) == nil {
		p.appendLines(p.withEOL(pairLines(len(p.indent), key, List(v))))
		p.want.kids = append(p.want.kids, keyDatum(key), seqDatum(datumOf(v)))
		return nil
	}
	pr, i, err := p.target(key)
	if err != nil {
		return err
	}
	n, want := pr.val, p.want.kids[i+1]
	switch {
	case n.Kind == yaml.SequenceNode && n.Style&yaml.FlowStyle != 0:
		err = p.appendFlow(n, v)
	case n.Kind == yaml.SequenceNode:
		err = p.appendBlock(pr, v)
	case n.Kind == yaml.MappingNode && n.Style&yaml.FlowStyle == 0:
		err = p.mapToList(pr, v)
	case n.Kind == yaml.MappingNode:
		err = p.flowMapToList(pr, v)
	default:
		return reject("the value of %q is not a list", key)
	}
	if err != nil {
		return err
	}
	if n.Kind == yaml.MappingNode {
		p.want.kids[i+1] = seqDatum(want, datumOf(v))
	} else {
		want.kids = append(want.kids, datumOf(v))
	}
	return nil
}

// appendBlock adds the item behind the last item of a block list, in its dash column and indentation,
// ahead of the comment and blank lines that follow the list.
func (p *patcher) appendBlock(pr *pair, v Value) error {
	n := pr.val
	last := n.Content[len(n.Content)-1]
	m := dashRe.FindStringSubmatch(p.lines[last.Line-1])
	if m == nil || byteCol(p.lines[last.Line-1], last.Column) != len(m[0]) {
		return reject("the last list item does not start behind its dash")
	}
	lead := m[0]
	body := itemBodyLines(v)
	if _, isMap := v.(mapValue); isMap && last.Kind == yaml.MappingNode && last.Style&yaml.FlowStyle != 0 {
		text, ok := flowItemText(v) // the items are flow mappings: so is the new one
		if !ok {
			return reject("a new list item holds a value that a flow mapping cannot carry")
		}
		body = []string{text}
	}
	out := make([]string, len(body))
	for i, b := range body {
		if i == 0 {
			out[i] = lead + b
		} else {
			out[i] = pad(len(lead)) + b
		}
	}
	p.insertLines(p.contentEnd(n, pr.line, pr.next), p.withEOL(out)...)
	return nil
}

// appendFlow inserts the item inside the brackets of a flow list, directly ahead of the closing one.
func (p *patcher) appendFlow(n *yaml.Node, v Value) error {
	text, ok := flowItemText(v)
	if !ok {
		return reject("a new list item holds a value that a flow list cannot carry")
	}
	fl, err := p.scanFlow(n)
	if err != nil {
		return err
	}
	switch fl.lastChar {
	case '[':
	case ',':
		text = " " + text
	default:
		text = ", " + text
	}
	at, line := fl.lastEnd, p.lines[fl.lastEnd.l]
	p.setLine(at.l, line[:at.c]+text+line[at.c:])
	return nil
}

// mapToList turns the block mapping value of pr into the first item of a block list and adds the new
// entry as the second item: every line of the mapping moves in by the dash.
func (p *patcher) mapToList(pr *pair, v Value) error {
	if _, ok := v.(mapValue); !ok {
		return reject("a scalar cannot be appended to a mapping")
	}
	n := pr.val
	first := n.Line - 1
	end := p.contentEnd(n, pr.line, pr.next)
	col := byteCol(p.lines[first], n.Column)
	for i := pr.line + 1; i < end; i++ {
		switch l := p.lines[i]; {
		case isBlank(l):
		case i == first:
			p.setLine(i, l[:col]+"- "+l[col:])
		default:
			p.setLine(i, "  "+l)
		}
	}
	p.insertLines(end, p.withEOL(itemLines(col, v))...)
	return nil
}

// flowMapToList makes the single-line flow mapping on the key line, with its trailing comment, the first
// item of a block list and adds the new entry as the second item.
func (p *patcher) flowMapToList(pr *pair, v Value) error {
	if _, ok := v.(mapValue); !ok {
		return reject("a scalar cannot be appended to a mapping")
	}
	n := pr.val
	if n.Line-1 != pr.line || p.contentEnd(n, pr.line, pr.next) != pr.line+1 {
		return reject("a flow mapping over several lines cannot become a list")
	}
	line := p.lines[pr.line]
	c0 := byteCol(line, n.Column)
	out := []string{strings.TrimRight(line[:c0], " \t") + p.eol, p.indent + "  - " + line[c0:]}
	out = append(out, p.withEOL(itemLines(len(p.indent)+2, v))...)
	p.replaceLines(pr.line, pr.line+1, out...)
	return nil
}

// ---- list items

// dashOf is the line and the byte offset of the dash of item i of the block list n.
func (p *patcher) dashOf(n *yaml.Node, i int) (line, col int, err error) {
	item := n.Content[i]
	l := item.Line - 1
	m := dashRe.FindStringSubmatch(p.lines[l])
	if m == nil || byteCol(p.lines[l], item.Column) != len(m[0]) {
		return 0, 0, reject("list item %d does not start behind its dash", i)
	}
	return l, len(m[1]), nil
}

// listTarget finds the list value of key and checks the item index.
func (p *patcher) listTarget(key string, idx int) (*pair, int, error) {
	pr, i, err := p.target(key)
	if err != nil {
		return nil, 0, err
	}
	if pr.val.Kind != yaml.SequenceNode {
		return nil, 0, reject("the value of %q is not a list", key)
	}
	if idx < 0 || idx >= len(pr.val.Content) {
		return nil, 0, reject("the list %q has no item %d", key, idx)
	}
	return pr, i, nil
}

func (p *patcher) renameItem(key string, idx int, s string) error {
	pr, i, err := p.listTarget(key, idx)
	if err != nil {
		return err
	}
	v := Str(s)
	if err := validate(v); err != nil {
		return err
	}
	n, item := pr.val, pr.val.Content[idx]
	if item.Kind != yaml.ScalarNode || isBlockScalar(item) || (item.Style == 0 && item.Value == "") {
		return reject("item %d of %q is not a plain or quoted scalar", idx, key)
	}
	if n.Style&yaml.FlowStyle != 0 {
		fl, err := p.scanFlow(n)
		if err != nil {
			return err
		}
		sp := fl.items[idx]
		p.splice(sp.from.l, sp.from.c, sp.to.l, sp.to.c, restyle(item, v, ctxFlow))
	} else {
		_, dc, err := p.dashOf(n, idx)
		if err != nil {
			return err
		}
		limit := pr.next
		if idx+1 < len(n.Content) {
			if limit, _, err = p.dashOf(n, idx+1); err != nil {
				return err
			}
		}
		if err := p.setScalar(item, v, ctxItem, limit, dc+1); err != nil {
			return err
		}
	}
	p.want.kids[i+1].kids[idx] = datumOf(v)
	return nil
}

func (p *patcher) deleteItem(key string, idx int) error {
	pr, i, err := p.listTarget(key, idx)
	if err != nil {
		return err
	}
	if pr.val.Style&yaml.FlowStyle != 0 {
		err = p.deleteFlowItem(pr, idx)
	} else {
		err = p.deleteBlockItem(pr, idx)
	}
	if err != nil {
		return err
	}
	want := p.want.kids[i+1]
	want.kids = slices.Delete(want.kids, idx, idx+1)
	return nil
}

// deleteBlockItem removes only the lines of the item. The only item of a list takes the list with it:
// the key is left with an empty flow list `[]`.
func (p *patcher) deleteBlockItem(pr *pair, idx int) error {
	n := pr.val
	starts := make([]int, len(n.Content))
	for k := range n.Content {
		l, _, err := p.dashOf(n, k)
		if err != nil {
			return err
		}
		starts[k] = l
	}
	hi := pr.next
	if idx+1 < len(starts) {
		hi = starts[idx+1]
	}
	end := p.contentEnd(n.Content[idx], starts[idx], hi)
	if len(n.Content) > 1 {
		p.replaceLines(starts[idx], end)
		return nil
	}
	colon, err := p.colonOf(pr)
	if err != nil {
		return err
	}
	p.replaceLines(starts[idx], end)
	line := p.lines[pr.line]
	p.setLine(pr.line, line[:colon+1]+" []"+line[colon+1:])
	return nil
}

// deleteFlowItem removes the item and one separator and keeps the brackets and the other items.
func (p *patcher) deleteFlowItem(pr *pair, idx int) error {
	fl, err := p.scanFlow(pr.val)
	if err != nil {
		return err
	}
	var from, to pos
	switch items := fl.items; {
	case len(items) == 1:
		from, to = pos{fl.open.l, fl.open.c + 1}, fl.close
	case idx+1 < len(items):
		from, to = items[idx].from, items[idx+1].from
	default:
		from, to = items[idx-1].to, items[idx].to
	}
	p.splice(from.l, from.c, to.l, to.c, "")
	return nil
}

// colonOf is the byte offset of the colon behind the key of pr, which must stand on one line.
func (p *patcher) colonOf(pr *pair) (int, error) {
	k, line := pr.key, p.lines[pr.line]
	c := byteCol(line, k.Column)
	end := c
	switch {
	case k.Style&(yaml.DoubleQuotedStyle|yaml.SingleQuotedStyle) != 0:
		el, ec, ok := p.scanQuoted(pr.line, c, k.Style&yaml.SingleQuotedStyle != 0)
		if !ok || el != pr.line {
			return 0, reject("the key %q is not written on one line", k.Value)
		}
		end = ec
	case k.Style != 0 || !strings.HasPrefix(line[c:], k.Value):
		return 0, reject("the key %q is written in a form that is not patched", k.Value)
	default:
		end += len(k.Value)
	}
	for end < len(line) && (line[end] == ' ' || line[end] == '\t') {
		end++
	}
	if end >= len(line) || line[end] != ':' {
		return 0, reject("the key %q is written in a form that is not patched", k.Value)
	}
	return end, nil
}

// ---- delete, replace, flow to block

func (p *patcher) deleteKey(key string) error {
	pr, i, err := p.target(key)
	if err != nil {
		return err
	}
	p.replaceLines(pr.line, p.contentEnd(pr.val, pr.line, pr.next))
	p.want.kids = slices.Delete(p.want.kids, i, i+2)
	return nil
}

func (p *patcher) replaceKey(oldKey, key string, v Value) error {
	pr, i, err := p.target(oldKey)
	if err != nil {
		return err
	}
	if key != oldKey && p.find(key) != nil {
		return reject("the key %q is already in the frontmatter", key)
	}
	p.replaceLines(pr.line, p.contentEnd(pr.val, pr.line, pr.next), p.withEOL(pairLines(len(p.indent), key, v))...)
	p.want.kids[i], p.want.kids[i+1] = keyDatum(key), datumOf(v)
	return nil
}

// flowToBlock writes the key line without the list, its trailing comment at the column it had, and one
// `- item` line per item with the item text unchanged.
func (p *patcher) flowToBlock(key string) error {
	pr, _, err := p.target(key)
	if err != nil {
		return err
	}
	n := pr.val
	switch {
	case n.Kind != yaml.SequenceNode || n.Style&yaml.FlowStyle == 0:
		return reject("the value of %q is not a flow list", key)
	case len(n.Content) == 0:
		return reject("the flow list of %q is empty", key)
	case n.Line-1 != pr.line:
		return reject("the flow list of %q does not start on its key line", key)
	}
	fl, err := p.scanFlow(n)
	if err != nil {
		return err
	}
	for _, it := range fl.items {
		if it.from.l != it.to.l {
			return reject("an item of the flow list of %q spans several lines", key)
		}
	}
	head := strings.TrimRight(p.lines[pr.line][:fl.open.c], " \t")
	if !strings.HasSuffix(head, ":") {
		return reject("the flow list of %q does not follow its colon", key)
	}
	closing := p.lines[fl.close.l]
	tail := closing[fl.close.c+1:]
	comment := strings.TrimLeft(tail, " \t")
	var keyLine string
	switch {
	case strings.HasPrefix(comment, "#"):
		col := utf8.RuneCountInString(closing[:fl.close.c+1+len(tail)-len(comment)])
		keyLine = head + pad(max(col-utf8.RuneCountInString(head), 1)) + comment
	case strings.Trim(tail, " \t\r\n") == "":
		keyLine = head + p.eol
	default:
		return reject("text follows the flow list of %q", key)
	}
	out := []string{keyLine}
	for _, it := range fl.items {
		out = append(out, p.indent+"  - "+p.lines[it.from.l][it.from.c:it.to.c]+p.eol)
	}
	p.replaceLines(pr.line, fl.close.l+1, out...)
	return nil
}
