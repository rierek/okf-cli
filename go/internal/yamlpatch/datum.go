package yamlpatch

import (
	"go.yaml.in/yaml/v3"
)

// datum is the data of a node tree without positions, styles and comments: what the self-check
// compares. The intended datum is worked out from the datum of the stored text and the edit, the actual
// one is read back from the patched text.
type datum struct {
	kind   yaml.Kind
	tag    string   // resolved short tag
	text   string   // scalar text; for an alias the name of its anchor
	anchor string   // anchor defined on the node
	kids   []*datum // list items; for a mapping key, value, key, value, ...
	// intended side only: a typed plain scalar matches any tag but must be plain; actual side only:
	// isPlain says the scalar is written plain (no quotes, no block style, no explicit tag).
	anyTag, needPlain, isPlain bool
}

// buildDatum reads the datum of a node tree.
func buildDatum(n *yaml.Node) *datum {
	d := &datum{kind: n.Kind, anchor: n.Anchor}
	switch n.Kind {
	case yaml.AliasNode:
		d.text = n.Value
	case yaml.ScalarNode:
		d.tag, d.text = n.ShortTag(), n.Value
		d.isPlain = n.Style&(yaml.TaggedStyle|yaml.DoubleQuotedStyle|yaml.SingleQuotedStyle|yaml.LiteralStyle|yaml.FoldedStyle) == 0
	default:
		d.tag = n.ShortTag()
	}
	for _, c := range n.Content {
		d.kids = append(d.kids, buildDatum(c))
	}
	return d
}

// matches reports whether the actual datum g is the intended datum w (values, types, key order).
func (w *datum) matches(g *datum) bool {
	if w.kind != g.kind || w.anchor != g.anchor || len(w.kids) != len(g.kids) {
		return false
	}
	switch w.kind {
	case yaml.AliasNode:
		return w.text == g.text
	case yaml.ScalarNode:
		if w.text != g.text || (!w.anyTag && w.tag != g.tag) || (w.needPlain && !g.isPlain) {
			return false
		}
	}
	for i, k := range w.kids {
		if !k.matches(g.kids[i]) {
			return false
		}
	}
	return true
}

// pairIndex is the index in kids of the value of the string key, or -1.
func (d *datum) pairIndex(key string) int {
	for i := 0; i+1 < len(d.kids); i += 2 {
		if k := d.kids[i]; k.kind == yaml.ScalarNode && k.tag == "!!str" && k.text == key {
			return i
		}
	}
	return -1
}

func (d *datum) pairAt(i int) (key, val *datum) { return d.kids[i], d.kids[i+1] }
