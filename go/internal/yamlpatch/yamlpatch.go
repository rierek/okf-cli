// Package yamlpatch is the one writer of a concept file's frontmatter (D05, R-03). Every edit patches
// the lines of the keys it targets in the stored text; the block is never re-serialised as a whole, so
// every other byte (comments, blank lines, quote styles, flow or block styles, line endings) stays.
//
// The frontmatter reader (package frontmatter) parses the block once with go.yaml.in/yaml/v3 only to
// learn line, column, style and kind of each node. An edit it cannot patch safely is refused with a
// *Rejection and no text (R-04); after every patch the text is read back and compared with the data
// the edit intends, so a fault of the patcher is turned into a rejection, never into a written file.
//
// The package writes no file: Apply takes a stored text and returns the new text.
package yamlpatch

import (
	"fmt"
	"strings"
	"unicode/utf8"

	"go.yaml.in/yaml/v3"

	"nas/volume1/data/git/okf-tools/go/internal/frontmatter"
	"nas/volume1/data/git/okf-tools/go/internal/okferr"
	"nas/volume1/data/git/okf-tools/go/internal/pytext"
)

// Rejection is the writer's refusal of an edit: the reason is one line. Nothing is returned with it.
// It unwraps to an okferr invalid_input error (exit class 2).
type Rejection struct{ Reason string }

func (r *Rejection) Error() string { return r.Reason }

// Unwrap classifies the rejection for okferr.As.
func (r *Rejection) Unwrap() error { return okferr.New(okferr.InvalidInput, r.Reason) }

// ParseError is B's reader error passed through: the frontmatter of the stored text does not read.
// Reason is the reader's one-line reason, `<problem> (line L, column C)` or `block is not a mapping`.
// It unwraps to an okferr invalid_input error.
type ParseError struct{ Reason string }

func (e *ParseError) Error() string { return e.Reason }

// Unwrap classifies the error for okferr.As.
func (e *ParseError) Unwrap() error { return okferr.New(okferr.InvalidInput, e.Reason) }

func reject(format string, args ...any) error {
	return &Rejection{Reason: pytext.Collapse(fmt.Sprintf(format, args...))}
}

// Apply runs the edits in order on the stored file text, each on the result of the one before (a list
// index counts in the list as it stands at that edit), and returns the full new text. Any rejected
// edit gives only the rejection. An empty edit list returns the input.
func Apply(stored string, edits ...Edit) (string, error) {
	if len(edits) == 0 {
		return stored, nil
	}
	if !utf8.ValidString(stored) {
		return "", reject("the stored text is not valid UTF-8")
	}
	text := stored
	for _, e := range edits {
		next, err := applyOne(text, e)
		if err != nil {
			return "", err
		}
		text = next
	}
	return text, nil
}

func applyOne(text string, e Edit) (string, error) {
	return applyWith(text, func(p *patcher) error { return p.do(e) })
}

// applyWith runs one patch on the text and returns the new text only after it was read back and found to
// be what the patch intends (the seam the tests use to hand the guard a faulty patch).
func applyWith(text string, patch func(*patcher) error) (string, error) {
	p, err := newPatcher(text)
	if err != nil {
		return "", err
	}
	if err := patch(p); err != nil {
		return "", err
	}
	out := p.result()
	if err := p.selfCheck(out); err != nil {
		return "", err
	}
	return out, nil
}

// pair is a top-level key of the block with the lines it owns.
type pair struct {
	key, val *yaml.Node
	line     int // 0-based line of the key
	next     int // 0-based line of the next key; len(lines) for the last one
}

// patcher holds one stored text while one edit runs on it.
type patcher struct {
	doc      frontmatter.Doc
	created  bool     // the text has no frontmatter block: a block is created when a key is added
	touched  bool     // a line was changed
	lines    []string // the block, line by line, endings kept; line 0 is the rest of the opening delimiter line
	eol      string   // the line ending of lines the edit writes
	body     string   // the text behind the closing delimiter (created: the whole stored text)
	pairs    []*pair
	pairsOK  bool
	indent   string // the indentation of the keys of the block
	flowRoot int    // line of an empty `{}` root that stands alone on its line, else -1
	want     *datum // the data the edit intends
	wantBody string // the body the patched text must read back with
}

func newPatcher(text string) (*patcher, error) {
	doc := frontmatter.Read(text)
	p := &patcher{doc: doc, eol: "\n", flowRoot: -1}
	if doc.Head == "" {
		p.created, p.body = true, text
		p.wantBody = "\n" + text
		if strings.Contains(text, "\r\n") {
			p.eol = "\r\n"
			p.wantBody = "\r\n" + text
		}
		p.want = &datum{kind: yaml.MappingNode, tag: "!!map"}
		return p, nil
	}
	if doc.Err != "" {
		return nil, &ParseError{Reason: doc.Err}
	}
	p.lines, p.body, p.wantBody = splitLines(doc.Block), doc.Body, doc.Body
	if strings.Contains(doc.Block, "\r\n") {
		p.eol = "\r\n"
	}
	if hasBareCR(doc.Block) {
		return nil, reject("the frontmatter holds a carriage return that does not end a line")
	}
	p.want = buildDatum(doc.Root)
	return p, nil
}

// hasBareCR reports a carriage return that is not part of CRLF: YAML counts it as a line break, the
// line model does not.
func hasBareCR(s string) bool {
	for i := range len(s) {
		if s[i] == '\r' && (i+1 >= len(s) || s[i+1] != '\n') {
			return true
		}
	}
	return false
}

// result is the new full text.
func (p *patcher) result() string {
	switch {
	case p.created && !p.touched:
		return p.body
	case p.created:
		return "---" + p.eol + strings.Join(p.lines, "") + "---" + p.eol + p.body
	}
	return "---" + strings.Join(p.lines, "") + "---" + p.body
}

// selfCheck reads the patched text back and compares it with the intended data.
func (p *patcher) selfCheck(out string) error {
	if p.created && !p.touched {
		return nil // only the body was set: no block was written
	}
	got := frontmatter.Read(out)
	switch {
	case got.Head == "":
		return reject("the patched text has no frontmatter block")
	case got.Err != "":
		return reject("the patched frontmatter does not read: %s", got.Err)
	case got.Body != p.wantBody:
		return reject("the patched text changed the text behind the frontmatter")
	case !p.want.matches(buildDatum(got.Root)):
		return reject("the patched frontmatter does not read back as intended")
	}
	return nil
}

func (p *patcher) setLine(i int, s string) {
	p.lines[i] = s
	p.touched = true
}

func (p *patcher) insertLines(at int, lines ...string) {
	out := make([]string, 0, len(p.lines)+len(lines))
	out = append(out, p.lines[:at]...)
	out = append(out, lines...)
	p.lines = append(out, p.lines[at:]...)
	p.touched = true
}

// replaceLines replaces the lines [lo, hi) by the new ones.
func (p *patcher) replaceLines(lo, hi int, lines ...string) {
	out := make([]string, 0, len(p.lines)-(hi-lo)+len(lines))
	out = append(out, p.lines[:lo]...)
	out = append(out, lines...)
	p.lines = append(out, p.lines[hi:]...)
	p.touched = true
}

// splice replaces the text from (sl, sc) to (el, ec) by text.
func (p *patcher) splice(sl, sc, el, ec int, text string) {
	p.replaceLines(sl, el+1, p.lines[sl][:sc]+text+p.lines[el][ec:])
}

// appendLines adds lines behind the last line of the block, or in place of the `{}` root line.
func (p *patcher) appendLines(lines []string) {
	if p.flowRoot >= 0 {
		p.replaceLines(p.flowRoot, p.flowRoot+1, lines...)
		return
	}
	p.insertLines(len(p.lines), lines...)
}

// withEOL ends every line with the line ending of the text.
func (p *patcher) withEOL(lines []string) []string {
	out := make([]string, len(lines))
	for i, l := range lines {
		out[i] = l + p.eol
	}
	return out
}

// ensurePairs lists the top-level keys with their line ranges. A shape with no clear lines (a flow
// mapping root, two keys on one line, a key on the opening delimiter line, a key that is no scalar)
// is refused.
func (p *patcher) ensurePairs() error {
	if p.pairsOK || p.created {
		return nil
	}
	root := p.doc.Root
	if root.Style&yaml.FlowStyle != 0 {
		l := root.Line - 1
		if len(root.Content) != 0 || l < 1 || strings.Trim(p.lines[l], " \t\r\n") != "{}" {
			return reject("the frontmatter is a flow mapping")
		}
		p.flowRoot = l
		p.pairsOK = true
		return nil
	}
	for i := 0; i+1 < len(root.Content); i += 2 {
		k := root.Content[i]
		if k.Kind != yaml.ScalarNode {
			return reject("a key of the frontmatter is not a scalar")
		}
		pr := &pair{key: k, val: root.Content[i+1], line: k.Line - 1}
		if n := len(p.pairs); n > 0 {
			if pr.line <= p.pairs[n-1].line {
				return reject("two keys of the frontmatter share one line")
			}
			p.pairs[n-1].next = pr.line
		} else if pr.line < 1 {
			return reject("a key of the frontmatter sits on the opening delimiter line")
		}
		p.pairs = append(p.pairs, pr)
	}
	if n := len(p.pairs); n > 0 {
		p.pairs[n-1].next = len(p.lines)
		p.indent = strings.Repeat(" ", indentOf(p.lines[p.pairs[0].line]))
	}
	p.pairsOK = true
	return nil
}

// find is the pair of a string key, or nil.
func (p *patcher) find(key string) *pair {
	for _, pr := range p.pairs {
		if pr.key.Kind == yaml.ScalarNode && pr.key.ShortTag() == "!!str" && pr.key.Value == key {
			return pr
		}
	}
	return nil
}

// target is find for an edit that needs the key; the pair, its datum index and a check that nothing in
// it carries an anchor, an alias or an explicit tag (a change would change every alias).
func (p *patcher) target(key string) (*pair, int, error) {
	if err := p.ensurePairs(); err != nil {
		return nil, 0, err
	}
	pr := p.find(key)
	if pr == nil {
		return nil, 0, reject("the key %q is not in the frontmatter", key)
	}
	if err := plainTree(pr.key); err != nil {
		return nil, 0, err
	}
	if err := plainTree(pr.val); err != nil {
		return nil, 0, err
	}
	return pr, p.want.pairIndex(key), nil
}

// plainTree refuses a node, or a node below it, with an anchor, an alias or an explicit tag.
func plainTree(n *yaml.Node) error {
	if n.Anchor != "" || n.Kind == yaml.AliasNode || (n.Kind == yaml.ScalarNode && n.Style&yaml.TaggedStyle != 0) ||
		(n.Kind != yaml.ScalarNode && n.Kind != yaml.AliasNode && n.Style&yaml.TaggedStyle != 0) {
		return reject("the value of a key carries an anchor, an alias or an explicit tag")
	}
	for _, c := range n.Content {
		if err := plainTree(c); err != nil {
			return err
		}
	}
	return nil
}

func (p *patcher) do(e Edit) error {
	if e.val != nil {
		if err := validate(e.val); err != nil {
			return err
		}
	}
	switch e.kind {
	case kindSetValue:
		return p.setValue(e.key, e.val)
	case kindNewKey:
		return p.newKey(e.key, e.val)
	case kindAppendItem:
		return p.appendItem(e.key, e.val)
	case kindRenameItem:
		return p.renameItem(e.key, e.index, e.text)
	case kindDeleteItem:
		return p.deleteItem(e.key, e.index)
	case kindDeleteKey:
		return p.deleteKey(e.key)
	case kindReplaceKey:
		return p.replaceKey(e.key, e.key2, e.val)
	case kindFlowToBlock:
		return p.flowToBlock(e.key)
	case kindSetBody:
		if !utf8.ValidString(e.text) {
			return reject("a new body is not valid UTF-8")
		}
		p.body, p.wantBody = e.text, e.text
		return nil
	}
	return reject("unknown edit")
}
